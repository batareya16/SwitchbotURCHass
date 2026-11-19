"""IR fan, projector and light pages follow the official app's layout (urc-bundle.js).

Expectations are derived by hand from the app's handlers: ``getFan_fun_key_name`` /
``getProjector_fun_key_name`` / ``getLight_fun_key_name`` (key id -> function id),
``get<Type>KeyIndex`` (main position), ``checkIs<Type>DefaultSupport`` (page membership),
``getDefaultKeysCmd`` (soft keys, placeholders, power) and ``getDefaultKeysCount`` (sub-pages).
"""
import pytest

from conftest import INTEGRATION, load

commands = load(INTEGRATION / "commands.py")
home = load(INTEGRATION / "ir_pages_home.py")

REMOTE_ID = bytes.fromhex("0300000e0e0e0e0e0e0e0e")
HEADER = 3 + 2 + 2          # 0F 62 06, length, crc
PAGE_BODY = 5 + 11 + 64     # index/type/ctrl/mode/icon, id, name
RECORD = 36

ON, OFF, A, B, C, D = 4, 5, 0, 1, 2, 3
LEFT, RIGHT, UP, DOWN, OK, BACK, HOME = 6, 7, 8, 9, 10, 11, 12
SOUNDOFF, VOLADD, VOLDEL, CHUP, CHDOWN = 14, 15, 16, 17, 18
BANK, CUSTOM, SOFT, EMPTY = 1, 2, 4, 254


def parse(packet):
    body = packet[HEADER:]
    count = body[PAGE_BODY + 2]
    start = PAGE_BODY + 3
    assert len(body) == start + count * RECORD
    out = []
    for i in range(count):
        raw = body[start + i * RECORD:start + (i + 1) * RECORD]
        out.append((raw[0], int.from_bytes(raw[1:3], "big"), raw[3], raw[4:]))
    return out


def page_number(packet):
    return packet[HEADER + PAGE_BODY + 1]


def triples(packet):
    return [(pos, fun, kind) for pos, fun, kind, _ in parse(packet)]


def bank(start, length):
    return start.to_bytes(4, "big") + length.to_bytes(2, "big") + bytes(26)


def fun_payload(fun):
    return fun.to_bytes(2, "big") + bytes(30)


def build(device_type, key_map, **extra):
    builder = home.LAYOUT_TYPES[device_type]
    return builder(remote_index=5, device_type=device_type, remote_id=REMOTE_ID, name="Home",
                   key_map=key_map, **extra)


def test_layout_types_cover_every_type_and_custom_variant():
    assert set(home.LAYOUT_TYPES) == {6, 20, 7, 21, 14, 27}
    assert home.LAYOUT_TYPES[6] is home.LAYOUT_TYPES[20]
    assert home.LAYOUT_TYPES[7] is home.LAYOUT_TYPES[21]
    assert home.LAYOUT_TYPES[14] is home.LAYOUT_TYPES[27]


# ------------------------------------------------------------------------------------- FAN ---

def test_fan_full_key_map_uses_three_pages_with_the_app_function_ids():
    # WOFANTAG: ON 2, OFF 4, TIMER 9, AUTO_DIR 5, WIN_1 39, WIN_3 43, ANION 6, MUTE 8, POWER 1
    pages = build(6, [(2, 0, 10), (4, 10, 10), (9, 20, 5), (5, 25, 5), (39, 30, 5), (43, 35, 5),
                      (6, 40, 5), (8, 45, 5), (1, 50, 5)])
    # the page byte is the sub-page number: a fan has pages 0, 3 and 4 (never 1 or 2)
    assert [page_number(p) for p in pages] == [0, 3, 4]
    # main page: keys in key-map order, then soft C (wind speeds, fun 70) and soft D (fun 100)
    assert triples(pages[0]) == [
        (ON, 5, BANK), (OFF, 6, BANK), (A, 90, BANK), (B, 89, BANK), (C, 70, SOFT), (D, 100, SOFT),
    ]
    main = parse(pages[0])
    assert main[0][3] == bank(0, 10) and main[3][3] == bank(25, 5)
    assert main[4][3] == fun_payload(70) and main[5][3] == fun_payload(100)
    # sub-pages count positions from zero in key-map order; POWER is a page-4 key here (fun 105)
    assert triples(pages[1]) == [(0, 72, BANK), (1, 74, BANK)]
    assert triples(pages[2]) == [(0, 113, BANK), (1, 19, BANK), (2, 105, BANK)]
    assert parse(pages[2])[2][3] == bank(50, 5)


