"""Remote lifecycle operations Remote Studio shares with the options flow.

Rename, recreate, HID host pairing, adding a HID remote and the read-only diagnostics all
existed only as options-flow steps. They run the same command builders here, against an
inventory built exactly the way the options flow builds it, so a remote renamed in the panel
and one renamed in the settings end up in the same state locally, on the device and in the
SwitchBot account.
"""
from __future__ import annotations

import logging
import uuid
from copy import deepcopy
from typing import Any

import voluptuous as vol
from bleak import BleakScanner
from homeassistant.components import bluetooth, websocket_api

from . import commands as c
from . import install
from . import physical_layout
from .catalog import DEFAULT_BUTTONS, DEVICE_TYPES, ICONS, buttons_for
from .client import UrcResponseDecodeError
from .cloud import CloudError
from .cloud_ir import find_cloud_items, profile_from_cloud
from .const import DOMAIN
from .inventory import merge_inventory, stable_id_for_local
from . import addressing
from . import studio_remotes
from . import targets
from .studio_catalog import cloud_client

_LOGGER = logging.getLogger(__name__)


def _entry(hass, msg):
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        raise ValueError("Integration not found")
    return entry


def _client(hass, entry):
    client = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("client")
    if client is None:
        raise ValueError("WoRWS is not connected")
    return client


def _save_remotes(hass, entry, remotes: list[dict[str, Any]]) -> None:
    options = deepcopy(dict(entry.options))
    options["remotes"] = remotes
    hass.config_entries.async_update_entry(entry, options=options)


async def _inventory(hass, entry, client) -> list[dict[str, Any]]:
    """The same merged view the options flow works from: device table + local + cloud."""
    raw = await client.query(0x07)
    if not raw:
        raise ValueError("The remote did not answer with its device table")
    return merge_inventory(
        c.parse_added_devices(raw),
        entry.options.get("remotes", []),
        [item for item in entry.options.get("cloud_remotes", []) if isinstance(item, dict)],
    )


def _find(inventory: list[dict[str, Any]], remote_id: str) -> dict[str, Any]:
    """Match the panel's remote identity against the merged inventory.

    The panel identifies a remote the way `studio_physical.remote_identity` does — the stored
    `remote_id`, else the `device_id`. The inventory's own key prefixes that with `managed:`.
    """
    for item in inventory:
        managed = item.get("managed_item") or {}
        identity = str(managed.get("remote_id") or managed.get("device_id") or "")
        if remote_id and identity == remote_id:
            return item
        if item.get("key") in (remote_id, f"managed:{remote_id}"):
            return item
    raise ValueError("That remote is not in the device table; refresh first")


async def _recreate_physical_layout(
    hass, entry, client, item: dict[str, Any], managed: dict[str, Any],
    name: str, icon_name: str | None, connection, request_id: int, *, kind: str,
) -> None:
    """Rewrite edited IR/HID key pages in place, retaining the installed remote row."""
    slot = int(item["index"])
    stages, pages, draft = physical_layout.compile_recreate(
        managed,
        slot=slot,
        device_type=int(item["device_type_byte"]),
        control_type=int(item["control_type"]),
        name=name,
        icon_name=icon_name,
    )
    if draft["kind"] != kind:
        raise ValueError("The saved physical layout does not match this remote")
    responses = await client.send_command_sequence(
        tuple(packet for _stage, packet, _accepted in stages),
        timeout=45,
        timeout_retries=0,
        accepted_codes=tuple(accepted for _stage, _packet, accepted in stages),
    )
    for (stage, _packet, accepted), response in zip(stages, responses):
        if not response or response[0] not in accepted:
            raise ValueError(
                f"{stage}: response {response.hex() if response else 'timeout'}"
            )
    if len(responses) != len(stages):
        raise ValueError(f"{stages[len(responses)][0]}: no acknowledgement")

    raw = await client.query(0x07)
    table = c.parse_added_devices(raw) if raw else []
    expected_id = item["device_id_bytes"]
    if not any(row[0] == slot and row[1] == int(item["device_type_byte"])
               and row[2] == int(item["control_type"]) and row[3] == expected_id
               for row in table):
        raise ValueError("The remote row changed after rewriting its physical buttons")

    remotes = deepcopy(list(entry.options.get("remotes", [])))
    identity = str(managed.get("remote_id") or managed.get("device_id") or "")
    updated = False
    for remote in remotes:
        remote_identity = str(remote.get("remote_id") or remote.get("device_id") or "")
        if remote_identity != identity:
            continue
        remote.update({
            "index": slot,
            "name": name,
            "physical_layout": draft,
            "physical_packets": [packet.hex() for packet in pages],
            "icon_code": pages[0][11] if pages and len(pages[0]) > 11 else 0,
        })
        if icon_name is not None:
            remote["icon"] = icon_name
        updated = True
        break
    if not updated:
        raise ValueError("The remote was rewritten but its local record could not be found")
    _save_remotes(hass, entry, remotes)
    connection.send_result(request_id, {"slot": slot, "kind": kind})


