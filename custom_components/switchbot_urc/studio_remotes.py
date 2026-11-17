"""Create and delete remotes from Remote Studio.

The same operations exist in the integration's options flow. They are exposed here so the panel
does not have to send people to a different screen for half the work, and both paths go through
the same verified command builders and the same read-table-then-mutate transaction.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from copy import deepcopy
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from dataclasses import asdict

from . import commands as c
from . import addressing
from . import install
from . import ir_catalog
from . import targets
from .catalog import DEVICE_TYPES, ICONS
from .cloud import CloudError
from .cloud_ir import find_cloud_items, generate_remote_id, profile_from_cloud
from .const import DOMAIN, RESP_OK
from .inventory import stable_id_for_local
from .studio_catalog import cloud_client
from .studio_physical import cached_device_table, read_device_table, resolve, store_device_table

_LOGGER = logging.getLogger(__name__)


def _client(hass, entry):
    client = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("client")
    if client is None:
        raise ValueError("WoRWS is not connected")
    return client


def new_remote_id(entry) -> str:
    """An event identity no other remote on this integration already uses.

    Bindings are matched on this value alone, so a collision would silently run one remote's
    actions for another's presses. Thirty-two bits make that unlikely, not impossible, and the
    check costs nothing.
    """
    taken = {
        str(item.get("remote_id", "")).lower()
        for item in entry.options.get("remotes", [])
    }
    for _ in range(100):
        candidate = uuid.uuid4().hex[:8]
        if candidate not in taken:
            return candidate
    raise ValueError("could not find a free remote id")


def _save_remotes(hass, entry, remotes: list[dict[str, Any]]) -> None:
    options = deepcopy(dict(entry.options))
    options["remotes"] = remotes
    hass.config_entries.async_update_entry(entry, options=options)


def ensure_distinct_identities(hass, entry) -> int:
    """Give every remote an identity nothing else can answer to.

    A remote with no `remote_id` is matched by its address, and several native tiles used to
    share one bridge address — so a press on either ran both of their actions. Each such remote
    gets an id of its own; its bindings follow only when exactly one remote held that identity,
    because splitting shared ones is a guess nobody asked us to make.
    """
    remotes = [item for item in entry.options.get("remotes", []) if isinstance(item, dict)]
    holders: dict[str, list[dict]] = {}
    for remote in remotes:
        if remote.get("remote_id"):
            continue
        holders.setdefault(str(remote.get("device_id", "")), []).append(remote)
    if not holders:
        return 0
    options = deepcopy(dict(entry.options))
    stored = [item for item in options.get("remotes", []) if isinstance(item, dict)]
    bindings = [item for item in options.get("bindings", []) if isinstance(item, dict)]
    taken = {str(item.get("remote_id", "")) for item in stored if item.get("remote_id")}
    changed = 0
    for address, sharing in holders.items():
        for remote in sharing:
            target = next(
                (item for item in stored
                 if item is remote or (
                     not item.get("remote_id")
                     and str(item.get("device_id", "")) == address
                     and item.get("name") == remote.get("name"))),
                None,
            )
            if target is None:
                continue
            new_id = uuid.uuid4().hex[:8]
            while new_id in taken:
                new_id = uuid.uuid4().hex[:8]
            taken.add(new_id)
            target["remote_id"] = new_id
            changed += 1
            if len(sharing) == 1:
                for binding in bindings:
                    if str(binding.get("remote_id", "")) == address:
                        binding["remote_id"] = new_id
            else:
                _LOGGER.warning(
                    "%s was shared by %d remotes; %r now has its own id but its actions must "
                    "be set again, because which of them owned each one is not recorded",
                    address, len(sharing), remote.get("name", ""),
                )
    if not changed:
        return 0
    options["remotes"] = stored
    options["bindings"] = bindings
    hass.config_entries.async_update_entry(entry, options=options)
    _LOGGER.warning("gave %d remote(s) an identity of their own", changed)
    return changed


def _forget_remote(hass, entry, identity: str) -> int:
    """Remove a remote and the actions bound to it, in one write.

    A binding outlives its remote otherwise. That is not merely untidy: a remote is matched by
    `remote_id or device_id`, so an orphan left over from a deleted remote starts answering for
    whichever remaining remote shares that identity — which is how one remote's button came to
    switch on another's light.
    """
    options = deepcopy(dict(entry.options))
    # One remote, not every remote that answers to this identity: two can share one, and
    # deleting the tile of one is not a reason to forget the other's record as well.
    kept_remotes = []
    removed = False
    for item in options.get("remotes", []):
        matches = str(item.get("remote_id") or item.get("device_id") or "") == identity
        if matches and not removed:
            removed = True
            continue
        kept_remotes.append(item)
    options["remotes"] = kept_remotes
    bindings = [item for item in options.get("bindings", []) if isinstance(item, dict)]
    kept = [item for item in bindings if str(item.get("remote_id", "")) != identity]
    dropped = len(bindings) - len(kept)
    # Only when nothing else answers to that identity: two remotes can share one, and the
    # survivor's actions are not ours to delete.
    still_used = any(
        str(item.get("remote_id") or item.get("device_id") or "") == identity
        for item in options["remotes"]
    )
    if dropped and not still_used:
        options["bindings"] = kept
        _LOGGER.info("removed %d binding(s) that belonged to %s", dropped, identity)
    else:
        dropped = 0
    hass.config_entries.async_update_entry(entry, options=options)
    return dropped


def _bridges(hass):
    """Bridge pools reported by the add-on over MQTT."""
    reported = hass.data.get(DOMAIN, {}).get("_bridge_capabilities") or {}
    return [
        addressing.Bridge(
            adapter=str(data.get("adapter") or "bridge"),
            address=addressing.format_address(address),
            advertising_sets=data["advertising_sets"],
            serving=data["serving"],
            extended_advertising=data["extended_advertising"],
        )
        for address, data in reported.items()
        if addressing.is_valid(address)
    ]


def remote_management_lock(hass):
    return hass.data.setdefault(DOMAIN, {}).setdefault("_remote_management_lock", asyncio.Lock())


def _native_table_addresses(table) -> list[str]:
    return [row[3][:6][::-1].hex() for row in table if row[2] == c.CTRL_NATIVE]


def _used_addresses(entry) -> list[str]:
    """Every address a native remote is already bound to."""
    return [
        str(remote.get("physical_device_id") or remote.get("device_id") or "")
        for remote in entry.options.get("remotes", [])
        if str(remote.get("device_type", "")).upper() in c.NATIVE_DEVTYPE
    ]


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/remote/delete",
    vol.Required("entry_id"): str,
    vol.Required("remote_id"): str,
})
@websocket_api.async_response
async def ws_remote_delete(hass, connection, msg):
    async with remote_management_lock(hass):
        await _delete_remote(hass, connection, msg)


async def _delete_remote(hass, connection, msg):
    """Remove one remote from the device and from the integration's own list."""
    try:
        entry, remote = resolve(hass, msg)
        client = _client(hass, entry)
        table = await read_device_table(hass, entry, client)
        # A native remote is found in the table by the bridge address it is bound to, which is
        # `physical_device_id` once it has been moved. Everything below works from this one
        # value, so the delete, its preflight and the key repair all name the same address.
        bound_address = str(remote.get("physical_device_id") or remote["device_id"])
        expected_id = stable_id_for_local(bound_address)
        matches = [row for row in table if row[3] == expected_id]
        if len(matches) > 1:
            # Several native profiles can share one target address and then store the same id,
            # so fall back to the slot recorded when this remote was installed.
            narrowed = [row for row in matches if row[0] == remote.get("index")]
            if len(narrowed) == 1:
                matches = narrowed
        if not matches:
            # Nothing to delete on the device — it was removed elsewhere, or the remote was
            # factory reset. Dropping the local record is then the whole job, and refusing
            # would leave Studio showing a remote that does not exist.
            dropped = _forget_remote(hass, entry, msg["remote_id"])
            connection.send_result(msg["id"], {
                "deleted": msg["remote_id"], "rows": len(table), "device_untouched": True,
                "bindings_removed": dropped,
            })
            return
        if len(matches) != 1:
            raise ValueError(
                f"{len(matches)} rows in the device table carry this id; refresh first"
            )
        slot, device_type, control_type, _ = matches[0]
        command = c.build_delete(
            remote_index=slot, device_type=device_type, control_type=control_type,
            device_id=bound_address,
        )

        def _still_there(raw: bytes) -> bool:
            return any(
                (row[0], row[1], row[2], row[3]) == (slot, device_type, control_type, expected_id)
                for row in c.parse_added_devices(raw)
            )

        # One session: read the table, prove the row is there, then the single destructive write.
        _before, response = await client.send_command_with_preflight_query(
            command, subcommand=0x07, preflight_check=_still_there,
        )
        if response and response[0] != RESP_OK:
            raise ValueError(f"the remote rejected the delete with 0x{response[0]:02X}")

        # A lost acknowledgement is not a failure on its own; the table is the truth. Several
        # native profiles on one address share an id, so count the matching rows rather than
        # asking whether the id is still present — it legitimately is, for the survivors.
        def _count(rows) -> int:
            return sum(1 for row in rows if row[3] == expected_id and row[2] == control_type)

        after = await read_device_table(hass, entry, client)
        if _count(after) >= _count(table):
            raise ValueError("the remote is still in the device table after the delete")

        dropped = _forget_remote(hass, entry, msg["remote_id"])
        connection.send_result(msg["id"], {
            "bindings_removed": dropped,
            "deleted": msg["remote_id"], "rows": len(after),
        })
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio delete failed")
        connection.send_error(msg["id"], "remote_delete_failed", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/remote/create",
    vol.Required("entry_id"): str,
    vol.Required("name"): str,
    vol.Optional("device_type"): str,
    vol.Optional("native_type"): str,
    vol.Optional("icon"): str,
    vol.Optional("target_id"): str,
    vol.Optional("new_target_address"): str,
    vol.Optional("auto_address", default=False): bool,
})
@websocket_api.async_response
async def ws_remote_create(hass, connection, msg):
    """Install a Native tile at a free address served by a running bridge."""
    async with remote_management_lock(hass):
        await _create_native_remote(hass, connection, msg)


