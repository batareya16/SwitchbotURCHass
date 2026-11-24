"""Home Assistant action mappings for logical WoRWS remotes."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .commands import KATA_BUTTON_ID, KATA_POSITION

ACTION_NONE = "none"
ACTION_TURN_ON = "turn_on"
ACTION_TURN_OFF = "turn_off"
ACTION_TOGGLE = "toggle"
ACTION_BRIGHTER = "brighter"
ACTION_DARKER = "darker"
ACTION_WARMER = "warmer"
ACTION_COOLER = "cooler"


def _button_identity(value: str) -> tuple[int, int]:
    try:
        page, key = value.removeprefix("p").split("_k", 1)
        page_index, key_index = int(page), int(key)
    except (AttributeError, ValueError):
        raise ValueError(f"Invalid button identity {value!r}") from None
    if not 0 <= page_index <= 4 or not 0 <= key_index <= 18:
        raise ValueError(f"Invalid button identity {value!r}")
    if (page_index, key_index) == (0, KATA_POSITION):
        raise ValueError("KATA is reserved for the Universal Remote")
    return page_index, key_index


def plan_button_identity_migrations(
    binding: dict[str, Any] | None, changes: object, removals: object = (),
) -> list[dict[str, str]]:
    """Validate key moves and prevent overwriting actions on the destination keys."""
    if not isinstance(changes, list):
        raise ValueError("Button identity migrations must be a list")
    result = []
    sources, destinations = set(), set()
    for item in changes:
        if not isinstance(item, dict):
            raise ValueError("Each button identity migration must be an object")
        source, destination = str(item.get("from", "")), str(item.get("to", ""))
        _button_identity(source)
        _button_identity(destination)
        if source == destination or source in sources or destination in destinations:
            raise ValueError("Button identity migrations must have unique source and destination keys")
        sources.add(source)
        destinations.add(destination)
        result.append({"from": source, "to": destination})
    actions = binding.get("button_actions", {}) if binding else {}
    if not isinstance(removals, (list, tuple, set)):
        raise ValueError("Removed button identities must be a list")
    removed = {str(value) for value in removals}
    for identity in removed:
        _button_identity(identity)
    if isinstance(actions, dict) and any(
        destination in actions and destination not in sources and destination not in removed
        for destination in destinations
    ):
        raise ValueError("A moved button would overwrite Home Assistant actions already saved for its destination")
    return result


def migrate_button_action_identities(
    binding: dict[str, Any], migrations: list[dict[str, str]], removals: object = (),
) -> dict[str, Any]:
    """Move per-button actions with their physical button when the screen position changes."""
    result = deepcopy(binding)
    actions = result.get("button_actions")
    if not isinstance(actions, dict):
        return result
    for identity in removals:
        actions.pop(identity, None)
    moved = {item["to"]: actions[item["from"]]
             for item in migrations if item["from"] in actions}
    for item in migrations:
        if item["from"] in actions:
            actions.pop(item["from"])
    actions.update(moved)
    return result

# Native WoStrip/WoFloorLamp colour functions use the same RGB payloads as the
# official app profile. Keep the preset action names readable in Studio while
# retaining one authoritative colour table for the event handler.
RGB_ACTIONS: dict[str, tuple[int, int, int]] = {
    "color_white": (255, 255, 255),
    "color_cold_white": (210, 240, 255),
    "color_warm_white": (255, 240, 210),
    "color_red": (255, 0, 0),
    "color_coral": (244, 74, 74),
    "color_orange": (255, 131, 72),
    "color_amber": (253, 161, 4),
    "color_yellow": (255, 243, 48),
    "color_lime": (150, 237, 93),
    "color_mint": (35, 255, 145),
    "color_green": (0, 255, 56),
    "color_turquoise": (6, 254, 222),
    "color_sky": (55, 217, 244),
    "color_cyan": (3, 164, 255),
    "color_azure": (3, 106, 255),
    "color_blue": (0, 56, 255),
    "color_violet": (120, 78, 249),
    "color_pink": (244, 74, 167),
}

# keyFun 321-323 are the three white presets on the main page. 331-345 are
# the official page-D colour palette. Function aliases make the mapping stable
# even if a future bridge supplies a translated button label.
LIGHT_COLOR_PRESET_MAPPINGS: dict[str, str] = {
    "WHITE": "color_white",
    "function:321": "color_white",
    "COLD_WHITE": "color_cold_white",
    "function:323": "color_cold_white",
    "WARM_WHITE": "color_warm_white",
    "function:322": "color_warm_white",
}
for _index, _action in enumerate(
    (
        "color_red", "color_coral", "color_orange", "color_amber",
        "color_yellow", "color_lime", "color_mint", "color_green",
        "color_turquoise", "color_sky", "color_cyan", "color_azure",
        "color_blue", "color_violet", "color_pink",
    ),
    start=1,
):
    LIGHT_COLOR_PRESET_MAPPINGS[f"COLOR_{_index}"] = _action
    LIGHT_COLOR_PRESET_MAPPINGS[f"function:{330 + _index}"] = _action

ACTION_LABELS = {
    ACTION_NONE: "No action",
    ACTION_TURN_ON: "Turn on",
    ACTION_TURN_OFF: "Turn off",
    ACTION_TOGGLE: "Toggle",
    ACTION_BRIGHTER: "Increase brightness by 10%",
    ACTION_DARKER: "Decrease brightness by 10%",
    ACTION_WARMER: "Make light warmer",
    ACTION_COOLER: "Make light cooler",
}

# One editor row can cover both the decoded native function name and the older
# position-based label. This keeps bindings working across existing and newly
# recreated remotes without tying them to a physical WoRWS slot.
LIGHT_MAPPING_ROWS: dict[str, tuple[str, ...]] = {
    "power_on": ("ON", "LIGHT_ON", "OPEN", "UNLOCK"),
    "power_off": ("OFF", "LIGHT_OFF", "CLOSE", "LOCK"),
    "brightness_up": ("BRIGHTER", "UP"),
    "brightness_down": ("DARKER", "DOWN"),
    "warmer": ("WARMER", "LEFT"),
    "cooler": ("COOLER", "RIGHT"),
    "center": ("PRESS", "OK"),
    "button_a": ("A",),
    "button_b": ("B",),
    "button_c": ("C",),
    "button_d": ("D",),
}


def event_matches_remote_address(
    expected_address: str, event_data: dict[str, Any]
) -> bool:
    """Return whether an event belongs to one physical Universal Remote.

    Older bridge payloads did not carry a source address, so an absent value remains
    backward-compatible. New MQTT payloads use ``worws_address`` while direct integration
    notifications use ``address``.
    """
    source = event_data.get("worws_address") or event_data.get("address")
    if not source:
        return True

    def _compact(value: object) -> str:
        return str(value).replace(":", "").replace("-", "").strip().lower()

    return _compact(source) == _compact(expected_address)


def native_button_label(device_type: str, function: int, fallback: str) -> str:
    """Apply the device-specific meaning used by the bridge event decoder."""
    normalized = device_type.upper()
    if function in (5, 6):
        if normalized in {"CURTAIN", "ROLLER_SHADE", "GARAGE_DOOR"}:
            return "OPEN" if function == 5 else "CLOSE"
        if normalized == "LOCK":
            return "UNLOCK" if function == 5 else "LOCK"
    return fallback

LIGHT_MAPPING_DEFAULTS = {
    "power_on": ACTION_TURN_ON,
    "power_off": ACTION_TURN_OFF,
    "brightness_up": ACTION_BRIGHTER,
    "brightness_down": ACTION_DARKER,
    "warmer": ACTION_WARMER,
    "cooler": ACTION_COOLER,
    "center": ACTION_TOGGLE,
    "button_a": ACTION_NONE,
    "button_b": ACTION_NONE,
    "button_c": ACTION_NONE,
    "button_d": ACTION_NONE,
}


def light_mapping_from_rows(rows: dict[str, str]) -> dict[str, str]:
    """Expand friendly editor rows to every event-label alias."""
    mapping: dict[str, str] = {}
    for row, aliases in LIGHT_MAPPING_ROWS.items():
        action = str(rows.get(row, LIGHT_MAPPING_DEFAULTS[row]))
        for alias in aliases:
            mapping[alias] = action
    mapping.update(LIGHT_COLOR_PRESET_MAPPINGS)
    return mapping


def light_rows_from_mapping(mapping: dict[str, Any]) -> dict[str, str]:
    """Collapse an event mapping back into the editable light rows."""
    rows: dict[str, str] = {}
    for row, aliases in LIGHT_MAPPING_ROWS.items():
        rows[row] = next(
            (
                str(mapping[alias])
                for alias in aliases
                if alias in mapping
            ),
            LIGHT_MAPPING_DEFAULTS[row],
        )
    return rows


def event_mapping_candidates(event_data: dict[str, Any]) -> list[str]:
    """Return stable-to-legacy keys that may identify one button press."""
    candidates: list[str] = []
    button_id = event_data.get("button_id")
    if button_id == KATA_BUTTON_ID or (
        event_data.get("button_page"), event_data.get("button_index")
    ) == (0, KATA_POSITION):
        return []
    if button_id:
        candidates.append(str(button_id))
    for field in ("button_name", "button"):
        value = event_data.get(field)
        if value:
            normalized = str(value).strip().upper()
            if normalized and normalized not in candidates:
                candidates.append(normalized)
    function = event_data.get("button_function")
    if function is not None:
        candidates.append(f"function:{function}")
    return candidates


def resolve_binding_match(
    binding: dict[str, Any], event_data: dict[str, Any]
) -> tuple[str | None, str | None]:
    """Resolve a button event against one stored binding: the action and the key that matched.

    The key is the button's own id, or a name or function it shares with other buttons: a key
    without actions of its own runs the Quick bind of any button with the same action name.
    """
    if not binding.get("enabled", True):
        return None, None
    if str(binding.get("remote_id", "")) != str(event_data.get("remote_id", "")):
        return None, None
    mapping = binding.get("mappings")
    if not isinstance(mapping, dict):
        return None, None
    candidates = event_mapping_candidates(event_data)
    for candidate in candidates:
        action = str(mapping.get(candidate, ACTION_NONE))
        if action != ACTION_NONE:
            return action, candidate
        # An explicitly stored colour entry is authoritative. Exact physical-button
        # overrides are handled before this function and remain the preferred way to
        # customize or disable one palette key.
        if candidate in mapping and candidate in LIGHT_COLOR_PRESET_MAPPINGS:
            return None, None
    # Bindings created before 0.19.29 have no colour keys. Supply the native light
    # palette at runtime so an existing Quick bind is upgraded without user action.
    if str(binding.get("profile", "")) == "light":
        for candidate in candidates:
            action = LIGHT_COLOR_PRESET_MAPPINGS.get(candidate)
            if action is not None:
                return action, candidate
    return None, None


def resolve_binding_action(
    binding: dict[str, Any], event_data: dict[str, Any]
) -> str | None:
    """Resolve a button event against one stored binding."""
    return resolve_binding_match(binding, event_data)[0]


def resolve_button_action_sequence(
    binding: dict[str, Any], event_data: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """Resolve an exact physical-button override.

    ``None`` means that no override exists and the quick-bind preset may run.
    An empty list is an intentional override that disables the selected button.
    """
    if not binding.get("enabled", True):
        return None
    if str(binding.get("remote_id", "")) != str(event_data.get("remote_id", "")):
        return None
    button_actions = binding.get("button_actions")
    if not isinstance(button_actions, dict):
        return None
    for candidate in event_mapping_candidates(event_data):
        if candidate not in button_actions:
            continue
        sequence = button_actions[candidate]
        if not isinstance(sequence, list):
            return []
        return [dict(action) for action in sequence if isinstance(action, dict)]
    return None
