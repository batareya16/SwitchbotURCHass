"""Manage the separate scene list and receive WoRWS scene activations."""
from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import asdict

import voluptuous as vol
from homeassistant.components import bluetooth, websocket_api
from homeassistant.core import callback
from homeassistant.helpers.script import Script, async_validate_actions_config

from .const import CONF_ADDRESS, DOMAIN
from .matter_text import COMPANY_ID
from .scenes import (
    SCENE_LIMIT,
    SCENE_LIST_QUERY,
    Scene,
    ScenePressTracker,
    build_scene_list,
    parse_scene_list,
)
from .studio_remotes import remote_management_lock

_LOGGER = logging.getLogger(__name__)
SCENE_BINDINGS = "scene_bindings"
_SCENE_FIELDS = {
    vol.Required("index"): vol.All(int, vol.Range(min=0, max=SCENE_LIMIT - 1)),
    vol.Required("name"): str,
    vol.Required("icon"): vol.All(int, vol.Range(min=0, max=255)),
    vol.Required("color"): vol.All(int, vol.Range(min=0, max=255)),
}


def _entry_and_runtime(hass, connection, msg):
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    runtime = hass.data[DOMAIN].get(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN or not runtime or "client" not in runtime:
        connection.send_error(msg["id"], "not_found", "Universal Remote is unavailable")
        return None, None
    return entry, runtime


def _reconcile_bindings(entry, scenes):
    return {
        str(index): binding
        for index, scene in scenes.items()
        if (binding := entry.options.get(SCENE_BINDINGS, {}).get(str(index)))
        and binding.get("scene") == asdict(scene)
    }


def _store_bindings(hass, entry, bindings):
    if entry.options.get(SCENE_BINDINGS, {}) != bindings:
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, SCENE_BINDINGS: bindings}
        )


def _binding_actions(binding):
    if "actions" in binding:
        return deepcopy(binding["actions"])
    entity_id = binding.get("entity_id", "")
    if entity_id.startswith(("scene.", "script.")):
        return [{"action": f"{entity_id.split('.', 1)[0]}.turn_on",
                 "target": {"entity_id": entity_id}}]
    return []


def _result(scenes, bindings):
    return {
        "limit": SCENE_LIMIT,
        "scenes": [
            {**asdict(scene), "entity_id": bindings.get(str(index), {}).get("entity_id", ""),
             "actions": _binding_actions(bindings.get(str(index), {}))}
            for index, scene in sorted(scenes.items())
        ],
    }


async def _read(client):
    return parse_scene_list(await client.query(SCENE_LIST_QUERY))


