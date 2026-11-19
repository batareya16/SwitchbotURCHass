"""IR fan, projector and light pages, laid out the way the official app writes them.

Same idea as ``commands.build_tv_pages`` (read its comment first): the remote finds a key by the
firmware *function id* written next to a *screen position*, never by the cloud key id. The three
handlers in the app's React Native bundle (urc-bundle.js) share one skeleton, ported once here:

* Page 0 is the main page. A cloud key goes to the position that ``get<Type>KeyIndex`` assigns
  it (default positions: ``WORWSTAG_D`` for an unknown key, which page 0 never keeps).
* The soft key D (and, for a fan, C) opens a sub-page. Sub-pages are written only when
  ``getDefaultKeysCount(page) > 0``; their keys are numbered 0, 1, 2... in key-map order and the
  page byte of the header is the sub-page number itself (a fan uses pages 3 and 4, a projector
  and a light only page 4; pages 1 and 2 never exist).
* A cloud ``POWER`` key with no discrete ON/OFF key beside it ("only power", ``getIsOnlyPower``)
  is not a sub-page key: it is written at the end of page 0 twice, on ON and on OFF.
* A main-page slot that the cloud did not fill gets a placeholder record of kind 254 whose
  payload is its function id (A-C for a light, A-B for a fan, A-C for a projector).

Unlike a TV, the app writes the function id of a soft key or placeholder into the first two
payload bytes of its record; it does so here too.

Learned keys (``learned_keys``, the cloud ``keyDetail`` as ordered ``(keyName, keyType)``) follow
the second loop of ``getDefaultKeysCmd``: a name the key map did not write goes, as a kind-2 name
reference, to the page that supports it (position from the key index on page 0, a running counter
elsewhere); every other name that is not a default key of the type goes to page 4 with function
115, up to 15 records on that page. The key map may be empty (a custom remote with code
"no_data"). Without ``learned_keys`` the default-id names in ``custom_keys`` act in id order.

Soft-key gating assumes a remote whose BLE version is >= 21 (the V48 firmware we target): the
soft keys then show only when their sub-page has keys (``urcIsSupport_FE_D`` /
``remoteTag_default``).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import commands

TAG = commands.TAG

# Key kinds of a page record: 1 = slice of the uploaded code bank, 2 = custom key referenced by
# its name, 4 = soft key shown, 254 = soft key hidden / empty placeholder.
_KIND_BANK = 1
_KIND_CUSTOM = 2
_KIND_SOFT = 4
_KIND_EMPTY = 254


@dataclass(frozen=True)
class _Layout:
    """One remote type's page rules."""

    power: int
    on: int
    off: int
    # cloud key id -> firmware function id (``get<Type>_fun_key_name``; ``[hi, lo]`` = hi*256+lo)
    function: dict[int, int]
    # page number -> cloud key ids written on that page (``checkIs<Type>DefaultSupport``)
    pages: dict[int, tuple[int, ...]]
    # cloud key id -> page-0 screen position (``get<Type>KeyIndex``)
    main_position: dict[int, int]
    # page-0 soft keys in write order: (position, function id, gate, argument). Gate "tag" shows
    # the key when any listed cloud key is present (``remoteTag_default``); gate "count" when
    # that sub-page has keys (``getDefaultKeysCount``).
    soft: tuple[tuple[int, int, str, tuple[int, ...] | int], ...]
    # page-0 placeholders in write order: (position, function id, cloud keys that fill the slot)
    placeholders: tuple[tuple[int, int, tuple[int, ...]], ...]


# ---- FAN (type 6, custom 20): module m1118658 ------------------------------------------------
# WOFANTAG_*: POWER 1, ON 2, OFF 4, AUTO_DIR 5, ANION 6, MUTE 8, TIMER 9, WIN_1 39, WIN_2 41,
# WIN_3 43.
_FAN_POWER, _FAN_ON, _FAN_OFF = 1, 2, 4
_FAN_AUTO_DIR, _FAN_ANION, _FAN_MUTE, _FAN_TIMER = 5, 6, 8, 9
_FAN_WIN = (39, 41, 43)
FAN_REMOTE_TYPES = (6, 20)
_FAN = _Layout(
    power=_FAN_POWER, on=_FAN_ON, off=_FAN_OFF,
    # getFan_fun_key_name
    function={
        _FAN_ON: 5, _FAN_POWER: 105, _FAN_OFF: 6, 39: 72, 41: 73, 43: 74, _FAN_ANION: 113,
        _FAN_TIMER: 90, _FAN_AUTO_DIR: 89, _FAN_MUTE: 19,
    },
    # checkIsFanDefaultSupport (page 0: timer, auto direction, on, off; C page 3: wind speeds;
    # D page 4: anion, mute, power)
    pages={
        0: (_FAN_TIMER, _FAN_AUTO_DIR, _FAN_ON, _FAN_OFF),
        3: _FAN_WIN,
        4: (_FAN_ANION, _FAN_MUTE, _FAN_POWER),
    },
    # getFanKeyIndex
    main_position={
        _FAN_ON: TAG["ON"], _FAN_OFF: TAG["OFF"], _FAN_TIMER: TAG["A"], _FAN_AUTO_DIR: TAG["B"],
    },
    # getDefaultKeysCmd: C opens the wind speeds (remoteTag C = WIN_1..3), D the page-4 keys
    soft=((TAG["C"], 70, "tag", _FAN_WIN), (TAG["D"], 100, "count", 4)),
    # getDefaultKeysCmd: A = timer (fun 90), B = auto direction (fun 89)
    placeholders=(
        (TAG["A"], 90, (_FAN_TIMER,)),
        (TAG["B"], 89, (_FAN_AUTO_DIR,)),
    ),
)

