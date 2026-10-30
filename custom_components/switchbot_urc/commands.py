"""Plaintext command builders for the SwitchBot Universal Remote (WoRWS).

All builders return the AES-CTR *plaintext* (the leading 0x57 transport magic is added later by
`UrcCrypto.frame_command`). Every layout here is reverse-engineered from the readable URC RN
bundle (`urc-bundle.js`) and verified 1:1 against live captures — see ../CRYPTO-FINDINGS.md.

Opcodes (plaintext, 0x0F = 15, 0x62 = 98):
  0F 21 03 <keyId>            get-random handshake (unencrypted, built in crypto.py)
  0F 62 06 <len><crc><body>   create / bind remote  (getBindCmd / assembleKeysByPage)
  0F 62 01 <id>...            initialise an IR-code-bank transfer
  0F 62 02 <part><crc><data>  upload one IR-code-bank part
  0F 62 03 <count><len><crc>  finish an IR-code-bank transfer
  0F 62 0C <count><phase>     begin/end IR remote synchronisation
  0F 62 04 02 <idx>...        delete remote         (deleteDeviceByIdBin)
  0F 62 0E 01 <mac11>         HID-pair remote to a host (startPairHIDDevice)
  0F 41 02 <ac-state>         AC set-state (draw on screen)
  02                          status poll
"""
from __future__ import annotations

# ---- primitives ----------------------------------------------------------------------------


def crc16_modbus(data: bytes) -> int:
    """CRC-16/MODBUS (init 0xFFFF, poly 0xA001). Verified: crc('123456789') == 0x4B37."""
    n = 0xFFFF
    for b in data:
        n ^= b
        for _ in range(8):
            n = (n >> 1) ^ 0xA001 if (n & 1) else (n >> 1)
    return n & 0xFFFF


def s16(n: int, big_endian: bool = True) -> bytes:
    hi, lo = (n >> 8) & 0xFF, n & 0xFF
    return bytes([hi, lo]) if big_endian else bytes([lo, hi])


def pad(data: bytes, size: int) -> bytes:
    """Right-pad with zeros (or truncate) to exactly `size` bytes."""
    return (bytes(data) + bytes(size))[:size]


def id_to_bytes(device_id: str, reverse: bool = True) -> bytes:
    """11-byte id field. App uses macToBytes(id, true) = 6 hex bytes REVERSED, padded to 11.

    `device_id` is 12 hex chars (a MAC without separators, or a 12-digit HID deviceID as hex).
    Verified: id "021791812216" -> bytes 16 22 81 91 17 02 (reversed) + 5 pad.
    """
    compact = device_id.replace(":", "").replace("-", "")
    if len(compact) == 22:
        return bytes.fromhex(compact)
    if len(compact) != 12:
        raise ValueError("device id must contain exactly 12 or 22 hexadecimal characters")
    raw = bytes.fromhex(compact)
    if reverse:
        raw = raw[::-1]
    return pad(raw, 11)


BRIDGE_TAG_MAGIC = bytes.fromhex("f09d")
BRIDGE_TAG_MAGIC_V2 = bytes.fromhex("f09e")
BRIDGE_EVENT_MAGIC_V3 = bytes.fromhex("57f003")


def native_logical_device_id(physical_device_id: str, remote_id: str) -> str:
    """Build the firmware-compatible 11-byte native target table ID.

    Hardware testing disproved the assumption that the trailing five bytes can distinguish
    logical targets: WoRWS connects to the six-byte MAC but aborts after service discovery when
    that tail is non-zero. Keep the stable logical ID solely in button-command metadata.
    """
    compact_id = remote_id.replace("-", "").lower()
    if len(compact_id) != 8:
        raise ValueError("bridge remote id must contain exactly eight hexadecimal characters")
    bytes.fromhex(compact_id)
    return id_to_bytes(physical_device_id).hex()


def _tag_bridge_keys(
    keys: list[dict], *, remote_id: str | None, remote_slot: int | None,
    page_index: int, profile_id: int = 0,
) -> list[dict]:
    """Replace target commands with a compact, profile-independent bridge event.

    Native commands are limited to twenty bytes.  Appending metadata worked for short
    WoStrip commands but cannot represent longer profiles such as TRV.  The fake hub does
    not execute the original target command, so v3 stores a dedicated 13-byte event packet:
    ``57 F0 03 profile remote-id slot page index keyFun``.
    """
    if remote_id is None:
        return [dict(item) for item in keys]
    compact_id = remote_id.replace("-", "").lower()
    if len(compact_id) != 8:
        raise ValueError("bridge remote id must contain exactly eight hexadecimal characters")
    token = bytes.fromhex(compact_id)
    if remote_slot is None or not 0 <= remote_slot <= 0xFF:
        raise ValueError("bridge remote slot must fit in one byte")
    tagged: list[dict] = []
    for item in keys:
        copy = dict(item)
        if copy.get("cmd"):
            key_index = int(copy["keyIndex"])
            key_fun = int(copy.get("keyFun", 0))
            if not 0 <= key_index <= 0xFF:
                raise ValueError("bridge key index must fit in one byte")
            if not 0 <= key_fun <= 0xFFFF:
                raise ValueError("bridge key function must fit in two bytes")
            copy["cmd"] = list(
                BRIDGE_EVENT_MAGIC_V3
                + bytes([profile_id & 0xFF])
                + token
                + bytes([remote_slot, page_index & 0xFF, key_index])
                + key_fun.to_bytes(2, "big")
            )
        tagged.append(copy)
    return tagged


def cloud_remote_id_to_bytes(remote_id: str) -> bytes:
    """Convert the cloud's decimal-pair IR id to the 11-byte on-device id.

    Example: ``01-202610142303-11317791`` becomes
    ``01 14 1a 0a 0e 17 03 0b 1f 4d 5b``.  A plain 22-character hexadecimal
    id is accepted too, which makes the helper useful for persisted records.
    """
    compact = remote_id.replace("-", "").replace(":", "")
    if len(compact) == 22 and all(char in "0123456789abcdefABCDEF" for char in compact):
        # A hyphenated cloud id is decimal even though it only contains digits.
        if "-" not in remote_id:
            return bytes.fromhex(compact)
    digits = remote_id.replace("-", "")
    if len(digits) != 22 or not digits.isdigit():
        raise ValueError("cloud IR remote id must contain eleven decimal pairs")
    values = [int(digits[offset:offset + 2]) for offset in range(0, 22, 2)]
    if any(value > 0xFF for value in values):
        raise ValueError("cloud IR remote id contains a byte above 255")
    return bytes(values)


# ---- enums (from urc-bundle.js) ------------------------------------------------------------

# WORWSTAG key-function / on-screen position ids.
TAG = {
    "A": 0, "B": 1, "C": 2, "D": 3, "ON": 4, "OFF": 5, "LEFT": 6, "RIGHT": 7, "UP": 8,
    "DOWN": 9, "OK": 10, "BACK": 11, "HOME": 12, "KATA": 13, "SOUNDOFF": 14, "VOLADD": 15,
    "VOLDEL": 16, "CHUP": 17, "CHDOWN": 18,
}

# URC device-type codes (HID remotes; all go direct-BLE, no hub).
DEVTYPE = {"APPLE_TV": 0xF0, "FIRE_TV": 0xF1, "UNIVERSAL_BLE": 0xF2, "GOOGLE_TV": 0xF3}

# controlType: HID=4, Matter=3, IR=1, native SwitchBot device=0.
CTRL_HID = 4
CTRL_NATIVE = 0
CTRL_IR = 1