def test_fan_without_wind_speeds_or_extras_hides_the_soft_keys_and_fills_the_slots():
    pages = build(6, [(2, 0, 10), (4, 10, 10)])
    assert [page_number(p) for p in pages] == [0]
    # soft C and D hidden (kind 254); timer (A, 90) and auto direction (B, 89) are empty slots
    assert triples(pages[0]) == [
        (ON, 5, BANK), (OFF, 6, BANK), (C, 70, EMPTY), (D, 100, EMPTY), (A, 90, EMPTY), (B, 89, EMPTY),
    ]
    rows = parse(pages[0])
    assert [row[3] for row in rows[2:]] == [fun_payload(70), fun_payload(100), fun_payload(90),
                                            fun_payload(89)]


def test_fan_with_only_a_power_key_writes_it_on_on_and_off_after_the_placeholders():
    pages = build(6, [(1, 7, 100)])
    # POWER alone: nothing is left for page 4 (count 1 - 1), so only the main page exists
    assert [page_number(p) for p in pages] == [0]
    assert triples(pages[0]) == [
        (C, 70, EMPTY), (D, 100, EMPTY), (A, 90, EMPTY), (B, 89, EMPTY), (ON, 105, BANK), (OFF, 105, BANK),
    ]
    rows = parse(pages[0])
    assert rows[4][3] == rows[5][3] == bank(7, 100)


def test_fan_only_power_is_not_repeated_on_page_4_and_the_other_page_4_keys_keep_d_shown():
    pages = build(6, [(1, 0, 10), (6, 10, 5)])
    assert [page_number(p) for p in pages] == [0, 4]
    assert triples(pages[0]) == [
        (C, 70, EMPTY), (D, 100, SOFT), (A, 90, EMPTY), (B, 89, EMPTY), (ON, 105, BANK), (OFF, 105, BANK),
    ]
    assert triples(pages[1]) == [(0, 113, BANK)]


def test_fan_on_key_alone_keeps_power_as_a_page_4_key():
    # an ON key means POWER is not "only power": it stays a regular page-4 key
    pages = build(6, [(2, 0, 10), (1, 10, 10)])
    assert [page_number(p) for p in pages] == [0, 4]
    assert triples(pages[0]) == [
        (ON, 5, BANK), (C, 70, EMPTY), (D, 100, SOFT), (A, 90, EMPTY), (B, 89, EMPTY),
    ]
    assert triples(pages[1]) == [(0, 105, BANK)]


def test_fan_custom_key_is_referenced_by_name_and_custom_power_goes_on_on_and_off():
    pages = build(20, [(5, 0, 10), (1, 10, 10)], custom_keys=frozenset({"5", "1"}))
    rows = parse(pages[0])
    # AUTO_DIR (5) is custom: kind 2 with the key id as its name, at position B
    assert rows[0][:3] == (B, 89, CUSTOM) and rows[0][3].rstrip(b"\0") == b"5"
    # custom power: ON and OFF both carry kind 2 and the name
    assert [row[:3] for row in rows[-2:]] == [(ON, 105, CUSTOM), (OFF, 105, CUSTOM)]
    assert rows[-1][3].rstrip(b"\0") == b"1"
    assert pages[0][HEADER + 1] == 20      # the custom type id is written as the device type


def test_fan_unknown_keys_are_left_out():
    pages = build(6, [(2, 0, 10), (999, 10, 5), (13, 15, 5)])
    assert all(fun not in (999, 13) for _, fun, _ in triples(pages[0]))


# ------------------------------------------------------------------------------ PROJECTOR ---

PJT_FULL = [
    (1, 0, 1), (3, 1, 1), (12, 2, 1), (4, 3, 1), (8, 4, 1), (10, 5, 1), (41, 6, 1), (33, 7, 1),
    (35, 8, 1), (37, 9, 1), (15, 10, 1), (17, 11, 1), (23, 12, 1), (29, 13, 1), (25, 14, 1),
    (27, 15, 1), (6, 16, 1), (2, 17, 1), (14, 18, 1),
]


