"""Read and update physical remote settings from Remote Studio."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.components import websocket_api

from . import device_settings
from .const import DOMAIN
from .studio_remotes import remote_management_lock

_LOGGER = logging.getLogger(__name__)
_CHANGES = vol.Schema({
    vol.Optional(field): bool if field in device_settings.BOOLEAN_SETTINGS else int
    for field in device_settings.SETTING_OFFSETS
})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/device_settings",
    vol.Required("entry_id"): str,
    vol.Optional("changes"): _CHANGES,
})
@websocket_api.async_response
async def ws_device_settings(hass, connection, msg):
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    runtime = hass.data.get(DOMAIN, {}).get(msg["entry_id"], {})
    if entry is None or entry.domain != DOMAIN or "client" not in runtime:
        connection.send_error(msg["id"], "not_found", "Universal Remote is unavailable")
        return
    try:
        async with remote_management_lock(hass):
            if "changes" in msg:
                values = await device_settings.apply_settings(runtime["client"], msg["changes"])
            else:
                values = await device_settings.read_settings(runtime["client"])
        device_settings.remember_firmware(hass, entry, values.get("firmware_version"))
    except device_settings.SettingsVerificationError as err:
        connection.send_error(msg["id"], "settings_unverified", str(err))
        return
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_settings", str(err))
        return
    except Exception:
        _LOGGER.exception("Could not read or save physical remote settings from Remote Studio")
        connection.send_error(msg["id"], "settings_failed",
                              "Could not read or save the remote settings. Wake the remote and try again.")
        return
    connection.send_result(msg["id"], {"settings": values})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/firmware_read",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def ws_firmware_read(hass, connection, msg):
    """Read the remote's firmware version and keep it (the panel asks in the background)."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    runtime = hass.data.get(DOMAIN, {}).get(msg["entry_id"], {})
    if entry is None or entry.domain != DOMAIN or "client" not in runtime:
        connection.send_error(msg["id"], "not_found", "Universal Remote is unavailable")
        return
    async with remote_management_lock(hass):
        version = await device_settings.read_firmware(hass, entry, runtime["client"])
    connection.send_result(msg["id"], {"firmware_version": version})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/firmware_check",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def ws_firmware_check(hass, connection, msg):
    """The remote's firmware version, read from it, and what the SwitchBot account offers."""
    from .studio_catalog import cloud_client

    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    runtime = hass.data.get(DOMAIN, {}).get(msg["entry_id"], {})
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Universal Remote is unavailable")
        return
    current = entry.data.get(device_settings.FIRMWARE_KEY)
    if "client" in runtime:
        async with remote_management_lock(hass):
            current = await device_settings.read_firmware(hass, entry, runtime["client"])
    result = {"current": current, "latest": None, "required": None, "error": ""}
    if not current:
        result["error"] = "The remote did not report its firmware version. Wake it and try again."
    elif not entry.data.get("cloud"):
        result["error"] = "Connect the SwitchBot account to check for updates."
    else:
        try:
            found = await cloud_client(hass, entry).firmware_versions(current)
        except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
            _LOGGER.warning("Firmware check failed: %s", err)
            result["error"] = f"Could not check for updates: {err}"
        else:
            result.update(latest=found["latest"], required=found["required"])
            if found["latest"] is None and found["required"] is None and found["errors"]:
                result["error"] = "Could not check for updates: " + "; ".join(found["errors"])
    connection.send_result(msg["id"], result)


def register(hass):
    websocket_api.async_register_command(hass, ws_device_settings)
    websocket_api.async_register_command(hass, ws_firmware_check)
    websocket_api.async_register_command(hass, ws_firmware_read)