# Native SwitchBot-device remote types (controlType 0, NO HID-pair needed). devType bytes from
# getDeviceTypeCmd in urc-bundle.js. These remotes connect OUT to a target device's MAC on press,
# so the target (our fake-device add-on) receives the button command directly.
NATIVE_DEVTYPE = {
    "PLUG": 0x67, "PLUG_US": 0x67, "PLUG_JP": 0x6A,
    "CURTAIN": 0x63, "CURTAIN_3": 0x7B, "BLIND_TILT": 0x78,
    "CEILING": 0x71, "CEILING_PRO": 0x6E, "BULB": 0x75,
    "LIGHT": 0x72, "STRIP": 0x72,
    "FLOOR_LAMP": 0x0010D0B0, "RGBICWW_LIGHT_BARS": 0x0011BEF8,
    "STRIP_3": 0x0010D0B1, "NEON_LIGHT": 0x0010D0B2,
    "RGBICWW_STRIP_LIGHT": 0x0010D0B3, "RGBICWW_FLOOR_LAMP": 0x0010D0B4,
    "RGBIC_NEON_WIRE_ROPE_LIGHT": 0x0010D0B5,
    "RGBIC_NEON_ROPE_LIGHT": 0x0010D0B6,
    "RGBIC_PERMANENT_OUTDOOR_LIGHT": 0x0010D0B7,
    "CEILING_LIGHT_2": 0x0011BB10, "CANDLE": 0x001122B8, "CANDLE_LAMP": 0x001122B8,
    "BOT": 0x48, "FAN": 0x7E, "FAN_2": 0x7E, "FAN_3": 0x00110760,
    "FAN_PRO": 0x0011B340, "ROLLER_SHADE": 0x2C,
    "AIR_PURIFIER_US": 0x2A, "AIR_PURIFIER_JP": 0x2B,
    "AIR_PURIFIER_US_PRO": 0x37, "AIR_PURIFIER_JP_PRO": 0x38,
    "HUMIDIFIER": 0x23, "HUMIDIFIER_2": 0x23,
    "LOCK": 0x6F, "LOCK_LITE": 0x2D, "LOCK_PRO": 0x24,
    "LOCK_PRO_WIFI": 0x0010FF90, "LOCK_2": 0x0010A5B8,
    "LOCK_ULTRA_2": 0x00119FB8, "VISION_DEADBOLT": 0x00116908,
    "VISION_DEADBOLT_PRO": 0x00116909,
    "SWITCH": 0x3C, "SWITCH_1PM": 0x3C, "SWITCH_1PLUS": 0x3B,
    "PLUG_EU": 0x3F, "GARAGE_DOOR": 0x3E, "TRV": 0x00113640,
}


def _button(index: int, function: int, *, actionable: bool = True) -> dict:
    return {"keyIndex": index, "keyFun": function, "cmd": [0x57] if actionable else None}


def _page(*items: tuple[int, int] | tuple[int, int, bool]) -> list[dict]:
    return [_button(*item[:2], actionable=item[2] if len(item) == 3 else True) for item in items]


COLOR_PAGE = _page(*[(index, 331 + index) for index in range(15)])
FAN_MODE_PAGE = _page(*[(index, 120 + index if index < 3 else 141 + index) for index in range(12)])
FAN_VERTICAL_PAGE = _page((0, 136), (1, 137), (2, 138), (3, 139))
FAN_HORIZONTAL_PAGE = _page((0, 140), (1, 141), (2, 142), (3, 143))
FAN_LIGHT_PAGE = _page((0, 133), (1, 134), (2, 135))

# Native layouts recovered from BleKeyHandlerFactory and its handlers in urc-bundle.js.
# Page numbers match Main/A/B/C/D = 0/1/2/3/4.  A false third tuple item is a submenu link.
NATIVE_PROFILE_LAYOUTS: dict[str, dict] = {
    "PLUG": {"id": 1, "pages": {0: _page((TAG["ON"], 5), (TAG["OFF"], 6))}},
    "CURTAIN": {"id": 2, "pages": {0: _page(
        (TAG["ON"], 5), (TAG["OFF"], 6), (TAG["LEFT"], 5), (TAG["RIGHT"], 6),
        (TAG["OK"], 22), (TAG["A"], 1310), (TAG["B"], 1330),
        (TAG["C"], 1350), (TAG["D"], 1370))}},
    "BLIND_TILT": {"id": 3, "pages": {0: _page(
        (TAG["ON"], 1500), (TAG["OFF"], 1700), (TAG["UP"], 1600),
        (TAG["DOWN"], 1700), (TAG["OK"], 22), (TAG["A"], 1610),
        (TAG["B"], 1630), (TAG["C"], 1650), (TAG["D"], 1670))}},
    "CEILING": {"id": 4, "pages": {
        0: _page((TAG["ON"], 5), (TAG["OFF"], 6), (TAG["UP"], 300),
                 (TAG["DOWN"], 301), (TAG["LEFT"], 303), (TAG["RIGHT"], 302),
                 (TAG["A"], 311), (TAG["B"], 312), (TAG["C"], 320, False),
                 (TAG["D"], 100, False)),
        3: _page((0, 321), (1, 322), (2, 323)),
        4: _page((0, 313), (1, 314), (2, 315), (3, 316), (4, 317)),
    }},
    "BULB": {"id": 5, "pages": {
        0: _page((TAG["ON"], 5), (TAG["OFF"], 6), (TAG["UP"], 300),
                 (TAG["DOWN"], 301), (TAG["LEFT"], 303), (TAG["RIGHT"], 302),
                 (TAG["A"], 321), (TAG["B"], 322), (TAG["C"], 330, False),
                 (TAG["D"], 318)),
        3: COLOR_PAGE,
    }},
    "STRIP": {"id": 6, "pages": {
        0: lambda: strip_light_keys(), 4: lambda: strip_color_keys(),
    }},
    "CANDLE": {"id": 7, "pages": {0: _page(
        (TAG["ON"], 5), (TAG["OFF"], 6), (TAG["UP"], 300), (TAG["DOWN"], 301))}},
    "BOT": {"id": 8, "pages": {0: _page(
        (TAG["ON"], 5), (TAG["OFF"], 6), (TAG["OK"], 11))}},
    "FAN": {"id": 9, "pages": {
        0: _page((TAG["ON"], 5), (TAG["OFF"], 6), (TAG["A"], 119, False),
                 (TAG["B"], 123, False), (TAG["C"], 124, False),
                 (TAG["D"], 125, False)),
        1: FAN_MODE_PAGE, 2: FAN_VERTICAL_PAGE, 3: FAN_HORIZONTAL_PAGE, 4: FAN_LIGHT_PAGE,
    }},
    "ROLLER_SHADE": {"id": 10, "pages": {0: _page(
        (TAG["ON"], 5), (TAG["OFF"], 6), (TAG["UP"], 5), (TAG["DOWN"], 6),
        (TAG["OK"], 22), (TAG["A"], 1310), (TAG["B"], 1330),
        (TAG["C"], 1350), (TAG["D"], 1370))}},
    "AIR_PURIFIER": {"id": 11, "pages": {
        0: _page((TAG["ON"], 5), (TAG["OFF"], 6), (TAG["A"], 126, False),
                 (TAG["B"], 117), (TAG["C"], 127), (TAG["D"], 121)),
        1: _page((0, 131), (1, 130), (2, 129)),
    }},
    "HUMIDIFIER": {"id": 12, "pages": {
        0: _page((TAG["ON"], 5), (TAG["OFF"], 6), (TAG["A"], 126, False),
                 (TAG["B"], 121), (TAG["C"], 128), (TAG["D"], 117)),
        1: _page((0, 132), (1, 131), (2, 130), (3, 129)),
    }},
    "LOCK": {"id": 13, "pages": {0: _page((TAG["ON"], 5), (TAG["OFF"], 6))}},
    "SWITCH": {"id": 14, "pages": {0: _page((TAG["ON"], 5), (TAG["OFF"], 6))}},
    "GARAGE_DOOR": {"id": 15, "pages": {0: _page((TAG["ON"], 5), (TAG["OFF"], 6))}},
    "TRV": {"id": 16, "control_mode": 6, "pages": {0: _page(
        (TAG["ON"], 5), (TAG["OFF"], 6), (TAG["UP"], 60), (TAG["DOWN"], 61),
        (TAG["VOLADD"], 60), (TAG["VOLDEL"], 61),
        (TAG["CHUP"], 60), (TAG["CHDOWN"], 61))}},
}