def test_projector_main_page_positions_and_function_ids():
    pages = build(7, PJT_FULL)
    assert [page_number(p) for p in pages] == [0, 4]
    # WOPJTTAG key order of the map above -> (position, function id)
    assert triples(pages[0]) == [
        (ON, 5, BANK), (OFF, 6, BANK),
        (BACK, 12, BANK),        # Back 12 -> BACK, fun 12
        (HOME, 118, BANK),       # Menu 4 -> HOME, fun 118
        (A, 700, BANK),          # Screen 8 -> A, fun [2,188]
        (B, 21, BANK),           # Play 10 -> B
        (C, 22, BANK),           # Pause 41 -> C
        (VOLADD, 15, BANK),      # VolumeAdd 33
        (VOLDEL, 16, BANK),      # VolumeDelete 35
        (SOUNDOFF, 19, BANK),    # Mute 37
        (CHUP, 107, BANK),       # ScreenAdd 15
        (CHDOWN, 108, BANK),     # ScreenDelete 17
        (UP, 9, BANK), (DOWN, 10, BANK), (LEFT, 7, BANK), (RIGHT, 8, BANK), (OK, 11, BANK),
        (D, 100, SOFT),
    ]
    assert len(parse(pages[0])) == 18
    # Power (2) and List (14) are page-4 keys; Power is not alone so it stays there
    assert triples(pages[1]) == [(0, 105, BANK), (1, 116, BANK)]
    assert parse(pages[1])[1][3] == bank(18, 1)


def test_projector_with_only_power_fills_the_empty_slots_and_writes_power_twice():
    pages = build(21, [(6, 0, 10), (2, 10, 20)])
    assert [page_number(p) for p in pages] == [0]
    assert triples(pages[0]) == [
        (OK, 11, BANK), (D, 100, EMPTY),
        (A, 700, EMPTY), (B, 21, EMPTY), (C, 22, EMPTY),
        (ON, 105, BANK), (OFF, 105, BANK),
    ]
    rows = parse(pages[0])
    assert rows[1][3] == fun_payload(100) and rows[2][3] == fun_payload(700)
    assert rows[5][3] == rows[6][3] == bank(10, 20)
    assert pages[0][HEADER + 1] == 21


def test_projector_list_key_makes_page_4_even_beside_a_lone_power_key():
    pages = build(7, [(2, 0, 10), (14, 10, 10)])
    assert [page_number(p) for p in pages] == [0, 4]
    assert triples(pages[1]) == [(0, 116, BANK)]
    assert (D, 100, SOFT) in triples(pages[0])


def test_projector_custom_key_and_custom_only_power():
    # Menu is custom; Power exists only as a learned key (no key-map entry)
    pages = build(7, [(4, 0, 10)], custom_keys=frozenset({"4", "2"}))
    rows = parse(pages[0])
    assert rows[0][:3] == (HOME, 118, CUSTOM) and rows[0][3].rstrip(b"\0") == b"4"
    assert [row[:3] for row in rows[-2:]] == [(ON, 105, CUSTOM), (OFF, 105, CUSTOM)]
    assert rows[-1][3].rstrip(b"\0") == b"2"
    assert [page_number(p) for p in pages] == [0]


# ----------------------------------------------------------------------------------- LIGHT ---

def test_light_main_page_positions_function_ids_and_empty_slots():
    # WOLIGHTTAG: ON 1, OFF 3, BrightnessAdd 5, BrightnessDelete 7, TemperatureAdd 17,
    # TemperatureDelete 19, TIME30M 6, MODE 9, TIME 4
    pages = build(14, [(1, 0, 10), (3, 10, 10), (5, 20, 5), (7, 25, 5), (17, 30, 5), (19, 35, 5),
                       (6, 40, 5), (9, 45, 5), (4, 50, 5)])
    assert [page_number(p) for p in pages] == [0, 4]
    assert triples(pages[0]) == [
        (ON, 5, BANK), (OFF, 6, BANK),
        (UP, 300, BANK),         # BrightnessAdd -> [1,44]
        (DOWN, 301, BANK),       # BrightnessDelete -> [1,45]
        (RIGHT, 302, BANK),      # TemperatureAdd -> [1,46]
        (LEFT, 303, BANK),       # TemperatureDelete -> [1,47]
        (A, 91, BANK),           # TIME30M
        (D, 100, SOFT),
        (B, 311, EMPTY),         # NIGHT missing -> [1,55]
        (C, 312, EMPTY),         # LIGHT missing -> [1,56]
    ]
    rows = parse(pages[0])
    assert rows[8][3] == fun_payload(311) and rows[9][3] == fun_payload(312)
    assert triples(pages[1]) == [(0, 56, BANK), (1, 90, BANK)]


