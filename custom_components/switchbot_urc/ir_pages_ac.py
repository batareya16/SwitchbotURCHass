"""IR air conditioner (ARC) and air purifier (AIR) pages, as the official app lays them out.

Ported from the app's React Native bundle (``urc-bundle.js``), the per-type key handlers:

* ARC (type 1, custom 15): the air conditioner handler. An air conditioner has no per-key code
  slices at all. The remote holds the model's code bank plus two side blobs (``keyMapFastBin``,
  ``fastConfigBin``) and builds each frame from its state; a page record therefore carries the
  *firmware function id* (kind 3), never a code-bank offset. The key map is not read.
* AIR (type 10, custom 23): the air *purifier* handler (``WOAIRTAG_*`` ids). It follows the TV
  scheme: firmware function ids on fixed main positions, other keys on sub-pages, kind 1 records
  referencing the code bank (kind 2: a separately uploaded key, referenced by name).

Both builders share the signature of ``commands.build_tv_pages`` (the ARC one takes two extra,
optional keywords, see its docstring) and return the same page packets. ``LAYOUT_TYPES`` maps
each remote type id covered here, including the ``*_CUSTOM`` variant, to its builder.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from . import commands

TAG = commands.TAG
_NAME_BYTES = 64
_KEY_BYTES = 32

# Record kinds (the byte after the function id).
KIND_CODE = 1        # code-bank slice: offset (4) + length (2)
KIND_NAME = 2        # separately uploaded key: its name
KIND_FUNCTION = 3    # firmware function id only (air conditioner states)
KIND_SOFT = 4        # soft key A-D, opens a sub-page
KIND_SOFT_HIDDEN = 254   # soft key A-D that has nothing behind it


def _record(position: int, function: int, kind: int, payload: bytes = b"") -> bytes:
    if not 0 <= function <= 0xFFFF:
        raise ValueError("IR key function must fit in two bytes")
    return bytes([position & 0xFF]) + function.to_bytes(2, "big") + bytes([kind]) \
        + commands.pad(payload, _KEY_BYTES)


def _page_packet(
    *, remote_index: int, device_type: int, remote_id: bytes, name_bytes: bytes, icon: int,
    page: int, records: list[bytes],
) -> bytes:
    body = bytes([remote_index & 0xFF, device_type & 0xFF, commands.CTRL_IR, 0, icon & 0xFF]) \
        + remote_id + name_bytes + bytes([0, page & 0xFF, len(records) & 0xFF]) + b"".join(records)
    return b"\x0f\x62\x06" + commands.s16(len(body)) + commands.s16(commands.crc16_modbus(body)) + body


def _name_field(name: str, *, strip_slash: bool) -> bytes:
    """The 64-byte remote name: NUL terminated, so at most 63 bytes (getNameBytes_64)."""
    text = name.replace("/", "") if strip_slash else name
    field = bytearray(commands.pad(text.encode("utf-8"), _NAME_BYTES))
    field[_NAME_BYTES - 1] = 0
    return bytes(field)


def _code_payload(start: int, length: int) -> bytes:
    if not 0 <= start <= 0xFFFFFFFF or not 0 < length <= 0xFFFF:
        raise ValueError("IR code-bank reference is out of range")
    return start.to_bytes(4, "big") + length.to_bytes(2, "big")


def _key_name(label: str) -> bytes:
    """getKeyNameBytes_32: the key name, NUL terminated inside 32 bytes."""
    return label.encode("utf-8")[:_KEY_BYTES - 1]


# =============================================================================================
# AIR (air purifier): handler m995225, helpers checkIsAirDefaultSupport / getAirKeyIndex
# =============================================================================================
AIR_REMOTE_TYPES = (10, 23)

# WOAIRTAG_* ids (the cloud key ids that appear in a key map).
_AIR_POWER, _AIR_ON, _AIR_AUTOMATE, _AIR_OFF, _AIR_WIND1, _AIR_SCHEDULE, _AIR_WIND2, _AIR_MODE = \
    1, 2, 3, 4, 6, 7, 8, 9
_AIR_WIND3, _AIR_ANION, _AIR_SLEEP, _AIR_COZY, _AIR_CHILDLOCK, _AIR_MUTE, _AIR_TIMER = \
    10, 11, 12, 13, 14, 15, 16

# getAir_fun_key_name: key id -> firmware function id; anything else (including WOAIRTAG_Speed=5)
# is function 115.
_AIR_FUNCTION = {
    _AIR_ON: 5, _AIR_OFF: 6, _AIR_MODE: 56, _AIR_TIMER: 90, _AIR_MUTE: 19,
    _AIR_WIND1: 72, _AIR_WIND2: 73, _AIR_WIND3: 74, _AIR_POWER: 105, _AIR_AUTOMATE: 117,
    _AIR_ANION: 113, _AIR_COZY: 58, _AIR_CHILDLOCK: 112, _AIR_SCHEDULE: 92, _AIR_SLEEP: 57,
}
_AIR_FUNCTION_OTHER = 115

# checkIsAirDefaultSupport(page, id): which key ids belong to which page (0 main, 1 = soft key A,
# 4 = soft key D). The pages 2 and 3 do not exist for this type.
_AIR_PAGE_KEYS = {
    0: (_AIR_ON, _AIR_OFF, _AIR_MUTE, _AIR_MODE, _AIR_TIMER),
    1: (_AIR_WIND1, _AIR_WIND2, _AIR_WIND3),
    4: (_AIR_POWER, _AIR_AUTOMATE, _AIR_COZY, _AIR_CHILDLOCK, _AIR_ANION, _AIR_SCHEDULE, _AIR_SLEEP),
}
# getAirKeyIndex: the page-0 position of each main-page key (Mode and Timer sit on B and C).
_AIR_MAIN_POSITION = {
    _AIR_ON: TAG["ON"], _AIR_OFF: TAG["OFF"], _AIR_MUTE: TAG["SOUNDOFF"],
    _AIR_MODE: TAG["B"], _AIR_TIMER: TAG["C"],
}
# getRemoteTagAry (the order only matters for the app's UI): the key ids behind each soft key.
_AIR_SOFT_KEYS = {
    TAG["A"]: (_AIR_WIND1, _AIR_WIND2, _AIR_WIND3),
    TAG["B"]: (_AIR_MODE,),
    TAG["C"]: (_AIR_TIMER,),
    TAG["D"]: (_AIR_AUTOMATE, _AIR_POWER, _AIR_CHILDLOCK, _AIR_ANION, _AIR_SCHEDULE, _AIR_SLEEP),
}
# checkCustomKeysIsDefaultKey(AIR): learned keys with these names replace a default key and are
# not listed again on page 4.
_AIR_CUSTOM_DEFAULT = (
    _AIR_ON, _AIR_OFF, _AIR_MODE, _AIR_WIND1, _AIR_WIND2, _AIR_WIND3, _AIR_MUTE, _AIR_TIMER,
)
# Soft key function ids written by getDefaultKeysCmd: A is 70, D is 100; B and C only appear as
# hidden placeholders (function = Mode / Timer) when the key map has no Mode / Timer key. The
# placeholder payloads are what the app writes: B repeats A's [0, 70], C holds Timer's id.
_AIR_SOFT_FUNCTION = {TAG["A"]: 70, TAG["D"]: 100}
_AIR_B_PLACEHOLDER_PAYLOAD = (70).to_bytes(2, "big")
_AIR_PAGE_D_LIMIT = 15      # custom keys appended to page 4 stop at 15 records


def _air_function(name: str) -> int:
    try:
        return _AIR_FUNCTION.get(int(name), _AIR_FUNCTION_OTHER)
    except ValueError:
        return _AIR_FUNCTION_OTHER


def _custom_sort_key(label: str) -> tuple[int, int, str]:
    return (0, int(label), label) if label.isdigit() else (1, 0, label)


def _learned_list(
    learned_keys: tuple[tuple[str, str], ...], custom_keys: frozenset[str],
) -> list[tuple[str, str]]:
    """The app's keyDetail as ordered (name, type) pairs: first occurrence of each name.

    Without ``learned_keys`` the names in ``custom_keys`` stand in for it, all of type "key",
    in numeric-then-alphabetical order (a frozenset has no order of its own).
    """
    if learned_keys:
        pairs = [(str(label), str(kind)) for label, kind in learned_keys]
    else:
        pairs = [(label, "key") for label in sorted(custom_keys, key=_custom_sort_key)]
    seen: set[str] = set()
    result = []
    for label, kind in pairs:
        if label not in seen:
            seen.add(label)
            result.append((label, kind))
    return result


def build_air_pages(
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
    """Build the pages the official app writes for an IR air purifier (types 10 and 23).

    Page 0 puts ON, OFF and Mute on their own positions, Mode on B and Timer on C (as real key
    records, or a hidden placeholder when absent), and soft keys A (fan speeds) and D (the other
    keys). Page 1 holds the three fan speeds, page 4 the D keys (Power, Auto, Cozy, Child lock,
    Anion, Schedule, Sleep) followed by learned keys, at most 15 records.

    Power: a remote that has the Power key but neither ON nor OFF gets Power written twice on the
    ON and OFF positions (the code-bank slice or custom name is shared) and is left out of page 4.

    ``learned_keys`` is the cloud ``keyDetail`` as ordered ``(keyName, keyType)`` pairs. A key-map
    key that has a ``"key"`` entry of the same name is referenced by name (kind 2). The entries the
    key map does not place are walked in order: the main-page and fan-speed ones join their page,
    the others go to page 4 (function 115 unless the name is a known key) as kind 2; as in the app
    the type does not matter there, except that a ``"text"`` entry is counted for page 4 even when
    its name is a default key (and then not written), and that only a ``"key"`` Power counts for the
    Power-only rule. Without ``learned_keys`` the names in ``custom_keys`` are used, all of type
    ``"key"``. The key map may be empty (a custom type whose keys are all learned).
    """
    if len(remote_id) != 11:
        raise ValueError("IR remote id must be exactly 11 bytes")
    detail = _learned_list(learned_keys, custom_keys)
    name_bytes = _name_field(name, strip_slash=True)

    entries = [(str(key), start, length) for key, start, length in key_map]
    custom = {label for label, kind in detail if kind == "key"}      # checkIsCustomKey
    ids = {key for key, _s, _l in entries} | {label for label, _kind in detail}
    power, on_off = str(_AIR_POWER), {str(_AIR_ON), str(_AIR_OFF)}
    has_power = power in {key for key, _s, _l in entries} or power in custom
    only_power = has_power and not (on_off & ({key for key, _s, _l in entries} | custom))

    def block(key: str, start: int, length: int) -> tuple[int, bytes]:
        if key in custom:
            return KIND_NAME, _key_name(key)
        return KIND_CODE, _code_payload(start, length)

    def supported(page: int, key: str) -> bool:
        return key.isdigit() and int(key) in _AIR_PAGE_KEYS[page]

    def default_key(label: str) -> bool:
        return label.isdigit() and int(label) in _AIR_CUSTOM_DEFAULT

    def mapped(page: int) -> list[tuple[str, int, int]]:
        """The key-map entries of this page, first occurrence of each id, in map order."""
        result: list[tuple[str, int, int]] = []
        for entry in entries:
            if supported(page, entry[0]) and entry[0] not in (item[0] for item in result):
                result.append(entry)
        return result

    def count(page: int) -> int:
        """getDefaultKeysCount: a page is written only when this is above zero."""
        counted = {entry[0] for entry in mapped(page)}
        for label, kind in detail:
            if label in counted:
                continue
            if page == 4:
                if kind != "text" and default_key(label):
                    continue
            elif not supported(page, label):
                continue
            counted.add(label)
        total = len(counted)
        if page == 0:
            total += 2
        if page == 4 and only_power:
            total -= 1
        return total

    def page_records(page: int) -> list[bytes]:
        records: list[bytes] = []
        pushed: set[str] = set()

        def position(key: str) -> int:
            return _AIR_MAIN_POSITION.get(int(key), TAG["D"]) if page == 0 else len(records)

        for key, start, length in mapped(page):
            if key == power and only_power:
                continue
            kind, payload = block(key, start, length)
            records.append(_record(position(key), _air_function(key), kind, payload))
            pushed.add(key)
        for label, kind in detail:
            if label in pushed:
                continue
            if page == 4:
                if len(records) >= _AIR_PAGE_D_LIMIT:
                    continue
                if label == power and kind == "key" and only_power:
                    continue
                if default_key(label):
                    continue
            elif not supported(page, label):
                continue
            records.append(_record(position(label), _air_function(label), KIND_NAME, _key_name(label)))
            pushed.add(label)
        return records

    def has_soft(position: int) -> bool:
        return any(str(key) in ids for key in _AIR_SOFT_KEYS[position])

    pages: list[bytes] = []
    for page in (0, 1, 4):
        if count(page) <= 0:
            continue
        records = page_records(page)
        if page == 0:
            a_state = KIND_SOFT if has_soft(TAG["A"]) else KIND_SOFT_HIDDEN
            d_state = KIND_SOFT_HIDDEN if count(4) <= 0 else KIND_SOFT
            records.append(_record(
                TAG["A"], _AIR_SOFT_FUNCTION[TAG["A"]], a_state, _AIR_SOFT_FUNCTION[TAG["A"]].to_bytes(2, "big")))
            records.append(_record(
                TAG["D"], _AIR_SOFT_FUNCTION[TAG["D"]], d_state, _AIR_SOFT_FUNCTION[TAG["D"]].to_bytes(2, "big")))
            if not has_soft(TAG["B"]):
                records.append(_record(
                    TAG["B"], _AIR_FUNCTION[_AIR_MODE], KIND_SOFT_HIDDEN, _AIR_B_PLACEHOLDER_PAYLOAD))
            if not has_soft(TAG["C"]):
                records.append(_record(
                    TAG["C"], _AIR_FUNCTION[_AIR_TIMER], KIND_SOFT_HIDDEN,
                    _AIR_FUNCTION[_AIR_TIMER].to_bytes(2, "big")))
            if only_power:
                power = next((entry for entry in entries if entry[0] == str(_AIR_POWER)), None)
                kind, payload = block(*(power or (str(_AIR_POWER), 0, 1)))
                for slot in (TAG["ON"], TAG["OFF"]):
                    records.append(_record(slot, _AIR_FUNCTION[_AIR_POWER], kind, payload))
        pages.append(_page_packet(
            remote_index=remote_index, device_type=device_type, remote_id=remote_id,
            name_bytes=name_bytes, icon=icon, page=page, records=records))
    return tuple(pages)


# =============================================================================================
# ARC (air conditioner): handler m1065039
# =============================================================================================
ARC_REMOTE_TYPES = (1, 15)

# getARCKeysPageMain: (position, function). Temperature up/down is written on the volume,
# channel and arrow positions alike.
_ARC_MAIN_KEYS = (
    (TAG["ON"], 5), (TAG["OFF"], 6),
    (TAG["VOLADD"], 60), (TAG["VOLDEL"], 61),
    (TAG["CHUP"], 60), (TAG["CHDOWN"], 61),
    (TAG["UP"], 60), (TAG["DOWN"], 61),
)
# getABCDKeysCmd: the soft keys are always on page 0. A, B and C are kind 4; D has function 0
# and so (the app tests only 59/70/80) is written as kind 3.
_ARC_SOFT_KEYS = ((TAG["A"], 59), (TAG["B"], 70), (TAG["C"], 80), (TAG["D"], 0))
_ARC_SOFT_FUNCTIONS = (59, 70, 80)
# getARCKeysPageA/B/C: (function, fixed position on the page). The position is fixed, so a
# missing key leaves a gap; the list order is the page order.
_ARC_PAGE_KEYS = {
    1: ((51, 0), (54, 1), (52, 2), (50, 3), (53, 4), (55, 5)),   # cool, heat, dry, auto, wind, humidify
    2: ((71, 0), (72, 1), (73, 2), (74, 3), (75, 4), (76, 5)),   # fan speed auto, 1-5
    3: ((82, 0), (83, 1), (84, 2)),                              # swing 1-3
}
# isSupportKey: function id -> fastConfigMap mode entry. 5, 6, 60 and 61 are always supported.
_ARC_MODE_FOR_KEY = {50: "auto", 51: "cool", 52: "dry", 53: "wind", 54: "heat", 55: "humidifier"}
_ARC_MODES = ("auto", "cool", "dry", "wind", "heat", "humidifier")
_ARC_SPEED_BASE = 71
_ARC_DIR_BASE = 81
_ARC_CUSTOM_LABEL_CHARS = 16     # assembleCmd keeps the first 16 characters of a custom name


def _is_empty(value: Any) -> bool:
    """CommonUtils.isEmptyDataSource for the values met here."""
    return value is None or value == "" or value == [] or value == {}


def _as_config_map(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _arc_range(config: dict[str, Any], low_field: str, high_field: str, base: int) -> tuple[float, float]:
    """The loop shared by isSupportSpeed / isSupportDir. The lower bound starts at 0, as in the app."""
    low = high = 0.0
    for mode in _ARC_MODES:
        entry = config.get(mode)
        if _is_empty(entry) or not isinstance(entry, dict):
            continue
        entry_low, entry_high = _number(entry.get(low_field)), _number(entry.get(high_field))
        if entry_low is not None and entry_low + base < low:
            low = entry_low + base
        if entry_high is not None and entry_high + base > high:
            high = entry_high + base
    return low, high


def arc_key_supported(fast_config_map: Any, function: int) -> bool:
    """isSupportKey / isSupportSpeed / isSupportDir against the cloud's ``fastConfigMap``."""
    config = _as_config_map(fast_config_map)
    if _is_empty(config):
        return True
    if function in (5, 6, 60, 61):
        return True
    if function in _ARC_MODE_FOR_KEY:
        entry = config.get(_ARC_MODE_FOR_KEY[function])
        return isinstance(entry, dict) and entry.get("modeEnable") == 1
    if 71 <= function <= 76:
        low, high = _arc_range(config, "speedMin", "speedMax", _ARC_SPEED_BASE)
        return low <= function <= high
    if 82 <= function <= 84:
        low, high = _arc_range(config, "dirMin", "dirMax", _ARC_DIR_BASE)
        return low <= function <= high
    return False


