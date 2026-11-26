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
from dataclasses import asdict

import voluptuous as vol
from homeassistant.components import websocket_api

from . import cloud_sync
from .cloud import parse_communication_credentials
from .const import CONF_KEY, CONF_KEY_ID, DOMAIN
from .cloud_ir import account_ir_codes, find_cloud_items
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
    try:
        entry = _entry(hass, msg)
    except ValueError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
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


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/cloud/ir_codes",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def ws_cloud_ir_codes(hass, connection, msg):
    """The keys of every IR remote in the account, for "Copy from a button"."""
    try:
        entry = _entry(hass, msg)
        if not entry.data.get("cloud"):
            connection.send_result(msg["id"], {"codes": [], "connected": False})
            return
        records = [item for item in entry.options.get("cloud_remotes", [])
                   if isinstance(item, dict) and item.get("remoteID")]
        names = {str(item["remoteID"]): str(item.get("remoteName") or item["remoteID"])
                 for item in records}
        groups: dict[str, list[str]] = {}
        for item in records:
            groups.setdefault(str(item.get("createFrom") or "hub"), []).append(str(item["remoteID"]))
        client = cloud_client(hass, entry)
        codes = []
        for created_from, ids in groups.items():
            for downloaded in find_cloud_items(await client.get_ir_remotes(ids, created_from)):
                remote_id = str(downloaded.get("remoteID", ""))
                codes.extend(account_ir_codes(
                    downloaded, names.get(remote_id) or str(downloaded.get("remoteName") or "Remote")))
        connection.send_result(msg["id"], {"codes": codes, "connected": True})
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio account IR codes failed")
        connection.send_error(msg["id"], "cloud_codes_failed", str(err))


async def _sync_inputs(hass, entry):
    """The remote's table and scenes, and the account's bound list, read together."""
    from . import studio_physical, studio_scenes
    from .studio_remotes import _client, remote_management_lock

    client = _client(hass, entry)
    async with remote_management_lock(hass):
        table = await studio_physical.read_device_table(hass, entry, client)
        scenes = [asdict(scene) for scene in (await studio_scenes._read(client)).values()]
    cloud = cloud_client(hass, entry)
    payload = await cloud.get_bindable_devices()
    bound = [item for item in (payload or {}).get("bindDevices", []) if isinstance(item, dict)]
    known = {str(item["remoteID"]) for key in ("bindDevices", "remotes")
             for item in (payload or {}).get(key, []) if isinstance(item, dict) and item.get("remoteID")}
    return cloud, table, scenes, bound, known, payload


def _account_ir_remotes(payload) -> list[dict]:
    """Every IR remote the account holds: those bound to this Universal Remote and the rest."""
    return [item for key in ("bindDevices", "remotes") for item in (payload or {}).get(key, [])
            if isinstance(item, dict) and item.get("remoteID")]


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/cloud/sync_status",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def ws_cloud_sync_status(hass, connection, msg):
    """What the SwitchBot app would report as different between the account and the remote."""
    try:
        entry = _entry(hass, msg)
        if not entry.data.get("cloud"):
            raise ValueError("Connect the SwitchBot account first")
        _cloud, table, scenes, bound, known, payload = await _sync_inputs(hass, entry)
        steps = cloud_sync.plan(table, entry.options.get("remotes", []), bound, known, scenes)
        connection.send_result(msg["id"], {
            "differences": cloud_sync.differences(bound, table, scenes),
            "plan": cloud_sync.preview(steps, _account_ir_remotes(payload), table, bound),
        })
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio sync check failed")
        connection.send_error(msg["id"], "cloud_sync_check_failed", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/cloud/sync",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def ws_cloud_sync(hass, connection, msg):
    """List exactly what is on the remote as this Universal Remote's remotes in the account."""
    try:
        entry = _entry(hass, msg)
        if not entry.data.get("cloud"):
            raise ValueError("Connect the SwitchBot account first")
        cloud, table, scenes, bound, known, payload = await _sync_inputs(hass, entry)
        steps = cloud_sync.plan(table, entry.options.get("remotes", []), bound, known, scenes)
        # A remote installed from the account under a new id gets a copy of every button of its
        # source; the source itself is never changed or deleted (only no longer listed here).
        copied = []
        for index, create in enumerate(steps["create"]):
            source = cloud_sync.account_source(create, _account_ir_remotes(payload), table)
            if source is None:
                continue
            downloaded = find_cloud_items(await cloud.get_ir_remote(
                str(source["remoteID"]), str(source.get("createFrom") or "hub")))
            if not downloaded:
                raise ValueError(f"Your account returned no buttons for {source.get('remoteName')}; "
                                 "nothing was changed")
            steps["create"][index] = cloud_sync.with_source_keys(create, {**source, **downloaded[0]})
            copied.append(str(create["remoteName"]))
        if steps["create"]:
            await cloud.create_ir_remotes(steps["create"])
        if steps["remove"]:
            await cloud.delete_bind_devices(steps["remove"])
        if steps["items"]:
            await cloud.update_bind_devices(steps["items"])
        after = await cloud.get_bindable_devices()
        bound_after = [item for item in (after or {}).get("bindDevices", []) if isinstance(item, dict)]
        options = deepcopy(dict(entry.options))
        options["cloud_remotes"] = cloud_items(after)
        hass.config_entries.async_update_entry(entry, options=options)
        connection.send_result(msg["id"], {
            "created": len(steps["create"]), "removed": len(steps["remove"]), "copied": copied,
            "listed": len(steps["items"]), "skipped": steps["skipped"],
            "differences": cloud_sync.differences(bound_after, table, scenes),
        })
    except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
        _LOGGER.exception("Remote Studio account sync failed")
        connection.send_error(msg["id"], "cloud_sync_failed", str(err))


def register(hass) -> None:
    websocket_api.async_register_command(hass, ws_cloud_sync_status)
    websocket_api.async_register_command(hass, ws_cloud_sync)
    websocket_api.async_register_command(hass, ws_cloud_ir_codes)
    websocket_api.async_register_command(hass, ws_cloud_status)
    websocket_api.async_register_command(hass, ws_cloud_refresh)
    websocket_api.async_register_command(hass, ws_cloud_refresh_key)
