"""Create and delete remotes from Remote Studio.

The same operations exist in the integration's options flow. They are exposed here so the panel
does not have to send people to a different screen for half the work, and both paths go through
the same verified command builders and the same read-table-then-mutate transaction.
"""
from __future__ import annotations

import logging
import uuid
from copy import deepcopy
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import commands as c
from .const import DOMAIN, RESP_OK
from .inventory import stable_id_for_local
from .studio_physical import resolve

_LOGGER = logging.getLogger(__name__)


def _client(hass, entry):
    client = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("client")
    if client is None:
        raise ValueError("WoRWS is not connected")
    return client


def _save_remotes(hass, entry, remotes: list[dict[str, Any]]) -> None:
    options = deepcopy(dict(entry.options))
    options["remotes"] = remotes
    hass.config_entries.async_update_entry(entry, options=options)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/remote/delete",
    vol.Required("entry_id"): str,
    vol.Required("remote_id"): str,
})
@websocket_api.async_response
async def ws_remote_delete(hass, connection, msg):
    """Remove one remote from the device and from the integration's own list."""
    try:
        entry, remote = resolve(hass, msg)
        client = _client(hass, entry)
        table = c.parse_added_devices(await client.query(7))
        expected_id = stable_id_for_local(str(remote["device_id"]))
        matches = [row for row in table if row[3] == expected_id]
        if len(matches) > 1:
            # Several native profiles can share one target address and then store the same id,
            # so fall back to the slot recorded when this remote was installed.
            narrowed = [row for row in matches if row[0] == remote.get("index")]
            if len(narrowed) == 1:
                matches = narrowed
        if len(matches) != 1:
            raise ValueError(
                f"{len(matches)} rows in the device table carry this id; refresh first"
                if matches else "this remote is not in the device table"
            )
        slot, device_type, control_type, _ = matches[0]
        command = c.build_delete(
            remote_index=slot, device_type=device_type, control_type=control_type,
            device_id=str(remote["device_id"]),
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

        # A lost acknowledgement is not a failure on its own; the table is the truth.
        after = c.parse_added_devices(await client.query(7))
        if any(row[3] == expected_id and row[2] == control_type for row in after):
            raise ValueError("the remote is still in the device table after the delete")

        remotes = [
            item for item in entry.options.get("remotes", [])
            if str(item.get("remote_id") or item.get("device_id") or "") != msg["remote_id"]
        ]
        _save_remotes(hass, entry, remotes)
        connection.send_result(msg["id"], {"deleted": msg["remote_id"], "rows": len(after)})
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio delete failed")
        connection.send_error(msg["id"], "remote_delete_failed", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/remote/create",
    vol.Required("entry_id"): str,
    vol.Required("name"): str,
    vol.Optional("device_type"): str,
    vol.Optional("icon"): str,
})
@websocket_api.async_response
async def ws_remote_create(hass, connection, msg):
    """Install a native bridge remote using the credentials already stored for the bridge.

    Only the native kind is offered here: it is the one that needs no extra input beyond a name,
    because the target address and key were captured when the bridge was first set up. IR and HID
    remotes need a catalogue choice or a pairing step and stay in the integration options.
    """
    try:
        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            raise ValueError("Integration not found")
        target = entry.data.get("native_target") or {}
        if not target.get("device_id") or not target.get("target_key"):
            raise ValueError(
                "No native bridge credentials are stored yet. Add the first native remote in the "
                "integration settings; after that this button can reuse them."
            )
        client = _client(hass, entry)
        table = c.parse_added_devices(await client.query(7))
        slot = len(table)
        device_type = str(msg.get("device_type") or target.get("device_type") or "STRIP")
        remote_id = uuid.uuid4().hex[:8]
        stages = c.build_native_bind_sequence(
            key_id=0x01,
            target_key=bytes.fromhex(str(target["target_key"])),
            device_type_name=device_type,
            remote_index=slot,
            name=msg["name"],
            device_id=str(target["device_id"]),
            icon_name=str(msg.get("icon") or target.get("icon") or "strip"),
            control_mode=0,
            event_remote_id=remote_id,
        )
        responses = await client.send_command_sequence(
            tuple(packet for _stage, packet in stages), timeout=35.0, timeout_retries=1,
        )
        for (stage, _), response in zip(stages, responses):
            if not response or response[0] != RESP_OK:
                code = f"0x{response[0]:02X}" if response else "no reply"
                raise ValueError(f"{stage}: {code}")

        remotes = list(entry.options.get("remotes", []))
        remotes.append({
            "index": slot,
            "name": msg["name"],
            "device_type": device_type,
            "icon": str(msg.get("icon") or target.get("icon") or "strip"),
            "device_id": str(target["device_id"]),
            "physical_device_id": str(target["device_id"]),
            "remote_id": remote_id,
            "buttons": [],
        })
        _save_remotes(hass, entry, remotes)
        connection.send_result(msg["id"], {"remote_id": remote_id, "slot": slot})
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio create failed")
        connection.send_error(msg["id"], "remote_create_failed", str(err))


def register(hass) -> None:
    websocket_api.async_register_command(hass, ws_remote_delete)
    websocket_api.async_register_command(hass, ws_remote_create)
