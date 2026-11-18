"""Remote Studio physical-layout API. All drafts compile before device writes."""
from __future__ import annotations

import asyncio
import logging
from copy import deepcopy

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import bindings as binding_utils
from . import commands as c
from . import physical_layout as physical
from . import targets
from .const import DOMAIN
from .cloud import SwitchBotCloudClient
from .inventory import cloud_items, cloud_item_id
from .cloud_ir import find_cloud_items, profile_from_cloud

_LOGGER = logging.getLogger(__name__)


def store_device_table(hass, entry, table):
    hass.data.setdefault(DOMAIN, {}).setdefault("_studio_device_tables", {})[entry.entry_id] = tuple(table)


def cached_device_table(hass, entry):
    return hass.data.get(DOMAIN, {}).get("_studio_device_tables", {}).get(entry.entry_id)


async def read_device_table(hass, entry, client, *, raw=None):
    if not raw:
        raw = await client.query(7)
    if not raw:
        raise ValueError("The remote did not answer with its device table.")
    table = c.parse_added_devices(raw)
    store_device_table(hass, entry, table)
    return table


def remote_identity(remote):
    return str(remote.get("remote_id") or remote.get("device_id") or "")


def resolve(hass, msg):
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        raise ValueError("Integration not found")
    remote = next((item for item in entry.options.get("remotes", [])
                   if remote_identity(item) == msg["remote_id"]), None)
    if remote is None:
        raise ValueError("Remote not found")
    return entry, remote


def ir_sources(entry):
    sources = []
    for remote in entry.options.get("remotes", []):
        bank = bytes.fromhex(remote.get("ir_code_bank", ""))
        if not bank:
            continue
        packet_sources = physical.source_packets(remote) + [
            bytes.fromhex(value) for value in remote.get("physical_original_packets", [])
        ]
        for packet in packet_sources:
            body = packet[7:]
            for off in range(83, len(body), 36):
                record = body[off:off + 36]
                if len(record) != 36 or record[3] != 1:
                    continue
                start, length = int.from_bytes(record[4:8], "big"), int.from_bytes(record[8:10], "big")
                if length and start + length <= len(bank):
                    sources.append({"label": f"{remote['name']} · page {body[81]} / key {record[0]}",
                                    "code_hex": bank[start:start + length].hex()})
    return sources


def persist(hass, entry, identity, **changes):
    options = deepcopy(dict(entry.options))
    remote = next(item for item in options["remotes"] if remote_identity(item) == identity)
    remote.update(changes)
    remote.setdefault("remote_id", identity)
    hass.config_entries.async_update_entry(entry, options=options)


def _migrate_button_actions(hass, entry, remote_id, migrations, removals=()):
    if not migrations and not removals:
        return
    options = deepcopy(dict(entry.options))
    bindings = options.get("bindings", [])
    updated = False
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict) or str(binding.get("remote_id", "")) != str(remote_id):
            continue
        bindings[index] = binding_utils.migrate_button_action_identities(
            binding, migrations, removals)
        updated = True
    if updated:
        options["bindings"] = bindings
        hass.config_entries.async_update_entry(entry, options=options)


def _functions_for(device_type: str, remote: dict) -> list[dict]:
    """The functions a key of this remote can actually carry.

    Offering the whole generic action list put "Climate - Auto" on a light, which is not a key
    the profile has. A native remote is narrowed to the functions its own stock profile uses,
    with the generic list kept behind them so nothing becomes unreachable.
    """
    if device_type in c.DEVTYPE:
        return [{"value": value, "label": label,
                 "aliases": physical.HID_FUNCTION_ALIASES.get(value, ())}
                for label, value in physical.HID_FUNCTIONS.items()]
    generic = {
        value: c.custom_action_label(name) for name, value in c.CUSTOM_ACTION_FUNCTIONS.items()
    }
    profile_name = c.NATIVE_PROFILE_ALIASES.get(str(remote.get("device_type", "")).upper())
    profile = c.NATIVE_PROFILE_LAYOUTS.get(profile_name or "")
    own: list[dict] = []
    seen: set[int] = set()
    if profile:
        for keys in profile["pages"].values():
            for key in (keys() if callable(keys) else keys):
                function = int(key.get("keyFun", 0))
                if not function or function in seen:
                    continue
                seen.add(function)
                own.append({"value": function, "label": generic.get(function, f"Function {function}")})
    rest = [{"value": value, "label": label} for value, label in generic.items() if value not in seen]
    return own + rest


