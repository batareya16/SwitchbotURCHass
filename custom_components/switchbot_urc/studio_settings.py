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


def register(hass):
    websocket_api.async_register_command(hass, ws_device_settings)