# ---- PJT projector (type 7, custom 21): module m1173787 --------------------------------------
# WOPJTTAG_*: ON 1, Power 2, OFF 3, Menu 4, OK 6, Screen 8, Play 10, Back 12, List 14,
# ScreenAdd 15, ScreenDelete 17, Up 23, Left 25, Right 27, Down 29, VolumeAdd 33,
# VolumeDelete 35, Mute 37, Pause 41.
_PJT_POWER, _PJT_ON, _PJT_OFF = 2, 1, 3
_PJT_SCREEN, _PJT_PLAY, _PJT_PAUSE = 8, 10, 41
PJT_REMOTE_TYPES = (7, 21)
_PJT = _Layout(
    power=_PJT_POWER, on=_PJT_ON, off=_PJT_OFF,
    # getProjector_fun_key_name; Screen is [2, 188] = 700
    function={
        _PJT_ON: 5, _PJT_POWER: 105, _PJT_OFF: 6, 12: 12, 4: 118, 14: 116, _PJT_SCREEN: 700,
        _PJT_PLAY: 21, _PJT_PAUSE: 22, 35: 16, 33: 15, 37: 19, 17: 108, 15: 107, 23: 9, 29: 10,
        25: 7, 27: 8, 6: 11,
    },
    # checkIsProjectorDefaultSupport (page 4: power, list)
    pages={
        0: (_PJT_ON, _PJT_OFF, 12, 4, _PJT_SCREEN, _PJT_PLAY, _PJT_PAUSE, 35, 33, 37, 17, 15,
            23, 29, 25, 27, 6),
        4: (_PJT_POWER, 14),
    },
    # getProjectorKeyIndex
    main_position={
        _PJT_ON: TAG["ON"], _PJT_OFF: TAG["OFF"], 12: TAG["BACK"], 4: TAG["HOME"],
        _PJT_SCREEN: TAG["A"], _PJT_PLAY: TAG["B"], _PJT_PAUSE: TAG["C"], 35: TAG["VOLDEL"],
        33: TAG["VOLADD"], 37: TAG["SOUNDOFF"], 17: TAG["CHDOWN"], 15: TAG["CHUP"],
        23: TAG["UP"], 29: TAG["DOWN"], 25: TAG["LEFT"], 27: TAG["RIGHT"], 6: TAG["OK"],
    },
    soft=((TAG["D"], 100, "count", 4),),
    # getDefaultKeysCmd: A = Screen (700), B = Play (21), C = Pause (22)
    placeholders=(
        (TAG["A"], 700, (_PJT_SCREEN,)),
        (TAG["B"], 21, (_PJT_PLAY,)),
        (TAG["C"], 22, (_PJT_PAUSE,)),
    ),
)

