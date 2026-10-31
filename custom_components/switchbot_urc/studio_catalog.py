"""Browse the bundled IR catalog from Remote Studio and pull one button's code out of it.

The options flow installs a whole catalog remote. Studio needs the opposite granularity: the
code for a single key, so a mixed profile can borrow Power from one TV and Mute from another.
Both paths read the same local metadata catalog and ask the cloud for the same code bank; only
the last step differs, where this module keeps the bank's per-key slices instead of installing
them. Banks are cached per hxd_index for the lifetime of the entry, because picking several
buttons off one model is the normal case and each download is a cloud round trip.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import ir_catalog
from .cloud import SwitchBotCloudClient
from .cloud_ir import find_cloud_items, generate_remote_id, profile_from_cloud
from .commands import custom_action_name
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CACHE_KEY = "studio_catalog_banks"


def _entry(hass, msg):
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        raise ValueError("Integration not found")
    return entry


def cloud_client(hass, entry) -> SwitchBotCloudClient:
    settings = entry.data.get("cloud")
    if not isinstance(settings, dict) or not settings:
        raise ValueError(
            "Catalog codes are downloaded from the SwitchBot cloud. Connect a SwitchBot "
            "account in the integration settings first."
        )

    async def _save_tokens(access_token: str, refresh_token: str) -> None:
        data = dict(entry.data)
        cloud = dict(data.get("cloud", {}))
        cloud["access_token"] = access_token
        cloud["refresh_token"] = refresh_token
        data["cloud"] = cloud
        hass.config_entries.async_update_entry(entry, data=data)

    return SwitchBotCloudClient(async_get_clientsession(hass), dict(settings), _save_tokens)


def _button_label(key_fun: int) -> str:
    """Turn a keyFun into something readable without hiding the ones we have no name for."""
    name = custom_action_name(int(key_fun))
    if name.startswith("FUNCTION_"):
        return f"Function {name.removeprefix('FUNCTION_')}"
    return name.replace("_", " ").capitalize()


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/studio/catalog/types"})
@websocket_api.async_response
async def ws_catalog_types(hass, connection, msg):
    available = await hass.async_add_executor_job(ir_catalog.available)
    connection.send_result(msg["id"], {
        "available": available,
        "types": [{"value": value, "label": label}
                  for value, label in sorted(ir_catalog.REMOTE_TYPES.items(), key=lambda i: i[1])],
    })


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/catalog/brands",
    vol.Required("remote_type"): int,
})
@websocket_api.async_response
async def ws_catalog_brands(hass, connection, msg):
    brands = await hass.async_add_executor_job(ir_catalog.brands, msg["remote_type"])
    connection.send_result(msg["id"], {"brands": brands})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/catalog/models",
    vol.Required("remote_type"): int,
    vol.Required("brand"): str,
})
@websocket_api.async_response
async def ws_catalog_models(hass, connection, msg):
    models = await hass.async_add_executor_job(
        ir_catalog.profiles, msg["remote_type"], msg["brand"]
    )
    connection.send_result(msg["id"], {"models": [
        {
            "hxd_index": item.hxd_index,
            "label": f"{item.model} — {item.hxd_index}" if item.model != "no_model"
                     else f"{item.brand} — {item.hxd_index}",
        }
        for item in models
    ]})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/catalog/buttons",
    vol.Required("entry_id"): str,
    vol.Required("hxd_index"): str,
    vol.Required("remote_type"): int,
})
@websocket_api.async_response
async def ws_catalog_buttons(hass, connection, msg):
    """Download one catalog model's code bank and return its keys as ready-to-use codes."""
    try:
        entry = _entry(hass, msg)
        cache: dict[str, Any] = hass.data.setdefault(DOMAIN, {}).setdefault(CACHE_KEY, {})
        hxd_index = str(msg["hxd_index"])
        if hxd_index not in cache:
            payload = await cloud_client(hass, entry).get_ir_model(hxd_index)
            downloaded = find_cloud_items(payload)
            item = next(
                (row for row in downloaded
                 if str(row.get("itemID", row.get("hxdIndex", ""))) == hxd_index),
                downloaded[0] if downloaded else None,
            )
            if item is None:
                raise ValueError("The cloud returned no code bank for this model")
            profile = profile_from_cloud(
                item,
                remote_id=generate_remote_id(),
                name="catalog",
                remote_type=int(msg["remote_type"]),
            )
            bank = profile.code_bank
            cache[hxd_index] = [
                {"label": _button_label(key_fun), "code_hex": bank[start:start + length].hex()}
                for key_fun, start, length in profile.key_map
                if length and start + length <= len(bank)
            ]
        connection.send_result(msg["id"], {"buttons": cache[hxd_index]})
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio catalog lookup failed")
        connection.send_error(msg["id"], "catalog_lookup_failed", str(err))


def register(hass) -> None:
    websocket_api.async_register_command(hass, ws_catalog_types)
    websocket_api.async_register_command(hass, ws_catalog_brands)
    websocket_api.async_register_command(hass, ws_catalog_models)
    websocket_api.async_register_command(hass, ws_catalog_buttons)
