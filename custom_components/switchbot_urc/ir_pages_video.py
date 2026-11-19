"""IR IPTV, set-top box and DVD pages, as the official app lays them out.

Ported from the SwitchBot app's React Native bundle (urc-bundle.js), handler modules for
IPTV (``getIPTV_fun_key_name`` / ``getDefaultKeysCmd``), set-top box (``getTVBox_*``) and DVD
(``getDVD_*``), plus the shared helpers ``checkIsXxxDefaultSupport`` / ``getXxxKeyIndex``.
It follows the TV port in ``commands.build_tv_pages``: the remote finds a key by the firmware
function id written next to a screen position, not by the cloud key id.

What differs from the TV layout:

* A and D (and B for DVD) are written with kind 4 when their sub-page has keys and kind 254
  when it has none. Their payload starts with the soft key's own function id (the app does
  ``payload.set(functionBytes)`` for these), unlike a key record whose payload is a code reference.
* IPTV and set-top box have no B or C sub-page: B is the TV-power key and C the list/favourite
  key, each living directly on the main page at position B / C. When that key is missing a kind
  254 placeholder takes the position. DVD has C as a single key (eject) and B as a sub-page.
* There are only sub-pages A (digits, page 1), B (DVD transport, page 2) and D (page 4).
  Page 3 is never written.
* Power: when the key map has Power but no On/Off key (always for DVD, which has no On/Off), the
  Power code goes on both ON and OFF and Power is kept out of every sub-page. When the key map
  has On/Off keys too, they take ON/OFF and Power goes to the D page.
* Function ids are two bytes in the app; the TV-box/IPTV "TV on/power/off" keys use the 3xx
  range (for example ``[3, 34]`` is 802).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import commands

TAG = commands.TAG

# Remote type ids (REMOTE_*_TYPE in the app); the ``*_CUSTOM`` variant is the type plus 14.
IPTV_TYPE, IPTV_TYPE_CUSTOM = 3, 17
TVBOX_TYPE, TVBOX_TYPE_CUSTOM = 4, 18
DVD_TYPE, DVD_TYPE_CUSTOM = 5, 19

# Function ids shared by the three types: ``[hi, lo]`` is ``hi << 8 | lo``.
_FN_POWER = 105
_FN_SOFT_A = 39       # getDefaultKeysCmd: A soft key is [0, 39]
_FN_SOFT_B = 20       # DVD only: B soft key is [0, 20]
_FN_SOFT_D = 100      # D soft key is [0, 100]
_PAGE_DIGITS, _PAGE_TRANSPORT, _PAGE_D = 1, 2, 4
_KIND_CODE, _KIND_NAME, _KIND_SHOWN, _KIND_HIDDEN = 1, 2, 4, 254


@dataclass(frozen=True)
class _Layout:
    """One remote type's key tables."""

    function: dict[int, int]            # getXxx_fun_key_name: cloud key id -> function id
    main_position: dict[int, int]       # getXxxKeyIndex for the page-0 keys: id -> position
    pages: dict[int, tuple[int, ...]]   # checkIsXxxDefaultSupport(page, key): page -> key ids
    power: int                          # the Power key id (WOxxxTAG_Power)
    on_off: tuple[int, ...]             # the On / Off key ids (empty when the type has none)
    # (position, function id, page) soft keys, written always: kind 4 if the page has keys.
    soft_pages: tuple[tuple[int, int, int], ...]
    # (position, function id, key id) single-key soft keys: written only (as kind 254) when
    # the key is missing; when present the key itself sits on that position.
    soft_single: tuple[tuple[int, int, int], ...]


# ---- IPTV (type 3, custom 17): WOIPTVTAG_* ids from the app's constants table ----------------
_IPTV_POWER, _IPTV_MUTE, _IPTV_VOL_ADD, _IPTV_VOL_DEL = 1, 3, 5, 7
_IPTV_UP, _IPTV_LEFT, _IPTV_OK, _IPTV_RIGHT, _IPTV_DOWN = 13, 15, 17, 19, 21
_IPTV_DIGITS = (43, 25, 27, 29, 31, 33, 35, 37, 39, 41)    # Number0, Number1 .. Number9
_IPTV_BACK, _IPTV_ON, _IPTV_OFF, _IPTV_TV_ON, _IPTV_TV_POWER, _IPTV_TV_OFF = 45, 2, 4, 6, 8, 10
_IPTV_MENU, _IPTV_LIST = 12, 14
# ChannelAdd (9) and ChannelDelete (11) exist in the cloud but the app writes them nowhere.