def _native_profiles() -> list[dict]:
    profiles = []
    for native_type in c.native_type_picker_options():
        name = native_type["profile"]
        profile = c.NATIVE_PROFILE_LAYOUTS[name]
        item = c.native_profile_metadata(name) | native_type
        item["label"] = f"{item['title']} · " + (
            "main page only" if len(profile["pages"]) == 1 else
            "pages " + ", ".join("Main" if int(page) == 0 else "ABCD"[int(page) - 1]
                                 for page in sorted(profile["pages"]))
        )
        profiles.append(item)
    return profiles


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/studio/physical/import",
                                vol.Required("entry_id"): str,
                                vol.Optional("remote_id"): str})
@websocket_api.async_response
async def ws_physical_import(hass, connection, msg):
    """Refresh installed remotes and read their native appearance from the device."""
    try:
        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            raise ValueError("Integration not found")
        settings = entry.data.get("cloud")
        client = hass.data[DOMAIN][entry.entry_id]["client"]
        table = await read_device_table(hass, entry, client)

        async def save_tokens(access_token, refresh_token):
            data = deepcopy(dict(entry.data))
            data["cloud"].update(access_token=access_token, refresh_token=refresh_token)
            hass.config_entries.async_update_entry(entry, data=data)
        cloud = (SwitchBotCloudClient(async_get_clientsession(hass), dict(settings), save_tokens)
                 if settings else None)
        metadata = []
        if cloud:
            try:
                metadata = cloud_items(await cloud.get_bindable_devices())
            except Exception as err:  # Native appearance is read over BLE.
                _LOGGER.warning("Could not refresh SwitchBot cloud metadata: %s", err)
                cloud = None
        options = deepcopy(dict(entry.options))
        remotes = options.setdefault("remotes", [])
        imported = 0
        for slot, device_type, control, device_id in table:
            if not cloud or control != 4 or any(c.id_to_bytes(item["device_id"]) == device_id for item in remotes if item.get("device_id")):
                continue
            payload = await cloud.get_button_data([slot])
            records = payload.get("items", []) if isinstance(payload, dict) else payload
            record = next((item for item in records if isinstance(item, dict) and
                           int(item.get("index", item.get("remoteIndex", -1))) == slot), None) if isinstance(records, list) else None
            if not record or not isinstance(record.get("buttonList"), list):
                continue
            native_type = next((name for name, value in c.DEVTYPE.items() if value == device_type), None)
            if native_type is None:
                continue
            meta = next((item for item in metadata if cloud_item_id(item) == device_id), {})
            remote = {"index": slot, "device_id": device_id.hex(), "remote_id": device_id.hex(),
                      "name": record.get("remoteName") or meta.get("thirdPartyDeviceName") or f"HID remote {slot}",
                      "device_type": native_type, "buttons": []}
            remote["physical_layout"] = physical.validate(remote, physical.hid_draft_from_cloud(native_type, record["buttonList"]))
            remotes.append(remote)
            imported += 1
        imported += await _adopt_ir_remotes(cloud, table, remotes, metadata)
        imported += _adopt_native_remotes(table, remotes, metadata)
        appearance_error = await _refresh_native_appearances(client, table, remotes)
        dropped = _drop_absent_remotes(table, remotes)
        selected = next((item for item in remotes if remote_identity(item) == msg.get("remote_id")), None)
        native_readback = None
        if selected and str(selected.get("device_type", "")).upper() in c.NATIVE_DEVTYPE:
            if not appearance_error:
                native_readback = selected.get("native_appearance_readback")
            if native_readback is None and not appearance_error:
                appearance_error = "Could not match this Native remote to the device details."
                _LOGGER.warning(
                    "Native appearance match failed: remote_id=%s slot=%s type=%s "
                    "device_id=%s physical_device_id=%s native_rows=%s",
                    remote_identity(selected), selected.get("index"), selected.get("device_type"),
                    selected.get("device_id"), selected.get("physical_device_id"),
                    [(slot, hex(kind), identifier.hex())
                     for slot, kind, control, identifier in table if control == c.CTRL_NATIVE],
                )
        hass.config_entries.async_update_entry(entry, options=options)
        connection.send_result(msg["id"], {"imported": imported, "dropped": dropped,
                                           "appearance_error": appearance_error,
                                           "native_readback": native_readback})
    except Exception as err:
        connection.send_error(msg["id"], "physical_import_failed", str(err))