def test_light_with_all_main_keys_has_no_placeholders_and_no_page_4():
    pages = build(14, [(1, 0, 1), (3, 1, 1), (5, 2, 1), (7, 3, 1), (17, 4, 1), (19, 5, 1),
                       (6, 6, 1), (8, 7, 1), (10, 8, 1)])
    assert [page_number(p) for p in pages] == [0]
    assert triples(pages[0]) == [
        (ON, 5, BANK), (OFF, 6, BANK), (UP, 300, BANK), (DOWN, 301, BANK), (RIGHT, 302, BANK),
        (LEFT, 303, BANK), (A, 91, BANK), (B, 311, BANK), (C, 312, BANK), (D, 100, EMPTY),
    ]


def test_light_only_power_writes_power_on_on_and_off_after_three_placeholders():
    pages = build(27, [(2, 3, 30)])
    assert [page_number(p) for p in pages] == [0]
    assert triples(pages[0]) == [
        (D, 100, EMPTY), (A, 91, EMPTY), (B, 311, EMPTY), (C, 312, EMPTY),
        (ON, 105, BANK), (OFF, 105, BANK),
    ]
    rows = parse(pages[0])
    assert rows[4][3] == rows[5][3] == bank(3, 30)
    assert pages[0][HEADER + 1] == 27


def test_light_timeadd_and_timedelete_are_not_written():
    # TIMEADD 13 and TIMEDELETE 15 have no page in the app; SET 11 and TIME 4 are page-4 keys
    pages = build(14, [(1, 0, 1), (13, 1, 1), (15, 2, 1), (11, 3, 1), (4, 4, 1)])
    assert [page_number(p) for p in pages] == [0, 4]
    assert triples(pages[1]) == [(0, 110, BANK), (1, 90, BANK)]
    assert all(fun != 115 for _, fun, _ in triples(pages[0]) + triples(pages[1]))


def test_light_custom_key_is_referenced_by_name():
    pages = build(14, [(5, 0, 10), (1, 10, 10)], custom_keys=frozenset({"5"}))
    rows = parse(pages[0])
    assert (UP, 300, CUSTOM) == rows[0][:3] and rows[0][3].rstrip(b"\0") == b"5"
    assert rows[1][:3] == (ON, 5, BANK)


# ---------------------------------------------------------------------------- ALL TYPES ---

@pytest.mark.parametrize("device_type", sorted(home.LAYOUT_TYPES))
def test_packets_are_well_formed_for_every_type(device_type):
    key_map = {6: [(2, 0, 4)], 20: [(2, 0, 4)], 7: [(6, 0, 4)], 21: [(6, 0, 4)],
               14: [(1, 0, 4)], 27: [(1, 0, 4)]}[device_type]
    pages = home.LAYOUT_TYPES[device_type](
        remote_index=7, device_type=device_type, remote_id=REMOTE_ID, name="Living room",
        key_map=key_map, icon=9,
    )
    for packet in pages:
        assert packet[:3] == b"\x0f\x62\x06"
        length = int.from_bytes(packet[3:5], "big")
        assert len(packet) == HEADER + length
        assert int.from_bytes(packet[5:7], "big") == commands.crc16_modbus(packet[HEADER:])
        body = packet[HEADER:]
        assert body[:5] == bytes([7, device_type, commands.CTRL_IR, 0, 9])
        assert body[5:16] == REMOTE_ID
        assert body[16:16 + 11] == b"Living room"
        assert body[16 + 63] == 0


def test_invalid_input_is_rejected():
    with pytest.raises(ValueError):
        home.build_fan_pages(remote_index=0, device_type=6, remote_id=b"short", name="x",
                             key_map=[(2, 0, 1)])
    with pytest.raises(ValueError):
        home.build_light_pages(remote_index=0, device_type=14, remote_id=REMOTE_ID, name="x",
                               key_map=[])
    with pytest.raises(ValueError):
        home.build_projector_pages(remote_index=0, device_type=7, remote_id=REMOTE_ID, name="x",
                                   key_map=[(6, 0, 0)])
