"""Interactive Home Assistant panel for WoRWS remotes and button mappings."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.script import async_validate_actions_config

from . import commands
from .bindings import (
    LIGHT_MAPPING_DEFAULTS,
    light_mapping_from_rows,
    native_button_label,
    resolve_binding_action,
)
from .const import CONF_ADDRESS, DOMAIN, EVENT_BUTTON
from .ir_profiles import PROFILES
from . import studio_physical

PANEL_URL = "switchbot-urc"
STATIC_URL = "/switchbot_urc_static"
FRONTEND_VERSION = "0.20.5"


def _entry(hass: HomeAssistant, entry_id: str) -> ConfigEntry | None:
    return next(
        (entry for entry in hass.config_entries.async_entries(DOMAIN) if entry.entry_id == entry_id),
        None,
    )


def _binding_for(entry: ConfigEntry, remote_id: str) -> dict[str, Any] | None:
    return next(
        (
            binding
            for binding in entry.options.get("bindings", [])
            if isinstance(binding, dict)
            and str(binding.get("remote_id", "")) == remote_id
        ),
        None,
    )


def _remote_for(entry: ConfigEntry, remote_id: str) -> dict[str, Any] | None:
    return next(
        (
            remote
            for remote in entry.options.get("remotes", [])
            if isinstance(remote, dict)
            and studio_physical.remote_identity(remote) == remote_id
        ),
        None,
    )


def _button_record(
    *,
    remote_id: str,
    remote_slot: int | None,
    page: int,
    index: int,
    function: int,
    position: str,
    label: str,
    binding: dict[str, Any] | None,
) -> dict[str, Any]:
    button_id = f"p{page}_k{index}"
    event_data = {
        "remote_id": remote_id,
        "remote_slot": remote_slot,
        "button_id": button_id,
        "button": label,
        "button_name": label,
        "button_page": page,
        "button_index": index,
        "button_function": function,
    }
    actions = binding.get("button_actions", {}) if binding else {}
    has_override = isinstance(actions, dict) and button_id in actions
    override = actions.get(button_id, []) if has_override else []
    if not isinstance(override, list):
        override = []
    return {
        **event_data,
        "position": position,
        "label": label.replace("_", " ").title(),
        "preset_action": resolve_binding_action(binding, event_data) if binding else None,
        "has_override": has_override,
        "actions": deepcopy(override),
    }


def _remote_pages(remote: dict[str, Any], binding: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return a frontend-safe description of every actionable remote page."""
    remote_id = studio_physical.remote_identity(remote)
    remote_slot = remote.get("index") if isinstance(remote.get("index"), int) else None
    result: list[dict[str, Any]] = []
    stored_pages = remote.get("studio_pages")
    if stored_pages is None and remote.get("profile") in PROFILES:
        stored_pages = commands.studio_pages_from_packets(PROFILES[remote["profile"]].pages)
    if isinstance(stored_pages, list):
        positions = {value: key for key, value in commands.TAG.items()}
        for page in stored_pages:
            page_index = int(page["index"])
            result.append({
                "index": page_index,
                "name": str(page.get("name") or ("Main" if page_index == 0 else f"Page {page_index}")),
                "buttons": [
                    _button_record(
                        remote_id=remote_id, remote_slot=remote_slot,
                        page=page_index, index=int(button["index"]),
                        function=int(button["function"]),
                        position=positions.get(int(button["index"]), "") if page_index == 0 else "",
                        label=str(button.get("label") or f"Function {button['function']}"),
                        binding=binding,
                    ) for button in page.get("buttons", [])
                ],
            })
        return result
    device_type = str(remote.get("device_type", "")).upper()
    if device_type in commands.DEVTYPE:
        return [{"index": 0, "name": "Main", "buttons": [
            _button_record(
                remote_id=remote_id, remote_slot=remote_slot, page=0,
                index=commands.TAG[name], function=commands.TAG[name],
                position=name, label=name, binding=binding,
            ) for name in remote.get("buttons", []) if name in commands.TAG
        ]}]
    layout = remote.get("custom_layout")
    if isinstance(layout, dict):
        main = []
        try:
            main_layout = commands.normalize_main_buttons(
                layout.get("main_buttons", {})
            )
        except ValueError:
            main_layout = {}
        for position, name in main_layout.items():
            index = commands.TAG[position]
            try:
                function = commands.custom_action_function(name)
            except ValueError:
                continue
            main.append(
                _button_record(
                    remote_id=remote_id,
                    remote_slot=remote_slot,
                    page=0,
                    index=index,
                    function=function,
                    position=position,
                    label=str(name),
                    binding=binding,
                )
            )
        if main:
            result.append({"index": 0, "name": "Main", "buttons": main})
        page_names = layout.get("page_names", {})
        for raw_page, names in layout.get("pages", {}).items():
            try:
                page = int(raw_page)
            except (TypeError, ValueError):
                continue
            if not isinstance(names, list):
                continue
            default_name = f"Page {'ABCD'[page - 1]}" if 1 <= page <= 4 else f"Page {page}"
            page_name = str(
                page_names.get(str(raw_page), page_names.get(raw_page, default_name))
            )
            buttons = []
            for index, name in enumerate(names):
                try:
                    function = commands.custom_action_function(str(name))
                except ValueError:
                    continue
                buttons.append(
                    _button_record(
                        remote_id=remote_id,
                        remote_slot=remote_slot,
                        page=page,
                        index=index,
                        function=function,
                        position=f"BUTTON_{index + 1}",
                        label=str(name),
                        binding=binding,
                    )
                )
            result.append({"index": page, "name": page_name, "buttons": buttons})
        return result

    device_type = str(remote.get("device_type", "")).upper()
    profile_name = commands.NATIVE_PROFILE_ALIASES.get(device_type)
    profile = commands.NATIVE_PROFILE_LAYOUTS.get(profile_name or "")
    if not profile:
        return []
    positions = {value: key for key, value in commands.TAG.items()}
    function_names: dict[int, str] = {}
    for name, value in commands.CUSTOM_ACTION_FUNCTIONS.items():
        function_names.setdefault(value, name)
    for page, page_keys in profile["pages"].items():
        keys = page_keys() if callable(page_keys) else page_keys
        buttons = []
        for key in keys:
            if not key.get("cmd"):
                continue
            index = int(key["keyIndex"])
            function = int(key.get("keyFun", 0))
            fallback = function_names.get(
                function, positions.get(index, f"FUNCTION_{function}")
            )
            label = native_button_label(device_type, function, fallback)
            buttons.append(
                _button_record(
                    remote_id=remote_id,
                    remote_slot=remote_slot,
                    page=int(page),
                    index=index,
                    function=function,
                    position=positions.get(index, f"BUTTON_{index + 1}"),
                    label=label,
                    binding=binding,
                )
            )
        page_name = "Main" if page == 0 else f"Page {'ABCD'[page - 1]}"
        result.append({"index": page, "name": page_name, "buttons": buttons})
    return result