async def _refresh_native_appearances(client, table, remotes):
    native_ids = {(slot, device_type, device_id) for slot, device_type, control, device_id in table
                  if control == c.CTRL_NATIVE}
    if not native_ids:
        return None
    try:
        appearances = c.parse_device_appearances(await client.query(5, timeout=8, timeout_retries=0))
        if appearances.keys() != native_ids:
            raise ValueError("Native entries differ between the device details and the slot list")
    except Exception as err:
        _LOGGER.warning("Could not read Native remote appearance from WoRWS: %s", err)
        return "Could not read the current Native appearance from the remote."

    for remote in remotes:
        device_type = c.NATIVE_DEVTYPE.get(str(remote.get("device_type", "")).upper())
        if device_type is None or not remote.get("device_id"):
            continue
        remote.pop("native_appearance_readback", None)
        identity = physical.match_native_appearance(remote, appearances, device_type)
        if identity is None:
            continue
        remote["index"] = identity[0]
        if device_type != identity[1]:
            type_name = next((name for name, code in c.NATIVE_DEVTYPE.items()
                              if code == identity[1]), None)
            if type_name is not None:
                remote["device_type"] = type_name
        mode, icon = appearances[identity]
        remote["native_appearance_readback"] = {
            "slot": identity[0], "device_type": identity[1], "mode": mode, "icon": icon,
        }


async def _adopt_ir_remotes(cloud, table, remotes, catalogue) -> int:
    """List installed IR remotes and load editable profiles where the account has them."""
    known = {}
    for item in remotes:
        if not str(item.get("device_type", "")).upper().startswith("IR_"):
            continue
        try:
            known[c.id_to_bytes(item["device_id"])] = item
        except (KeyError, TypeError, ValueError):
            continue
    metadata_by_id = {cloud_item_id(item): item for item in catalogue}
    adopted = 0
    for slot, device_type, control, device_id in table:
        if control != c.CTRL_IR:
            continue
        metadata = metadata_by_id.get(device_id, {})
        remote_id = str(metadata.get("remoteID") or "")
        record = known.get(device_id)
        if record is None:
            record = {
                "name": str(metadata.get("remoteName") or f"IR remote (slot {slot})"),
                "device_type": f"IR_{device_type}",
                "icon": "tv" if device_type == 2 else "light",
                "device_id": device_id.hex(),
                "remote_id": remote_id or device_id.hex(),
                "buttons": [],
                "ir_profile_pending": True,
            }
            remotes.append(record)
            known[device_id] = record
            adopted += 1
        elif record.get("ir_profile_pending") and (
            record["name"] == f"IR remote (slot {record.get('index')})"
        ):
            record["name"] = str(metadata.get("remoteName") or f"IR remote (slot {slot})")
        record["index"] = slot
        if not record.get("ir_profile_pending"):
            continue
        if not cloud or not remote_id:
            continue
        name = str(metadata.get("remoteName") or record["name"])
        try:
            payload = await cloud.get_ir_remotes(
                [remote_id], str(metadata.get("createFrom") or "hub")
            )
            records = find_cloud_items(payload)
            if not records:
                raise ValueError("queryIrRemote returned no record")
            profile = profile_from_cloud(
                records[0], remote_id=remote_id, name=name,
                remote_type=device_type, metadata=metadata,
            )
            pages = c.build_ir_pages(
                remote_index=slot, device_type=profile.device_type,
                remote_id=profile.remote_id, name=name,
                key_map=list(profile.key_map), icon=profile.icon,
            )
            studio_pages = c.studio_pages_from_packets(tuple(pages))
        except Exception as err:  # noqa: BLE001 - one unreadable remote must not stop the rest
            _LOGGER.warning("could not rebuild IR remote in slot %s: %s", slot, err)
            continue
        record.update({
            "name": name,
            "device_type": f"IR_{profile.device_type}",
            "icon": "tv" if profile.device_type == 2 else "light",
            "studio_pages": studio_pages,
            "physical_packets": [packet.hex() for packet in pages],
            "ir_code_bank": profile.code_bank.hex(),
            "buttons": [],
            "profile": profile.key,
            "imported_from_cloud": True,
        })
        record.pop("ir_profile_pending")
    return adopted


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/studio/physical/get",
                                vol.Required("entry_id"): str, vol.Required("remote_id"): str})