async def _create_native_remote(hass, connection, msg):
    try:
        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            raise ValueError("Integration not found")
        wanted = str(msg.get("new_target_address") or msg.get("target_id") or "").strip()
        if wanted and not addressing.is_valid(wanted):
            raise ValueError("Enter a six-byte Bluetooth address.")
        bridges = _bridges(hass)
        if not bridges:
            raise ValueError("Start the SwitchBot URC Bridge add-on first.")
        client = _client(hass, entry)
        table = await read_device_table(hass, entry, client)
        c.require_remote_slot(len(table))
        if not c.remaining_remote_kind_slots(table, c.CTRL_NATIVE):
            raise ValueError("No more Bridge remotes can be added.")
        used = _native_table_addresses(table)
        free = list(addressing.free_advertised_addresses(bridges, used))
        if wanted:
            free = [(address, bridge) for address, bridge in free
                    if addressing.normalise(address) == addressing.normalise(wanted)]
        if not free:
            raise ValueError("No free advertised bridge address is available.")
        address, bridge = free[0]
        if not await _confirm_bridge_address(hass, bridge, address):
            raise ValueError("The add-on did not confirm the selected address. Try again when it is ready.")
        slot = len(table)
        selected_type = c.native_type_metadata(
            str(msg.get("native_type") or msg.get("device_type") or "STRIP")
        )
        device_type = selected_type["device_type"]
        remote_id = new_remote_id(entry)
        stages = c.build_native_bind_sequence(
            device_type_name=device_type,
            remote_index=slot,
            name=msg["name"],
            device_id=address,
            icon_name=selected_type["icon_name"],
            control_mode=selected_type["control_mode"],
            event_remote_id=remote_id,
        )
        await install.bind_native_once(client, stages, device_id=address)
        store_device_table(hass, entry, [*table, (
            slot, c.NATIVE_DEVTYPE[device_type], c.CTRL_NATIVE, c.id_to_bytes(address),
        )])

        remotes = list(entry.options.get("remotes", []))
        remotes.append({
            "index": slot,
            "name": msg["name"],
            "device_type": device_type,
            "native_type": selected_type["value"],
            "control_mode": selected_type["control_mode"],
            "icon": selected_type["icon_name"],
            "icon_code": selected_type["icon_code"],
            "device_id": address,
            "physical_device_id": address,
            "remote_id": remote_id,
            "buttons": [],
            "custom_layout": c.editable_layout_from_native_profile(device_type),
            "physical_packets": [packet.hex() for stage, packet in stages if stage.startswith("bind_")],
        })
        _save_remotes(hass, entry, remotes)
        connection.send_result(msg["id"], {
            "remote_id": remote_id, "slot": slot, "bridge": address,
        })
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio create failed")
        connection.send_error(msg["id"], "remote_create_failed", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/remote/install_ir",
    vol.Required("entry_id"): str,
    vol.Required("source"): vol.In(("catalog", "cloud")),
    vol.Required("name"): str,
    vol.Optional("hxd_index"): str,
    vol.Optional("remote_type"): int,
    vol.Optional("remote_id"): str,
    vol.Optional("replace_existing", default=False): bool,
})
@websocket_api.async_response
async def ws_remote_install_ir(hass, connection, msg):
    async with remote_management_lock(hass):
        await _install_ir_remote(hass, connection, msg)


