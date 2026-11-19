"""IR page layouts of the official app for audio, water heater, robot vacuum and camera remotes.

Ported from the app's React Native bundle (urc-bundle.js). Every type has its own handler there,
with the same shape as the TV one (see ``commands.build_tv_pages``): a table that turns a cloud
key id into a firmware function id (``getXxx_fun_key_name``), the screen position of each key on
the main page (``getXxxKeyIndex``), the keys that go to the numbered sub-pages
(``checkIsXxxDefaultSupport``) and the soft-key / placeholder records the main page ends with.

What differs from the TV layout:

* Only pages 0, 1 and 4 exist (audio), or 0 and 4 (water heater, robot), or 0 alone (camera).
  Pages 2 and 3 are never written; the handlers return a key count of 0 for them.
* The A, B and C soft keys are not always sub-page openers. Where the type has one key that
  belongs on that position (audio Last/Next, water heater Mode/Heat/KeepWarm, robot
  Charge/Mode/Schedule, camera Shutter/Menu/Timer) the key itself sits on A, B or C of the main
  page, and a hidden placeholder (kind 254, carrying the key's function id) is written in its
  place when the key is missing.
* Power: audio and water heater use separate ON/OFF keys. When the key map has only a ``Power``
  key (no ON/OFF) it is written on ON and OFF, like the TV does. Robot and camera have no power
  key at all.

Assumes a remote firmware that supports the hidden D soft key (urc version >= 21), as the TV
builder does: soft keys with nothing behind them are written hidden (254).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from . import commands

TAG = commands.TAG


class _Soft(NamedTuple):
    """A soft key record of the main page, shown (4) when ``keys`` has a key in the key map.

    ``keys`` is ``None`` for the D key, which is shown when the page-4 list has any key.
    """

    position: int
    function: int
    keys: tuple[int, ...] | None


class _Hold(NamedTuple):
    """A hidden placeholder for ``key``, written when the key map does not have it.

    ``payload`` overrides the two function-id bytes the placeholder carries by default.
    """

    position: int
    key: int
    payload: bytes | None = None


class _Layout(NamedTuple):
    function: dict[int, int]          # getXxx_fun_key_name: cloud key id -> firmware function id
    main: dict[int, int]              # getXxxKeyIndex for the keys of checkIsXxxDefaultSupport(0)
    sub: dict[int, tuple[int, ...]]   # checkIsXxxDefaultSupport(page) for pages 1..4
    soft: tuple[_Soft | _Hold, ...]   # tail of page 0, in the order the handler writes it
    power: int | None = None          # the generic Power key (written on ON and OFF when alone)
    on_off: tuple[int, ...] = ()      # the ON / OFF keys that make Power an ordinary key


# ---- Audio (ADO 11, ADO_CUSTOM 24): module 1789124910520, WOAUDIOTAG_* --------------------------
_ADO_POWER = 11
_ADO_FUNCTION = {
    13: 15, 17: 16, 11: 105, 15: 19, 8: 12,                      # volume +/-, power, mute, back
    30: 40, 12: 41, 14: 42, 16: 43, 18: 44, 20: 45, 22: 46, 24: 47, 26: 48, 28: 49,  # 0..9
    21: 21, 27: 22, 6: 23, 19: 25, 23: 26, 25: 27, 29: 28,       # play, pause, stop, <<, >>, |<, >|
    1: 7, 9: 8, 3: 9, 7: 10, 5: 11,                              # left, right, up, down, ok
    2: 115, 4: 115,                                              # ON / OFF have no case: default
}
# getAudioKeyIndex for checkIsAudioDefaultSupport(0): Last and Next sit on B and C themselves.
_ADO_MAIN = {
    2: TAG["ON"], 4: TAG["OFF"], 15: TAG["SOUNDOFF"], 8: TAG["BACK"], 13: TAG["VOLADD"],
    17: TAG["VOLDEL"], 1: TAG["LEFT"], 9: TAG["RIGHT"], 3: TAG["UP"], 7: TAG["DOWN"],
    5: TAG["OK"], 25: TAG["B"], 29: TAG["C"],
}
_ADO_DIGITS = (30, 12, 14, 16, 18, 20, 22, 24, 26, 28)
_ADO_SUB = {
    1: _ADO_DIGITS,                       # opened by A
    4: (19, 21, 23, 27, 6, _ADO_POWER),   # opened by D: playback and Power
}
_ADO_LAYOUT = _Layout(
    function=_ADO_FUNCTION,
    main=_ADO_MAIN,
    sub=_ADO_SUB,
    soft=(
        _Soft(TAG["A"], 39, _ADO_DIGITS),
        _Soft(TAG["D"], 100, None),
        # The app copies A's function bytes (0, 39) into Last's placeholder, not Last's own.
        _Hold(TAG["B"], 25, bytes([0, 39])),
        _Hold(TAG["C"], 29),
    ),
    power=_ADO_POWER,
    on_off=(2, 4),
)

# ---- Water heater (WHEARER 12, WHEARER_CUSTOM 25): module ...531, WOWHEATERTAG_* ----------------
_WH_POWER = 1
_WH_FUNCTION = {2: 5, 4: 6, 11: 154, 8: 62, 13: 90, 7: 61, 5: 60, 1: 105, 15: 92, 6: 56}
# getWHeaterKeyIndex: Mode, Heat and KeepWarm sit on A, B, C; temperature uses the volume keys.
_WH_MAIN = {
    2: TAG["ON"], 4: TAG["OFF"], 7: TAG["VOLDEL"], 5: TAG["VOLADD"],
    6: TAG["A"], 11: TAG["B"], 8: TAG["C"],
}
_WH_SUB = {4: (_WH_POWER, 13, 15)}        # Power, Time, Schedule, opened by D
_WH_LAYOUT = _Layout(
    function=_WH_FUNCTION,
    main=_WH_MAIN,
    sub=_WH_SUB,
    soft=(
        _Soft(TAG["D"], 100, None),
        _Hold(TAG["A"], 6),
        _Hold(TAG["B"], 11),
        _Hold(TAG["C"], 8),
    ),
    power=_WH_POWER,
    on_off=(2, 4),
)

# ---- Robot vacuum (RBT 13, RBT_CUSTOM 26): module ...528, WORBTTAG_* ----------------------------
# Charge (900) and Automate (904) have a non-zero high byte: [3, 132] and [3, 136].
_RBT_FUNCTION = {1: 5, 3: 6, 15: 900, 4: 56, 37: 92, 6: 904, 5: 9, 7: 10, 9: 7, 11: 8, 2: 11}
_RBT_MAIN = {
    1: TAG["ON"], 3: TAG["OFF"], 15: TAG["A"], 4: TAG["B"], 37: TAG["C"],
    5: TAG["UP"], 7: TAG["DOWN"], 9: TAG["LEFT"], 11: TAG["RIGHT"], 2: TAG["OK"],
}
_RBT_SUB = {4: (6,)}                       # Automate, opened by D
_RBT_LAYOUT = _Layout(
    function=_RBT_FUNCTION,
    main=_RBT_MAIN,
    sub=_RBT_SUB,
    soft=(
        _Soft(TAG["D"], 100, None),
        _Hold(TAG["A"], 15),
        _Hold(TAG["B"], 4),
        _Hold(TAG["C"], 37),
    ),
)

# ---- SLR / camera (SLR 8, SLR_CUSTOM 22): module ...521 (m1090636), WOCAMERATAG_* ---------------
_SLR_FUNCTION = {1: 153, 2: 116, 4: 90}
_SLR_MAIN = {1: TAG["A"], 2: TAG["B"], 4: TAG["C"]}   # Shutter, Menu, Timer
_SLR_LAYOUT = _Layout(
    function=_SLR_FUNCTION,
    main=_SLR_MAIN,
    sub={},                                           # getDefaultKeysCount is 0 on every page > 0
    soft=(
        _Soft(TAG["D"], 100, None),
        _Hold(TAG["A"], 1),
        _Hold(TAG["B"], 2),
        _Hold(TAG["C"], 4),
    ),
)

# DIY (type 9, module ...526) is not covered: it has no cloud key map. Its keys all come from the
# remote's own ``keyDetail`` list (named keys, first three on A-C, the rest on page 4).


def _build(
    layout: _Layout,
    *,
    remote_index: int,
    device_type: int,
    remote_id: bytes,
    name: str,
    key_map: list[tuple[int, int, int]],
    icon: int,
    custom_keys: frozenset[str],
) -> tuple[bytes, ...]:
    if len(remote_id) != 11:
        raise ValueError("IR remote id must be exactly 11 bytes")
    if not key_map:
        raise ValueError("IR key map must not be empty")
    name_bytes = bytearray(commands.pad(name.encode("utf-8"), 64))
    name_bytes[63] = 0

    def block(key: int, start: int, length: int) -> tuple[int, bytes]:
        if str(key) in custom_keys:
            label = str(key).encode("utf-8")[:31]
            return 2, label.ljust(32, b"\0")
        if not 0 <= start <= 0xFFFFFFFF or not 0 < length <= 0xFFFF:
            raise ValueError("IR code-bank reference is out of range")
        return 1, (start.to_bytes(4, "big") + length.to_bytes(2, "big")).ljust(32, b"\0")

    def record(position: int, function: int, kind: int, payload: bytes = b"") -> bytes:
        return bytes([position]) + function.to_bytes(2, "big") + bytes([kind]) + payload.ljust(32, b"\0")

    supported = set(layout.main)
    for keys in layout.sub.values():
        supported.update(keys)
    entries = [entry for entry in key_map if entry[0] in layout.function and entry[0] in supported]
    listed = {entry[0] for entry in entries}
    # keys uploaded on their own (keyDetail) that the key map does not mention come after it
    for label in sorted(custom_keys):
        if label.isdigit() and int(label) in supported and int(label) not in listed:
            entries.append((int(label), 0, 1))
            listed.add(int(label))
    present = listed
    only_power = (
        layout.power is not None
        and layout.power in present
        and not any(key in present for key in layout.on_off)
    )
    page4_shown = any(
        key in present and not (only_power and key == layout.power) for key in layout.sub.get(4, ())
    )

    pages: list[bytes] = []
    for page in range(5):
        records: list[bytes] = []
        wanted = layout.main if page == 0 else layout.sub.get(page, ())
        for key, start, length in entries:
            if only_power and key == layout.power:
                continue
            if key not in wanted:
                continue
            kind, payload = block(key, start, length)
            position = layout.main[key] if page == 0 else len(records)
            records.append(record(position, layout.function[key], kind, payload))
        if page == 0:
            for step in layout.soft:
                if isinstance(step, _Soft):
                    shown = page4_shown if step.keys is None else any(key in present for key in step.keys)
                    records.append(record(
                        step.position, step.function, 4 if shown else 254,
                        step.function.to_bytes(2, "big"),
                    ))
                elif step.key not in present:
                    function = layout.function[step.key]
                    records.append(record(
                        step.position, function, 254,
                        step.payload if step.payload is not None else function.to_bytes(2, "big"),
                    ))
            if only_power:
                power = next(entry for entry in entries if entry[0] == layout.power)
                kind, payload = block(*power)
                for position in (TAG["ON"], TAG["OFF"]):
                    records.append(record(position, layout.function[layout.power], kind, payload))
        elif not records:
            continue
        body = bytes([remote_index & 0xFF, device_type & 0xFF, commands.CTRL_IR, 0, icon & 0xFF]) \
            + remote_id + bytes(name_bytes) + bytes([0, page, len(records)]) + b"".join(records)
        pages.append(b"\x0f\x62\x06" + commands.s16(len(body)) + commands.s16(commands.crc16_modbus(body)) + body)
    return tuple(pages)


def _builder(layout: _Layout) -> Callable[..., tuple[bytes, ...]]:
    def build(
        *,
        remote_index: int,
        device_type: int,
        remote_id: bytes,
        name: str,
        key_map: list[tuple[int, int, int]],
        icon: int = 0,
        custom_keys: frozenset[str] = frozenset(),
    ) -> tuple[bytes, ...]:
        return _build(
            layout, remote_index=remote_index, device_type=device_type, remote_id=remote_id,
            name=name, key_map=key_map, icon=icon, custom_keys=custom_keys,
        )

    return build


build_audio_pages = _builder(_ADO_LAYOUT)
build_water_heater_pages = _builder(_WH_LAYOUT)
build_robot_pages = _builder(_RBT_LAYOUT)
build_camera_pages = _builder(_SLR_LAYOUT)

# remote type id (and its *_CUSTOM variant, type + 14) -> page builder
LAYOUT_TYPES: dict[int, Callable[..., tuple[bytes, ...]]] = {
    8: build_camera_pages, 22: build_camera_pages,
    11: build_audio_pages, 24: build_audio_pages,
    12: build_water_heater_pages, 25: build_water_heater_pages,
    13: build_robot_pages, 26: build_robot_pages,
}
