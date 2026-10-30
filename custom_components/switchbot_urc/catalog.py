"""Local button catalog for HID remotes (no cloud needed).

The SwitchBot cloud exposes button lists via `getButtonData` (= GetBindKeys) and targets via
`getBindableDevices`. For HID remote types the full button set + HID usage is actually defined
*locally* in the URC RN bundle (WORWSTAG + getHIT_fun_key_name), so we embed it here and stay
fully hub/cloud-free.

Each entry maps a WORWSTAG button name -> (keyFun, [hid_value_type, hid_value]) as read from
`HIDUniversalBLEKeyHandler.getHIT_fun_key_name` in urc-bundle.js.
"""
from __future__ import annotations

# WORWSTAG id for every button name.
TAG = {
    "A": 0, "B": 1, "C": 2, "D": 3, "ON": 4, "OFF": 5, "LEFT": 6, "RIGHT": 7, "UP": 8,
    "DOWN": 9, "OK": 10, "BACK": 11, "HOME": 12, "KATA": 13, "SOUNDOFF": 14, "VOLADD": 15,
    "VOLDEL": 16, "CHUP": 17, "CHDOWN": 18,
}

# UniversalBLE HID usage per button: name -> [value_type, value] (from getHIT_fun_key_name).
UNIVERSAL_BLE_HID = {
    "A": [8, 55], "B": [8, 53], "C": [8, 54], "D": [8, 57],
    "ON": [0, 105], "OFF": [0, 105], "UP": [0, 9], "DOWN": [0, 10],
    "LEFT": [0, 7], "RIGHT": [0, 8], "OK": [0, 11], "BACK": [0, 12],
    "HOME": [8, 56], "SOUNDOFF": [8, 52], "VOLADD": [0, 15], "VOLDEL": [0, 16],
    "CHUP": [0, 15], "CHDOWN": [0, 16],
}

# HID remote types (controlType 4; need a HID-paired host; presses go BLE-HID to that host).
HID_DEVICE_TYPES = ["UNIVERSAL_BLE", "GOOGLE_TV", "FIRE_TV", "APPLE_TV"]

# Native SwitchBot-device remote types (controlType 0; no HID-pair; presses connect OUT to the
# target MAC — point them at the fake-device add-on to catch presses in HASS).
from .commands import NATIVE_DEVICE_TYPES

# The basic HID editor stays HID-only. Native layouts are installed atomically by the dedicated
# Add/Recreate Native Remote UI because they also require target-key provisioning.
DEVICE_TYPES = HID_DEVICE_TYPES


def is_native(device_type: str) -> bool:
    return device_type.upper() in NATIVE_DEVICE_TYPES

# Icons the remote screen supports.
ICONS = ["light", "desklamp", "floorlamp", "ceilinglamp", "strip", "switch", "tv"]

# Default button set offered for a new UniversalBLE remote.
DEFAULT_BUTTONS = ["ON", "OFF", "UP", "DOWN", "OK"]


def buttons_for(device_type: str) -> list[str]:
    """Button names available for a device type (UniversalBLE catalog is the superset)."""
    return list(UNIVERSAL_BLE_HID.keys())


def keys_from_names(names: list[str], device_type: str = "UNIVERSAL_BLE") -> list[dict]:
    """Turn selected button names into create() key dicts (keyIndex + keyFun)."""
    keys: list[dict] = []
    for name in names:
        if name not in TAG:
            continue
        keys.append({"keyIndex": TAG[name], "keyFun": TAG[name]})
    return keys