@callback
def ws_physical_get(hass, connection, msg):
    try:
        entry, remote = resolve(hass, msg)
        device_type = str(remote["device_type"]).upper()
        functions = _functions_for(device_type, remote)
        connection.send_result(msg["id"], {"layout": physical.draft_for(remote), "ir_sources": ir_sources(entry),
                                          "functions": functions,
                                          "native_profiles": _native_profiles(),
                                          "native_menu_glyphs": sorted(c.NATIVE_MENU_GLYPHS),
                                          "status": remote.get("physical_status", "")})
    except (ValueError, KeyError, TypeError) as err:
        connection.send_error(msg["id"], "physical_unavailable", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/studio/physical/table",
                                vol.Required("entry_id"): str})
@websocket_api.async_response
async def ws_physical_table(hass, connection, msg):
    """Read the remote's own device table so the panel can show what is really installed.

    Read-only. The panel needs this because the slot index of a row, not its device id,
    is what identifies it: several native profiles can share one target address and the
    firmware then stores the same id for all of them.
    """
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "physical_unavailable", "Integration not found")
        return
    client = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("client")
    if client is None:
        connection.send_error(msg["id"], "physical_unavailable", "WoRWS is not connected")
        return
    try:
        table = await read_device_table(hass, entry, client)
    except (ValueError, TypeError) as err:
        connection.send_error(msg["id"], "physical_unavailable", str(err))
        return
    kinds = {c.CTRL_NATIVE: "native", c.CTRL_IR: "ir", c.CTRL_HID: "hid"}
    by_address: dict[bytes, list[int]] = {}
    rows = []
    for index, device_type, control_type, device_id in table:
        address = device_id[:6]
        if control_type == c.CTRL_NATIVE:
            by_address.setdefault(address, []).append(index)
        rows.append({
            "slot": index,
            "device_type": f"0x{device_type:08X}" if device_type > 0xFF else f"0x{device_type:02X}",
            "control_type": control_type,
            "kind": kinds.get(control_type, str(control_type)),
            "device_id": device_id.hex(),
            "target_mac": ":".join(f"{byte:02X}" for byte in reversed(address)),
            # The name Studio knows this row by, so the order list can say which remote is which.
            "name": next((str(item.get("name") or "") for item in entry.options.get("remotes", [])
                          if isinstance(item, dict) and local_identity_bytes(item) == device_id), ""),
        })
    warnings = [
        "Slots " + ", ".join(str(slot) for slot in slots)
        + f" are native profiles sharing target {':'.join(f'{b:02X}' for b in reversed(address))}."
        " The firmware stores the same id for all of them, so presses are served by the"
        " first one and only its buttons work."
        for address, slots in by_address.items() if len(slots) > 1
    ]
    connection.send_result(msg["id"], {
        "rows": rows,
        "next_free_slot": len(rows) if c.remaining_remote_slots(len(rows)) else None,
        "warnings": warnings,
    })


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/studio/physical/apply",
    vol.Required("entry_id"): str, vol.Required("remote_id"): str, vol.Required("layout"): dict,
    vol.Optional("identity_migrations", default=[]): [
        {vol.Required("from"): str, vol.Required("to"): str}
    ], vol.Optional("identity_removals", default=[]): [str]})