_IPTV_FUNCTION = {   # getIPTV_fun_key_name
    _IPTV_ON: 5, _IPTV_POWER: _FN_POWER, _IPTV_OFF: 6,
    _IPTV_TV_ON: 0x0320, _IPTV_TV_POWER: 0x0322, _IPTV_TV_OFF: 0x0321,
    _IPTV_BACK: 12, _IPTV_MENU: 118, _IPTV_LIST: 116, _IPTV_VOL_DEL: 16, _IPTV_VOL_ADD: 15,
    _IPTV_MUTE: 19, _IPTV_UP: 9, _IPTV_DOWN: 10, _IPTV_LEFT: 7, _IPTV_RIGHT: 8, _IPTV_OK: 11,
    **{key: 40 + digit for digit, key in enumerate(_IPTV_DIGITS)},
}
_IPTV_MAIN_POSITION = {   # getIPTVKeyIndex for the keys checkIsIPTVDefaultSupport(0, key) accepts
    _IPTV_ON: TAG["ON"], _IPTV_OFF: TAG["OFF"], _IPTV_TV_POWER: TAG["B"], _IPTV_BACK: TAG["BACK"],
    _IPTV_MENU: TAG["HOME"], _IPTV_LIST: TAG["C"], _IPTV_VOL_DEL: TAG["VOLDEL"],
    _IPTV_VOL_ADD: TAG["VOLADD"], _IPTV_MUTE: TAG["SOUNDOFF"], _IPTV_UP: TAG["UP"],
    _IPTV_DOWN: TAG["DOWN"], _IPTV_LEFT: TAG["LEFT"], _IPTV_RIGHT: TAG["RIGHT"],
    _IPTV_OK: TAG["OK"],
}
_IPTV_LAYOUT = _Layout(
    function=_IPTV_FUNCTION,
    main_position=_IPTV_MAIN_POSITION,
    pages={   # checkIsIPTVDefaultSupport: page 0 / 1 (A, digits) / 4 (D)
        0: tuple(_IPTV_MAIN_POSITION),
        _PAGE_DIGITS: _IPTV_DIGITS,
        _PAGE_D: (_IPTV_POWER, _IPTV_TV_ON, _IPTV_TV_OFF),
    },
    power=_IPTV_POWER,
    on_off=(_IPTV_ON, _IPTV_OFF),
    # getDefaultKeysCmd: A and D, then B (TV power) and C (list) when missing
    soft_pages=((TAG["A"], _FN_SOFT_A, _PAGE_DIGITS), (TAG["D"], _FN_SOFT_D, _PAGE_D)),
    soft_single=(
        (TAG["B"], _IPTV_FUNCTION[_IPTV_TV_POWER], _IPTV_TV_POWER),
        (TAG["C"], _IPTV_FUNCTION[_IPTV_LIST], _IPTV_LIST),
    ),
)

# ---- Set-top box (type 4, custom 18): WOSTBTAG_* ids ------------------------------------------
_STB_POWER = 1
_STB_DIGITS = (23, 3, 5, 7, 9, 11, 13, 15, 17, 19)         # Number0, Number1 .. Number9
_STB_BACK, _STB_UP, _STB_LEFT, _STB_OK, _STB_RIGHT, _STB_DOWN = 25, 27, 29, 31, 33, 35
_STB_VOL_ADD, _STB_VOL_DEL, _STB_CH_ADD, _STB_CH_DEL, _STB_MUTE = 37, 39, 41, 43, 45
_STB_ON, _STB_OFF, _STB_TV_ON, _STB_TV_POWER, _STB_TV_OFF = 2, 4, 6, 8, 10
_STB_MENU, _STB_LIST, _STB_FAV = 12, 16, 18
# ThreeCode (14) exists in the cloud but the app writes it nowhere.