# ---- LIGHT (type 14, custom 27): module m1151098 ---------------------------------------------
# WOLIGHTTAG_*: ON 1, POWER 2, OFF 3, TIME 4, BrightnessAdd 5, TIME30M 6, BrightnessDelete 7,
# NIGHT 8, MODE 9, LIGHT 10, SET 11, TemperatureAdd 17, TemperatureDelete 19. (TIMEADD 13 and
# TIMEDELETE 15 are never written by the app.)
_LIGHT_POWER, _LIGHT_ON, _LIGHT_OFF = 2, 1, 3
_LIGHT_TIME, _LIGHT_TIME30M, _LIGHT_NIGHT, _LIGHT_LIGHT = 4, 6, 8, 10
_LIGHT_MODE, _LIGHT_SET = 9, 11
LIGHT_REMOTE_TYPES = (14, 27)
_LIGHT = _Layout(
    power=_LIGHT_POWER, on=_LIGHT_ON, off=_LIGHT_OFF,
    # getLight_fun_key_name; [1, 44] = 300, [1, 45] = 301, [1, 46] = 302, [1, 47] = 303,
    # [1, 55] = 311, [1, 56] = 312
    function={
        _LIGHT_ON: 5, _LIGHT_OFF: 6, _LIGHT_POWER: 105, 5: 300, 7: 301, 17: 302, 19: 303,
        _LIGHT_TIME30M: 91, _LIGHT_NIGHT: 311, _LIGHT_LIGHT: 312, _LIGHT_TIME: 90,
        _LIGHT_MODE: 56, _LIGHT_SET: 110,
    },
    # checkIsLightDefaultSupport (page 4: mode, set, power, time)
    pages={
        0: (_LIGHT_ON, _LIGHT_OFF, 5, 7, 17, 19, _LIGHT_TIME30M, _LIGHT_NIGHT, _LIGHT_LIGHT),
        4: (_LIGHT_MODE, _LIGHT_SET, _LIGHT_POWER, _LIGHT_TIME),
    },
    # getLightKeyIndex: brightness on UP/DOWN, colour temperature on RIGHT (+) / LEFT (-)
    main_position={
        _LIGHT_ON: TAG["ON"], _LIGHT_OFF: TAG["OFF"], 5: TAG["UP"], 7: TAG["DOWN"],
        17: TAG["RIGHT"], 19: TAG["LEFT"], _LIGHT_TIME30M: TAG["A"], _LIGHT_NIGHT: TAG["B"],
        _LIGHT_LIGHT: TAG["C"],
    },
    soft=((TAG["D"], 100, "count", 4),),
    # getDefaultKeysCmd: A = 30 minutes (91), B = night (311), C = light (312)
    placeholders=(
        (TAG["A"], 91, (_LIGHT_TIME30M,)),
        (TAG["B"], 311, (_LIGHT_NIGHT,)),
        (TAG["C"], 312, (_LIGHT_LIGHT,)),
    ),
)


def _name_bytes(name: str) -> bytes:
    """``getKeyNameBytes_32``: slashes dropped, UTF-8, the last of the 32 bytes stays zero."""
    return name.replace("/", "").encode("utf-8")[:31].ljust(32, b"\0")


