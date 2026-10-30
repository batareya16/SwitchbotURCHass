"""Remote Studio physical-layout API. All drafts compile before device writes."""
from __future__ import annotations

import asyncio
import logging
from copy import deepcopy

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import commands as c
from . import physical_layout as physical
from .const import DOMAIN
from .ir_profiles import PROFILES
from .cloud import SwitchBotCloudClient
from .inventory import cloud_items, cloud_item_id
from .cloud_ir import find_cloud_items, profile_from_cloud

_LOGGER = logging.getLogger(__name__)


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
        profile = PROFILES.get(remote.get("profile"))
        if not bank and profile:
            bank = profile.code_bank
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


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/studio/physical/import",
                                vol.Required("entry_id"): str})
@websocket_api.async_response
async def ws_physical_import(hass, connection, msg):
    """Read existing HID layouts from the account without rewriting TV bonds or commands."""
    try:
        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            raise ValueError("Integration not found")
        settings = entry.data.get("cloud")
        if not settings:
            raise ValueError("Sign in to SwitchBot in the integration settings to import existing HID button layouts")
        client = hass.data[DOMAIN][entry.entry_id]["client"]
        table = c.parse_added_devices(await client.query(7))
        async def save_tokens(access_token, refresh_token):
            data = deepcopy(dict(entry.data))
            data["cloud"].update(access_token=access_token, refresh_token=refresh_token)
            hass.config_entries.async_update_entry(entry, data=data)
        cloud = SwitchBotCloudClient(async_get_clientsession(hass), dict(settings), save_tokens)
        metadata = cloud_items(await cloud.get_bindable_devices())
        slots = [slot for slot, _, control, _ in table if control == 4]
        options = deepcopy(dict(entry.options))
        remotes = options.setdefault("remotes", [])
        imported = 0
        for slot, device_type, control, device_id in table:
            if control != 4 or any(c.id_to_bytes(item["device_id"]) == device_id for item in remotes if item.get("device_id")):
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
        imported += await _adopt_ir_remotes(cloud, table, remotes)
        imported += _adopt_native_remotes(table, remotes, metadata)
        hass.config_entries.async_update_entry(entry, options=options)
        connection.send_result(msg["id"], {"imported": imported})
    except Exception as err:
        connection.send_error(msg["id"], "physical_import_failed", str(err))


async def _adopt_ir_remotes(cloud, table, remotes) -> int:
    """Record IR remotes that already live on the device, without rewriting any of them.

    An IR remote created in the SwitchBot app exists in the device table, but the integration
    has no idea what its buttons do, so Remote Studio cannot show it. The account does know:
    `queryIrRemote` returns the same code bank and key map the app installed. Rebuilding the
    profile from that gives Studio a layout to display, and nothing is written to the remote.
    """
    known = {
        c.id_to_bytes(item["device_id"]) for item in remotes if item.get("device_id")
    }
    pending = [
        (slot, device_id) for slot, _type, control, device_id in table
        if control == c.CTRL_IR and device_id not in known
    ]
    if not pending:
        return 0
    try:
        catalogue = cloud_items(await cloud.get_bindable_devices())
    except Exception as err:  # noqa: BLE001 - the physical import above already succeeded
        _LOGGER.warning("could not list cloud remotes while importing IR layouts: %s", err)
        return 0

    adopted = 0
    for slot, device_id in pending:
        metadata = next(
            (item for item in catalogue if cloud_item_id(item) == device_id), None
        )
        if not metadata or not metadata.get("remoteID"):
            _LOGGER.info("IR remote in slot %s has no saved cloud record; skipping", slot)
            continue
        remote_id = str(metadata["remoteID"])
        try:
            payload = await cloud.get_ir_remotes(
                [remote_id], str(metadata.get("createFrom") or "hub")
            )
            records = find_cloud_items(payload)
            if not records:
                raise ValueError("queryIrRemote returned no record")
            profile = profile_from_cloud(
                records[0], remote_id=remote_id,
                name=str(metadata.get("remoteName") or remote_id), metadata=metadata,
            )
        except Exception as err:  # noqa: BLE001 - one unreadable remote must not stop the rest
            _LOGGER.warning("could not rebuild IR remote in slot %s: %s", slot, err)
            continue
        name = str(metadata.get("remoteName") or f"IR remote {slot}")
        # Rebuild only the page packets. They describe the button layout and are what Studio
        # renders; the surrounding transfer/sync stages of a real install are not run here, and
        # nothing is sent to the remote.
        pages = c.build_ir_pages(
            remote_index=slot, device_type=profile.device_type,
            remote_id=profile.remote_id, name=name,
            key_map=list(profile.key_map), icon=profile.icon,
        )
        remotes.append({
            "index": slot,
            "name": name,
            "device_type": f"IR_{profile.device_type}",
            "icon": "tv" if profile.device_type == 2 else "light",
            "device_id": profile.remote_id.hex(),
            "remote_id": profile.remote_id_text or profile.remote_id.hex(),
            "studio_pages": c.studio_pages_from_packets(tuple(pages)),
            "physical_packets": [packet.hex() for packet in pages],
            "ir_code_bank": profile.code_bank.hex(),
            "buttons": [],
            "profile": profile.key,
            "imported_from_cloud": True,
        })
        adopted += 1
    return adopted


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/studio/physical/get",
                                vol.Required("entry_id"): str, vol.Required("remote_id"): str})