_STB_FUNCTION = {   # getTVBox_fun_key_name
    _STB_ON: 5, _STB_POWER: _FN_POWER, _STB_OFF: 6,
    _STB_TV_ON: 0x0320, _STB_TV_POWER: 0x0322, _STB_TV_OFF: 0x0321,
    _STB_BACK: 12, _STB_MENU: 118, _STB_LIST: 116, _STB_CH_DEL: 18, _STB_CH_ADD: 17,
    _STB_FAV: 109, _STB_VOL_DEL: 16, _STB_VOL_ADD: 15, _STB_MUTE: 19, _STB_UP: 9,
    _STB_DOWN: 10, _STB_LEFT: 7, _STB_RIGHT: 8, _STB_OK: 11,
    **{key: 40 + digit for digit, key in enumerate(_STB_DIGITS)},
}
_STB_MAIN_POSITION = {   # getTVBoxKeyIndex for the keys checkIsTVBoxDefaultSupport(0, key) accepts
    _STB_ON: TAG["ON"], _STB_OFF: TAG["OFF"], _STB_TV_POWER: TAG["B"], _STB_BACK: TAG["BACK"],
    _STB_MENU: TAG["HOME"], _STB_CH_DEL: TAG["CHDOWN"], _STB_CH_ADD: TAG["CHUP"],
    _STB_FAV: TAG["C"], _STB_VOL_DEL: TAG["VOLDEL"], _STB_VOL_ADD: TAG["VOLADD"],
    _STB_MUTE: TAG["SOUNDOFF"], _STB_UP: TAG["UP"], _STB_DOWN: TAG["DOWN"],
    _STB_LEFT: TAG["LEFT"], _STB_RIGHT: TAG["RIGHT"], _STB_OK: TAG["OK"],
}
_STB_LAYOUT = _Layout(
    function=_STB_FUNCTION,
    main_position=_STB_MAIN_POSITION,
    pages={   # checkIsTVBoxDefaultSupport: page 0 / 1 (A, digits) / 4 (D)
        0: tuple(_STB_MAIN_POSITION),
        _PAGE_DIGITS: _STB_DIGITS,
        _PAGE_D: (_STB_POWER, _STB_TV_ON, _STB_TV_OFF, _STB_LIST),
    },
    power=_STB_POWER,
    on_off=(_STB_ON, _STB_OFF),
    # getDefaultKeysCmd: A and D, then B (TV power) and C (favourites) when missing
    soft_pages=((TAG["A"], _FN_SOFT_A, _PAGE_DIGITS), (TAG["D"], _FN_SOFT_D, _PAGE_D)),
    soft_single=(
        (TAG["B"], _STB_FUNCTION[_STB_TV_POWER], _STB_TV_POWER),
        (TAG["C"], _STB_FUNCTION[_STB_FAV], _STB_FAV),
    ),
)

# ---- DVD (type 5, custom 19): WODVDTAG_* ids --------------------------------------------------
_DVD_MUTE, _DVD_MENU, _DVD_STOP, _DVD_VOL_DEL, _DVD_VOL_ADD = 1, 2, 4, 6, 8
_DVD_UP, _DVD_POWER, _DVD_LEFT, _DVD_DOWN, _DVD_FAST_REVERSE = 10, 11, 12, 14, 15
_DVD_RIGHT, _DVD_PLAY, _DVD_OK, _DVD_FAST_FORWARD, _DVD_BACK = 16, 17, 18, 19, 20
_DVD_LAST, _DVD_LIST, _DVD_NEXT, _DVD_PAUSE, _DVD_TAKE_OUT = 21, 24, 25, 29, 33
_DVD_DIGITS = (44, 26, 28, 30, 32, 34, 36, 38, 40, 42)     # Number0, Number1 .. Number9
# ThreeCode (22) exists in the cloud but the app writes it nowhere.