def _make_builder(layout: _Layout, doc: str) -> Callable[..., tuple[bytes, ...]]:
    # checkIs<Type>DefaultSupport by page, as key-id strings (the app compares strings)
    support = {page: {str(key) for key in keys} for page, keys in layout.pages.items()}
    # checkCustomKeysIsDefaultKey: the keys of every page but 4 (fan: on, off, timer, auto
    # direction, wind speeds; projector and light: the page-0 keys)
    default_keys = {name for page, names in support.items() if page != 4 for name in names}
    power_name, on_name, off_name = str(layout.power), str(layout.on), str(layout.off)

    def function_of(name: str) -> int:
        """``get<Type>_fun_key_name``: unknown or non-numeric key names are function 115."""
        return layout.function.get(int(name), 115) if name.isdigit() else 115

    def build(
        *,
        remote_index: int,
        device_type: int,
        remote_id: bytes,
        name: str,
        key_map: list[tuple[int, int, int]],
        icon: int = 0,
        custom_keys: frozenset[str] = frozenset(),
        learned_keys: tuple[tuple[str, str], ...] = (),
    ) -> tuple[bytes, ...]:
        """``learned_keys`` are the cloud ``keyDetail`` entries as ordered ``(keyName, keyType)``.

        ``keyType`` "key" is a learned replacement for the default key with that id, "text" a
        free-named key. The key map may be empty (a custom remote whose keys are all learned).
        """
        if len(remote_id) != 11:
            raise ValueError("IR remote id must be exactly 11 bytes")
        name_bytes = bytearray(commands.pad(name.encode("utf-8"), 64))
        name_bytes[63] = 0

        if learned_keys:
            details = [(str(key_name), str(key_type)) for key_name, key_type in learned_keys]
        else:
            # no keyDetail order known: the default-id custom keys, by id
            details = [
                (label, "key")
                for label in sorted((x for x in custom_keys if x.isdigit()), key=int)
                if int(label) in layout.function
            ]
        # checkIsCustomKey: a keyDetail entry of type "key" turns a key-map key into a name reference
        custom = set(custom_keys) | {key_name for key_name, key_type in details if key_type == "key"}
        entries = [(str(key), start, length) for key, start, length in key_map]
        map_names = {entry[0] for entry in entries}
        # remoteTag_default looks at the key map and at every keyDetail name
        tag_names = map_names | {key_name for key_name, _ in details}
        # getIsOnlyPower: a power key with no ON/OFF key beside it (keyDetail counts for "key")
        typed = {key_name for key_name, key_type in details if key_type == "key"}
        has_power = power_name in map_names or power_name in typed
        has_on_off = bool({on_name, off_name} & (map_names | typed))
        only_power = has_power and not has_on_off

        def block(key_name: str, start: int, length: int) -> tuple[int, bytes]:
            if key_name in custom:
                return _KIND_CUSTOM, _name_bytes(key_name)
            if not 0 <= start <= 0xFFFFFFFF or not 0 < length <= 0xFFFF:
                raise ValueError("IR code-bank reference is out of range")
            return _KIND_BANK, (start.to_bytes(4, "big") + length.to_bytes(2, "big")).ljust(32, b"\0")

        def record(position: int, function: int, kind: int, payload: bytes = b"") -> bytes:
            return (
                bytes([position]) + function.to_bytes(2, "big") + bytes([kind])
                + payload.ljust(32, b"\0")
            )

        def function_payload(function: int) -> bytes:
            return function.to_bytes(2, "big")

        def count(page: int) -> int:
            """``getDefaultKeysCount``: the sub-page's distinct keys, minus the lone power key."""
            if page not in support:
                return 0
            seen: list[str] = []
            for key_name, _start, _length in entries:
                if key_name in support[page] and key_name not in seen:
                    seen.append(key_name)
            for key_name, key_type in details:
                if page == 4:
                    if key_name in seen or (key_type != "text" and key_name in default_keys):
                        continue
                    seen.append(key_name)
                elif key_name in support[page] and key_name not in seen:
                    seen.append(key_name)
            return len(seen) - 1 if page == 4 and only_power else len(seen)

        def position_of(page: int, key_name: str, counter: int) -> int:
            return layout.main_position[int(key_name)] if page == 0 else counter

        pages: list[bytes] = []
        for page in (0, *sorted(number for number in layout.pages if number)):
            if page and count(page) <= 0:
                continue
            records: list[bytes] = []
            written: set[str] = set()
            for key_name, start, length in entries:
                if key_name == power_name and only_power:
                    continue
                if key_name not in support[page]:
                    continue
                kind, payload = block(key_name, start, length)
                records.append(record(
                    position_of(page, key_name, len(records)), function_of(key_name), kind, payload,
                ))
                written.add(key_name)
            # the keyDetail loop: learned keys the key map did not write, always by name
            for key_name, key_type in details:
                if key_name in written:
                    continue
                if page == 4:
                    if len(records) >= 15:
                        continue
                    if key_name == power_name and key_type == "key" and only_power:
                        continue
                    if key_name in default_keys:
                        continue
                    position = len(records)
                elif key_name in support[page]:
                    position = position_of(page, key_name, len(records))
                else:
                    continue
                records.append(record(position, function_of(key_name), _KIND_CUSTOM, _name_bytes(key_name)))
                written.add(key_name)
            if page == 0:
                for position, function, gate, argument in layout.soft:
                    if gate == "tag":
                        shown = any(str(key) in tag_names for key in argument)
                    else:
                        shown = count(argument) > 0
                    records.append(record(
                        position, function, _KIND_SOFT if shown else _KIND_EMPTY,
                        function_payload(function),
                    ))
                for position, function, fillers in layout.placeholders:
                    if not any(str(key) in tag_names for key in fillers):
                        records.append(record(
                            position, function, _KIND_EMPTY, function_payload(function),
                        ))
                if only_power:
                    # getPowerCmd: the key-map power key, else the learned one (by name)
                    power = next((entry for entry in entries if entry[0] == power_name), None)
                    if power is not None:
                        kind, payload = block(*power)
                    else:
                        kind, payload = _KIND_CUSTOM, _name_bytes(power_name)
                    for position in (TAG["ON"], TAG["OFF"]):
                        records.append(record(position, layout.function[layout.power], kind, payload))
            body = (
                bytes([remote_index & 0xFF, device_type & 0xFF, commands.CTRL_IR, 0, icon & 0xFF])
                + remote_id + bytes(name_bytes) + bytes([0, page, len(records)]) + b"".join(records)
            )
            pages.append(
                b"\x0f\x62\x06" + commands.s16(len(body)) + commands.s16(commands.crc16_modbus(body)) + body
            )
        return tuple(pages)

    build.__doc__ = doc
    return build


build_fan_pages = _make_builder(
    _FAN, "Pages the official app writes for an IR fan (page 0, wind speeds on 3, extras on 4).",
)
build_projector_pages = _make_builder(
    _PJT, "Pages the official app writes for an IR projector (page 0, power and list on 4).",
)
build_light_pages = _make_builder(
    _LIGHT, "Pages the official app writes for an IR light (page 0, mode/set/timer on 4).",
)

LAYOUT_TYPES: dict[int, Callable[..., tuple[bytes, ...]]] = {
    **dict.fromkeys(FAN_REMOTE_TYPES, build_fan_pages),
    **dict.fromkeys(PJT_REMOTE_TYPES, build_projector_pages),
    **dict.fromkeys(LIGHT_REMOTE_TYPES, build_light_pages),
}
