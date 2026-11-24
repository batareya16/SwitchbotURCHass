"""Translate SwitchBot IR catalog tags into WoRWS V48 screen functions."""

# The official app's get*fun_key_name tables translate catalog tags before writing
# 0F 62 06. The DSP IR screen (0x2002fbf0 -> 0x2002f858 -> 0x20023ac0)
# reads keyFun from a key record and selects the corresponding RES.bin image.
_IR_TAG_FUNCTIONS = {
    2: {  # TV
        1: 16, 2: 221, 3: 17, 4: 222, 5: 13, 6: 224, 7: 18, 8: 106,
        9: 15, 10: 101, 11: 105, 12: 102, 13: 19, 14: 103, 15: 41, 16: 104,
        17: 42, 18: 220, 19: 43, 20: 109, 21: 44, 22: 211, 23: 45, 24: 212,
        25: 46, 26: 213, 27: 47, 28: 214, 29: 48, 30: 203, 31: 49, 32: 25,
        34: 21, 36: 26, 38: 27, 39: 12, 40: 22, 41: 11, 42: 28, 43: 9,
        44: 24, 45: 7, 46: 23, 47: 8, 48: 111, 49: 10, 50: 223, 51: 200,
        53: 201, 55: 202, 57: 114,
    },
    3: {  # IPTV
        1: 105, 2: 5, 3: 19, 4: 6, 5: 15, 6: 800, 7: 16, 8: 802,
        10: 801, 12: 118, 13: 9, 14: 116, 15: 7, 17: 11, 19: 8, 21: 10,
        25: 41, 27: 42, 29: 43, 31: 44, 33: 45, 35: 46, 37: 47, 39: 48,
        41: 49, 43: 40, 45: 12,
    },
    4: {  # TVBox
        1: 105, 2: 5, 3: 41, 4: 6, 5: 42, 6: 800, 7: 43, 8: 802,
        9: 44, 10: 801, 11: 45, 12: 118, 13: 46, 15: 47, 16: 116, 17: 48,
        18: 109, 19: 49, 23: 40, 25: 12, 27: 9, 29: 7, 31: 11, 33: 8,
        35: 10, 37: 15, 39: 16, 41: 17, 43: 18, 45: 19,
    },
    5: {  # DVD
        1: 19, 2: 118, 4: 23, 6: 16, 8: 15, 10: 9, 11: 105, 12: 7,
        14: 10, 15: 25, 16: 8, 17: 21, 18: 11, 19: 26, 20: 12, 21: 27,
        24: 116, 25: 28, 26: 41, 28: 42, 29: 22, 30: 43, 32: 44, 33: 111,
        34: 45, 36: 46, 38: 47, 40: 48, 42: 49, 44: 40,
    },
    6: {  # Fan
        1: 105, 2: 5, 4: 6, 5: 89, 6: 113, 8: 19, 9: 90, 39: 72,
        41: 73, 43: 74,
    },
    7: {  # Projector
        1: 5, 2: 105, 3: 6, 4: 118, 6: 11, 8: 700, 10: 21, 12: 12,
        14: 116, 15: 107, 17: 108, 23: 9, 25: 7, 27: 8, 29: 10, 33: 15,
        35: 16, 37: 19, 41: 22,
    },
    8: {  # Camera
        1: 153, 2: 116, 4: 90,
    },
    10: {  # Air
        1: 105, 2: 5, 3: 117, 4: 6, 6: 72, 7: 92, 8: 73, 9: 56,
        10: 74, 11: 113, 12: 57, 13: 58, 14: 112, 15: 19, 16: 90,
    },
    11: {  # Audio
        1: 7, 3: 9, 5: 11, 6: 23, 7: 10, 8: 12, 9: 8, 11: 105,
        12: 41, 13: 15, 14: 42, 15: 19, 16: 43, 17: 16, 18: 44, 19: 25,
        20: 45, 21: 21, 22: 46, 23: 26, 24: 47, 25: 27, 26: 48, 27: 22,
        28: 49, 29: 28, 30: 40,
    },
    12: {  # WHeater
        1: 105, 2: 5, 4: 6, 5: 60, 6: 56, 7: 61, 8: 62, 11: 154,
        13: 90, 15: 92,
    },
    13: {  # Robot
        1: 5, 2: 11, 3: 6, 4: 56, 5: 9, 6: 904, 7: 10, 9: 7,
        11: 8, 15: 900, 37: 92,
    },
    14: {  # Light
        1: 5, 2: 105, 3: 6, 4: 90, 5: 300, 6: 91, 7: 301, 8: 311,
        9: 56, 10: 312, 11: 110, 17: 302, 19: 303,
    },
}

