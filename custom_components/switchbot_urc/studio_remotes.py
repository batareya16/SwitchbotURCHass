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

from dataclasses import asdict

from . import commands as c
from . import install
from . import ir_catalog
from . import targets
from .catalog import DEFAULT_BUTTONS, DEVICE_TYPES, ICONS, buttons_for
from .cloud import CloudError
from .cloud_ir import find_cloud_items, generate_remote_id, profile_from_cloud
from .const import DOMAIN, RESP_OK
from .inventory import stable_id_for_local
from .ir_profiles import PROFILES
from .studio_catalog import cloud_client
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
        if not matches:
            # Nothing to delete on the device — it was removed elsewhere, or the remote was
            # factory reset. Dropping the local record is then the whole job, and refusing
            # would leave Studio showing a remote that does not exist.
            remotes = [
                item for item in entry.options.get("remotes", [])
                if str(item.get("remote_id") or item.get("device_id") or "") != msg["remote_id"]
            ]
            _save_remotes(hass, entry, remotes)
            connection.send_result(msg["id"], {
                "deleted": msg["remote_id"], "rows": len(table), "device_untouched": True,
            })
            return
        if len(matches) != 1:
            raise ValueError(
                f"{len(matches)} rows in the device table carry this id; refresh first"
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

        # A lost acknowledgement is not a failure on its own; the table is the truth. Several
        # native profiles on one address share an id, so count the matching rows rather than
        # asking whether the id is still present — it legitimately is, for the survivors.
        def _count(rows) -> int:
            return sum(1 for row in rows if row[3] == expected_id and row[2] == control_type)

        after = c.parse_added_devices(await client.query(7))
        if _count(after) >= _count(table):
            raise ValueError("the remote is still in the device table after the delete")

        # Deleting a native row clears the target key, which is held per six-byte address and
        # not per profile, so any sibling profile on that address loses its key here.
        key_restored = False
        if control_type == c.CTRL_NATIVE:
            key_restored = await install.reassociate_shared_target(
                client, str(remote["device_id"])) is not None

        remotes = [
            item for item in entry.options.get("remotes", [])
            if str(item.get("remote_id") or item.get("device_id") or "") != msg["remote_id"]
        ]
        _save_remotes(hass, entry, remotes)
        connection.send_result(msg["id"], {
            "deleted": msg["remote_id"], "rows": len(after), "key_restored": key_restored,
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
    vol.Optional("icon"): str,
    vol.Optional("target_id"): str,
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
        known = targets.all_targets(entry)
        wanted = str(msg.get("target_id") or "").replace(":", "").lower()
        target = next(
            (item for item in known
             if str(item.get("device_id", "")).replace(":", "").lower() == wanted),
            known[0] if known else {},
        )
        if not target.get("device_id") or not target.get("target_key"):
            raise ValueError(
                "No native bridge credentials are stored yet. Add the first native remote in the "
                "integration settings; after that this button can reuse them."
            )
        if wanted and str(target["device_id"]).replace(":", "").lower() != wanted:
            raise ValueError("That bridge is not known to this integration")
        client = _client(hass, entry)
        table = c.parse_added_devices(await client.query(7))
        # One address holds one native tile: the firmware keys the target key on the address,
        # and binding a second tile to it is refused outright with 0x02.
        if any(row[2] == c.CTRL_NATIVE
               and row[3][:6] == c.id_to_bytes(str(target["device_id"]))[:6]
               for row in table):
            raise ValueError(
                f"{target['device_id']} already carries a native tile. Each native remote needs "
                "its own Bluetooth adapter running its own bridge."
            )
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


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/remote/install_ir",
    vol.Required("entry_id"): str,
    vol.Required("source"): vol.In(("catalog", "cloud", "profile")),
    vol.Required("name"): str,
    vol.Optional("hxd_index"): str,
    vol.Optional("remote_type"): int,
    vol.Optional("remote_id"): str,
    vol.Optional("profile_key"): str,
    vol.Optional("replace_existing", default=False): bool,
})
@websocket_api.async_response
async def ws_remote_install_ir(hass, connection, msg):
    """Install a whole IR remote, from the catalog, the account, or a bundled profile.

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

        if source == "profile":
            key = msg.get("profile_key") or next(iter(PROFILES))
            if key not in PROFILES:
                raise ValueError(f"Unknown bundled profile {key!r}")
            profile = PROFILES[key]
        elif source == "catalog":
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
        )
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


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/remote/sources",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def ws_remote_sources(hass, connection, msg):
    """What the panel may offer on its Add remote dialog, for this installation."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Integration not found")
        return
    known = targets.all_targets(entry)
    connection.send_result(msg["id"], {
        "native": any(item.get("device_id") and item.get("target_key") for item in known),
        "bridges": [
            {"target_id": str(item["device_id"]), "name": str(item.get("name") or item["device_id"])}
            for item in known if item.get("target_key")
        ],
        "catalog": await hass.async_add_executor_job(ir_catalog.available),
        "cloud": bool(entry.data.get("cloud")),
        "cloud_remotes": [
            {"remote_id": str(item["remoteID"]),
             "name": str(item.get("remoteName") or item["remoteID"])}
            for item in entry.options.get("cloud_remotes", [])
            if isinstance(item, dict) and item.get("remoteID")
        ],
        "profiles": [{"key": key, "label": getattr(value, "title", key)}
                     for key, value in PROFILES.items()],
        # HID remotes need a paired host before the firmware accepts them, so the panel is
        # told the current pairing as well as the choices.
        "hid": {
            "host_mac": str(entry.options.get("host_mac", "")),
            "device_types": list(DEVICE_TYPES),
            "icons": list(ICONS),
            "buttons": buttons_for(DEVICE_TYPES[0]),
            "default_buttons": list(DEFAULT_BUTTONS),
        },
    })


def register(hass) -> None:
    websocket_api.async_register_command(hass, ws_remote_delete)
    websocket_api.async_register_command(hass, ws_remote_create)
    websocket_api.async_register_command(hass, ws_remote_install_ir)
    websocket_api.async_register_command(hass, ws_remote_sources)