async def _recreate_physical_layout(
    hass, entry, client, item: dict[str, Any], managed: dict[str, Any],
    name: str, icon_name: str | None, connection, request_id: int, *, kind: str,
) -> None:
    """Rewrite edited IR/HID key pages in place, retaining the installed remote row."""
    slot = int(item["index"])
    stages, pages, draft = physical_layout.compile_recreate(
        managed,
        slot=slot,
        device_type=int(item["device_type_byte"]),
        control_type=int(item["control_type"]),
        name=name,
        icon_name=icon_name,
    )
    if draft["kind"] != kind:
        raise ValueError("The saved physical layout does not match this remote")
    responses = await client.send_command_sequence(
        tuple(packet for _stage, packet, _accepted in stages),
        timeout=45,
        timeout_retries=0,
        accepted_codes=tuple(accepted for _stage, _packet, accepted in stages),
    )
    for (stage, _packet, accepted), response in zip(stages, responses):
        if not response or response[0] not in accepted:
            raise ValueError(
                f"{stage}: response {response.hex() if response else 'timeout'}"
            )
    if len(responses) != len(stages):
        raise ValueError(f"{stages[len(responses)][0]}: no acknowledgement")

    raw = await client.query(0x07)
    table = c.parse_added_devices(raw) if raw else []
    expected_id = item["device_id_bytes"]
    if not any(row[0] == slot and row[1] == int(item["device_type_byte"])
               and row[2] == int(item["control_type"]) and row[3] == expected_id
               for row in table):
        raise ValueError("The remote row changed after rewriting its physical buttons")

    remotes = deepcopy(list(entry.options.get("remotes", [])))
    identity = str(managed.get("remote_id") or managed.get("device_id") or "")
    updated = False
    for remote in remotes:
        remote_identity = str(remote.get("remote_id") or remote.get("device_id") or "")
        if remote_identity != identity:
            continue
        remote.update({
            "index": slot,
            "name": name,
            "physical_layout": draft,
            "physical_packets": [packet.hex() for packet in pages],
            "icon_code": pages[0][11] if pages and len(pages[0]) > 11 else 0,
        })
        if icon_name is not None:
            remote["icon"] = icon_name
        updated = True
        break
    if not updated:
        raise ValueError("The remote was rewritten but its local record could not be found")
    _save_remotes(hass, entry, remotes)
    connection.send_result(request_id, {"slot": slot, "kind": kind})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/remote/rename",
    vol.Required("entry_id"): str,
    vol.Required("remote_id"): str,
    vol.Required("name"): str,
})
@websocket_api.async_response
async def ws_remote_rename(hass, connection, msg):
    """Rename on the device, in the account when it is an IR remote, and locally."""
    try:
        entry = _entry(hass, msg)
        name = msg["name"].strip()
        if not name:
            raise ValueError("Give the remote a name")
        client = _client(hass, entry)
        item = _find(await _inventory(hass, entry, client), msg["remote_id"])
        if not item.get("physical"):
            raise ValueError("That remote is not installed on the device")
        response = await client.send_command(c.build_rename(
            remote_index=int(item["index"]),
            device_type=int(item["device_type_byte"]),
            control_type=int(item["control_type"]),
            device_id=item["device_id_bytes"],
            name=name,
        ))
        error = install.resp_error(response)
        if error:
            raise ValueError(f"the remote rejected the rename ({error})")

        cloud_warning = ""
        cloud_item = item.get("cloud_item", {})
        if item["control_type"] == c.CTRL_IR and cloud_item.get("remoteID"):
            try:
                await cloud_client(hass, entry).rename_ir(
                    str(cloud_item["remoteID"]), name,
                    bool(cloud_item.get("waitModify", False)),
                )
            except (CloudError, ValueError) as err:
                # The device is already renamed; the account is a mirror, not the truth.
                _LOGGER.warning("cloud rename failed: %s", err)
                cloud_warning = "Renamed on the remote, but the SwitchBot account still shows the old name."

        remotes = deepcopy(list(entry.options.get("remotes", [])))
        managed_identity = str(
            (item.get("managed_item") or {}).get("remote_id")
            or (item.get("managed_item") or {}).get("device_id") or ""
        )
        renamed = False
        for remote in remotes:
            identity = str(remote.get("remote_id") or remote.get("device_id") or "")
            same_managed = bool(managed_identity) and identity == managed_identity
            try:
                same_slot = (
                    not managed_identity
                    and stable_id_for_local(str(remote["device_id"])).hex() == item["device_key"]
                    and int(remote.get("index", -1)) == int(item["index"])
                )
            except (KeyError, ValueError):
                continue
            if same_managed or same_slot:
                remote["name"] = name
                remote["name_override"] = True
                renamed = True
        if not renamed:
            # A remote created elsewhere: record it so the new name survives a refresh.
            reverse_hid = {value: key for key, value in c.DEVTYPE.items()}
            device_type = ("IR_TV" if item["control_type"] == c.CTRL_IR
                           else reverse_hid.get(item["device_type_byte"], "UNKNOWN"))
            remotes.append({
                "index": item["index"],
                "name": name,
                "device_type": device_type,
                "icon": "tv" if device_type == "IR_TV" else "light",
                "device_id": (item["device_key"] if device_type == "IR_TV"
                              else item["device_id_bytes"][:6][::-1].hex()),
                "buttons": [],
                "name_override": True,
            })
        _save_remotes(hass, entry, remotes)
        connection.send_result(msg["id"], {"name": name, "warning": cloud_warning})
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio rename failed")
        connection.send_error(msg["id"], "rename_failed", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/remote/recreate",
    vol.Required("entry_id"): str,
    vol.Required("remote_id"): str,
    vol.Optional("name"): str,
    vol.Optional("target_address"): str,
    vol.Optional("auto_address", default=False): bool,
    vol.Optional("icon"): vol.In(ICONS),
})
@websocket_api.async_response
async def ws_remote_recreate(hass, connection, msg):
    """Write a remote to the device again from what is stored for it.

    Use it when the tile on the screen is wrong or missing. IR remotes are reinstalled from
    their account record; HID remotes are deleted and rebuilt from
    the stored button list; native remotes are deleted and bound again from the stored bridge
    credentials. A native profile missing from the device table is restored from its local
    record without issuing another delete.

    A native remote can also move: `target_address` binds it to a different address and
    `auto_address` picks the next free one. That is what fixes a tile whose controller was
    replaced — its old address no longer answers, and nothing else can re-point it.
    """
    try:
        entry = _entry(hass, msg)
        client = _client(hass, entry)
        inventory = await _inventory(hass, entry, client)
        try:
            item = _find(inventory, msg["remote_id"])
        except ValueError:
            # A failed delete-then-bind can leave the local profile intact but no physical
            # row. Allow "Write again" to restore that saved native profile without issuing
            # another delete.
            managed = next((remote for remote in entry.options.get("remotes", [])
                            if str(remote.get("remote_id") or remote.get("device_id") or "")
                            == msg["remote_id"]), None)
            device_type = str((managed or {}).get("device_type", "")).upper()
            if not managed or device_type not in c.NATIVE_DEVTYPE:
                raise
            item = {
                "managed_item": managed,
                "physical": False,
                "control_type": c.CTRL_NATIVE,
                "device_type_byte": c.NATIVE_DEVTYPE[device_type],
                "index": managed.get("index", 0),
                "device_key": c.id_to_bytes(
                    str(managed.get("physical_device_id") or managed["device_id"])
                ).hex(),
                "name": managed.get("name", "Remote"),
            }
        managed = item.get("managed_item") or {}
        name = (msg.get("name") or item.get("name") or "Remote").strip()
        # The icon code is part of the page record. Its distinct visual effect on V48 is
        # limited by the firmware artwork selector; still preserve the selected app code
        # when rebuilding a tile.
        icon = str(msg.get("icon") or managed.get("icon") or "")

        if item["control_type"] == c.CTRL_IR:
            if managed.get("physical_layout"):
                await _recreate_physical_layout(
                    hass, entry, client, item, managed, name,
                    msg.get("icon"), connection, msg["id"], kind="ir",
                )
                return
            cloud_item = item.get("cloud_item", {})
            remote_id = cloud_item.get("remoteID")
            if not remote_id:
                raise ValueError(
                    "Nothing to rebuild this IR remote from: it has no account record. "
                    "Add it again from the catalog instead."
                )
            downloaded = find_cloud_items(await cloud_client(hass, entry).get_ir_remote(
                str(remote_id), str(cloud_item.get("createFrom") or "hub")))
            if not downloaded:
                raise ValueError("The account holds no IR record for that remote")
            profile = profile_from_cloud(
                downloaded[0], remote_id=str(remote_id), name=name, metadata=cloud_item)
            requested_icon = msg.get("icon")
            previous_icon_code = managed.get("icon_code")
            errors, slot, record = await install.install_ir_profile(
                client, profile, name=name, replace_existing=True,
                remotes=entry.options.get("remotes", []),
                targets=targets.all_targets(entry),
                icon_name=requested_icon,
                icon_code=(previous_icon_code if requested_icon is None else None),
            )
            if errors or record is None:
                raise ValueError("; ".join(errors.values()) or "the rebuild failed")
            if requested_icon is None and managed.get("icon"):
                record["icon"] = managed["icon"]
            remotes = [other for other in entry.options.get("remotes", [])
                       if other.get("device_id") != profile.remote_id.hex()]
            remotes.append(record)
            _save_remotes(hass, entry, remotes)
            connection.send_result(msg["id"], {"slot": slot, "kind": "ir"})
            return

        if item["control_type"] == c.CTRL_HID:
            if not managed:
                raise ValueError("No stored button list for this HID remote")
            if managed.get("physical_layout"):
                await _recreate_physical_layout(
                    hass, entry, client, item, managed, name,
                    msg.get("icon"), connection, msg["id"], kind="hid",
                )
                return
            if item.get("physical"):
                error = await install.delete_and_verify(
                    client,
                    c.build_delete(
                        remote_index=int(item["index"]),
                        device_type=int(item["device_type_byte"]),
                        control_type=int(item["control_type"]),
                        device_id=item["device_key"],
                    ),
                    device_type=int(item["device_type_byte"]),
                    control_type=int(item["control_type"]),
                    device_id=str(item["device_key"]),
                )
                if error:
                    raise ValueError(f"could not remove the old copy ({error})")
            raw = await client.query(0x07)
            if not raw:
                raise ValueError("The remote did not answer with its device table")
            slot = len(c.parse_added_devices(raw))
            response = await client.send_command(c.build_remote(
                device_type_name=str(managed["device_type"]),
                remote_index=slot,
                name=name,
                device_id=str(managed["device_id"]),
                icon_name=icon or str(managed.get("icon") or "light"),
                buttons=list(managed.get("buttons") or DEFAULT_BUTTONS),
            ))
            error = install.resp_error(response)
            if error:
                raise ValueError(f"the remote rejected the rebuild ({error})")
            remotes = deepcopy(list(entry.options.get("remotes", [])))
            for remote in remotes:
                if remote.get("remote_id") == managed.get("remote_id"):
                    remote["index"] = slot
                    remote["name"] = name
                    if icon:
                        remote["icon"] = icon
            _save_remotes(hass, entry, remotes)
            connection.send_result(msg["id"], {"slot": slot, "kind": "hid"})
            return

        if item["control_type"] == c.CTRL_NATIVE:
            target = targets.target_for(entry, managed)
            if not managed or not target.get("target_key"):
                raise ValueError(
                    "No stored bridge credentials for this remote, so it cannot be written again"
                )
            device_id = str(managed.get("physical_device_id") or managed["device_id"])
            moved_from = ""
            wanted = str(msg.get("target_address") or "").strip()
            if msg.get("auto_address") and not wanted:
                # The address this remote is leaving is free again, so release it before
                # planning, or a full controller would refuse its own tile's move.
                chosen = studio_remotes.allocate_address(
                    hass, entry, release=device_id)
                wanted = chosen.address
            if wanted:
                if not addressing.is_valid(wanted):
                    raise ValueError(
                        "A bridge address is six hex bytes, like DA:71:16:E0:1F:92")
                wanted = addressing.format_address(addressing.normalise(wanted))
                if addressing.normalise(wanted) != addressing.normalise(device_id):
                    moved_from, device_id = device_id, wanted
            if moved_from:
                # Checked before the delete, not after: the firmware refuses a second tile on
                # one address with 0x02, and by then this remote's own tile would be gone.
                table = c.parse_added_devices(await client.query(0x07))
                if any(row[2] == c.CTRL_NATIVE
                       and row[3][:6] == c.id_to_bytes(device_id)[:6]
                       for row in table):
                    raise ValueError(
                        f"{device_id} already carries a native tile. Move that one first, or "
                        "choose an address that is free."
                    )
            if item.get("physical"):
                error = await install.delete_and_verify(
                    client,
                    c.build_delete(
                        remote_index=int(item["index"]),
                        device_type=int(item["device_type_byte"]),
                        control_type=int(item["control_type"]),
                        device_id=item["device_key"],
                    ),
                    device_type=int(item["device_type_byte"]),
                    control_type=int(item["control_type"]),
                    device_id=str(item["device_key"]),
                )
                if error:
                    raise ValueError(f"could not remove the old copy ({error})")
            raw = await client.query(0x07)
            if not raw:
                raise ValueError("The remote did not answer with its device table")
            slot = len(c.parse_added_devices(raw))
            custom_layout = managed.get("custom_layout")
            native_icon = str(managed.get("icon") or "light")
            native_mode = managed.get("control_mode")
            if custom_layout:
                stages = c.build_custom_native_bind_sequence(
                    key_id=0x01,
                    target_key=bytes.fromhex(str(target["target_key"])),
                    remote_index=slot,
                    name=name,
                    device_id=device_id,
                    icon_name=native_icon,
                    event_remote_id=str(managed.get("remote_id") or msg["remote_id"]),
                    main_buttons=c.normalize_main_buttons(custom_layout["main_buttons"]),
                    page_buttons={
                        int(page): list(actions)
                        for page, actions in custom_layout["pages"].items()
                    },
                    template=custom_layout.get("template"),
                    control_mode=native_mode,
                    device_type_name=str(managed["device_type"]),
                )
            else:
                stages = c.build_native_bind_sequence(
                    key_id=0x01,
                    target_key=bytes.fromhex(str(target["target_key"])),
                    device_type_name=str(managed["device_type"]),
                    remote_index=slot,
                    name=name,
                    device_id=device_id,
                    icon_name=native_icon,
                    control_mode=native_mode or 0,
                    event_remote_id=managed.get("remote_id"),
                )
            await install.bind_native_once(client, stages, device_id=device_id)
            restored_id = c.id_to_bytes(device_id)
            restored_type = c.NATIVE_DEVTYPE[str(managed["device_type"]).upper()]
            if (slot, restored_type, c.CTRL_NATIVE, restored_id) not in c.parse_added_devices(
                await client.query(0x07)
            ):
                raise ValueError("The saved Native remote was not found in its expected slot after writing")
            # The bind sequence rewrote the key for this address; siblings on the same address
            # were released by the delete above and are covered by the same association.
            if item.get("physical"):
                await install.reassociate_shared_target(client, device_id)
            if moved_from:
                # The tile it was moved off also loses its key entry, and a sibling may still
                # be using that address.
                await install.reassociate_shared_target(client, moved_from)
            remotes = deepcopy(list(entry.options.get("remotes", [])))
            for remote in remotes:
                if str(remote.get("remote_id") or remote.get("device_id") or "") == msg["remote_id"]:
                    remote["index"] = slot
                    remote["name"] = name
                    remote["icon"] = native_icon
                    remote["icon_code"] = c.ICON.get(native_icon, 1)
                    remote["physical_packets"] = [packet.hex() for stage, packet in stages
                                                  if stage.startswith("bind_")]
                    if moved_from:
                        # Both, not just one: `device_id` is what the device table is searched
                        # by, so leaving it on the old address would make this remote
                        # undeletable — the row would never be found and the local record
                        # would be dropped while the tile stayed on the screen.
                        remote["physical_device_id"] = device_id
                        remote["device_id"] = device_id
                    remote.pop("icon_variant_backup_packet", None)
                    remote.pop("washer_artwork_backup_packet", None)
            _save_remotes(hass, entry, remotes)
            warning = ""
            if moved_from:
                targets.remember_target(hass, entry, dict(target) | {
                    "device_id": device_id, "name": name,
                })
                warning = await studio_remotes.ask_bridge_to_serve(hass, entry, device_id)
            connection.send_result(msg["id"], {
                "slot": slot, "kind": "native",
                "address": device_id, "moved_from": moved_from, "warning": warning,
            })
            return

        raise ValueError(f"Control type {item['control_type']} cannot be written again from here")
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio recreate failed")
        connection.send_error(msg["id"], "recreate_failed", str(err) or type(err).__name__)


