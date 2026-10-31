"""The SwitchBot account actions that belong next to the remotes they affect.

Signing in stays in the integration's settings: it takes a password, and Home Assistant's config
flow is the right place to collect one. What Studio needs is everything that happens *after*
sign-in and that people actually hit while editing remotes — seeing whether the account is
reachable, refreshing the saved-remote list that the Add remote dialog reads, and pulling a
fresh communication key when the old one rotates and the remote starts answering with
undecodable responses.
"""
from __future__ import annotations

import logging
from copy import deepcopy

import voluptuous as vol
from homeassistant.components import websocket_api

from .cloud import parse_communication_credentials
from .const import CONF_KEY, CONF_KEY_ID, DOMAIN
from .inventory import cloud_items
from .studio_catalog import cloud_client

_LOGGER = logging.getLogger(__name__)


def _entry(hass, msg):
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        raise ValueError("Integration not found")
    return entry


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/cloud/status",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def ws_cloud_status(hass, connection, msg):
    """What the account is set to, without touching the network."""
    entry = _entry(hass, msg)
    settings = entry.data.get("cloud")
    settings = settings if isinstance(settings, dict) else {}
    cached = [
        item for item in entry.options.get("cloud_remotes", []) if isinstance(item, dict)
    ]
    connection.send_result(msg["id"], {
        # Never send tokens or the key itself to the panel; its id is enough to tell them apart.
        "connected": bool(settings),
        "username": str(settings.get("username", "")),
        "home": str(settings.get("group_id", "")),
        "cached_remotes": len(cached),
        "key_id": str(entry.data.get(CONF_KEY_ID, "")),
    })


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/cloud/refresh",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def ws_cloud_refresh(hass, connection, msg):
    """Re-read the account's remote list, which is what Add remote offers to reinstall."""
    try:
        entry = _entry(hass, msg)
        records = cloud_items(await cloud_client(hass, entry).get_bindable_devices())
        options = deepcopy(dict(entry.options))
        options["cloud_remotes"] = records
        hass.config_entries.async_update_entry(entry, options=options)
        connection.send_result(msg["id"], {"remotes": len(records)})
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio cloud refresh failed")
        connection.send_error(msg["id"], "cloud_refresh_failed", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/cloud/refresh_key",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def ws_cloud_refresh_key(hass, connection, msg):
    """Fetch the rotating WoRWS communication key from the account and reload.

    The remote's key changes on its own, and once it has, every reply decodes to nonsense. The
    account is its source of truth, so there is no reason to make anyone copy it by hand.
    """
    try:
        entry = _entry(hass, msg)
        credentials = parse_communication_credentials(
            await cloud_client(hass, entry).get_communication_key()
        )
        if credentials is None:
            raise ValueError("The account did not return a usable communication key")
        key, key_id = credentials
        if entry.data.get(CONF_KEY) == key.hex() and str(
            entry.data.get(CONF_KEY_ID, "")
        ).upper() == f"{key_id:02X}":
            connection.send_result(msg["id"], {"key_id": f"{key_id:02X}", "changed": False})
            return
        data = dict(entry.data)
        data[CONF_KEY] = key.hex()
        data[CONF_KEY_ID] = f"{key_id:02X}"
        hass.config_entries.async_update_entry(entry, data=data)
        hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
        connection.send_result(msg["id"], {"key_id": f"{key_id:02X}", "changed": True})
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio communication key refresh failed")
        connection.send_error(msg["id"], "cloud_key_failed", str(err))


def register(hass) -> None:
    websocket_api.async_register_command(hass, ws_cloud_status)
    websocket_api.async_register_command(hass, ws_cloud_refresh)
    websocket_api.async_register_command(hass, ws_cloud_refresh_key)