NATIVE_PROFILE_ALIASES = {
    **{name: "PLUG" for name in ("PLUG", "PLUG_US", "PLUG_JP")},
    **{name: "CURTAIN" for name in ("CURTAIN", "CURTAIN_3")},
    "BLIND_TILT": "BLIND_TILT",
    **{name: "CEILING" for name in ("CEILING", "CEILING_PRO", "CEILING_LIGHT_2")},
    "BULB": "BULB",
    **{name: "STRIP" for name in ("LIGHT", "STRIP", "FLOOR_LAMP", "RGBICWW_LIGHT_BARS",
        "STRIP_3", "NEON_LIGHT", "RGBICWW_STRIP_LIGHT", "RGBICWW_FLOOR_LAMP",
        "RGBIC_NEON_WIRE_ROPE_LIGHT", "RGBIC_NEON_ROPE_LIGHT",
        "RGBIC_PERMANENT_OUTDOOR_LIGHT")},
    **{name: "CANDLE" for name in ("CANDLE", "CANDLE_LAMP")},
    "BOT": "BOT",
    **{name: "FAN" for name in ("FAN", "FAN_2", "FAN_3", "FAN_PRO")},
    "ROLLER_SHADE": "ROLLER_SHADE",
    **{name: "AIR_PURIFIER" for name in ("AIR_PURIFIER_US", "AIR_PURIFIER_JP",
        "AIR_PURIFIER_US_PRO", "AIR_PURIFIER_JP_PRO")},
    **{name: "HUMIDIFIER" for name in ("HUMIDIFIER", "HUMIDIFIER_2")},
    **{name: "LOCK" for name in ("LOCK", "LOCK_LITE", "LOCK_PRO", "LOCK_PRO_WIFI",
        "LOCK_2", "LOCK_ULTRA_2", "VISION_DEADBOLT", "VISION_DEADBOLT_PRO")},
    **{name: "SWITCH" for name in ("SWITCH", "SWITCH_1PM", "SWITCH_1PLUS", "PLUG_EU")},
    "GARAGE_DOOR": "GARAGE_DOOR", "TRV": "TRV",
}

NATIVE_DEVICE_TYPES = tuple(NATIVE_PROFILE_ALIASES)

# WoRWS firmware accepts only single-byte native device types over the local 0F6206 bind. The
# newer multi-byte RGBICWW / lock / fan types (e.g. FLOOR_LAMP 0x10D0B0, STRIP_3 0x10D0B1) are
# rejected with a 0x02 value error — hardware-confirmed — so the UI only offers the supported set.
SUPPORTED_NATIVE_DEVICE_TYPES = tuple(
    name for name in NATIVE_DEVICE_TYPES if NATIVE_DEVTYPE[name] <= 0xFF
)


def native_device_type_supported(device_type_name: str) -> bool:
    """True when this remote firmware accepts the native type over a local bind (single-byte)."""
    return NATIVE_DEVTYPE.get(device_type_name.upper(), 0x10000) <= 0xFF

# User-facing building blocks for custom bridge remotes.  The main page uses the physical
# WoRWS key positions; submenu pages are compact lists whose keyIndex is assigned in display
# order.  Values are the official keyFun numbers, so the screen keeps native SwitchBot icons
# while Home Assistant receives a stable page/index identity.
CUSTOM_MAIN_BUTTONS = {
    "ON": (TAG["ON"], 5), "OFF": (TAG["OFF"], 6),
    "UP": (TAG["UP"], 300), "DOWN": (TAG["DOWN"], 301),
    "LEFT": (TAG["LEFT"], 303), "RIGHT": (TAG["RIGHT"], 302),
    "OK": (TAG["OK"], 11), "BACK": (TAG["BACK"], 11),
    "HOME": (TAG["HOME"], 100), "MUTE": (TAG["SOUNDOFF"], 132),
    "VOLUME_UP": (TAG["VOLADD"], 300), "VOLUME_DOWN": (TAG["VOLDEL"], 301),
    "CHANNEL_UP": (TAG["CHUP"], 60), "CHANNEL_DOWN": (TAG["CHDOWN"], 61),
}

CUSTOM_ACTION_FUNCTIONS = {
    "ON": 5, "OFF": 6, "PRESS": 11, "PAUSE": 22,
    "TEMP_UP": 60, "TEMP_DOWN": 61, "MORE": 100,
    "AUTO": 117, "MODE": 119, "NATURAL": 120, "SLEEP": 121,
    "BABY": 122, "VERTICAL_SWING": 123, "HORIZONTAL_SWING": 124,
    "LIGHT_MODE": 125, "GEAR": 126, "PET": 127, "HUMIDIFY": 128,
    "LEVEL_3": 129, "LEVEL_2": 130, "LEVEL_1": 131, "MUTE": 132,
    "LIGHT_ON": 133, "LIGHT_DIM": 134, "LIGHT_OFF": 135,
    "VERTICAL_30": 136, "VERTICAL_60": 137, "VERTICAL_90": 138,
    "VERTICAL_OFF": 139, "HORIZONTAL_30": 140, "HORIZONTAL_60": 141,
    "HORIZONTAL_90": 142, "HORIZONTAL_OFF": 143,
    **{f"SPEED_{index}": 143 + index for index in range(1, 10)},
    "BRIGHTER": 300, "DARKER": 301, "WARMER": 302, "COOLER": 303,
    "NIGHT": 311, "DAY": 312, "MIDNIGHT": 313, "SLEEP_LIGHT": 314,
    "READ": 315, "RELAX": 316, "EAT": 317, "FLASH": 318,
    "WHITE": 321, "WARM_WHITE": 322, "COLD_WHITE": 323,
    **{f"COLOR_{index}": 330 + index for index in range(1, 16)},
}

CUSTOM_PAGE_LINK_FUNCTIONS = {1: 119, 2: 123, 3: 124, 4: 125}

CUSTOM_ACTION_CATEGORIES = {
    **{name: "Power" for name in ("ON", "OFF", "PRESS", "PAUSE")},
    **{name: "Climate" for name in (
        "TEMP_UP", "TEMP_DOWN", "AUTO", "MODE", "NATURAL", "SLEEP", "BABY",
        "GEAR", "PET", "HUMIDIFY", "LEVEL_1", "LEVEL_2", "LEVEL_3", "MUTE",
    )},
    **{name: "Fan" for name in (
        "VERTICAL_SWING", "HORIZONTAL_SWING", "VERTICAL_30", "VERTICAL_60",
        "VERTICAL_90", "VERTICAL_OFF", "HORIZONTAL_30", "HORIZONTAL_60",
        "HORIZONTAL_90", "HORIZONTAL_OFF", *[f"SPEED_{index}" for index in range(1, 10)],
    )},
    **{name: "Lighting" for name in (
        "LIGHT_MODE", "LIGHT_ON", "LIGHT_DIM", "LIGHT_OFF", "BRIGHTER", "DARKER",
        "WARMER", "COOLER", "NIGHT", "DAY", "MIDNIGHT", "SLEEP_LIGHT", "READ",
        "RELAX", "EAT", "FLASH", "WHITE", "WARM_WHITE", "COLD_WHITE",
        *[f"COLOR_{index}" for index in range(1, 16)],
    )},
    "MORE": "Navigation",
}