def remote_pages(remote: dict[str, Any], binding: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """One page catalogue shared by Studio and the integration settings."""
    layout = remote.get("physical_layout")
    if isinstance(layout, dict):
        positions = {value: key for key, value in commands.TAG.items()}
        pages = [{"index": page["index"], "name": "Main" if page["index"] == 0 else f"Page {'ABCD'[page['index'] - 1]}",
                  "buttons": [_button_record(
                      remote_id=studio_physical.remote_identity(remote), remote_slot=remote.get("index"),
                      page=page["index"], index=key["index"], function=key.get("function", 0x7D3),
                      position=positions.get(key["index"], "") if page["index"] == 0 else "",
                      label=(commands.custom_action_name(key["function"]) if key["transport"] == "native"
                             else positions.get(key["index"], f"Button {key['index'] + 1}") if page["index"] == 0
                             else f"Button {key['index'] + 1}"), binding=binding,
                  ) for key in page["buttons"]]} for page in layout["pages"]]
    else:
        pages = _remote_pages(remote, binding)
    labels = remote.get("studio_labels", {})
    for page in pages:
        page["name"] = labels.get(f"page_{page['index']}", page["name"])
        for button in page["buttons"]:
            button["label"] = labels.get(button["button_id"], button["label"])
    return pages


def _serialize_entry(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    registry = er.async_get(hass)
    unique_id = f"{str(entry.data[CONF_ADDRESS]).replace(':', '').lower()}_battery"
    battery_entity = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    battery_state = hass.states.get(battery_entity) if battery_entity else None
    remotes = []
    for remote in entry.options.get("remotes", []):
        if not isinstance(remote, dict) or not studio_physical.remote_identity(remote):
            continue
        remote_id = studio_physical.remote_identity(remote)
        binding = _binding_for(entry, remote_id)
        layout = remote.get("custom_layout")
        device_type = str(remote.get("device_type", "Unknown"))
        if isinstance(layout, dict) and layout.get("template"):
            device_type = str(layout["template"])
        remotes.append(
            {
                "remote_id": remote_id,
                "name": str(remote.get("name") or remote_id),
                "device_type": device_type,
                "layout_editable": True,
                "remote_slot": remote.get("index"),
                "binding": deepcopy(binding) if binding else None,
                "pages": remote_pages(remote, binding),
            }
        )
    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "address": entry.data[CONF_ADDRESS],
        "battery": battery_state.state if battery_state else None,
        "remotes": remotes,
    }


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/save_labels",
    vol.Required("entry_id"): str,
    vol.Required("remote_id"): str,
    vol.Required("labels"): {str: str},
})
@callback
def ws_studio_save_labels(hass, connection, msg):
    """Save page and button display names for any protocol."""
    entry = _entry(hass, msg["entry_id"])
    remote = _remote_for(entry, msg["remote_id"]) if entry else None
    if remote is None:
        connection.send_error(msg["id"], "not_found", "Remote not found")
        return
    pages = remote_pages(remote)
    allowed = {f"page_{page['index']}" for page in pages} | {
        button["button_id"] for page in pages for button in page["buttons"]
    }
    if any(key not in allowed or not value.strip() or len(value) > 80 for key, value in msg["labels"].items()):
        connection.send_error(msg["id"], "invalid_labels", "Use existing pages/buttons and names of 1–80 characters")
        return
    options = deepcopy(dict(entry.options))
    target = next(item for item in options["remotes"] if studio_physical.remote_identity(item) == msg["remote_id"])
    target.setdefault("studio_labels", {}).update({key: value.strip() for key, value in msg["labels"].items()})
    hass.config_entries.async_update_entry(entry, options=options)
    connection.send_result(msg["id"], _serialize_entry(hass, entry))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/studio/get"})