async def _install_ir_remote(hass, connection, msg):
    """Install a whole IR remote from the catalog or the account.

    This is the options flow's add-IR-remote path, driven from the panel instead of a form
    sequence. Both call the same `install.install_ir_profile`, so the device sees the same
    delete-duplicates / transfer / pages / sync transaction either way.
    """
    try:
        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            raise ValueError("Integration not found")
        source = msg["source"]
        name = msg["name"]
        cloud = None
        cloud_item = None

        if source == "catalog":
            metadata = await hass.async_add_executor_job(
                ir_catalog.profile_by_index, str(msg.get("hxd_index", ""))
            )
            if metadata is None:
                raise ValueError("That model is not in the bundled catalog")
            cloud = cloud_client(hass, entry)
            downloaded = find_cloud_items(await cloud.get_ir_model(metadata.hxd_index))
            item = next(
                (row for row in downloaded
                 if str(row.get("itemID", row.get("hxdIndex", ""))) == metadata.hxd_index),
                downloaded[0] if downloaded else None,
            )
            if item is None:
                raise ValueError("The cloud returned no code bank for this model")
            profile = profile_from_cloud(
                item, remote_id=generate_remote_id(), name=name,
                remote_type=metadata.remote_type, metadata=asdict(metadata),
            )
        else:
            remote_id = str(msg.get("remote_id", ""))
            record = next(
                (item for item in entry.options.get("cloud_remotes", [])
                 if isinstance(item, dict) and str(item.get("remoteID")) == remote_id),
                None,
            )
            if record is None:
                raise ValueError("That remote is not in the cached account list; refresh first")
            cloud = cloud_client(hass, entry)
            downloaded = find_cloud_items(await cloud.get_ir_remote(
                remote_id, str(record.get("createFrom") or "hub")))
            if not downloaded:
                raise ValueError("The account holds no IR record for that remote")
            profile = profile_from_cloud(
                downloaded[0], remote_id=remote_id, name=name, metadata=record)

        client = _client(hass, entry)
        status: list[str] = []
        errors, remote_index, installed = await install.install_ir_profile(
            client, profile,
            name=name,
            replace_existing=bool(msg.get("replace_existing")),
            remotes=entry.options.get("remotes", []),
            targets=targets.all_targets(entry),
            status=status.append,
            observe_table=lambda table: store_device_table(hass, entry, table),
        )
        if errors.get("base") in {"ir_device_table_full", "ir_capacity_full"}:
            raise ValueError("No more IR remotes can be added. You can replace an installed IR remote.")
        if errors or installed is None:
            raise ValueError(
                f"{'; '.join(errors.values()) or 'install failed'}"
                f"{' — ' + status[-1] if status else ''}"
            )
        remotes = [item for item in entry.options.get("remotes", [])
                   if item.get("device_id") != profile.remote_id.hex()]
        remotes.append(installed)
        _save_remotes(hass, entry, remotes)

        # A catalog remote is also registered in the account, so the phone app shows it too.
        # Failing that leaves a working remote, so it is reported, not raised.
        cloud_warning = ""
        if source == "catalog" and cloud is not None:
            try:
                await cloud.create_ir(profile.create_cloud_item(
                    remote_index=remote_index, name=name))
                await cloud.bind_ir(
                    remote_id=profile.remote_id_text, remote_index=remote_index,
                    name=name, remote_type=profile.device_type,
                )
            except CloudError as err:
                _LOGGER.warning("catalog IR cloud save failed: %s", err)
                cloud_warning = (
                    "Installed on the remote, but saving it to the SwitchBot account failed."
                )
        connection.send_result(msg["id"], {
            "remote_id": installed["remote_id"], "slot": remote_index,
            "warning": cloud_warning, "stages": len(status),
        })
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio IR install failed")
        connection.send_error(msg["id"], "ir_install_failed", str(err))