CUSTOM_ACTION_HA_ICONS = {
    "ON": "mdi:power", "OFF": "mdi:power-off", "PRESS": "mdi:gesture-tap-button",
    "PAUSE": "mdi:pause", "TEMP_UP": "mdi:thermometer-plus",
    "TEMP_DOWN": "mdi:thermometer-minus", "AUTO": "mdi:autorenew",
    "MODE": "mdi:tune", "NATURAL": "mdi:weather-windy", "SLEEP": "mdi:sleep",
    "BABY": "mdi:baby-face-outline", "VERTICAL_SWING": "mdi:swap-vertical",
    "HORIZONTAL_SWING": "mdi:swap-horizontal", "LIGHT_MODE": "mdi:lightbulb-auto",
    "GEAR": "mdi:cog", "PET": "mdi:paw", "HUMIDIFY": "mdi:air-humidifier",
    "MUTE": "mdi:volume-mute", "LIGHT_ON": "mdi:lightbulb-on",
    "LIGHT_DIM": "mdi:brightness-6", "LIGHT_OFF": "mdi:lightbulb-off",
    "BRIGHTER": "mdi:brightness-7", "DARKER": "mdi:brightness-5",
    "WARMER": "mdi:weather-sunny", "COOLER": "mdi:snowflake",
    "NIGHT": "mdi:weather-night", "DAY": "mdi:white-balance-sunny",
    "READ": "mdi:book-open-page-variant", "RELAX": "mdi:sofa",
    "EAT": "mdi:silverware-fork-knife", "FLASH": "mdi:flash",
    "WHITE": "mdi:lightbulb", "WARM_WHITE": "mdi:lightbulb-on-50",
    "COLD_WHITE": "mdi:lightbulb-fluorescent-tube-outline", "MORE": "mdi:dots-horizontal",
}

CUSTOM_ACTION_DISPLAY_NAMES = {
    "COLOR_1": "Red", "COLOR_2": "Coral", "COLOR_3": "Orange",
    "COLOR_4": "Amber", "COLOR_5": "Yellow", "COLOR_6": "Lime",
    "COLOR_7": "Mint", "COLOR_8": "Green", "COLOR_9": "Turquoise",
    "COLOR_10": "Sky", "COLOR_11": "Cyan", "COLOR_12": "Azure",
    "COLOR_13": "Blue", "COLOR_14": "Violet", "COLOR_15": "Pink",
}


def custom_action_label(name: str) -> str:
    """Return a friendly categorized label for HA's native multi-select control."""
    if name.startswith("FUNCTION_") and name[9:].isdigit():
        return f"Device-specific · Function {name[9:]}"
    category = CUSTOM_ACTION_CATEGORIES.get(name, "Other")
    display_name = CUSTOM_ACTION_DISPLAY_NAMES.get(
        name, name.replace("_", " ").title()
    )
    return f"{category} · {display_name}"


def custom_action_function(name: str) -> int:
    """Resolve a friendly action name or a preserved device-specific function."""
    if name in CUSTOM_ACTION_FUNCTIONS:
        return CUSTOM_ACTION_FUNCTIONS[name]
    if name.startswith("FUNCTION_") and name[9:].isdigit():
        value = int(name[9:])
        if 0 <= value <= 0xFFFF:
            return value
    raise ValueError(f"unknown editable action {name!r}")


def custom_action_name(function: int) -> str:
    """Return a stable editable name without losing unknown native functions."""
    for name, value in CUSTOM_ACTION_FUNCTIONS.items():
        if value == function:
            return name
    return f"FUNCTION_{function}"


def normalize_main_buttons(value: object) -> dict[str, str]:
    """Normalize legacy main-button lists and the universal position map."""
    if isinstance(value, dict):
        result: dict[str, str] = {}
        for raw_position, raw_action in value.items():
            position = str(raw_position).upper()
            action = str(raw_action)
            if position not in TAG:
                raise ValueError(f"unknown main-page position {position!r}")
            custom_action_function(action)
            result[position] = action
        return result
    if isinstance(value, list):
        result = {}
        for raw_name in value:
            name = str(raw_name)
            if name not in CUSTOM_MAIN_BUTTONS:
                raise ValueError(f"unknown legacy main button {name!r}")
            index, function = CUSTOM_MAIN_BUTTONS[name]
            position = next(tag for tag, tag_index in TAG.items() if tag_index == index)
            result[position] = custom_action_name(function)
        return result
    return {}


def editable_layout_from_native_profile(device_type_name: str) -> dict:
    """Materialize any recovered native profile as an editable Main/A-D layout."""
    key = device_type_name.upper()
    profile_name = NATIVE_PROFILE_ALIASES.get(key)
    if profile_name is None:
        raise ValueError(f"unknown native layout {device_type_name!r}")
    profile = NATIVE_PROFILE_LAYOUTS[profile_name]
    positions = {value: name for name, value in TAG.items()}
    main: dict[str, str] = {}
    pages: dict[str, list[str]] = {}
    page_names: dict[str, str] = {}
    for raw_page, raw_keys in profile["pages"].items():
        page = int(raw_page)
        keys = raw_keys() if callable(raw_keys) else [dict(item) for item in raw_keys]
        if page == 0:
            for item in keys:
                if not item.get("cmd"):
                    continue
                position = positions.get(int(item["keyIndex"]))
                if position is not None:
                    main[position] = custom_action_name(int(item.get("keyFun", 0)))
            continue
        actions = [
            custom_action_name(int(item.get("keyFun", 0)))
            for item in keys
            if item.get("cmd")
        ]
        if actions:
            pages[str(page)] = actions
            page_names[str(page)] = (
                "Colors" if profile_name in {"BULB", "STRIP"} else f"Page {'ABCD'[page - 1]}"
            )
    return {
        "layout_version": 2,
        "main_buttons": main,
        "pages": pages,
        "page_names": page_names,
        "template": profile_name,
    }


def custom_action_ha_icon(name: str) -> str:
    """Return an MDI hint for an enriched Home Assistant event."""
    if name.startswith("COLOR_"):
        return "mdi:palette"
    if name.startswith("SPEED_"):
        return "mdi:fan-speed-3"
    if name.startswith("LEVEL_"):
        return "mdi:signal-cellular-2"
    return CUSTOM_ACTION_HA_ICONS.get(name, "mdi:remote")