def _native_page_source_packets(remote: dict[str, Any], slot: int) -> list[bytes]:
    """Use cached native pages, or rebuild the known profile records exactly."""
    device_type_name = str(remote.get("device_type", "")).upper()
    if device_type_name not in c.NATIVE_DEVTYPE:
        raise ValueError("The selected remote is not a supported native profile")

    saved_packets = remote.get("physical_packets") or []
    if saved_packets:
        packets = [bytes.fromhex(value) for value in saved_packets]
    elif isinstance(remote.get("custom_layout"), dict):
        layout = remote["custom_layout"]
        template = str(layout.get("template") or device_type_name).upper()
        packets = [
            packet for _, packet in c.build_custom_native_pages(
                remote_index=slot,
                name=str(remote.get("name", "Remote")),
                device_id=str(remote["device_id"]),
                icon_name=str(remote.get("icon", "light")),
                event_remote_id=str(remote.get("remote_id") or ""),
                main_buttons=c.normalize_main_buttons(layout.get("main_buttons", {})),
                page_buttons={
                    int(page): list(actions)
                    for page, actions in layout.get("pages", {}).items()
                },
                template=template,
            )
        ]
    else:
        packets = list(c.build_native_pages(
            device_type_name=device_type_name,
            remote_index=slot,
            name=str(remote.get("name", "Remote")),
            device_id=str(remote["device_id"]),
            icon_name=str(remote.get("icon", "light")),
            event_remote_id=str(remote.get("remote_id") or ""),
        ))

    if not packets:
        raise ValueError("A complete native page record is not available for this remote")
    expected_type = c.device_type_bytes(c.NATIVE_DEVTYPE[device_type_name])
    expected_id = c.id_to_bytes(str(remote.get("physical_device_id") or remote["device_id"]))
    for packet in packets:
        if packet[:3] != b"\x0f\x62\x06" or len(packet) <= 87 + len(expected_type):
            raise ValueError("A cached native page packet is incomplete")
        c.rewrite_native_page_icon(packet, packet[7 + 1 + len(expected_type) + 2])
        body = packet[7:]
        if (body[0] != slot or body[1:1 + len(expected_type)] != expected_type
                or body[1 + len(expected_type)] != c.CTRL_NATIVE
                or body[4 + len(expected_type):15 + len(expected_type)] != expected_id):
            raise ValueError("A cached native page does not match this remote and slot")
    return packets