@callback
def ws_studio_get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return every locally managed remote and its current mappings."""
    connection.send_result(
        msg["id"],
        {"entries": [_serialize_entry(hass, entry) for entry in hass.config_entries.async_entries(DOMAIN)]},
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/studio/save_button_action",
        vol.Required("entry_id"): str,
        vol.Required("remote_id"): str,
        vol.Required("button_id"): str,
        vol.Required("mode"): vol.In(("actions", "disabled", "preset")),
        vol.Optional("actions", default=[]): list,
    }
)
@websocket_api.async_response
async def ws_studio_save_button_action(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Validate and save an exact physical-button override."""
    entry = _entry(hass, msg["entry_id"])
    remote = _remote_for(entry, msg["remote_id"]) if entry else None
    if entry is None or remote is None:
        connection.send_error(msg["id"], "not_found", "Remote not found")
        return
    current_binding = _binding_for(entry, msg["remote_id"])
    known_button_ids = {
        button["button_id"]
        for page in _remote_pages(remote, current_binding)
        for button in page["buttons"]
    }
    if msg["button_id"] not in known_button_ids:
        connection.send_error(msg["id"], "not_found", "Button not found")
        return
    actions = deepcopy(msg["actions"])
    if msg["mode"] == "actions":
        if not actions:
            connection.send_error(
                msg["id"], "empty_actions", "Add at least one action"
            )
            return
        try:
            await async_validate_actions_config(hass, deepcopy(actions))
        except Exception as err:  # noqa: BLE001
            connection.send_error(msg["id"], "invalid_actions", str(err))
            return
    options = deepcopy(dict(entry.options))
    bindings = [item for item in options.get("bindings", []) if isinstance(item, dict)]
    binding = next(
        (item for item in bindings if str(item.get("remote_id", "")) == msg["remote_id"]),
        None,
    )
    if binding is None:
        binding = {
            "remote_id": msg["remote_id"],
            "remote_name": str(remote.get("name") or msg["remote_id"]),
            "entity_id": "",
            "profile": "custom",
            "enabled": True,
            "mappings": {},
            "button_actions": {},
        }
        bindings.append(binding)
    button_actions = binding.setdefault("button_actions", {})
    if not isinstance(button_actions, dict):
        button_actions = binding["button_actions"] = {}
    if msg["mode"] == "preset":
        button_actions.pop(msg["button_id"], None)
    elif msg["mode"] == "disabled":
        button_actions[msg["button_id"]] = []
    else:
        button_actions[msg["button_id"]] = actions
    options["bindings"] = bindings
    hass.config_entries.async_update_entry(entry, options=options)
    connection.send_result(msg["id"], _serialize_entry(hass, entry))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/studio/quick_bind",
        vol.Required("entry_id"): str,
        vol.Required("remote_id"): str,
        vol.Required("entity_id"): str,
    }
)
@callback
def ws_studio_quick_bind(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create or replace a whole-remote light preset from Studio."""
    entry = _entry(hass, msg["entry_id"])
    remote = _remote_for(entry, msg["remote_id"]) if entry else None
    if entry is None or remote is None:
        connection.send_error(msg["id"], "not_found", "Remote not found")
        return
    if not msg["entity_id"].startswith("light."):
        connection.send_error(msg["id"], "invalid_entity", "Choose a light entity")
        return
    options = deepcopy(dict(entry.options))
    bindings = [item for item in options.get("bindings", []) if isinstance(item, dict)]
    old = next(
        (item for item in bindings if str(item.get("remote_id", "")) == msg["remote_id"]),
        None,
    )
    button_actions = deepcopy(old.get("button_actions", {})) if old else {}
    bindings = [item for item in bindings if str(item.get("remote_id", "")) != msg["remote_id"]]
    bindings.append(
        {
            "remote_id": msg["remote_id"],
            "remote_name": str(remote.get("name") or msg["remote_id"]),
            "entity_id": msg["entity_id"],
            "profile": "light",
            "enabled": True,
            "mappings": light_mapping_from_rows(LIGHT_MAPPING_DEFAULTS),
            "button_actions": button_actions,
        }
    )
    options["bindings"] = bindings
    hass.config_entries.async_update_entry(entry, options=options)
    connection.send_result(msg["id"], _serialize_entry(hass, entry))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/studio/test_button",
        vol.Required("entry_id"): str,
        vol.Required("remote_id"): str,
        vol.Required("button_id"): str,
    }
)
@callback
def ws_studio_test_button(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Re-fire one normalized button event for an explicit Studio preview."""
    entry = _entry(hass, msg["entry_id"])
    remote = _remote_for(entry, msg["remote_id"]) if entry else None
    if entry is None or remote is None:
        connection.send_error(msg["id"], "not_found", "Remote not found")
        return
    binding = _binding_for(entry, msg["remote_id"])
    button = next(
        (
            button
            for page in _remote_pages(remote, binding)
            for button in page["buttons"]
            if button["button_id"] == msg["button_id"]
        ),
        None,
    )
    if button is None:
        connection.send_error(msg["id"], "not_found", "Button not found")
        return
    hass.bus.async_fire(
        EVENT_BUTTON,
        {
            key: value
            for key, value in button.items()
            if key
            in {
                "remote_id",
                "remote_slot",
                "button_id",
                "button",
                "button_name",
                "button_page",
                "button_index",
                "button_function",
            }
        }
        | {
            "source": "studio",
            "address": entry.data[CONF_ADDRESS],
            "worws_address": entry.data[CONF_ADDRESS],
        },
    )
    connection.send_result(msg["id"], {"fired": True})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/studio/subscribe"})
@callback
def ws_studio_subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Stream normalized physical presses to the interactive panel."""

    @callback
    def _forward(event: Event) -> None:
        connection.send_event(msg["id"], dict(event.data))

    connection.subscriptions[msg["id"]] = hass.bus.async_listen(EVENT_BUTTON, _forward)
    connection.send_result(msg["id"])


async def async_register_studio(hass: HomeAssistant) -> None:
    """Register the static panel and its WebSocket API once per HA process."""
    store = hass.data.setdefault(DOMAIN, {})
    lock = store.setdefault("_studio_registration_lock", asyncio.Lock())
    async with lock:
        if store.get("_studio_registered"):
            return
        if not store.get("_studio_commands_registered"):
            websocket_api.async_register_command(hass, ws_studio_get)
            studio_physical.register(hass)
            websocket_api.async_register_command(hass, ws_studio_save_labels)
            websocket_api.async_register_command(hass, ws_studio_save_button_action)
            websocket_api.async_register_command(hass, ws_studio_quick_bind)
            websocket_api.async_register_command(hass, ws_studio_test_button)
            websocket_api.async_register_command(hass, ws_studio_subscribe)
            store["_studio_commands_registered"] = True
        if not store.get("_studio_static_registered"):
            frontend_dir = Path(__file__).parent / "frontend"
            await hass.http.async_register_static_paths(
                [StaticPathConfig(STATIC_URL, str(frontend_dir), cache_headers=False)]
            )
            store["_studio_static_registered"] = True
        if not frontend.async_panel_exists(hass, PANEL_URL):
            await panel_custom.async_register_panel(
                hass=hass,
                frontend_url_path=PANEL_URL,
                webcomponent_name="switchbot-urc-panel",
                module_url=f"{STATIC_URL}/switchbot-urc-panel.js?v={FRONTEND_VERSION}",
                sidebar_title="Remote Studio",
                sidebar_icon="mdi:remote-tv",
                # Must stay False: the panel builds Home Assistant's own `ha-selector` for the
                # action editor, and an iframe has its own custom-element registry where that tag
                # is never defined. The element already implements the hass/narrow/route/panel
                # property contract that the non-iframe loader uses.
                embed_iframe=False,
                require_admin=True,
                handle_safe_area=True,
            )
        store["_studio_registered"] = True