def custom_native_layout(
    main_buttons: list[str] | dict[str, str], page_buttons: dict[int, list[str]],
) -> dict[int, list[dict]]:
    """Build a validated editable Main/A/B/C/D page map for the fake bridge."""
    normalized_main = normalize_main_buttons(main_buttons)
    enabled_pages = {int(page) for page, actions in page_buttons.items() if actions}
    pages: dict[int, list[dict]] = {
        0: [
            _button(TAG[position], custom_action_function(action))
            for position, action in normalized_main.items()
            if not (
                position in "ABCD"
                and (ord(position) - ord("A") + 1) in enabled_pages
            )
        ]
    }
    for page_index in sorted(page_buttons):
        if page_index not in CUSTOM_PAGE_LINK_FUNCTIONS:
            raise ValueError("custom page must be A, B, C or D")
        actions = page_buttons[page_index]
        if not actions:
            continue
        if len(actions) > 18:
            raise ValueError("a custom page can contain at most 18 buttons")
        for action in actions:
            custom_action_function(action)
        # A-D without a command are native submenu links.  Their official Fan-family keyFun
        # values are the only captured layout that exposes all four subpages at once.
        pages[0].append(_button(page_index - 1, CUSTOM_PAGE_LINK_FUNCTIONS[page_index], actionable=False))
        pages[page_index] = [
            _button(index, custom_action_function(name))
            for index, name in enumerate(actions)
        ]
    if not pages[0]:
        raise ValueError("the custom main page must contain a button or a page link")
    return pages

# Real WoStrip/WoFloorLamp V2.1 main page, verified against StripKeyHandler.getKeyListMain.
# Commands include their 0x57 device-protocol prefix: these bytes are stored in the remote and
# later written verbatim to the native target when a physical button is pressed.
STRIP_MAIN_KEYS = [
    # (keyIndex, keyFun, cmd)
    (TAG["ON"], 5, [0x57, 0x0F, 0x49, 0x01, 0x01]),
    (TAG["OFF"], 6, [0x57, 0x0F, 0x49, 0x01, 0x02]),
    (TAG["UP"], 300, [0x57, 0x0F, 0x49, 0x01, 0x44, 0x00, 0x0A]),      # brighter
    (TAG["DOWN"], 301, [0x57, 0x0F, 0x49, 0x01, 0x44, 0x01, 0x0A]),     # darker
    (TAG["VOLADD"], 300, [0x57, 0x0F, 0x49, 0x01, 0x44, 0x00, 0x0A]),
    (TAG["VOLDEL"], 301, [0x57, 0x0F, 0x49, 0x01, 0x44, 0x01, 0x0A]),
    (TAG["A"], 321, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0xFF, 0xFF, 0xFF]),
    (TAG["B"], 323, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0xD2, 0xF0, 0xFF]),
    (TAG["C"], 322, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0xFF, 0xF0, 0xD2]),
    (TAG["D"], 330, None),
]
# Empty datasource entries are still serialized as placeholders. KATA is not part of this page.
STRIP_PLACEHOLDER_TAGS = [TAG["LEFT"], TAG["RIGHT"], TAG["OK"], TAG["BACK"], TAG["HOME"],
                          TAG["SOUNDOFF"], TAG["CHUP"], TAG["CHDOWN"]]

# WoStrip V2.1 page D. The app writes this second page after the main page; D on page 0 is a
# submenu link, not a device command. Acknowledging page 0 alone does not prove that the native
# model has been completely installed.
STRIP_COLOR_KEYS = [
    (331, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0xFF, 0x00, 0x00]),
    (332, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0xF4, 0x4A, 0x4A]),
    (333, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0xFF, 0x83, 0x48]),
    (334, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0xFD, 0xA1, 0x04]),
    (335, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0xFF, 0xF3, 0x30]),
    (336, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0x96, 0xED, 0x5D]),
    (337, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0x23, 0xFF, 0x91]),
    (338, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0x00, 0xFF, 0x38]),
    (339, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0x06, 0xFE, 0xDE]),
    (340, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0x37, 0xD9, 0xF4]),
    (341, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0x03, 0xA4, 0xFF]),
    (342, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0x03, 0x6A, 0xFF]),
    (343, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0x00, 0x38, 0xFF]),
    (344, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0x78, 0x4E, 0xF9]),
    (345, [0x57, 0x0F, 0x49, 0x01, 0x12, 0x64, 0xF4, 0x4A, 0xA7]),
]


def strip_light_keys() -> list[dict]:
    """Full page-0 key list for a WoStrip/WoFloorLamp remote (real keys + placeholders)."""
    keys = [{"keyIndex": i, "keyFun": f, "cmd": c} for (i, f, c) in STRIP_MAIN_KEYS]
    keys += [{"keyIndex": t, "keyFun": 0} for t in STRIP_PLACEHOLDER_TAGS]
    return keys


def strip_color_keys() -> list[dict]:
    """The fifteen colour commands on the official WoStrip page-D submenu."""
    return [
        {"keyIndex": index, "keyFun": key_fun, "cmd": cmd}
        for index, (key_fun, cmd) in enumerate(STRIP_COLOR_KEYS)
    ]

# iconCode: light=1 desklamp=2 floorlamp=3 ceilinglamp=4 strip=5 switch=6 ... tv=10.
ICON = {"light": 1, "desklamp": 2, "floorlamp": 3, "ceilinglamp": 4, "strip": 5,
        "switch": 6, "tv": 10}

# bleKeyType for UniversalBLE keys.
BLE_KEY_TYPE_UNIVERSAL = 6
IR_TRANSFER_PART_SIZE = 4096


# ---- builders ------------------------------------------------------------------------------


def build_status_poll() -> bytes:
    """Minimal status poll; device replies 4F2D... on notify."""
    return bytes([0x02])


def build_set_target_key(key_id: int, key: bytes) -> bytes:
    """Store the 16-byte AES key used when the remote connects to a native target (0F 20 09)."""
    if not 0 <= key_id <= 0xFF:
        raise ValueError("target key id must fit in one byte")
    if len(key) != 16:
        raise ValueError("target key must be exactly 16 bytes")
    return bytes([0x0F, 0x20, 0x09, key_id]) + key


def build_associate_target_key(key_id: int, device_id: str) -> bytes:
    """Associate a stored target key with the native target's 11-byte device id (0F 20 08)."""
    if not 0 <= key_id <= 0xFF:
        raise ValueError("target key id must fit in one byte")
    return bytes([0x0F, 0x20, 0x08, key_id]) + id_to_bytes(device_id)


def build_native_bind_sequence(
    *,
    key_id: int,
    target_key: bytes,
    device_type_name: str,
    remote_index: int,
    name: str,
    device_id: str,
    icon_name: str = "strip",
    control_mode: int = 0,
    event_remote_id: str | None = None,
) -> tuple[tuple[str, bytes], ...]:
    """Return target-key, association, and every official native-device page command."""
    pages = build_native_pages(
        device_type_name=device_type_name,
        remote_index=remote_index,
        name=name,
        device_id=device_id,
        icon_name=icon_name,
        control_mode=control_mode,
        event_remote_id=event_remote_id,
    )
    profile_name = NATIVE_PROFILE_ALIASES[device_type_name.upper()]
    page_indexes = tuple(NATIVE_PROFILE_LAYOUTS[profile_name]["pages"])
    page_stages = []
    for page_index, page in zip(page_indexes, pages, strict=True):
        if page_index == 0:
            stage = "bind_main"
        elif profile_name == "STRIP" and page_index == 4:
            stage = "bind_colors"
        else:
            stage = f"bind_page_{page_index}"
        page_stages.append((stage, page))
    return (
        ("set_key", build_set_target_key(key_id, target_key)),
        ("associate", build_associate_target_key(key_id, device_id)),
        *page_stages,
    )


def device_type_bytes(device_type: int | bytes | bytearray) -> bytes:
    """Encode the one- or four-byte device type used by the official app."""
    if isinstance(device_type, (bytes, bytearray)):
        value = bytes(device_type)
    elif 0 <= device_type <= 0xFF:
        value = bytes([device_type])
    elif 0 <= device_type <= 0xFFFFFFFF:
        value = device_type.to_bytes(4, "big")
    else:
        raise ValueError("device type must fit in one or four bytes")
    if len(value) not in (1, 4):
        raise ValueError("device type must contain one or four bytes")
    return value