def _native_main_page_source_packet(remote: dict[str, Any], slot: int) -> bytes:
    """Use saved bytes, or rebuild only a known stock native page exactly."""
    packets = _native_page_source_packets(remote, slot)
    page = next((packet for packet in packets
                 if packet[87 + (4 if packet[8] == 0 else 1)] == 0), None)
    if page is None:
        raise ValueError("A complete Main-page packet is not available for this remote")

    _validate_native_test_packet(remote, slot, page)
    return page


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/remote/update_native_icon",
    vol.Required("entry_id"): str,
    vol.Required("remote_id"): str,
    vol.Required("icon"): vol.In(ICONS),
})
@websocket_api.async_response
async def ws_native_icon_update(hass, connection, msg):
    """Rewrite native page icon fields in place without deleting the installed remote."""
    try:
        entry = _entry(hass, msg)
        remote_id = msg["remote_id"]
        remotes = deepcopy(list(entry.options.get("remotes", [])))
        managed = next((remote for remote in remotes
                       if str(remote.get("remote_id") or remote.get("device_id") or "")
                       == remote_id), None)
        if managed is None:
            raise ValueError("The saved native page data is unavailable; refresh the remote first")

        client = _client(hass, entry)
        item = _find(await _inventory(hass, entry, client), remote_id)
        if not item.get("physical") or item.get("control_type") != c.CTRL_NATIVE:
            raise ValueError("This icon update is only available for an installed native remote")
        slot = int(item["index"])
        device_type = str(managed.get("device_type", "")).upper()
        if device_type not in c.NATIVE_DEVTYPE:
            raise ValueError("The saved screen profile is not available for this native remote")
        table = c.parse_added_devices(await client.query(0x07))
        expected_id = c.id_to_bytes(str(managed.get("physical_device_id") or managed["device_id"]))
        if not any(row[0] == slot and row[1] == c.NATIVE_DEVTYPE[device_type]
                   and row[2] == c.CTRL_NATIVE and row[3] == expected_id for row in table):
            raise ValueError("The native remote changed before the icon update; refresh first")

        source_packets = _native_page_source_packets(managed, slot)
        icon_code = c.ICON[msg["icon"].lower()]
        packets = [c.rewrite_native_page_icon(packet, icon_code)
                   for packet in source_packets]
        responses = await client.send_command_sequence(
            tuple(packets), timeout=30.0, timeout_retries=0,
            accepted_codes=tuple(frozenset({1}) for _ in packets),
        )
        if len(responses) != len(packets):
            raise ValueError(
                "The remote did not acknowledge every page icon update; it remains installed. "
                "Retry the icon update to finish any remaining pages."
            )
        for index, response in enumerate(responses):
            if not response or response[0] != 1:
                raise ValueError(
                    f"Page icon update {index + 1} was rejected "
                    f"({response.hex() if response else 'timeout'}); the native remote "
                    "remains installed. Retry to finish any remaining pages."
                )

        for remote in remotes:
            if str(remote.get("remote_id") or remote.get("device_id") or "") != remote_id:
                continue
            remote.update({
                "icon": msg["icon"],
                "icon_code": icon_code,
                "physical_packets": [packet.hex() for packet in packets],
            })
            remote.pop("icon_variant_backup_packet", None)
            remote.pop("washer_artwork_backup_packet", None)
            break
        _save_remotes(hass, entry, remotes)
        connection.send_result(msg["id"], {"slot": slot, "icon": msg["icon"]})
    except Exception as err:  # noqa: BLE001 - the panel displays device and transport failures
        _LOGGER.exception("Remote Studio native icon update failed")
        connection.send_error(msg["id"], "native_icon_update_failed", str(err))