@websocket_api.async_response
async def ws_physical_apply(hass, connection, msg):
    from .studio_remotes import remote_management_lock

    store = hass.data.setdefault(DOMAIN, {})
    async with remote_management_lock(hass):
        stage = "validate"
        mutated = False
        try:
            entry, remote = resolve(hass, msg)
            identity = msg["remote_id"]
            draft = await hass.async_add_executor_job(
                physical.validate, remote, msg["layout"]
            )
            previous_layout = physical.draft_for(remote)
            current_binding = next((item for item in entry.options.get("bindings", [])
                                    if isinstance(item, dict)
                                    and str(item.get("remote_id", "")) == str(identity)), None)
            identity_migrations = binding_utils.plan_button_identity_migrations(
                current_binding, msg.get("identity_migrations", []),
                msg.get("identity_removals", []))
            client = store.get(entry.entry_id, {}).get("client")
            if client is None:
                raise ValueError("WoRWS is not connected")
            await client.ensure_strict_sequence_support()
            stage = "read device table"
            table = c.parse_added_devices(await client.query(7))
            bound_address = remote.get("physical_device_id") if draft["kind"] == "native" else None
            bound_address = bound_address or remote["device_id"]
            expected_id = c.id_to_bytes(bound_address)
            matches = [item for item in table if item[3] == expected_id]
            if len(matches) > 1:
                # Several native profiles can be installed against one target address, and the
                # firmware stores the same eleven-byte id for every one of them, so the id no
                # longer picks out a row. Fall back to the slot recorded when this remote was
                # installed; only give up when that does not resolve it either.
                narrowed = [item for item in matches if str(item[0]) == str(remote.get("index"))]
                if len(narrowed) == 1:
                    matches = narrowed
            recovering_native = not matches and draft["kind"] == "native" and remote.get("physical_pending")
            if len(matches) != 1 and not recovering_native:
                raise ValueError(
                    f"Could not uniquely identify the physical remote: {len(matches)} table rows "
                    f"carry this device id. Refresh the inventory, or remove the duplicate rows."
                    if matches else
                    "Could not find the physical remote in the device table; refresh the inventory first"
                )
            if recovering_native:
                c.require_remote_slot(len(table))
                slot, device_type, control_type = len(table), c.NATIVE_DEVTYPE[str(remote["device_type"]).upper()], c.CTRL_NATIVE
            else:
                slot, device_type, control_type, _ = matches[0]
            expected_control = {"hid": c.CTRL_HID, "ir": c.CTRL_IR, "native": c.CTRL_NATIVE}[draft["kind"]]
            if control_type != expected_control:
                raise ValueError("The physical remote type differs from the cached profile")
            uploads, pages = await hass.async_add_executor_job(
                physical.compile_pages, remote, draft, slot
            )
            stored_changes = {}
            verify_appearance = False
            if draft["kind"] == "native":
                if not targets.is_bridge_remote(entry, remote):
                    raise ValueError("This Native remote does not have a saved Bridge target")
                layout = physical.native_layout(draft)
                selected_type = c.native_type_metadata(layout["native_type"])
                new_slot = len(table) if recovering_native else slot
                bind = c.build_custom_native_bind_sequence(
                    remote_index=new_slot, name=remote["name"],
                    device_id=bound_address, icon_name=layout["icon_name"],
                    event_remote_id=identity, main_buttons=layout["main_buttons"],
                    page_buttons={int(p): values for p, values in layout["pages"].items()},
                    template=layout["template"],
                    control_mode=layout["control_mode"],
                    device_type_name=selected_type["device_type"],
                    glyphs=layout["glyphs"],
                )
                stages = [(name, packet, frozenset({1})) for name, packet in bind]
                if not recovering_native:
                    # 0F 62 06 updates only the records it carries. Explicitly clear
                    # positions left empty after a deletion, move or row compaction.
                    stages.extend(
                        (f"clear page {page} key {index}", c.build_delete_native_key(
                            remote_index=slot, device_type=c.NATIVE_DEVTYPE[selected_type["device_type"]],
                            device_id=expected_id, page=page, index=index,
                        ), frozenset({1}))
                        for page, index in physical.removed_native_keys(previous_layout, draft)
                    )
                pages = [packet for _, packet in bind]
                stored_changes = {"device_type": selected_type["device_type"],
                                  "custom_layout": layout,
                                  "native_type": layout["native_type"],
                                  "control_mode": layout["control_mode"],
                                  "index": new_slot,
                                  "icon": layout["icon_name"],
                                  "icon_code": c.ICON[layout["icon_name"]],
                                  "floor_lamp_test_applied": False,
                                  "native_appearance_readback": None,
                                  "icon_variant_backup_packet": None}
                previous = physical.native_appearance(remote)
                verify_appearance = (
                    c.NATIVE_DEVTYPE[selected_type["device_type"]], layout["control_mode"],
                    stored_changes["icon_code"],
                ) != (device_type, previous["control_mode"], previous["icon_code"])
            else:
                # Deleting keys leaves the physical remote and its existing HID bond in place.
                delete = bytes([15, 98, 4, 1, slot]) + c.device_type_bytes(device_type) + bytes([control_type]) + expected_id + b"\xff\xff"
                stages = uploads + [("replace keys", delete, frozenset({1}))] + [
                    (f"write page {packet[88]}", packet, frozenset({1})) for packet in pages]
                if uploads:
                    space = await client.query(6)
                    if len(space) < 9 or sum(len(bytes.fromhex(k.get("code_hex", ""))) for p in draft["pages"] for k in p["buttons"]) >= int.from_bytes(space[5:9], "big"):
                        raise ValueError("Not enough confirmed device storage for these IR codes")
            # Track the pending write before the first mutating command.
            persist(hass, entry, identity,
                physical_original_packets=remote.get("physical_original_packets") or [packet.hex() for packet in physical.source_packets(remote)],
                physical_pending=draft,
                physical_status="Applying physical layout")
            stage = "write transaction"
            mutated = True
            responses = await client.send_command_sequence(
                tuple(packet for _, packet, _ in stages), timeout=45, timeout_retries=0,
                accepted_codes=tuple(accepted for _, _, accepted in stages),
                readback_subcommand=7,
            )
            for (name, _, accepted), response in zip(stages, responses):
                if not response or response[0] not in accepted:
                    stage = name
                    raise ValueError(f"{name}: response {response.hex() if response else 'timeout'}")
            if len(responses) < len(stages):
                stage = stages[len(responses)][0]
                raise ValueError(f"{stage}: no acknowledgement")
            # Read-back of table identity proves the tile remains installed; it does not read keys.
            stage = "verify remote remains installed"
            readback = responses[len(stages)] if len(responses) > len(stages) else None
            after = await read_device_table(hass, entry, client, raw=readback)
            if not any(item[3] == expected_id and item[2] == expected_control for item in after):
                raise ValueError("The remote is missing from the physical table after writing")
            status = "Device acknowledged the layout update."
            if verify_appearance:
                expected = (stored_changes["control_mode"], stored_changes["icon_code"])
                prefix = f"Slot {new_slot}: sent mode 0x{expected[0]:02X}, icon 0x{expected[1]:02X}"
                wire_type = c.NATIVE_DEVTYPE[stored_changes["device_type"]]
                try:
                    details = c.parse_device_appearances(await client.query(5, timeout=8, timeout_retries=0))
                    mode, icon = details[new_slot, wire_type, expected_id]
                    stored_changes["native_appearance_readback"] = {
                        "slot": new_slot, "device_type": wire_type, "mode": mode, "icon": icon,
                    }
                    status = f"{prefix}; device stored mode 0x{mode:02X}, icon 0x{icon:02X}."
                    if (mode, icon) != expected:
                        _LOGGER.warning("WoRWS appearance differs after writing: %s", status)
                except Exception as err:
                    status = f"{prefix}; device appearance could not be read back."
                    _LOGGER.warning("WoRWS appearance verification failed: %s %s", status, err)
            persist(hass, entry, identity, physical_layout=draft,
                    physical_packets=[packet.hex() for packet in pages],
                    physical_pending=None,
                    physical_status=status, **stored_changes)
            _migrate_button_actions(hass, entry, identity, identity_migrations,
                                    msg.get("identity_removals", []))
            from .studio import _serialize_entry

            entry, updated = resolve(hass, msg)
            connection.send_result(msg["id"], {
                "status": status,
                "layout": physical.draft_for(updated),
                "entry": _serialize_entry(hass, entry),
            })
        except asyncio.CancelledError:
            if mutated:
                persist(hass, entry, msg["remote_id"], physical_status="Physical update interrupted. Check the remote and save the layout again.")
            raise
        except Exception as err:
            _LOGGER.exception("Physical remote update failed at %s", stage)
            message = f"{stage}: {err}"
            if mutated:
                message += ". The layout may be partially written. Check the remote and save the layout again."
                persist(hass, entry, msg["remote_id"], physical_status=message)
            connection.send_error(msg["id"], "physical_apply_failed", message)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/physical/rename_menu_item",
    vol.Required("entry_id"): str,
    vol.Required("remote_id"): str,
    vol.Required("page"): int,
    vol.Optional("row"): int,
    vol.Required("title"): str,
})
@websocket_api.async_response
async def ws_rename_menu_item(hass, connection, msg):
    from .studio_remotes import remote_management_lock

    async with remote_management_lock(hass):
        try:
            entry, remote = resolve(hass, msg)
            draft = physical.draft_for(remote)
            physical.rename_menu_item(draft, msg["page"], msg.get("row"), msg["title"])
            persist(hass, entry, msg["remote_id"], physical_layout=draft)
            connection.send_result(msg["id"], {"layout": draft})
        except (ValueError, KeyError, TypeError) as err:
            connection.send_error(msg["id"], "menu_rename_failed", str(err))