def build_hid_pair(host_mac: str) -> bytes:
    """startPairHIDDevice: tell the remote to HID-pair (become a BLE keyboard) to `host_mac`.

    `host_mac` = the TARGET host's real BLE MAC (12 hex). Response 01=ok, 11=HIDNoPairError.
    NOTE: the host must accept the incoming BLE-HID pairing (Linux/BlueZ; macOS does not).
    """
    return bytes([0x0F, 0x62, 0x0E, 0x01]) + id_to_bytes(host_mac)


def build_create(
    remote_index: int,
    device_type: int | bytes,
    control_type: int,
    control_mode: int,
    icon: int,
    device_id: str,
    name: str,
    ble_key_type: int,
    keys: list[dict],
    page_index: int = 0,
    big_endian: bool = True,
) -> bytes:
    """Create/bind one page of a remote (0F 62 06; assembleKeysByPage layout).

    keys: list of {keyIndex:int, keyFun:int, cmd:bytes|None}. When `cmd` is given it is an IR/raw
    code field (20 bytes + len, padded to 32); otherwise the 32-byte field holds keyFun.
    """
    name_bytes = bytearray(pad(name.encode("utf-8"), 64))
    name_bytes[63] = 0
    v = bytearray()
    v.append(remote_index & 0xFF)
    v += device_type_bytes(device_type)
    v += bytes([control_type & 0xFF, control_mode & 0xFF, icon & 0xFF])
    v += id_to_bytes(device_id)
    v += bytes(name_bytes)
    v += bytes([0x00, page_index & 0xFF, len(keys) & 0xFF])
    for k in keys:
        key_index = k["keyIndex"] & 0xFF
        key_fun = k.get("keyFun", 0)
        cmd = k.get("cmd")
        if "field32" in k:
            field = bytes(k["field32"])
            if len(field) != 32:
                raise ValueError("key field must be exactly 32 bytes")
        elif cmd:
            field = pad(pad(bytes(cmd), 20) + bytes([len(cmd)]), 32)
        else:
            field = pad(s16(key_fun, big_endian), 32)
        v += bytes([key_index]) + s16(key_fun, big_endian) + bytes([k.get("key_type", ble_key_type) & 0xFF]) + field
    length = s16(len(v), big_endian)
    crc = s16(crc16_modbus(bytes(v)), big_endian)
    return bytes([0x0F, 0x62, 0x06]) + length + crc + bytes(v)


def build_hid_edit_page(
    *, remote_index: int, device_type_name: str, device_id: str, name: str,
    keys: list[dict], page_index: int = 0,
) -> bytes:
    """Official getHidEditKeysCmd records: HID usage or uploaded custom IR name.

    IR names reference separately uploaded transferZipData(type=3) payloads.
    This builder neither uploads those payloads nor changes the existing HID bond.
    """
    device_type = DEVTYPE.get(device_type_name.upper())
    if device_type not in (0xF0, 0xF1, 0xF2, 0xF3):
        raise ValueError("expected a HID device type")
    if not 0 <= page_index <= 4 or len(keys) > (18 if page_index == 0 else 15):
        raise ValueError("invalid HID page or button count")
    records = []
    indexes = set()
    for key in keys:
        index = int(key["index"])
        if not 0 <= index <= (18 if page_index == 0 else 14) or index in indexes:
            raise ValueError("invalid or duplicate button position")
        indexes.add(index)
        if "ir_name" in key:
            ir_name = str(key["ir_name"])
            encoded = ir_name.encode("utf-8")
            if not encoded or len(encoded) > 31 or "/" in ir_name or "\x00" in ir_name:
                raise ValueError("IR key name must be 1–31 UTF-8 bytes without slash or NUL")
            function, key_type, field = 0x07D3, 2, pad(encoded, 32)
        else:
            usage = bytes(key["hid_usage"])
            if len(usage) != 2:
                raise ValueError("HID usage must contain two bytes")
            function, key_type, field = int.from_bytes(usage, "big"), 6, pad(usage, 32)
        records.append({"keyIndex": index, "keyFun": function, "key_type": key_type, "field32": field})
    return build_create(
        remote_index=remote_index, device_type=device_type, control_type=CTRL_HID,
        control_mode=0, icon=0, device_id=device_id, name=name,
        ble_key_type=6, keys=records, page_index=page_index,
    )


def build_hid_ir_transfer(*, device_id: str, key_name: str, code: bytes) -> tuple[tuple[str, bytes, frozenset[int]], ...]:
    """Named custom IR upload from official HID editor (transfer type 3).

    Code is the decompressed codeToHex payload, not a bank offset or gzip/base64 text.
    Unlike the captured full-bank transfer, this editor requires status 01 at every stage.
    """
    encoded = key_name.encode("utf-8")
    if not encoded or len(encoded) > 31 or "/" in key_name or "\x00" in key_name:
        raise ValueError("IR key name must be 1–31 UTF-8 bytes without slash or NUL")
    return tuple(
        (stage, packet, frozenset({1}))
        for stage, packet, _accepted in build_ir_transfer_sequence(
            id_to_bytes(device_id), code, data_type=3, transfer_name=key_name
        )
    )


def build_delete_hid_keys(*, remote_index: int, device_type_name: str, device_id: str) -> bytes:
    """Official getDeleteHIDKeysCmd(page=255), preserving the remote entry/bond."""
    device_type = DEVTYPE.get(device_type_name.upper())
    if device_type not in (0xF0, 0xF1, 0xF2, 0xF3):
        raise ValueError("expected a HID device type")
    return bytes([0x0F, 0x62, 0x04, 1, remote_index, device_type, CTRL_HID]) + id_to_bytes(device_id) + b"\xff\xff"


def build_delete(
    remote_index: int,
    device_type: int | bytes,
    control_type: int,
    device_id: str,
) -> bytes:
    """Delete a remote (0F 62 04 02; deleteDeviceByIdBin).

    Layout: 0F 62 04 02 <remoteIndex> <devType> <ctrlType> <deviceID 11B reversed>.
    """
    compact = device_id.replace(":", "").replace("-", "")
    # Cloud IR remotes use an opaque 11-byte remoteID, while BLE/native targets use a
    # six-byte MAC reversed and padded to the same field width.
    device_id_bytes = bytes.fromhex(compact) if len(compact) == 22 else id_to_bytes(device_id)
    return (
        bytes([0x0F, 0x62, 0x04, 0x02, remote_index & 0xFF])
        + device_type_bytes(device_type)
        + bytes([control_type & 0xFF])
        + device_id_bytes
    )


def build_rename(
    *, remote_index: int, device_type: int | bytes, control_type: int,
    device_id: bytes, name: str,
) -> bytes:
    """Rename an existing remote (official app's ``changeBleDeviceName`` command)."""
    if len(device_id) != 11:
        raise ValueError("device id must be exactly 11 bytes")
    name_bytes = bytearray(pad(name.encode("utf-8"), 64))
    name_bytes[63] = 0
    return (
        bytes([0x0F, 0x62, 0x07, remote_index & 0xFF])
        + device_type_bytes(device_type)
        + bytes([control_type & 0xFF])
        + device_id
        + bytes(name_bytes)
    )