@callback
def ws_physical_get(hass, connection, msg):
    try:
        entry, remote = resolve(hass, msg)
        device_type = str(remote["device_type"]).upper()
        functions = ([{"value": physical.hid_usage(device_type, position), "label": position}
                      for position in c.TAG] if device_type in c.DEVTYPE else
                     [{"value": value, "label": c.custom_action_label(name)} for name, value in c.CUSTOM_ACTION_FUNCTIONS.items()])
        connection.send_result(msg["id"], {"layout": physical.draft_for(remote), "ir_sources": ir_sources(entry),
                                          "functions": functions,
                                          "status": remote.get("physical_status", ""),
                                          "backup": remote.get("physical_backup")})
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
        table = c.parse_added_devices(await client.query(7))
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
        })
    warnings = [
        "Slots " + ", ".join(str(slot) for slot in slots)
        + f" are native profiles sharing target {':'.join(f'{b:02X}' for b in reversed(address))}."
        " The firmware stores the same id for all of them, so presses are served by the"
        " first one and only its buttons work."
        for address, slots in by_address.items() if len(slots) > 1
    ]
    connection.send_result(msg["id"], {"rows": rows, "next_free_slot": len(rows),
                                       "warnings": warnings})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/studio/physical/apply",
    vol.Required("entry_id"): str, vol.Required("remote_id"): str, vol.Required("layout"): dict})