def _validate_native_test_packet(remote: dict[str, Any], slot: int, packet: bytes) -> None:
    device_type_name = str(remote.get("device_type", "")).upper()
    expected_type = c.device_type_bytes(c.NATIVE_DEVTYPE[device_type_name])
    # Rewriting the current mode to itself validates the packet framing and CRC without changes.
    body = packet[7:]
    mode_offset = 1 + len(expected_type) + 1
    page_offset = 87 + len(expected_type)
    if (len(packet) <= max(7 + mode_offset, page_offset) or packet[page_offset] != 0
            or c.rewrite_native_page_control_mode(packet, body[mode_offset]) != packet):
        raise ValueError("The saved Main-page packet is malformed or has an invalid CRC")
    type_length = len(expected_type)
    control_offset = 1 + type_length
    id_offset = control_offset + 3
    expected_id = c.id_to_bytes(
        str(remote.get("physical_device_id") or remote["device_id"])
    )
    if (body[0] != slot or body[1:1 + type_length] != expected_type
            or body[control_offset] != c.CTRL_NATIVE
            or body[id_offset:id_offset + 11] != expected_id):
        raise ValueError("The saved Main-page packet does not match this native remote")


def _persist_artwork_test_packet(hass, entry, remote_id: str, packet: bytes | None) -> None:
    options = deepcopy(dict(entry.options))
    remote = next((item for item in options.get("remotes", [])
                   if str(item.get("remote_id") or item.get("device_id") or "") == remote_id), None)
    if remote is None:
        raise ValueError("Remote not found")
    if packet is None:
        remote.pop("icon_variant_backup_packet", None)
        remote.pop("washer_artwork_backup_packet", None)
    else:
        remote["icon_variant_backup_packet"] = packet.hex()
    hass.config_entries.async_update_entry(entry, options=options)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/remote/icon_variant_test",
    vol.Required("entry_id"): str,
    vol.Required("remote_id"): str,
    vol.Required("restore"): bool,
})
@websocket_api.async_response
async def ws_native_icon_variant_test(hass, connection, msg):
    """Temporarily switch one native Main page to the built-in Floor lamp profile."""
    try:
        entry = _entry(hass, msg)
        remote = next((item for item in entry.options.get("remotes", [])
                       if str(item.get("remote_id") or item.get("device_id") or "")
                       == msg["remote_id"]), None)
        if remote is None:
            raise ValueError("Remote not found")
        client = _client(hass, entry)
        expected_id = c.id_to_bytes(str(remote["device_id"]))
        expected_type = c.NATIVE_DEVTYPE.get(str(remote.get("device_type", "")).upper())
        slot = int(remote["index"])
        backup_hex = (remote.get("icon_variant_backup_packet")
                      or remote.get("washer_artwork_backup_packet"))
        source_mode = None
        source_icon = None
        if msg["restore"]:
            if not backup_hex:
                raise ValueError("There is no saved artwork test to restore")
            packet = bytes.fromhex(backup_hex)
            _validate_native_test_packet(remote, int(slot), packet)
            original_packet = None
        else:
            if backup_hex:
                original_packet = bytes.fromhex(backup_hex)
                _validate_native_test_packet(remote, int(slot), original_packet)
            else:
                original_packet = _native_main_page_source_packet(remote, int(slot))
                # Keep a recovery packet before the write in case the device applies it but loses its ACK.
                _persist_artwork_test_packet(hass, entry, msg["remote_id"], original_packet)
            body = original_packet[7:]
            type_length = 4 if body[1] == 0 and len(body) >= 5 else 1
            icon_offset = 1 + type_length + 2
            mode_offset = 1 + type_length + 1
            source_mode = body[mode_offset]
            source_icon = body[icon_offset]
            # controlMode selects the firmware artwork profile.  The icon byte only
            # selects that profile's normal/alternate rendering variant.
            packet = c.rewrite_native_page_control_mode(
                original_packet, c.NATIVE_FLOOR_LAMP_TEST_CONTROL_MODE)
            packet = c.rewrite_native_page_icon(packet, 1)

        packet_body = packet[7:]
        packet_type_length = 4 if packet_body[1] == 0 and len(packet_body) >= 5 else 1
        icon_offset = 1 + packet_type_length + 2
        mode_offset = 1 + packet_type_length + 1
        target_mode = packet_body[mode_offset]
        target_icon = packet_body[icon_offset]

        _LOGGER.warning(
            "Native Floor lamp profile command prepared: remote_id=%s slot=%s restore=%s "
            "source_mode=%s source_icon=%s target_mode=%s target_icon=%s bytes=%s prefix=%s",
            msg["remote_id"], slot, msg["restore"],
            None if source_mode is None else f"0x{source_mode:02x}",
            None if source_icon is None else f"0x{source_icon:02x}",
            f"0x{target_mode:02x}", f"0x{target_icon:02x}", len(packet), packet[:16].hex(),
        )
        before_raw, response = await client.send_command_with_preflight_query(
            packet,
            subcommand=7,
            query_timeout=20.0,
            command_timeout=30.0,
            prewrite_retries=3,
            refresh_credentials=True,
        )
        table = c.parse_added_devices(before_raw)
        matches = [row for row in table if row[0] == slot and row[2] == c.CTRL_NATIVE
                   and row[1] == expected_type and row[3] == expected_id]
        if len(matches) != 1:
            rows = [
                {"slot": row[0], "device_type": f"0x{row[1]:02x}",
                 "control_type": row[2], "device_id": row[3].hex()}
                for row in table
            ]
            raise ValueError(
                "The page command was sent, but the same-session device table did not confirm "
                f"the saved native remote: expected slot={slot}, "
                f"device_type=0x{expected_type:02x}, device_id={expected_id.hex()}; "
                f"device table={rows}"
            )
        error = install.resp_error(response)
        if error:
            raise ValueError(f"The remote did not acknowledge the Main-page rewrite ({error})")
        _LOGGER.info(
            "Native Floor lamp profile write acknowledged: remote_id=%s slot=%s restore=%s "
            "mode=0x%02x icon=0x%02x response=%s",
            msg["remote_id"], slot, msg["restore"],
            target_mode, target_icon,
            response.hex(),
        )
        if msg["restore"]:
            _persist_artwork_test_packet(hass, entry, msg["remote_id"], None)
        connection.send_result(msg["id"], {"restored": msg["restore"]})
    except Exception as err:  # noqa: BLE001 - the panel displays device and transport failures
        _LOGGER.exception("Remote Studio icon variant test failed")
        connection.send_error(msg["id"], "artwork_test_failed", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/host/pair",
    vol.Required("entry_id"): str,
    vol.Required("host_mac"): str,
})
@websocket_api.async_response
async def ws_pair_host(hass, connection, msg):
    """Point the remote's HID side at the machine that should receive key presses."""
    try:
        entry = _entry(hass, msg)
        client = _client(hass, entry)
        response = await client.send_command(c.build_hid_pair(msg["host_mac"]))
        error = install.resp_error(response)
        if error:
            raise ValueError(f"the remote rejected the pairing ({error})")
        options = deepcopy(dict(entry.options))
        options["host_mac"] = msg["host_mac"]
        hass.config_entries.async_update_entry(entry, options=options)
        connection.send_result(msg["id"], {"host_mac": msg["host_mac"]})
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio host pairing failed")
        connection.send_error(msg["id"], "pair_failed", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/remote/create_hid",
    vol.Required("entry_id"): str,
    vol.Required("name"): str,
    vol.Required("device_type"): vol.In(DEVICE_TYPES),
    vol.Required("device_id"): str,
    vol.Optional("icon", default=ICONS[0]): vol.In(ICONS),
    vol.Optional("buttons"): [str],
})
@websocket_api.async_response
async def ws_create_hid(hass, connection, msg):
    """Install a HID remote: presses go out as Bluetooth keys to the paired host."""
    try:
        entry = _entry(hass, msg)
        client = _client(hass, entry)
        buttons = list(msg.get("buttons") or DEFAULT_BUTTONS)
        allowed = set(buttons_for(msg["device_type"]))
        unknown = [name for name in buttons if name not in allowed]
        if unknown:
            raise ValueError(f"Unknown button(s): {', '.join(unknown)}")
        raw = await client.query(0x07)
        if not raw:
            raise ValueError("The remote did not answer with its device table")
        slot = len(c.parse_added_devices(raw))
        response = await client.send_command(c.build_remote(
            device_type_name=msg["device_type"],
            remote_index=slot,
            name=msg["name"],
            device_id=msg["device_id"],
            icon_name=msg["icon"],
            buttons=buttons,
        ))
        error = install.resp_error(response)
        if error:
            raise ValueError(
                "the remote rejected it because no host is paired yet"
                if error == "resp_hid_no_pair" else f"the remote rejected it ({error})"
            )
        remote_id = studio_remotes.new_remote_id(entry)
        remotes = list(entry.options.get("remotes", []))
        remotes.append({
            "index": slot,
            "name": msg["name"],
            "device_type": msg["device_type"],
            "icon": msg["icon"],
            "device_id": msg["device_id"],
            "remote_id": remote_id,
            "buttons": buttons,
        })
        _save_remotes(hass, entry, remotes)
        connection.send_result(msg["id"], {"remote_id": remote_id, "slot": slot})
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio HID create failed")
        connection.send_error(msg["id"], "hid_create_failed", str(err))