# A–D screen functions written by the stock IR profile builders. They sit
# outside the flat catalog key map, including when a position is disabled.
_IR_SOFTKEY_FUNCTIONS = {
    2: (39, 20, 210, 100),  # TV
    3: (39, 802, 116, 100),  # IPTV
    4: (39, 802, 109, 100),  # Set-top box
    5: (39, 20, 111, 100),  # DVD
    6: (90, 89, 70, 100),  # Fan
    7: (700, 21, 22, 100),  # Projector
    8: (153, 116, 90, 100),  # Camera
    10: (70, 56, 90, 100),  # Air purifier
    11: (39, 27, 28, 100),  # Audio
    12: (56, 154, 62, 100),  # Water heater
    13: (900, 56, 92, 100),  # Robot vacuum
    14: (91, 311, 312, 100),  # Light
}


def _profile(device_type: str) -> int | None:
    if device_type == "IR_TV":
        return 2
    prefix, _, value = device_type.partition("_")
    if prefix != "IR" or not value.isdecimal():
        return None
    number = int(value)
    if 15 <= number <= 22:
        return number - 14
    if 23 <= number <= 27:
        return number - 13
    return number


def catalog_glyphs(device_type: str) -> dict[int, int]:
    """IR tag to firmware glyph table for a known stock profile."""
    return _IR_TAG_FUNCTIONS.get(_profile(device_type), {})


def stock_softkey_glyphs(device_type: str) -> tuple[int, ...]:
    """Firmware glyphs that the stock profile writes at A–D."""
    return _IR_SOFTKEY_FUNCTIONS.get(_profile(device_type), ())


# IR remote types whose window draws a FIXED picture on Main A–D (light, fan, audio, air
# conditioner, and the custom versions of the first three; WoRWS V48, decoded, not run). The
# window shows a key only while the page holds a record whose function is that position's own id,
# and it ignores any icon chosen for the key, so Studio writes these ids and offers no choice.
FIXED_SOFTKEY_TYPES = frozenset({1, 6, 11, 14, 20, 24, 27})

# The ids of those four keys on a fixed window; air conditioner (type 1) is not in the table above.
_FIXED_SOFTKEY_FUNCTIONS = {
    1: (59, 70, 80, 100),
    6: (90, 89, 70, 100),
    11: (39, 27, 28, 100),
    14: (91, 311, 312, 100),
}

# Functions the firmware treats as menu shortcuts. A key with one of these and no page behind it
# shows "No list under this shortcut" when pressed, and never sends its command.
MENU_SHORTCUT_FUNCTIONS = frozenset({
    1, 2, 3, 4, 20, 39, 59, 70, 80, 94, 100, 119, 123, 124, 125, 126, 210, 320, 330,
    914, 915, 916, 917,
})


def _wire_type(device_type: str) -> int | None:
    prefix, _, value = str(device_type).partition("_")
    return int(value) if prefix == "IR" and value.isdecimal() else None


def fixed_softkey_functions(device_type: str) -> tuple[int, ...] | None:
    """The A–D ids a fixed-picture IR window needs, or None for a window that reads the record."""
    wire = _wire_type(device_type)
    if wire not in FIXED_SOFTKEY_TYPES:
        return None
    return _FIXED_SOFTKEY_FUNCTIONS[_profile(device_type)]