@websocket_api.async_response
async def ws_physical_apply(hass, connection, msg):
    store = hass.data.setdefault(DOMAIN, {})
    lock = store.setdefault("_physical_locks", {}).setdefault(msg["entry_id"], asyncio.Lock())
    async with lock:
        stage = "validate"
        mutated = False
        try:
            entry, remote = resolve(hass, msg)
            identity = msg["remote_id"]
            draft = physical.validate(remote, msg["layout"])
            client = store.get(entry.entry_id, {}).get("client")
            if client is None:
                raise ValueError("WoRWS is not connected")
            await client.ensure_strict_sequence_support()
            stage = "read device table"
            table = c.parse_added_devices(await client.query(7))
            expected_id = c.id_to_bytes(remote["device_id"])
            matches = [item for item in table if item[3] == expected_id]
            if len(matches) > 1:
                # Several native profiles can be installed against one target address, and the
                # firmware stores the same eleven-byte id for every one of them, so the id no
                # longer picks out a row. Fall back to the slot recorded when this remote was
                # installed; only give up when that does not resolve it either.
                narrowed = [item for item in matches if item[0] == remote.get("index")]
                if len(narrowed) == 1:
                    matches = narrowed
            recovering_native = not matches and draft["kind"] == "native" and remote.get("physical_backup") and remote.get("physical_pending")
            if len(matches) != 1 and not recovering_native:
                raise ValueError(
                    f"Could not uniquely identify the physical remote: {len(matches)} table rows "
                    f"carry this device id. Refresh the inventory, or remove the duplicate rows."
                    if matches else
                    "Could not find the physical remote in the device table; refresh the inventory first"
                )
            if recovering_native:
                slot, device_type, control_type = len(table), c.NATIVE_DEVTYPE[str(remote["device_type"]).upper()], c.CTRL_NATIVE
            else:
                slot, device_type, control_type, _ = matches[0]
            expected_control = {"hid": c.CTRL_HID, "ir": c.CTRL_IR, "native": c.CTRL_NATIVE}[draft["kind"]]
            if control_type != expected_control:
                raise ValueError("The physical remote type differs from the cached profile")
            uploads, pages = physical.compile_pages(remote, draft, slot)
            stored_changes = {}
            if draft["kind"] == "native":
                target = entry.data.get("native_target", {})
                key = bytes.fromhex(target.get("target_key", ""))
                if len(key) != 16:
                    raise ValueError("The native target key is missing")
                # Native update uses the already verified full delete/recreate path.
                layout = physical.native_layout(draft)
                new_slot = len(table) if recovering_native else len(table) - 1
                bind = c.build_custom_native_bind_sequence(
                    key_id=1, target_key=key, remote_index=new_slot, name=remote["name"],
                    device_id=remote["device_id"], icon_name=remote.get("icon", "tv"),
                    event_remote_id=identity, main_buttons=layout["main_buttons"],
                    page_buttons={int(p): values for p, values in layout["pages"].items()},
                )
                delete = c.build_delete(slot, device_type, control_type, remote["device_id"])
                stages = ([] if recovering_native else [("delete native remote", delete, frozenset({1}))]) + [
                    (name, packet, frozenset({1})) for name, packet in bind]
                pages = [packet for _, packet in bind if packet[:3] == b"\x0f\x62\x06"]
                stored_changes = {"device_type": "FAN", "custom_layout": layout, "index": new_slot}
            else:
                # Deleting keys leaves the physical remote and its existing HID bond in place.
                delete = bytes([15, 98, 4, 1, slot]) + c.device_type_bytes(device_type) + bytes([control_type]) + expected_id + b"\xff\xff"
                stages = uploads + [("replace keys", delete, frozenset({1}))] + [
                    (f"write page {packet[88]}", packet, frozenset({1})) for packet in pages]
                if uploads:
                    space = await client.query(6)
                    if len(space) < 9 or sum(len(bytes.fromhex(k.get("code_hex", ""))) for p in draft["pages"] for k in p["buttons"]) >= int.from_bytes(space[5:9], "big"):
                        raise ValueError("Not enough confirmed device storage for these IR codes")
            # Persist a recoverable snapshot before the first mutating command.
            persist(hass, entry, identity, physical_backup={"layout": physical.draft_for(remote),
                "packets": [packet.hex() for packet in physical.source_packets(remote)]},
                physical_original_packets=remote.get("physical_original_packets") or [packet.hex() for packet in physical.source_packets(remote)],
                physical_pending=draft,
                physical_status="Applying physical layout")
            stage = "write transaction"
            mutated = True
            responses = await client.send_command_sequence(
                tuple(packet for _, packet, _ in stages), timeout=45, timeout_retries=0,
                accepted_codes=tuple(accepted for _, _, accepted in stages),
            )
            for (name, _, accepted), response in zip(stages, responses):
                if not response or response[0] not in accepted:
                    stage = name
                    raise ValueError(f"{name}: response {response.hex() if response else 'timeout'}")
            if len(responses) != len(stages):
                stage = stages[len(responses)][0]
                raise ValueError(f"{stage}: no acknowledgement")
            # Read-back of table identity proves the tile remains installed; it does not read keys.
            stage = "verify remote remains installed"
            after = c.parse_added_devices(await client.query(7))
            if not any(item[3] == expected_id and item[2] == expected_control for item in after):
                raise ValueError("The remote is missing from the physical table after writing")
            persist(hass, entry, identity, physical_layout=draft,
                    physical_packets=[packet.hex() for packet in pages],
                    physical_pending=None,
                    physical_status="Device acknowledged all pages", **stored_changes)
            _, updated = resolve(hass, msg)
            connection.send_result(msg["id"], {"status": "Device acknowledged all pages. Test the physical buttons now.",
                                              "backup": updated.get("physical_backup")})
        except asyncio.CancelledError:
            if mutated:
                persist(hass, entry, msg["remote_id"], physical_status="Physical update interrupted. Load the previous layout to restore it.")
            raise
        except Exception as err:
            _LOGGER.exception("Physical remote update failed at %s", stage)
            message = f"{stage}: {err}"
            if mutated:
                message += ". The layout may be partially written. The previous layout is saved under Restore previous layout."
                persist(hass, entry, msg["remote_id"], physical_status=message)
            connection.send_error(msg["id"], "physical_apply_failed", message)


def register(hass):
    websocket_api.async_register_command(hass, ws_physical_get)
    websocket_api.async_register_command(hass, ws_physical_apply)
    websocket_api.async_register_command(hass, ws_physical_import)
    websocket_api.async_register_command(hass, ws_physical_table)


def _adopt_native_remotes(table, remotes, catalogue) -> int:
    """Record native remotes that already live on the device.

    A native remote installed by the SwitchBot app carries one of the stock profiles, and
    Studio can already render those from `NATIVE_PROFILE_LAYOUTS` given only the device type.
    So nothing has to be downloaded or rebuilt here: knowing the slot and the type is enough
    for the tile to appear. Its buttons act on the real target device, not on a bridge, so no
    bridge event metadata is invented for them.
    """
    known = {
        c.id_to_bytes(item["device_id"]) for item in remotes if item.get("device_id")
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