def build_ir_empty_remote(
    *, remote_index: int, device_type: int, remote_id: bytes, name: str, icon: int = 0
) -> bytes:
    """Create the header-only IR remote written before the official sync transaction."""
    if len(remote_id) != 11:
        raise ValueError("IR remote id must be exactly 11 bytes")
    name_bytes = bytearray(pad(name.encode("utf-8"), 64))
    name_bytes[63] = 0
    body = (
        bytes([remote_index & 0xFF, device_type & 0xFF, CTRL_IR, 0, icon & 0xFF])
        + remote_id
        + bytes(name_bytes)
        + b"\x00\x00\x00"
    )
    return (
        b"\x0f\x62\x06"
        + s16(len(body))
        + s16(crc16_modbus(body))
        + body
    )


def build_ir_sync(remote_count: int, phase: int) -> bytes:
    """Build the official 0F620C IR sync boundary (phase 1=start, 3=end)."""
    if phase not in (1, 3):
        raise ValueError("IR sync phase must be 1 (start) or 3 (end)")
    return bytes([0x0F, 0x62, 0x0C, remote_count & 0xFF, phase])


def build_ir_transfer_sequence(
    remote_id: bytes,
    code_bank: bytes,
    *,
    data_type: int = 0,
    transfer_name: str = "",
) -> tuple[tuple[str, bytes, frozenset[int]], ...]:
    """Build the 0F6201/02/03 transfer recovered from the official application.

    The WoRWS wire acknowledgements for these three commands differ from normal command
    acknowledgements: the captured successful transfer returned 10 00 for initialise and
    00 00 (the part number) for part zero.  Accept those values alongside firmware variants
    that return the usual 01 status.
    """
    if len(remote_id) != 11:
        raise ValueError("IR remote id must be exactly 11 bytes")
    if not code_bank:
        raise ValueError("IR code bank must not be empty")
    name = bytearray(pad(transfer_name.encode("utf-8"), 32))
    name[31] = 0
    total_len = len(code_bank).to_bytes(4, "big")
    parts = [
        code_bank[offset:offset + IR_TRANSFER_PART_SIZE]
        for offset in range(0, len(code_bank), IR_TRANSFER_PART_SIZE)
    ]
    commands: list[tuple[str, bytes, frozenset[int]]] = [
        (
            "ir_transfer_init",
            b"\x0f\x62\x01" + remote_id + bytes([data_type & 0xFF]) + bytes(name) + total_len,
            frozenset({0x01, 0x10}),
        )
    ]
    for index, part in enumerate(parts):
        commands.append(
            (
                f"ir_transfer_part_{index}",
                b"\x0f\x62\x02" + s16(index) + s16(crc16_modbus(part)) + part,
                frozenset({0x00, 0x01}),
            )
        )
    commands.append(
        (
            "ir_transfer_finish",
            b"\x0f\x62\x03"
            + s16(len(parts))
            + total_len
            + s16(crc16_modbus(code_bank)),
            frozenset({0x00, 0x01}),
        )
    )
    return tuple(commands)


def studio_pages_from_packets(packets: tuple[bytes, ...]) -> list[dict]:
    """Describe validated IR pages without discarding code-bank references."""
    positions = {value: key for key, value in TAG.items()}
    pages = []
    for packet in packets:
        rewrite_ir_page(packet, remote_index=packet[7], name="")
        body = packet[7:]
        page = body[81]
        buttons = []
        for offset in range(83, len(body), 36):
            record = body[offset:offset + 36]
            # Type 4 records navigate between pages; they are not presses sent to a device.
            if record[3] == 4:
                continue
            index = record[0]
            function = int.from_bytes(record[1:3], "big")
            buttons.append({
                "index": index, "function": function,
                "label": positions.get(index, f"Function {function}") if page == 0
                else f"Function {function}",
            })
        pages.append({"index": page, "name": "Main" if page == 0 else f"Page {page}", "buttons": buttons})
    return pages


def rewrite_ir_page(packet: bytes, *, remote_index: int, name: str) -> bytes:
    """Validate a captured 0F6206 IR page and rewrite its slot/name with a fresh CRC."""
    if len(packet) < 90 or packet[:3] != b"\x0f\x62\x06":
        raise ValueError("invalid IR page packet")
    body_len = int.from_bytes(packet[3:5], "big")
    body = bytearray(packet[7:])
    if body_len != len(body) or crc16_modbus(body) != int.from_bytes(packet[5:7], "big"):
        raise ValueError("IR page length or CRC is invalid")
    if body[2] != CTRL_IR or len(body) != 83 + 36 * body[82]:
        raise ValueError("IR page body layout is invalid")
    body[0] = remote_index & 0xFF
    name_bytes = bytearray(pad(name.encode("utf-8"), 64))
    name_bytes[63] = 0
    body[16:80] = name_bytes
    return (
        b"\x0f\x62\x06"
        + s16(len(body))
        + s16(crc16_modbus(body))
        + bytes(body)
    )


def build_ir_pages(
    *,
    remote_index: int,
    device_type: int,
    remote_id: bytes,
    name: str,
    key_map: list[tuple[int, int, int]],
    icon: int = 0,
    max_pages: int = 5,
) -> tuple[bytes, ...]:
    """Build generic WoRWS IR pages from ``(keyFun, offset, length)`` entries.

    The official app uses the same 83-byte page header and 36-byte key records.  A key
    record references a slice of the separately uploaded code bank; it does not embed the
    IR payload.  WoRWS supports up to five pages with eighteen screen positions each.
    """
    if len(remote_id) != 11:
        raise ValueError("IR remote id must be exactly 11 bytes")
    if not key_map:
        raise ValueError("IR key map must not be empty")
    if len(key_map) > max_pages * 18:
        raise ValueError("IR key map contains more than 90 displayable keys")
    name_bytes = bytearray(pad(name.encode("utf-8"), 64))
    name_bytes[63] = 0
    pages: list[bytes] = []
    for page_index, first in enumerate(range(0, len(key_map), 18)):
        page_keys = key_map[first:first + 18]
        body = bytearray(
            bytes([
                remote_index & 0xFF,
                device_type & 0xFF,
                CTRL_IR,
                0,
                icon & 0xFF,
            ])
            + remote_id
            + bytes(name_bytes)
            + bytes([0, page_index & 0xFF, len(page_keys) & 0xFF])
        )
        for key_index, (key_fun, offset, length) in enumerate(page_keys):
            if not 0 <= key_fun <= 0xFFFF:
                raise ValueError("IR key function must fit in two bytes")
            if not 0 <= offset <= 0xFFFFFFFF or not 0 < length <= 0xFFFF:
                raise ValueError("IR code-bank reference is out of range")
            body += (
                bytes([key_index])
                + s16(key_fun)
                + b"\x01"
                + offset.to_bytes(4, "big")
                + s16(length)
                + bytes(26)
            )
        pages.append(
            b"\x0f\x62\x06"
            + s16(len(body))
            + s16(crc16_modbus(body))
            + bytes(body)
        )
    return tuple(pages)