def build_arc_pages(
    *,
    remote_index: int,
    device_type: int,
    remote_id: bytes,
    name: str,
    key_map: list[tuple[int, int, int]],
    icon: int = 0,
    custom_keys: frozenset[str] = frozenset(),
    fast_config_map: Any = None,
    fast_config_bin: bytes | None = None,
    learned_keys: tuple[tuple[str, str], ...] = (),
) -> tuple[bytes, ...]:
    """Build the pages the official app writes for an IR air conditioner (types 1 and 15).

    ``key_map`` is accepted for the common signature and not read: an air conditioner key is a
    firmware function id (kind 3), the remote builds the frame from the code bank, ``keyMapFastBin``
    and ``fastConfigBin`` it was sent. Page 0 holds ON, OFF, the temperature keys on the volume,
    channel and arrow positions, and soft keys A, B, C, D. Page 1 (A) holds the modes, page 2 (B)
    the fan speeds and page 3 (C) the swing directions, each only for what ``fast_config_map``
    (the cloud's JSON, a dict or a string) says the model supports; no map means all of them. A
    page without keys is not written.

    ``fast_config_bin`` is the cloud's ``fastConfigBin``: the app treats a remote with no such
    data but with learned keys (``custom_keys``) as a "custom on/off" remote, that has a single
    page with just the ON and OFF keys, taken from the learned keys whose name starts with ``ON``
    or ``OFF`` (kind 2, the name cut to 16 characters). Pass ``b""`` for that case; ``None`` (the
    default) means the data is present.

    ``learned_keys`` is the cloud ``keyDetail`` as ordered ``(keyName, keyType)`` pairs; the
    "custom on/off" rule takes the first entry whose name starts with ``ON`` and the first that
    starts with ``OFF`` in that order, whatever the type (the app does not look at it), and the
    other entries, ``"text"`` ones included, are not written: an air conditioner remote has no
    page for them. Without it, ``custom_keys`` is used in numeric-then-alphabetical order. The key
    map may be empty, as for a custom type 15 remote whose code is ``no_data``.
    """
    if len(remote_id) != 11:
        raise ValueError("IR remote id must be exactly 11 bytes")
    name_bytes = _name_field(name, strip_slash=False)

    def packet(page: int, records: list[bytes]) -> bytes:
        return _page_packet(
            remote_index=remote_index, device_type=device_type, remote_id=remote_id,
            name_bytes=name_bytes, icon=icon, page=page, records=records)

    labels = [label for label, _kind in _learned_list(learned_keys, custom_keys)]
    if fast_config_bin is not None and not fast_config_bin and labels:
        records = []
        for position, function, prefix in ((TAG["ON"], 5, "ON"), (TAG["OFF"], 6, "OFF")):
            label = next((item for item in labels if item.startswith(prefix)), None)
            if label is not None:
                payload = label[:_ARC_CUSTOM_LABEL_CHARS].encode("utf-8")[:_KEY_BYTES]
                records.append(_record(position, function, KIND_NAME, payload))
        return (packet(0, records),) if records else ()

    pages = []
    main = [_record(position, function, KIND_FUNCTION, function.to_bytes(2, "big"))
            for position, function in _ARC_MAIN_KEYS]
    for position, function in _ARC_SOFT_KEYS:
        kind = KIND_SOFT if function in _ARC_SOFT_FUNCTIONS else KIND_FUNCTION
        main.append(_record(position, function, kind, function.to_bytes(2, "big")))
    pages.append(packet(0, main))
    for page in (1, 2, 3):
        records = [
            _record(position, function, KIND_FUNCTION, function.to_bytes(2, "big"))
            for function, position in _ARC_PAGE_KEYS[page]
            if arc_key_supported(fast_config_map, function)
        ]
        if records:
            pages.append(packet(page, records))
    return tuple(pages)


# Remote type id (including the *_CUSTOM variant, type + 14) -> page builder.
LAYOUT_TYPES: dict[int, Callable[..., tuple[bytes, ...]]] = {
    1: build_arc_pages,
    15: build_arc_pages,
    10: build_air_pages,
    23: build_air_pages,
}