def _binding_report(entry) -> dict[str, Any]:
    """Every remote identity next to every binding, with anything inconsistent called out.

    A press is matched to its actions by `remote_id` alone, so if one remote's button drives
    another's light the cause is in these two columns. Showing them beats reasoning about them.
    """
    remotes = []
    identities: dict[str, list[str]] = {}
    for remote in entry.options.get("remotes", []):
        if not isinstance(remote, dict):
            continue
        identity = str(remote.get("remote_id") or remote.get("device_id") or "")
        identities.setdefault(identity, []).append(str(remote.get("name", "")))
        remotes.append({
            "name": str(remote.get("name", "")),
            "identity": identity,
            "has_remote_id": bool(remote.get("remote_id")),
            "device_id": str(remote.get("device_id", "")),
            "physical_device_id": str(remote.get("physical_device_id", "")),
            "device_type": str(remote.get("device_type", "")),
        })

    bindings = []
    owners: dict[str, int] = {}
    for binding in entry.options.get("bindings", []):
        if not isinstance(binding, dict):
            continue
        owner = str(binding.get("remote_id", ""))
        owners[owner] = owners.get(owner, 0) + 1
        actions = binding.get("button_actions")
        bindings.append({
            "remote_id": owner,
            "remote_name": str(binding.get("remote_name", "")),
            "entity_id": str(binding.get("entity_id", "")),
            "enabled": bool(binding.get("enabled", True)),
            "preset": bool(binding.get("mappings")),
            "buttons": sorted(actions) if isinstance(actions, dict) else [],
            "orphan": owner not in identities,
        })

    problems = []
    for identity, names in identities.items():
        if len(names) > 1:
            problems.append(
                f"{len(names)} remotes share the identity {identity or '(empty)'}: "
                f"{', '.join(names)}. A press from any of them matches all of their bindings."
            )
    for owner, count in owners.items():
        if count > 1:
            problems.append(f"{count} bindings are stored for remote {owner}; only the first runs.")
    for binding in bindings:
        if binding["orphan"]:
            problems.append(
                f"a binding for {binding['remote_id'] or '(empty)'} belongs to no remote that "
                "exists here"
            )
    return {"remotes": remotes, "bindings": bindings, "problems": problems}


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/diagnostics",
    vol.Required("entry_id"): str,
    vol.Required("what"): vol.In(("queries", "bridge", "bindings")),
})
@websocket_api.async_response
async def ws_diagnostics(hass, connection, msg):
    """Read-only checks: the 0F 63 query namespace, and whether the bridge is advertising."""
    try:
        entry = _entry(hass, msg)
        if msg["what"] == "bindings":
            connection.send_result(msg["id"], _binding_report(entry))
            return
        if msg["what"] == "queries":
            client = _client(hass, entry)
            rows = []
            try:
                for subcommand in range(0x16):
                    raw = await client.query(subcommand, timeout=1.5)
                    rows.append({"query": f"0F63{subcommand:02X}",
                                 "value": raw.hex() if raw else "timeout"})
            except UrcResponseDecodeError:
                raise ValueError(
                    "The encrypted response could not be decoded; the communication key "
                    "has probably rotated."
                ) from None
            connection.send_result(msg["id"], {"rows": rows})
            return

        known = targets.all_targets(entry)
        if not known:
            raise ValueError("No native bridge is configured for this integration")
        results = []
        for target in known:
            compact = "".join(
                ch for ch in str(target["device_id"]) if ch in "0123456789abcdefABCDEF")
            address = ":".join(compact[index:index + 2] for index in range(0, 12, 2)).upper()
            device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
            # Home Assistant deliberately omits local controllers from its shared advertisement
            # cache, and a bridge is exactly such a controller, so fall back to a direct scan.
            if device is None:
                device = await BleakScanner.find_device_by_address(
                    address, timeout=12.0, bluez={"adapter": "hci0"})
            results.append({
                "name": str(target.get("name") or address),
                "address": address,
                "found": device is not None,
            })
        connection.send_result(msg["id"], {
            "bridges": results,
            "detail": (
                "A bridge seen here is advertising. It serves a firmware-specific raw ATT "
                "server, so only a real button press verifies the command path."
            ),
        })
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio diagnostics failed")
        connection.send_error(msg["id"], "diagnostics_failed", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/bindings/cleanup",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def ws_bindings_cleanup(hass, connection, msg):
    """Delete saved actions that belong to no remote that exists here.

    A binding used to outlive the remote it was made for. Because a remote is matched by
    `remote_id or device_id`, such a leftover starts answering for whichever remote shares that
    identity — one remote's button switching on another's light. Removing them is safe: nothing
    that still has a remote is touched.
    """
    try:
        entry = _entry(hass, msg)
        options = deepcopy(dict(entry.options))
        identities = {
            str(item.get("remote_id") or item.get("device_id") or "")
            for item in options.get("remotes", []) if isinstance(item, dict)
        }
        bindings = [item for item in options.get("bindings", []) if isinstance(item, dict)]
        kept = [item for item in bindings
                if str(item.get("remote_id", "")) in identities]
        removed = [
            {"remote_id": str(item.get("remote_id", "")),
             "remote_name": str(item.get("remote_name", "")),
             "entity_id": str(item.get("entity_id", ""))}
            for item in bindings if item not in kept
        ]
        if removed:
            options["bindings"] = kept
            hass.config_entries.async_update_entry(entry, options=options)
            _LOGGER.warning(
                "removed %d saved action set(s) belonging to no remote: %s",
                len(removed),
                ", ".join(f"{item['remote_name'] or item['remote_id']}" for item in removed),
            )
        connection.send_result(msg["id"], {"removed": removed})
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio binding cleanup failed")
        connection.send_error(msg["id"], "cleanup_failed", str(err))


def register(hass) -> None:
    websocket_api.async_register_command(hass, ws_remote_rename)
    websocket_api.async_register_command(hass, ws_remote_recreate)
    websocket_api.async_register_command(hass, ws_native_icon_update)
    websocket_api.async_register_command(hass, ws_native_icon_variant_test)
    websocket_api.async_register_command(hass, ws_pair_host)
    websocket_api.async_register_command(hass, ws_create_hid)
    websocket_api.async_register_command(hass, ws_diagnostics)
    websocket_api.async_register_command(hass, ws_bindings_cleanup)