def register(hass):
    websocket_api.async_register_command(hass, ws_physical_get)
    websocket_api.async_register_command(hass, ws_physical_apply)
    websocket_api.async_register_command(hass, ws_physical_import)
    websocket_api.async_register_command(hass, ws_physical_table)
    websocket_api.async_register_command(hass, ws_rename_menu_item)


def local_identity_bytes(remote: dict[str, Any]) -> bytes | None:
    """The table id a saved remote answers to, or None when it carries no usable address."""
    identity = remote.get("physical_device_id") or remote.get("device_id")
    if not identity:
        return None
    try:
        text = str(identity)
        return c.id_to_bytes(text) if len(text) in (12, 17) else bytes.fromhex(text)
    except ValueError:
        return None


def _adopt_native_remotes(table, remotes, catalogue) -> int:
    """Record native remotes that already live on the device.

    A native remote installed by the SwitchBot app carries one of the stock profiles, and
    Studio can already render those from `NATIVE_PROFILE_LAYOUTS` given only the device type.
    So nothing has to be downloaded or rebuilt here: knowing the slot and the type is enough
    for the tile to appear. Its buttons act on the real target device, not on a bridge, so no
    bridge event metadata is invented for them.
    """
    known = {
        c.id_to_bytes(item.get("physical_device_id") or item["device_id"])
        for item in remotes if item.get("physical_device_id") or item.get("device_id")
    }
    adopted = 0
    for slot, device_type, control, device_id in table:
        if control != c.CTRL_NATIVE or device_id in known:
            continue
        type_name = next(
            (name for name, value in c.NATIVE_DEVTYPE.items() if value == device_type), None
        )
        if type_name is None:
            _LOGGER.info(
                "native remote in slot %s has unknown device type %#x; skipping", slot, device_type
            )
            continue
        meta = next((item for item in catalogue if cloud_item_id(item) == device_id), {})
        remotes.append({
            "index": slot,
            "name": str(meta.get("remoteName") or meta.get("thirdPartyDeviceName")
                        or f"{type_name.title()} {slot}"),
            "device_type": type_name,
            "device_id": device_id.hex(),
            "remote_id": device_id.hex(),
            "buttons": [],
            "imported_from_device": True,
        })
        adopted += 1
    return adopted


def _drop_absent_remotes(table, remotes) -> int:
    """Forget local records whose row is no longer on the device.

    Refresh used to only ever add. A remote deleted elsewhere — in the app, by another tool, or
    by a factory reset — stayed in Studio for ever with no way to clear it, so the panel and the
    device disagreed and the only honest reading was "the cache is broken".
    """
    present = {row[3] for row in table}
    kept, dropped = [], 0
    for item in remotes:
        identity = item.get("physical_device_id") or item.get("device_id")
        if not identity:
            kept.append(item)
            continue
        try:
            stored = c.id_to_bytes(str(identity)) if len(str(identity)) in (12, 17) \
                else bytes.fromhex(str(identity))
        except ValueError:
            kept.append(item)
            continue
        if stored in present:
            kept.append(item)
        else:
            _LOGGER.info("dropping %s: no longer in the device table", item.get("name") or identity)
            dropped += 1
    remotes[:] = kept
    return dropped