def parse_added_devices(raw: bytes) -> list[tuple[int, int, int, bytes]]:
    """Parse the unencrypted 0F 63 07 response into 14-byte table entries."""
    if len(raw) < 9 or raw[:4] != b"\x01\x00\x00\x00":
        raise ValueError(f"unexpected device-table response header: {raw.hex()}")
    body_length = int.from_bytes(raw[4:6], "big")
    body = raw[8:8 + body_length]
    if len(body) != body_length:
        raise ValueError("truncated device-table response")
    count = body[0]
    items: list[tuple[int, int, int, bytes]] = []
    offset = 1
    for _ in range(count):
        # Newer SwitchBot products use a four-byte device type beginning with 00;
        # legacy products use one byte.  The remainder of each table record is fixed.
        type_length = 4 if offset + 4 <= len(body) and body[offset + 1] == 0 else 1
        record_length = 1 + type_length + 1 + 11
        entry = body[offset:offset + record_length]
        if len(entry) != record_length:
            raise ValueError("truncated device-table entry")
        device_type = int.from_bytes(entry[1:1 + type_length], "big")
        control_offset = 1 + type_length
        items.append((entry[0], device_type, entry[control_offset], entry[control_offset + 1:]))
        offset += record_length
    if offset != len(body):
        raise ValueError(
            f"device-table count/length mismatch: count={count}, body_length={len(body)}"
        )
    return items


def build_set_state_ac(temp: int, mode: int, fan: int, power_on: bool) -> bytes:
    """AC set-state (0F 41 02): draws temperature/mode/fan on the remote's screen.

    Field semantics are the appliance's AC model; exposed for the documented AC use-case. For a
    non-AC editable remote the screen is driven by the remote's own page, not this command.
    """
    return bytes([0x0F, 0x41, 0x02, temp & 0xFF, mode & 0xFF, fan & 0xFF, 0x01 if power_on else 0x00])


def default_universal_keys() -> list[dict]:
    """A sensible default UniversalBLE (HID) key set (ON/OFF/UP/DOWN/OK)."""
    return [
        {"keyIndex": TAG["ON"], "keyFun": TAG["ON"]},
        {"keyIndex": TAG["OFF"], "keyFun": TAG["OFF"]},
        {"keyIndex": TAG["UP"], "keyFun": TAG["UP"]},
        {"keyIndex": TAG["DOWN"], "keyFun": TAG["DOWN"]},
        {"keyIndex": TAG["OK"], "keyFun": TAG["OK"]},
    ]


def build_remote(
    device_type_name: str,
    remote_index: int,
    name: str,
    device_id: str,
    icon_name: str = "light",
    buttons: list[str] | None = None,
    control_mode: int = 0,
) -> bytes:
    """Build a create command for either a HID or a native-device remote by type name.

    HID types (UNIVERSAL_BLE/GOOGLE_TV/FIRE_TV/APPLE_TV): controlType 4, keyFun keys, needs a
    prior HID-pair. Native types use controlType 0 and point at the fake-device add-on MAC.
    """
    key = device_type_name.upper()
    icon = ICON.get(icon_name.lower(), 1)
    if key in NATIVE_DEVTYPE:
        return build_native_pages(
            device_type_name=key, remote_index=remote_index, name=name,
            device_id=device_id, icon_name=icon_name, control_mode=control_mode,
        )[0]
    if key in DEVTYPE:
        names = buttons or ["ON", "OFF", "UP", "DOWN", "OK"]
        keys = [{"keyIndex": TAG[n], "keyFun": TAG[n]} for n in names if n in TAG]
        return build_create(
            remote_index=remote_index, device_type=DEVTYPE[key],
            control_type=CTRL_HID, control_mode=control_mode, icon=icon,
            device_id=device_id, name=name, ble_key_type=BLE_KEY_TYPE_UNIVERSAL, keys=keys,
        )
    raise ValueError(f"unknown device_type {device_type_name!r}")


def build_native_pages(
    *,
    device_type_name: str,
    remote_index: int,
    name: str,
    device_id: str,
    icon_name: str = "light",
    control_mode: int = 0,
    event_remote_id: str | None = None,
) -> tuple[bytes, ...]:
    """Build every 0F6206 page written by the app for a supported native device.

    Layouts and page numbers mirror the app's native BleKeyHandlerFactory handlers.
    """
    key = device_type_name.upper()
    if key not in NATIVE_PROFILE_ALIASES:
        raise ValueError(f"unknown native layout {key!r}")
    profile_name = NATIVE_PROFILE_ALIASES[key]
    profile = NATIVE_PROFILE_LAYOUTS[profile_name]
    effective_control_mode = int(profile.get("control_mode", control_mode))
    common = {
        "remote_index": remote_index,
        "device_type": NATIVE_DEVTYPE[key],
        "control_type": CTRL_NATIVE,
        "control_mode": effective_control_mode,
        "icon": ICON.get(icon_name.lower(), 1),
        "device_id": device_id,
        "name": name,
        "ble_key_type": 0,
    }
    pages: list[bytes] = []
    for page_index, page_keys in profile["pages"].items():
        keys = page_keys() if callable(page_keys) else [dict(item) for item in page_keys]
        pages.append(build_create(
            **common,
            keys=_tag_bridge_keys(
                keys, remote_id=event_remote_id, remote_slot=remote_index,
                page_index=page_index, profile_id=int(profile["id"]),
            ),
            page_index=page_index,
        ))
    return tuple(pages)


def build_custom_native_pages(
    *,
    remote_index: int,
    name: str,
    device_id: str,
    icon_name: str,
    event_remote_id: str,
    main_buttons: list[str] | dict[str, str],
    page_buttons: dict[int, list[str]],
) -> tuple[tuple[int, bytes], ...]:
    """Build an editable multi-page native remote.

    FAN is used as the screen template because its official handler exposes all four A-D
    subpages.  The target is still the same fake bridge MAC/key and every actionable key stores
    a v3 bridge event rather than a real fan command.
    """
    layout = custom_native_layout(main_buttons, page_buttons)
    common = {
        "remote_index": remote_index,
        "device_type": NATIVE_DEVTYPE["FAN"],
        "control_type": CTRL_NATIVE,
        "control_mode": 0,
        "icon": ICON.get(icon_name.lower(), 1),
        "device_id": device_id,
        "name": name,
        "ble_key_type": 0,
    }
    return tuple(
        (
            page_index,
            build_create(
                **common,
                keys=_tag_bridge_keys(
                    keys,
                    remote_id=event_remote_id,
                    remote_slot=remote_index,
                    page_index=page_index,
                    profile_id=0xFE,
                ),
                page_index=page_index,
            ),
        )
        for page_index, keys in layout.items()
    )


def build_custom_native_bind_sequence(
    *,
    key_id: int,
    target_key: bytes,
    remote_index: int,
    name: str,
    device_id: str,
    icon_name: str,
    event_remote_id: str,
    main_buttons: list[str] | dict[str, str],
    page_buttons: dict[int, list[str]],
) -> tuple[tuple[str, bytes], ...]:
    """Return provisioning plus all pages for an editable native bridge remote."""
    pages = build_custom_native_pages(
        remote_index=remote_index,
        name=name,
        device_id=device_id,
        icon_name=icon_name,
        event_remote_id=event_remote_id,
        main_buttons=main_buttons,
        page_buttons=page_buttons,
    )
    return (
        ("set_key", build_set_target_key(key_id, target_key)),
        ("associate", build_associate_target_key(key_id, device_id)),
        *((f"bind_page_{page_index}", command) for page_index, command in pages),
    )


def devtype_byte(device_type_name: str) -> int:
    """Return the devType byte for a type name (for delete)."""
    key = device_type_name.upper()
    if key in NATIVE_DEVTYPE:
        return NATIVE_DEVTYPE[key]
    if key in DEVTYPE:
        return DEVTYPE[key]
    if key == "IR_TV":
        return 0x02
    raise ValueError(f"unknown device_type {device_type_name!r}")


def control_type_for(device_type_name: str) -> int:
    key = device_type_name.upper()
    if key in NATIVE_DEVTYPE:
        return CTRL_NATIVE
    if key == "IR_TV":
        return CTRL_IR
    return CTRL_HID


