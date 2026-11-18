"""Physical WoRWS settings, verified against the V48 ARM settings handler."""
from __future__ import annotations

STATUS_COMMAND = b"\x02"
# Offsets in the 03 command payload, after the opcode. FF leaves a field unchanged.
SETTING_OFFSETS = {
    "key_sounds": 0,
    "auto_brightness": 1,
    "lift_to_wake": 2,
    "screen_brightness": 3,
    "key_brightness": 4,
    "screen_timeout": 5,
    "temperature_unit": 6,
    "language": 7,
    "touch_wheel": 9,
}
BOOLEAN_SETTINGS = frozenset({"key_sounds", "auto_brightness", "lift_to_wake", "touch_wheel"})
BRIGHTNESS_SETTINGS = frozenset({"screen_brightness", "key_brightness"})
INTEGER_LIMITS = {
    "screen_brightness": (0, 100),
    "key_brightness": (0, 100),
    "screen_timeout": (3, 254),
    "temperature_unit": (0, 1),
    "language": (0, 2),
}


class SettingsVerificationError(RuntimeError):
    """A write may have succeeded, but its resulting settings could not be verified."""


def parse_settings(response: bytes) -> dict:
    """Decode the 16-byte status body, without inventing defaults after a bad read."""
    if len(response) != 16 or response[1] not in (0x2D, 0x30) or response[0] > 100:
        raise ValueError("The remote did not return a valid settings record")
    values = {
        "key_sounds": response[2],
        "auto_brightness": response[3],
        "lift_to_wake": response[4],
        "screen_brightness": response[5],
        "key_brightness": response[6],
        "screen_timeout": response[7],
        "temperature_unit": response[8] & 1,
        "language": response[9],
        "touch_wheel": response[12],
        "japan_model": bool(response[8] & 0x80),
    }
    for field in BOOLEAN_SETTINGS:
        if values[field] not in (0, 1):
            raise ValueError(f"Invalid {field} in the remote settings record")
        values[field] = bool(values[field])
    if any(values[field] > 100 for field in BRIGHTNESS_SETTINGS):
        raise ValueError("Invalid brightness in the remote settings record")
    return values


def build_settings(changes: dict) -> bytes:
    """Patch only requested settings. The destructive clear-data field stays FF."""
    # V48 also checks an optional timeout at offset 10. Leave it explicitly unchanged.
    payload = bytearray(b"\xff" * 11)
    for field, value in changes.items():
        if field not in SETTING_OFFSETS:
            raise ValueError(f"Unknown remote setting: {field}")
        if field in BOOLEAN_SETTINGS:
            if type(value) is not bool:
                raise ValueError(f"{field} must be a boolean")
        else:
            minimum, maximum = INTEGER_LIMITS[field]
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"Invalid value for {field}")
        payload[SETTING_OFFSETS[field]] = int(value)
    return b"\x03" + payload


async def read_settings(client) -> dict:
    return parse_settings(await client.send_command(STATUS_COMMAND))


async def apply_settings(client, changes: dict) -> dict:
    """Read fresh values, apply a sparse patch once, then verify the changed fields."""
    build_settings(changes)
    current = await read_settings(client)
    changes = {field: value for field, value in changes.items() if current[field] != value}
    if current["japan_model"] and "temperature_unit" in changes:
        raise ValueError("The Japanese remote keeps its temperature unit fixed")
    if changes.get("auto_brightness", current["auto_brightness"]) and any(
        field in changes for field in BRIGHTNESS_SETTINGS
    ):
        raise ValueError("Turn off automatic brightness before changing brightness levels")
    if not changes:
        return current
    command = build_settings(changes)
    response = await client.send_command(command)
    if response != b"\x01":
        raise RuntimeError(f"The remote rejected the settings command ({response.hex() or 'no reply'})")
    try:
        actual = await read_settings(client)
    except Exception as err:
        raise SettingsVerificationError(
            "The remote accepted the settings, but their readback failed. Reopen settings to check them."
        ) from err
    if any(actual[field] != value for field, value in changes.items()):
        raise SettingsVerificationError("The settings read back from the remote do not match the changes")
    return actual