async def refresh_scenes(hass, entry):
    """Read scenes as part of Studio's shared remote inventory."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    if "client" not in runtime:
        return
    async with remote_management_lock(hass):
        scenes = await _read(runtime["client"])
        bindings = _reconcile_bindings(entry, scenes)
        _store_bindings(hass, entry, bindings)
        runtime["studio_scenes"] = _result(scenes, bindings)
        runtime.pop("studio_scenes_error", None)
        runtime["scene_write_unverified"] = False


def serialized_remotes(hass, entry):
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    cached = runtime.get("studio_scenes", {})
    return [{
        **row, "remote_id": f"scene:{row['index']}", "kind": "scene",
        "device_type": "Scene", "scene_index": row["index"], "layout_editable": True,
        "can_move": False, "can_test_native_icon": False, "pages": [],
    } for row in cached.get("scenes", [])]


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/scenes/save",
    vol.Required("entry_id"): str,
    vol.Required("expected"): [_SCENE_FIELDS],
    vol.Optional("index"): vol.All(int, vol.Range(min=0, max=SCENE_LIMIT - 1)),
    vol.Optional("name"): str,
    vol.Optional("icon"): vol.All(int, vol.Range(min=0, max=255)),
    vol.Optional("color"): vol.All(int, vol.Range(min=0, max=255)),
    vol.Optional("entity_id", default=""): str,
    vol.Optional("actions"): list,
    vol.Optional("delete", default=False): bool,
})
@websocket_api.async_response
async def ws_save_scene(hass, connection, msg):
    entry, runtime = _entry_and_runtime(hass, connection, msg)
    if entry is None:
        return
    client = runtime["client"]
    try:
        async with remote_management_lock(hass):
            current = await _read(client)
            expected = {row["index"]: Scene(**row) for row in msg["expected"]}
            bindings = _reconcile_bindings(entry, current)
            if current != expected:
                _store_bindings(hass, entry, bindings)
                runtime["scene_write_unverified"] = False
                raise ValueError("The scene list changed on the remote. Refresh it first.")
            target = dict(current)
            index = msg.get("index")
            if index is not None and index not in target:
                raise ValueError("The scene is no longer on the remote")
            if msg["delete"]:
                if index is None:
                    raise ValueError("Choose a scene to delete")
                del target[index]
                bindings.pop(str(index), None)
            else:
                if index is None:
                    index = next((i for i in range(SCENE_LIMIT) if i not in target), None)
                    if index is None:
                        raise ValueError("The remote already has ten scenes")
                entity_id = msg["entity_id"]
                if entity_id and (
                    not entity_id.startswith(("scene.", "script.")) or not hass.states.get(entity_id)
                ):
                    raise ValueError("Choose a Home Assistant scene or script")
                actions = deepcopy(msg.get("actions", _binding_actions({"entity_id": entity_id})))
                if actions:
                    await async_validate_actions_config(hass, deepcopy(actions))
                scene = Scene(index, msg["name"].strip(), msg["icon"], msg["color"])
                installed = current.get(index)
                if scene.icon > 24 and (installed is None or scene.icon != installed.icon):
                    raise ValueError("Choose a supported scene icon")
                if scene.color > 7 and (installed is None or scene.color != installed.color):
                    raise ValueError("Choose a supported scene background")
                scene.encode()
                target[index] = scene
                bindings.pop(str(index), None)
                if actions:
                    bindings[str(index)] = {"scene": asdict(scene), "actions": actions}
            moved = {}
            if sorted(target) != list(range(len(target))):
                moved = {str(old): new for new, old in enumerate(sorted(target)) if old != new}
                # The remote draws its scenes by number, so the numbers must run 0, 1, 2… without
                # a gap (a gap shows as an empty tile, the scene after it is not drawn); as the app
                # does after a delete, the scenes are numbered again and their actions move along.
                target, bindings = reorder_scenes(target, bindings, sorted(target))
            if target != current:
                await _write_scene_list(client, runtime, current, target)
            _store_bindings(hass, entry, bindings)
            runtime["scene_write_unverified"] = False
            runtime["studio_scenes"] = _result(target, bindings)
            runtime.pop("studio_scenes_error", None)
    except Exception as err:
        _LOGGER.debug("Remote Studio scene save failed", exc_info=True)
        connection.send_error(msg["id"], "scene_save_failed", str(err))
        return
    connection.send_result(msg["id"], {**_result(target, bindings), "moved": moved})


async def _write_scene_list(client, runtime, current, target):
    """Write the whole scene list and read it back; refuse anything but exactly `target`."""
    packet = build_scene_list(list(target.values()))
    runtime["scene_write_unverified"] = True
    response = b""
    actual = None
    try:
        replies = await client.send_command_sequence([packet], readback_subcommand=SCENE_LIST_QUERY)
        if replies:
            response = replies[0]
        if len(replies) == 2:
            actual = parse_scene_list(replies[1])
    except Exception:
        _LOGGER.debug("Scene transaction returned no usable readback", exc_info=True)
    if actual is None:
        actual = await _read(client)
    if actual != target:
        runtime["scene_write_unverified"] = actual != current
        detail = f" (response {response.hex()})" if response else ""
        raise ValueError(f"The remote did not save the requested scene list{detail}")


def reorder_scenes(current, bindings, order):
    """The scene list in a new order, and the Home Assistant actions that follow their scenes.

    The remote shows its scenes by number, after all the remotes; there is no command to move one,
    so the list is written again with the scenes numbered 0, 1, 2… in the new order. A press
    announces the number, so each scene's actions move to its new number with it.
    """
    if sorted(order) != sorted(current) or len(set(order)) != len(order):
        raise ValueError("The new order must list every scene exactly once")
    target, moved = {}, {}
    for new_index, old_index in enumerate(order):
        old = current[old_index]
        scene = Scene(new_index, old.name, old.icon, old.color)
        target[new_index] = scene
        binding = bindings.get(str(old_index))
        if binding:
            moved[str(new_index)] = {**deepcopy(binding), "scene": asdict(scene)}
    return target, moved


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/scenes/reorder",
    vol.Required("entry_id"): str,
    vol.Required("expected"): [_SCENE_FIELDS],
    # The scenes' current numbers, in the order they should have afterwards.
    vol.Required("order"): [vol.All(int, vol.Range(min=0, max=SCENE_LIMIT - 1))],
})
@websocket_api.async_response
async def ws_reorder_scenes(hass, connection, msg):
    entry, runtime = _entry_and_runtime(hass, connection, msg)
    if entry is None:
        return
    client = runtime["client"]
    try:
        async with remote_management_lock(hass):
            current = await _read(client)
            expected = {row["index"]: Scene(**row) for row in msg["expected"]}
            bindings = _reconcile_bindings(entry, current)
            if current != expected:
                _store_bindings(hass, entry, bindings)
                runtime["scene_write_unverified"] = False
                raise ValueError("The scene list changed on the remote. Refresh it first.")
            target, moved = reorder_scenes(current, bindings, list(msg["order"]))
            if target != current:
                await _write_scene_list(client, runtime, current, target)
            _store_bindings(hass, entry, moved)
            runtime["scene_write_unverified"] = False
            runtime["studio_scenes"] = _result(target, moved)
            runtime.pop("studio_scenes_error", None)
    except Exception as err:
        _LOGGER.debug("Remote Studio scene reorder failed", exc_info=True)
        connection.send_error(msg["id"], "scene_reorder_failed", str(err))
        return
    connection.send_result(msg["id"], {**_result(target, moved),
                                       "moved": {str(old): new for new, old in enumerate(msg["order"])}})


async def _run_scene_actions(hass, entry, index):
    binding = entry.options.get(SCENE_BINDINGS, {}).get(str(index), {})
    actions = _binding_actions(binding)
    if not actions:
        return
    validated = await async_validate_actions_config(hass, actions)
    action_script = Script(hass, validated, f"WoRWS scene {index}", DOMAIN,
                           script_mode="parallel", max_runs=10)
    await action_script.async_run({"scene_index": index, "scene_name": binding["scene"]["name"]})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/scenes/test",
    vol.Required("entry_id"): str,
    vol.Required("index"): vol.All(int, vol.Range(min=0, max=SCENE_LIMIT - 1)),
})
@websocket_api.async_response
async def ws_test_scene(hass, connection, msg):
    entry, runtime = _entry_and_runtime(hass, connection, msg)
    if entry is None:
        return
    if runtime.get("scene_write_unverified"):
        connection.send_error(msg["id"], "scene_unverified", "Refresh the scene list first")
        return
    try:
        await _run_scene_actions(hass, entry, msg["index"])
    except Exception as err:
        connection.send_error(msg["id"], "scene_action_failed", str(err))
        return
    connection.send_result(msg["id"])


def listen_for_scenes(hass, entry, runtime):
    """Listen on Home Assistant's passive Bluetooth scanners for this physical remote."""
    address = entry.data[CONF_ADDRESS].upper()
    address_bytes = bytes.fromhex(address.replace(":", ""))
    tracker = ScenePressTracker()

    async def activate(index):
        try:
            await _run_scene_actions(hass, entry, index)
        except Exception:
            _LOGGER.exception("Could not run actions for WoRWS scene %s", index)

    @callback
    def receive(info, _change):
        payload = info.manufacturer_data.get(COMPANY_ID, b"")
        if payload[:6] not in (address_bytes, address_bytes[::-1]):
            return
        index = tracker.feed(payload)
        if index is None or runtime.get("scene_write_unverified"):
            return
        binding = entry.options.get(SCENE_BINDINGS, {}).get(str(index), {})
        if _binding_actions(binding):
            hass.async_create_task(activate(index))

    cached = bluetooth.async_last_service_info(hass, address, connectable=False)
    if cached:
        payload = cached.manufacturer_data.get(COMPANY_ID, b"")
        if payload[:6] in (address_bytes, address_bytes[::-1]):
            tracker.feed(payload)
    return bluetooth.async_register_callback(
        hass, receive, bluetooth.BluetoothCallbackMatcher(address=address, connectable=False),
        bluetooth.BluetoothScanningMode.PASSIVE,
    )


def register(hass):
    websocket_api.async_register_command(hass, ws_save_scene)
    websocket_api.async_register_command(hass, ws_reorder_scenes)
    websocket_api.async_register_command(hass, ws_test_scene)
