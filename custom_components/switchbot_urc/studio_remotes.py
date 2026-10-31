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
from . import addressing
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


def _bridges(hass, entry) -> list:
    """What Remote Studio can plan against: one entry per controller, with its real capacity.

    An add-on that reports its capabilities is believed. One that does not is assumed to be the
    single-address BlueZ build, which is what every bridge was before this existed — so an old
    add-on keeps working and is simply described as holding one address.
    """
    reported = hass.data.get(DOMAIN, {}).get("_bridge_capabilities") or {}
    seen: set[str] = set()
    result = []

    def add(address: str, fallback_name: str) -> None:
        compact = addressing.normalise(address)
        if not compact or compact in seen:
            return
        # An address a controller already serves, or could derive, is that controller's
        # capacity — not a second controller. Counting it twice would offer room that the
        # hardware does not have.
        if any(
            compact in {addressing.normalise(item) for item in bridge.serving}
            or compact in {addressing.normalise(item) for item in bridge.candidates()}
            for bridge in result
        ):
            return
        seen.add(compact)
        match = next(
            (value for key, value in reported.items()
             if addressing.normalise(key) == compact), {})
        result.append(addressing.Bridge(
            adapter=str(match.get("adapter") or fallback_name or "bridge"),
            address=addressing.format_address(compact),
            advertising_sets=int(match.get("advertising_sets") or 1),
            serving=[str(item) for item in match.get("serving") or [addressing.format_address(compact)]],
            extended_advertising=bool(match.get("extended_advertising", False)),
        ))

    # Controllers the add-on announced come first: they carry the capacity figures.
    for key, value in reported.items():
        add(key, str(value.get("adapter") or ""))
    # Then any bridge the integration stored that no add-on has announced — an adapter whose
    # add-on is stopped still holds the tiles bound to it.
    for item in targets.all_targets(entry):
        add(str(item.get("device_id", "")), str(item.get("name") or ""))
    return result


def _next_address(bridges, used) -> str:
    """The address Add remote would take, or empty when there is none.

    Suggesting an address is a convenience, so a failure here must not take the whole dialog
    down with it — without this the Add remote form would simply not open.
    """
    try:
        return addressing.allocate(bridges, used)[0].address
    except ValueError:
        return ""


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
    """Remove one remote from the device and from the integration's own list."""
    try:
        entry, remote = resolve(hass, msg)
        client = _client(hass, entry)
        table = c.parse_added_devices(await client.query(7))
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

        after = c.parse_added_devices(await client.query(7))
        if _count(after) >= _count(table):
            raise ValueError("the remote is still in the device table after the delete")

        # Deleting a native row clears the target key, which is held per six-byte address and
        # not per profile, so any sibling profile on that address loses its key here.
        key_restored = False
        if control_type == c.CTRL_NATIVE:
            key_restored = await install.reassociate_shared_target(
                client, bound_address) is not None

        dropped = _forget_remote(hass, entry, msg["remote_id"])
        connection.send_result(msg["id"], {
            "bindings_removed": dropped,
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
    vol.Optional("new_target_address"): str,
    vol.Optional("target_key"): str,
    vol.Optional("auto_address", default=False): bool,
})
@websocket_api.async_response
async def ws_remote_create(hass, connection, msg):
    """Install a native bridge remote, on a stored bridge address or a new one.

    A native tile connects to one fixed BLE address and the firmware keeps the target key per
    address, so a second tile needs a second address. `new_target_address` binds to one the
    integration has not seen before, reusing the key already stored for the first bridge — the
    add-on serves every address in its `addresses` option from the same controller, so the new
    address has to be listed there too.
    """
    try:
        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            raise ValueError("Integration not found")
        known = targets.all_targets(entry)
        new_address = str(msg.get("new_target_address") or "").strip()
        if msg.get("auto_address") and not new_address:
            # Pick the next free address across every controller, so nobody has to know what a
            # static random address is or which adapter still has room.
            chosen = allocate_address(hass, entry)
            new_address = chosen.address
            _LOGGER.info("allocated %s on %s for the new native remote",
                         chosen.address, chosen.bridge.adapter)
        if new_address:
            compact = new_address.replace(":", "").replace("-", "")
            if len(compact) != 12 or any(ch not in "0123456789abcdefABCDEF" for ch in compact):
                raise ValueError("A bridge address is six hex bytes, like DA:71:16:E0:1F:92")
            source = known[0] if known else {}
            if not source.get("target_key"):
                raise ValueError(
                    "No bridge key is stored yet, so there is nothing to reuse for a new "
                    "address. Add the first native remote in the integration settings."
                )
            # A new address defaults to the first bridge's key: the add-on serves every address
            # from one controller with one DEVICE_KEY, so a different key would simply fail to
            # decrypt. It stays editable because a second controller is also a valid setup.
            target = dict(source) | {"device_id": new_address, "name": msg["name"]}
            is_new = True
        else:
            wanted = str(msg.get("target_id") or "").replace(":", "").lower()
            target = next(
                (item for item in known
                 if str(item.get("device_id", "")).replace(":", "").lower() == wanted),
                known[0] if known else {},
            )
            if wanted and str(target.get("device_id", "")).replace(":", "").lower() != wanted:
                raise ValueError("That bridge is not known to this integration")
            is_new = False
        supplied_key = str(msg.get("target_key") or "").strip().replace(" ", "")
        if supplied_key:
            try:
                if len(bytes.fromhex(supplied_key)) != 16:
                    raise ValueError
            except ValueError:
                raise ValueError(
                    "The AES key must be exactly 32 hexadecimal characters"
                ) from None
            target = dict(target) | {"target_key": supplied_key}
        if not target.get("device_id") or not target.get("target_key"):
            raise ValueError(
                "No native bridge credentials are stored yet. Add the first native remote in the "
                "integration settings; after that this button can reuse them."
            )
        client = _client(hass, entry)
        table = c.parse_added_devices(await client.query(7))
        # One address holds one native tile: the firmware keys the target key on the address,
        # and binding a second tile to it is refused outright with 0x02.
        if any(row[2] == c.CTRL_NATIVE
               and row[3][:6] == c.id_to_bytes(str(target["device_id"]))[:6]
               for row in table):
            raise ValueError(
                f"{target['device_id']} already carries a native tile, and the firmware keys the "
                "target key on the address, so it cannot hold a second one. Give this remote a "
                "new address instead, and add that address to the add-on's `addresses` option — "
                "one Bluetooth 5 controller can serve several."
            )
        slot = len(table)
        device_type = str(msg.get("device_type") or target.get("device_type") or "STRIP")
        remote_id = new_remote_id(entry)
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
        await install.bind_native_once(client, stages, device_id=str(target["device_id"]))

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
        served = ""
        if is_new:
            served = await ask_bridge_to_serve(hass, entry, str(target["device_id"]))
        if is_new or supplied_key:
            # Only record the bridge once the remote is actually bound to it, so a failed
            # attempt does not leave an address the integration thinks it can use.
            targets.remember_target(hass, entry, {
                "name": msg["name"],
                "device_id": str(target["device_id"]),
                "device_type": device_type,
                "icon": str(msg.get("icon") or target.get("icon") or "strip"),
                "control_mode": 0,
                "target_key_id": str(target.get("target_key_id", "01")),
                "target_key": str(target["target_key"]),
            })
        connection.send_result(msg["id"], {
            "remote_id": remote_id, "slot": slot,
            "bridge": str(target["device_id"]), "new_bridge": is_new,
            "warning": served,
        })
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