_DVD_FUNCTION = {   # getDVD_fun_key_name
    _DVD_VOL_ADD: 15, _DVD_VOL_DEL: 16, _DVD_MENU: 118, _DVD_POWER: _FN_POWER, _DVD_MUTE: 19,
    _DVD_BACK: 12, _DVD_PLAY: 21, _DVD_PAUSE: 22, _DVD_STOP: 23, _DVD_FAST_REVERSE: 25,
    _DVD_FAST_FORWARD: 26, _DVD_LAST: 27, _DVD_NEXT: 28, _DVD_TAKE_OUT: 111, _DVD_LIST: 116,
    _DVD_LEFT: 7, _DVD_RIGHT: 8, _DVD_UP: 9, _DVD_DOWN: 10, _DVD_OK: 11,
    **{key: 40 + digit for digit, key in enumerate(_DVD_DIGITS)},
}
_DVD_MAIN_POSITION = {   # getDVDKeyIndex for the keys checkIsDVDDefaultSupport(0, key) accepts
    _DVD_POWER: TAG["ON"], _DVD_MUTE: TAG["SOUNDOFF"], _DVD_MENU: TAG["HOME"],
    _DVD_BACK: TAG["BACK"], _DVD_VOL_ADD: TAG["VOLADD"], _DVD_VOL_DEL: TAG["VOLDEL"],
    _DVD_LEFT: TAG["LEFT"], _DVD_RIGHT: TAG["RIGHT"], _DVD_UP: TAG["UP"],
    _DVD_DOWN: TAG["DOWN"], _DVD_OK: TAG["OK"], _DVD_TAKE_OUT: TAG["C"],
}
_DVD_LAYOUT = _Layout(
    function=_DVD_FUNCTION,
    main_position=_DVD_MAIN_POSITION,
    pages={   # checkIsDVDDefaultSupport: page 0 / 1 (A, digits) / 2 (B, transport) / 4 (D, list)
        0: tuple(_DVD_MAIN_POSITION),
        _PAGE_DIGITS: _DVD_DIGITS,
        _PAGE_TRANSPORT: (
            _DVD_FAST_REVERSE, _DVD_PLAY, _DVD_PAUSE, _DVD_FAST_FORWARD, _DVD_LAST, _DVD_STOP,
            _DVD_NEXT,
        ),
        _PAGE_D: (_DVD_LIST,),
    },
    power=_DVD_POWER,
    on_off=(),
    # getDefaultKeysCmd: A, B and D, then C (eject) when missing
    soft_pages=(
        (TAG["A"], _FN_SOFT_A, _PAGE_DIGITS),
        (TAG["B"], _FN_SOFT_B, _PAGE_TRANSPORT),
        (TAG["D"], _FN_SOFT_D, _PAGE_D),
    ),
    soft_single=((TAG["C"], _DVD_FUNCTION[_DVD_TAKE_OUT], _DVD_TAKE_OUT),),
)

# Sub-pages are numbered by their soft key plus one in the page header (A = 1, B = 2, D = 4).
_PAGE_ORDER = (0, 1, 2, 3, 4)