def next_move_address(hass, entry, occupied=()) -> str:
    table = cached_device_table(hass, entry)
    used = _used_addresses(entry) if table is None else _native_table_addresses(table)
    return next((address for address, _ in addressing.free_advertised_addresses(
        _bridges(hass), [*used, *occupied],
    )), "")


async def _confirm_bridge_address(hass, owner, address: str) -> bool:
    from . import async_bridge_control

    return await async_bridge_control(hass, "check_address", {
        "address": address, "adapter_address": owner.address,
    })


async def prepare_move_destination(hass, address: str) -> None:
    """Confirm the destination before removing a working tile."""
    compact = addressing.normalise(address)
    owner = next((bridge for bridge in _bridges(hass)
                  if any(addressing.normalise(item) == compact for item in bridge.serving)), None)
    if owner is None:
        raise ValueError(f"No running bridge reports {address} as an advertised address.")
    if not await _confirm_bridge_address(hass, owner, address):
        raise ValueError(
            f"The bridge did not confirm advertising {address}. "
            "The remote was left at its current address."
        )


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/remote/sources",
    vol.Required("entry_id"): str,
    vol.Optional("refresh_capacity", default=False): bool,
})
@websocket_api.async_response
async def ws_remote_sources(hass, connection, msg):
    """What the panel may offer on its Add remote dialog, for this installation."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Integration not found")
        return
    known = targets.all_targets(entry)
    table = cached_device_table(hass, entry)
    capacity_error = False
    if msg.get("refresh_capacity"):
        try:
            table = await read_device_table(hass, entry, _client(hass, entry))
        except Exception as err:
            _LOGGER.debug("Could not refresh the device capacity: %s", err)
            table = None
            capacity_error = True
    bridges = _bridges(hass)
    used = _used_addresses(entry) if table is None else _native_table_addresses(table)
    free = list(addressing.free_advertised_addresses(bridges, used))
    bridge_capacity = len({addressing.normalise(address) for bridge in bridges for address in bridge.serving})
    limits = {
        "ir": (c.CTRL_IR, c.MAX_IR_REMOTES),
        "native": (c.CTRL_NATIVE, min(bridge_capacity, c.MAX_BLE_REMOTES)),
        "hid": (c.CTRL_HID, c.MAX_HID_REMOTES),
    }
    remote_capacity = {}
    for kind, (control_type, total) in limits.items():
        available = None if table is None else c.remaining_remote_kind_slots(table, control_type)
        if kind == "native":
            available = 0 if not free else None if available is None else min(available, len(free))
        remote_capacity[kind] = {"available": available, "total": total}
    connection.send_result(msg["id"], {
        "native": bool(bridges),
        "remote_capacity": remote_capacity,
        "capacity_read_failed": capacity_error,
        "bridges": [
            {"target_id": address, "name": f"{bridge.adapter} · {address}"}
            for address, bridge in free
        ],
        "catalog": await hass.async_add_executor_job(ir_catalog.available),
        "cloud": bool(entry.data.get("cloud")),
        "cloud_remotes": [
            {"remote_id": str(item["remoteID"]),
             "name": str(item.get("remoteName") or item["remoteID"])}
            for item in entry.options.get("cloud_remotes", [])
            if isinstance(item, dict) and item.get("remoteID")
        ],
        "native_options": {
            "capacity": bridge_capacity,
            "free": len(free),
            "controllers": [
                {"adapter": bridge.adapter, "address": bridge.address,
                 "capacity": len(bridge.serving),
                 "used": len({addressing.normalise(item) for item in used}
                             & {addressing.normalise(address) for address in bridge.serving}),
                 "serving": list(bridge.serving),
                 "extended_advertising": bridge.extended_advertising}
                for bridge in bridges
            ],
            "next_move_address": next_move_address(hass, entry),
            "device_types": list(c.SUPPORTED_NATIVE_DEVICE_TYPES),
            "icons": list(ICONS),
            "default_device_type": str((known[0] if known else {}).get("device_type", "STRIP")),
            "default_screen_profile": next(
                (item["value"] for item in c.native_type_picker_options()
                 if str((known[0] if known else {}).get("device_type", "")).upper()
                 in (item["value"], *item["equivalent_types"])),
                "STRIP",
            ),
            "screen_profiles": c.native_type_picker_options(),
            "default_icon": str((known[0] if known else {}).get("icon", "strip")),
        },
        "hid": {
            "device_types": list(DEVICE_TYPES),
            "icons": list(ICONS),
        },
    })


def register(hass) -> None:
    websocket_api.async_register_command(hass, ws_remote_delete)
    websocket_api.async_register_command(hass, ws_remote_create)
    websocket_api.async_register_command(hass, ws_remote_install_ir)
    websocket_api.async_register_command(hass, ws_remote_sources)