# On a fixed window these positions only open the page behind them (with no page the press shows
# "No list under this shortcut"), so a command cannot be put there. Positions are A=0 … D=3.
_PAGE_ONLY_POSITIONS = {
    1: frozenset({0, 1, 2, 3}),
    6: frozenset({2, 3}),
    11: frozenset({3}),
    14: frozenset({3}),
}


def page_only_positions(device_type: str) -> frozenset[int]:
    """Main A–D positions of a fixed-picture window that cannot hold a command."""
    if fixed_softkey_functions(device_type) is None:
        return frozenset()
    return _PAGE_ONLY_POSITIONS[_profile(device_type)]


# The number pad (window 6, `digit`; WoRWS V48 0x20029c84, decoded, not run). A key whose function is
# 39 ("123") opens it instead of a list. It always draws the same 14 keys: the digits in a phone grid
# (1–9, then 0 under 8) and four keys under them. Each one sends the first IR command on the remote
# whose function is its own id (0x20022248), wherever that command is, and only IR commands are sent.
NUMBER_PAD_LINK = 39
# In the order Studio keeps them on the pad page: 1–9, 0, then the keys under the grid (A–D).
NUMBER_PAD_FUNCTIONS = (41, 42, 43, 44, 45, 46, 47, 48, 49, 40, 203, 200, 201, 202)

# Which window an IR remote type opens (its wire type; the custom types are their own numbers).
_TV_WINDOW = frozenset({2, 3, 4, 16, 17, 18})
_AUDIO_WINDOW = frozenset({11, 24})
_INFRARED_WINDOW = frozenset({5, 7, 8, 9, 10, 12, 13, 15, 19, 21, 22, 23, 25, 26})
# Main A–D positions that open a list page, per window (key callbacks of each window). The TV and
# audio windows open the number pad from A whatever the key's function, never a list.
_LIST_POSITIONS = {
    **dict.fromkeys(_TV_WINDOW, frozenset({1, 2, 3})),
    **dict.fromkeys(_AUDIO_WINDOW, frozenset({3})),
    **dict.fromkeys(_INFRARED_WINDOW, frozenset({0, 1, 2, 3})),
    1: frozenset({0, 1, 2, 3}),                         # air conditioner
    6: frozenset({2, 3}), 20: frozenset({2, 3}),        # fan
    14: frozenset({3}), 27: frozenset({3}),             # light
}
# A list link on a window that reads the key's function needs one of the menu-shortcut functions
# other than 39, which would open the number pad. These are the stock pictures, 100 on A.
_LIST_LINK_FUNCTIONS = (100, 20, 210, 100)


def _window_type(device_type: str) -> int | None:
    if str(device_type).upper() == "IR_TV":
        return 2
    return _wire_type(device_type)


def number_pad_positions(device_type: str) -> frozenset[int]:
    """Main A–D positions whose key can open the number pad on this IR remote type."""
    wire = _window_type(device_type)
    if wire in _TV_WINDOW or wire in _AUDIO_WINDOW:
        return frozenset({0})
    if wire in _INFRARED_WINDOW:
        return frozenset({0, 1, 2, 3})
    return frozenset()


def number_pad_always(device_type: str) -> bool:
    """True when the page under A is always the number pad (TV and audio windows)."""
    wire = _window_type(device_type)
    return wire in _TV_WINDOW or wire in _AUDIO_WINDOW


def list_page_positions(device_type: str) -> frozenset[int] | None:
    """Main A–D positions that open a list page, or None for a type whose window is not known."""
    return _LIST_POSITIONS.get(_window_type(device_type))


def list_link_functions(device_type: str) -> tuple[int, ...]:
    """The function each A–D key carries when it opens a list page."""
    return fixed_softkey_functions(device_type) or _LIST_LINK_FUNCTIONS