def _build(
    layout: _Layout,
    *,
    remote_index: int,
    device_type: int,
    remote_id: bytes,
    name: str,
    key_map: list[tuple[int, int, int]],
    icon: int = 0,
    custom_keys: frozenset[str] = frozenset(),
) -> tuple[bytes, ...]:
    if len(remote_id) != 11:
        raise ValueError("IR remote id must be exactly 11 bytes")
    if not key_map:
        raise ValueError("IR key map must not be empty")
    name_bytes = bytearray(commands.pad(name.encode("utf-8"), 64))
    name_bytes[63] = 0

    def block(key: int, start: int, length: int) -> tuple[int, bytes]:
        # checkIsCustomKey: a key uploaded on its own is referenced by name (kind 2)
        if str(key) in custom_keys:
            return _KIND_NAME, str(key).encode("utf-8")[:31].ljust(32, b"\0")
        if not 0 <= start <= 0xFFFFFFFF or not 0 < length <= 0xFFFF:
            raise ValueError("IR code-bank reference is out of range")
        return _KIND_CODE, (start.to_bytes(4, "big") + length.to_bytes(2, "big")).ljust(32, b"\0")

    def record(position: int, function: int, kind: int, payload: bytes = b"") -> bytes:
        return bytes([position]) + function.to_bytes(2, "big") + bytes([kind]) + payload.ljust(32, b"\0")

    def soft(position: int, function: int, kind: int) -> bytes:
        # the app puts the soft key's function id in the first two payload bytes
        return record(position, function, kind, function.to_bytes(2, "big"))

    # Keys from the key map first, in map order, then keys that only exist as separate uploads
    # (the app's second pass over keyDetail), each once.
    entries: list[tuple[int, int, int]] = []
    seen: set[int] = set()
    for key, start, length in key_map:
        if key not in seen:
            seen.add(key)
            entries.append((key, start, length))
    for label in sorted(label for label in custom_keys if label.isdecimal()):
        if int(label) not in seen:
            seen.add(int(label))
            entries.append((int(label), 0, 0))
    present = seen

    power_entry = next((entry for entry in entries if entry[0] == layout.power), None)
    has_power = layout.power in present
    # getIsOnlyPower: Power without any On/Off key
    only_power = has_power and not any(key in present for key in layout.on_off)

    def page_count(page: int) -> int:
        # getDefaultKeysCount(page): the page's keys present, less Power when it is moved
        count = sum(1 for key in layout.pages.get(page, ()) if key in present)
        if only_power and layout.power in layout.pages.get(page, ()):
            count -= 1
        return count

    pages: list[bytes] = []
    for page in _PAGE_ORDER:
        records: list[bytes] = []
        wanted = layout.pages.get(page, ())
        for key, start, length in entries:
            if key not in wanted or (key == layout.power and only_power):
                continue
            kind, payload = block(key, start, length)
            position = layout.main_position[key] if page == 0 else len(records)
            records.append(record(position, layout.function[key], kind, payload))
        if page == 0:
            for position, function, soft_page in layout.soft_pages:
                shown = page_count(soft_page) > 0
                records.append(soft(position, function, _KIND_SHOWN if shown else _KIND_HIDDEN))
            for position, function, key in layout.soft_single:
                if key not in present:
                    records.append(soft(position, function, _KIND_HIDDEN))
            if only_power:
                kind, payload = block(*(power_entry or (layout.power, 0, 1)))
                for position in (TAG["ON"], TAG["OFF"]):
                    records.append(record(position, _FN_POWER, kind, payload))
        elif not records:
            continue
        body = bytes([remote_index & 0xFF, device_type & 0xFF, commands.CTRL_IR, 0, icon & 0xFF]) \
            + remote_id + bytes(name_bytes) + bytes([0, page, len(records)]) + b"".join(records)
        pages.append(
            b"\x0f\x62\x06" + commands.s16(len(body)) + commands.s16(commands.crc16_modbus(body)) + body
        )
    return tuple(pages)


def build_iptv_pages(
    *,
    remote_index: int,
    device_type: int,
    remote_id: bytes,
    name: str,
    key_map: list[tuple[int, int, int]],
    icon: int = 0,
    custom_keys: frozenset[str] = frozenset(),
) -> tuple[bytes, ...]:
    """Pages for an IPTV remote (type 3 or custom 17), laid out like the official app."""
    return _build(
        _IPTV_LAYOUT, remote_index=remote_index, device_type=device_type, remote_id=remote_id, name=name,
        key_map=key_map, icon=icon, custom_keys=custom_keys,
    )


def build_tvbox_pages(
    *,
    remote_index: int,
    device_type: int,
    remote_id: bytes,
    name: str,
    key_map: list[tuple[int, int, int]],
    icon: int = 0,
    custom_keys: frozenset[str] = frozenset(),
) -> tuple[bytes, ...]:
    """Pages for a set-top box remote (type 4 or custom 18), laid out like the official app."""
    return _build(
        _STB_LAYOUT, remote_index=remote_index, device_type=device_type, remote_id=remote_id, name=name,
        key_map=key_map, icon=icon, custom_keys=custom_keys,
    )


def build_dvd_pages(
    *,
    remote_index: int,
    device_type: int,
    remote_id: bytes,
    name: str,
    key_map: list[tuple[int, int, int]],
    icon: int = 0,
    custom_keys: frozenset[str] = frozenset(),
) -> tuple[bytes, ...]:
    """Pages for a DVD remote (type 5 or custom 19), laid out like the official app."""
    return _build(
        _DVD_LAYOUT, remote_index=remote_index, device_type=device_type, remote_id=remote_id, name=name,
        key_map=key_map, icon=icon, custom_keys=custom_keys,
    )


LAYOUT_TYPES: dict[int, Callable[..., tuple[bytes, ...]]] = {
    IPTV_TYPE: build_iptv_pages,
    IPTV_TYPE_CUSTOM: build_iptv_pages,
    TVBOX_TYPE: build_tvbox_pages,
    TVBOX_TYPE_CUSTOM: build_tvbox_pages,
    DVD_TYPE: build_dvd_pages,
    DVD_TYPE_CUSTOM: build_dvd_pages,
}