def allocate_address(hass, entry, release: str = ""):
    """The next free address across every controller, as an `addressing.Allocation`.

    `release` is the address a remote is moving off: it stops counting as used, so a tile on a
    full controller can still be moved somewhere else.
    """
    used = _used_addresses(entry)
    if release:
        used = addressing.without(used, release)
    return addressing.allocate(_bridges(hass, entry), used)[0]


async def ask_bridge_to_serve(hass, entry, address: str) -> str:
    """Tell the add-on to advertise a newly bound address, and say so if it could not.

    Binding a tile writes the address into the remote; nothing answers on it until the add-on
    advertises it. Doing this automatically is the difference between a working remote and one
    that silently does nothing, so a failure is reported rather than swallowed — but it is a
    warning, not an error: the tile is already bound, and the add-on's `addresses` option is
    still a way to fix it by hand.
    """
    from . import async_bridge_control

    compact = addressing.normalise(address)
    owner = next(
        (bridge for bridge in _bridges(hass, entry)
         if addressing._belongs_to(bridge, address)), None)
    if owner is None:
        # The list sent to a bridge replaces everything it serves, so sending one that does not
        # describe a real controller would stop every other tile from being answered. Refusing
        # is the safe half: the tile is bound, and the add-on's own option still works.
        return (
            f"The remote is bound to {address}, but no known controller serves it. Add the "
            "address to the add-on's `addresses` option, or move the remote to an address one "
            "of the known controllers can carry."
        )
    # Always a superset of what it already serves: this list replaces the bridge's own.
    wanted = [addressing.format_address(addressing.normalise(item))
              for item in owner.serving] or [owner.address]
    if not any(addressing.normalise(item) == compact for item in wanted):
        wanted.append(addressing.format_address(compact))
    try:
        ok = await async_bridge_control(hass, "addresses", {
            "addresses": wanted,
            # One control topic serves every add-on instance, so each must be able to tell
            # whether a request is meant for its own controller.
            "adapter_address": owner.address,
        })
    except Exception as err:  # noqa: BLE001 - the tile is bound either way
        _LOGGER.warning("could not ask the add-on to serve %s: %s", address, err)
        ok = False
    if ok:
        return ""
    return (
        f"The remote is bound to {address}, but the add-on did not confirm it is advertising "
        "it. Check the add-on log, or add the address to its `addresses` option."
    )


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
    bridges = _bridges(hass, entry)
    used = _used_addresses(entry)
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
        # The same choices the options flow's bind_native step offers. The key is prefilled as
        # it is there: this command is admin-only, and binding a bridge without seeing which key
        # it will carry is how mismatched keys happen.
        "native_options": {
            "capacity": addressing.capacity(bridges),
            "free": addressing.free_slots(bridges, used),
            "summary": addressing.describe(bridges, used),
            "controllers": [
                {"adapter": bridge.adapter, "address": bridge.address,
                 "capacity": bridge.capacity,
                 "used": sum(1 for item in used if addressing._belongs_to(bridge, item)),
                 # What the add-on reports it is advertising right now. The add-on's own
                 # `addresses` option is only the seed: Studio adds to it at run time, so this
                 # is the one place that tells the truth about what is reachable.
                 "serving": list(bridge.serving),
                 "extended_advertising": bridge.extended_advertising}
                for bridge in bridges
            ],
            "next_address": _next_address(bridges, used),
            "device_types": list(c.SUPPORTED_NATIVE_DEVICE_TYPES),
            "icons": list(ICONS),
            "default_key": str((known[0] if known else {}).get("target_key", "")),
            "default_device_type": str((known[0] if known else {}).get("device_type", "STRIP")),
            "default_icon": str((known[0] if known else {}).get("icon", "strip")),
        },
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
