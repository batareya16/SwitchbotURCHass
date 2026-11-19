"""IR air conditioner and air purifier pages follow the official app's layout.

Expectations are derived by hand from the app's handlers in urc-bundle.js: the air conditioner
one (getARCKeysPage*, assembleCmd, isSupportKey) and the air purifier one (getAir_fun_key_name,
getDefaultKeysCmd, checkIsAirDefaultSupport, getAirKeyIndex).
"""
import pytest

from conftest import INTEGRATION, load

commands = load(INTEGRATION / "commands.py")
ac = load(INTEGRATION / "ir_pages_ac.py")

REMOTE_ID = bytes.fromhex("0300000e0e0e0e0e0e0e0e")
HEADER = 3 + 2 + 2          # 0F 62 06, length, crc
PAGE_BODY = 5 + 11 + 64     # index/type/ctrl/mode/icon, id, name
RECORD = 36

A, B, C, D, ON, OFF = 0, 1, 2, 3, 4, 5
LEFT, RIGHT, UP, DOWN = 6, 7, 8, 9
SOUNDOFF, VOLADD, VOLDEL, CHUP, CHDOWN = 14, 15, 16, 17, 18


def body(packet):
    return packet[HEADER:]


def page_number(packet):
    return body(packet)[PAGE_BODY + 1]


def records(packet):
    data = body(packet)
    count = data[PAGE_BODY + 2]
    start = PAGE_BODY + 3
    assert len(data) == start + count * RECORD
    out = []
    for i in range(count):
        row = data[start + i * RECORD:start + (i + 1) * RECORD]
        out.append((row[0], int.from_bytes(row[1:3], "big"), row[3], row[4:]))
    return out


def short(records_):
    return [(pos, fun, kind) for pos, fun, kind, _ in records_]


def code(start, length):
    return start.to_bytes(4, "big") + length.to_bytes(2, "big") + bytes(26)


def fun_payload(function):
    return function.to_bytes(2, "big") + bytes(30)


def by_page(pages):
    return {page_number(packet): packet for packet in pages}


def assert_well_formed(pages):
    for packet in pages:
        assert packet[:3] == b"\x0f\x62\x06"
        length = int.from_bytes(packet[3:5], "big")
        assert len(packet) == HEADER + length
        assert int.from_bytes(packet[5:7], "big") == commands.crc16_modbus(packet[HEADER:])


# ---- air purifier (types 10 and 23) --------------------------------------------------------
# WOAIRTAG ids: Power 1, ON 2, AutoMate 3, OFF 4, Wind1 6, Schedule 7, Wind2 8, Mode 9,
# Wind3 10, Anion 11, Sleep 12, Cozy 13, ChildLock 14, Mute 15, Timer 16.

def air(key_map, **extra):
    extra.setdefault("device_type", 10)
    return ac.build_air_pages(
        remote_index=7, remote_id=REMOTE_ID, name="Purifier", key_map=key_map, **extra)


FULL = [
    (2, 0, 10), (4, 10, 10), (15, 20, 10), (9, 30, 10), (16, 40, 10),
    (6, 50, 5), (8, 55, 5), (10, 60, 5),
    (1, 65, 8), (3, 73, 5), (12, 78, 5),
]


def test_layout_registry_covers_both_types_and_their_custom_variants():
    assert set(ac.LAYOUT_TYPES) == {1, 15, 10, 23}
    assert ac.LAYOUT_TYPES[1] is ac.LAYOUT_TYPES[15] is ac.build_arc_pages
    assert ac.LAYOUT_TYPES[10] is ac.LAYOUT_TYPES[23] is ac.build_air_pages


def test_air_main_page_positions_functions_and_soft_keys():
    pages = air(FULL)
    assert [page_number(p) for p in pages] == [0, 1, 4]
    main = records(pages[0])
    # key-map order, then A and D (functions 70 and 100, kind 4: both have keys); no Power pair
    assert short(main) == [
        (ON, 5, 1), (OFF, 6, 1), (SOUNDOFF, 19, 1), (B, 56, 1), (C, 90, 1), (A, 70, 4), (D, 100, 4),
    ]
    assert main[0][3] == code(0, 10)
    assert main[3][3] == code(30, 10)            # Mode sits on B as a real key
    assert main[5][3] == fun_payload(70) and main[6][3] == fun_payload(100)


def test_air_fan_speeds_and_d_keys_are_numbered_from_zero():
    pages = by_page(air(FULL))
    assert short(records(pages[1])) == [(0, 72, 1), (1, 73, 1), (2, 74, 1)]
    # Power 105, AutoMate 117, Sleep 57, in key-map order
    d = records(pages[4])
    assert short(d) == [(0, 105, 1), (1, 117, 1), (2, 57, 1)]
    assert d[0][3] == code(65, 8)


def test_air_header_of_a_page():
    packet = air(FULL, icon=3)[0]
    data = body(packet)
    assert data[:5] == bytes([7, 10, commands.CTRL_IR, 0, 3])
    assert data[5:16] == REMOTE_ID
    assert data[16:16 + 64] == b"Purifier".ljust(64, b"\0")
    assert data[PAGE_BODY:PAGE_BODY + 2] == b"\x00\x00"
    assert_well_formed([packet])


def test_air_custom_type_uses_the_same_layout_and_name_loses_slashes():
    pages = air(FULL, device_type=23)
    assert body(pages[0])[1] == 23
    named = ac.build_air_pages(remote_index=1, device_type=10, remote_id=REMOTE_ID, name="A/B/C",
                               key_map=FULL)
    assert body(named[0])[16:80].rstrip(b"\0") == b"ABC"


def test_air_minimal_remote_hides_soft_keys_and_adds_placeholders():
    pages = air([(2, 0, 10), (4, 10, 10)])
    assert [page_number(p) for p in pages] == [0]
    main = records(pages[0])
    # ON, OFF, A hidden (no fan speed), D hidden (no D key), then the B and C placeholders
    assert short(main) == [(ON, 5, 1), (OFF, 6, 1), (A, 70, 254), (D, 100, 254), (B, 56, 254), (C, 90, 254)]
    assert main[4][3] == fun_payload(70)          # the app copies A's id into B's payload
    assert main[5][3] == fun_payload(90)


def test_air_only_power_is_written_on_on_and_off_and_left_out_of_page_four():
    pages = air([(1, 100, 20), (6, 120, 5)])
    assert [page_number(p) for p in pages] == [0, 1]       # page 4 would hold nothing
    main = records(pages[0])
    assert short(main) == [
        (A, 70, 4), (D, 100, 254), (B, 56, 254), (C, 90, 254), (ON, 105, 1), (OFF, 105, 1),
    ]
    assert main[4][3] == main[5][3] == code(100, 20)


def test_air_power_next_to_on_off_stays_a_page_four_key():
    pages = by_page(air([(2, 0, 10), (4, 10, 10), (1, 20, 10)]))
    assert short(records(pages[0]))[:2] == [(ON, 5, 1), (OFF, 6, 1)]
    assert all(fun != 105 for _, fun, _ in short(records(pages[0])))
    assert short(records(pages[4])) == [(0, 105, 1)]
    soft = {pos: kind for pos, fun, kind in short(records(pages[0])) if fun in (70, 100)}
    assert soft == {A: 254, D: 4}


def test_air_custom_key_is_referenced_by_name_and_power_keeps_the_name():
    pages = air([(1, 0, 10), (9, 10, 5)], custom_keys=frozenset({"1", "9"}))
    main = records(pages[0])
    mode = next(r for r in main if r[1] == 56)
    assert (mode[0], mode[2], mode[3].rstrip(b"\0")) == (B, 2, b"9")
    power = [r for r in main if r[1] == 105]
    assert [r[0] for r in power] == [ON, OFF]
    assert all(r[2] == 2 and r[3].rstrip(b"\0") == b"1" for r in power)
    assert_well_formed(pages)


def test_air_learned_keys_join_their_page_or_page_four_with_function_115():
    pages = by_page(air([(2, 0, 5)], custom_keys=frozenset({"4", "99", "5"})))
    main = records(pages[0])
    # OFF is a default key learned by name: it keeps its place on the main page
    assert short(main)[:2] == [(ON, 5, 1), (OFF, 6, 2)]
    assert main[1][3].rstrip(b"\0") == b"4"
    # 5 (Speed) and 99 are not default keys of any page: page four, function 115, by name
    d = records(pages[4])
    assert short(d) == [(0, 115, 2), (1, 115, 2)]
    assert [r[3].rstrip(b"\0") for r in d] == [b"5", b"99"]
    assert {pos: kind for pos, fun, kind in short(main) if fun in (70, 100)} == {A: 254, D: 4}


def test_air_page_four_stops_at_fifteen_records():
    labels = frozenset(str(n) for n in range(100, 121))
    pages = by_page(air([(2, 0, 5)], custom_keys=labels))
    assert len(records(pages[4])) == 15
    assert [r[3].rstrip(b"\0") for r in records(pages[4])][:2] == [b"100", b"101"]


def test_air_unknown_keys_are_left_out_and_empty_input_is_rejected():
    pages = air([(2, 0, 5), (999, 5, 5)])
    assert all(fun != 115 for _, fun, _ in short(records(pages[0])))
    with pytest.raises(ValueError):
        air([])
    with pytest.raises(ValueError):
        ac.build_air_pages(remote_index=1, device_type=10, remote_id=b"short", name="x", key_map=FULL)


# ---- air conditioner (types 1 and 15) ------------------------------------------------------

def arc(key_map=(), **extra):
    extra.setdefault("device_type", 1)
    return ac.build_arc_pages(remote_index=4, remote_id=REMOTE_ID, name="AC", key_map=list(key_map), **extra)


def test_arc_main_page_is_all_function_records_with_soft_keys():
    pages = arc()
    assert [page_number(p) for p in pages] == [0, 1, 2, 3]
    main = records(pages[0])
    assert short(main) == [
        (ON, 5, 3), (OFF, 6, 3),
        (VOLADD, 60, 3), (VOLDEL, 61, 3), (CHUP, 60, 3), (CHDOWN, 61, 3), (UP, 60, 3), (DOWN, 61, 3),
        (A, 59, 4), (B, 70, 4), (C, 80, 4), (D, 0, 3),
    ]
    # the payload is the function id, never a code-bank slice
    assert main[0][3] == fun_payload(5)
    assert main[2][3] == fun_payload(60)
    assert main[8][3] == fun_payload(59)
    assert main[11][3] == fun_payload(0)


def test_arc_sub_pages_without_a_config_list_every_key_on_fixed_positions():
    pages = by_page(arc())
    assert short(records(pages[1])) == [(0, 51, 3), (1, 54, 3), (2, 52, 3), (3, 50, 3), (4, 53, 3), (5, 55, 3)]
    assert short(records(pages[2])) == [(i, 71 + i, 3) for i in range(6)]
    assert short(records(pages[3])) == [(0, 82, 3), (1, 83, 3), (2, 84, 3)]
    assert records(pages[1])[0][3] == fun_payload(51)


def test_arc_header_ignores_the_key_map_and_names_the_type():
    pages = arc([(11, 0, 10)], device_type=15, icon=2)
    data = body(pages[0])
    assert data[:5] == bytes([4, 15, commands.CTRL_IR, 0, 2])
    assert data[5:16] == REMOTE_ID and data[16:80].rstrip(b"\0") == b"AC"
    assert short(records(pages[0])) == short(records(arc()[0]))
    assert_well_formed(pages)
    assert arc([]) == arc()                       # an air conditioner may come without a key map


CONFIG = {
    "cool": {"modeEnable": 1, "speedMin": 0, "speedMax": 3, "dirMin": 1, "dirMax": 2},
    "heat": {"modeEnable": 1, "speedMin": 0, "speedMax": 2, "dirMin": 1, "dirMax": 1},
    "dry": {"modeEnable": 0},
    "auto": {"modeEnable": 0},
}


@pytest.mark.parametrize("as_text", [False, True])
def test_arc_config_map_selects_modes_speeds_and_swing(as_text):
    import json
    config = json.dumps(CONFIG) if as_text else CONFIG
    pages = by_page(arc(fast_config_map=config))
    # modes: cool and heat only, on their fixed positions 0 and 1
    assert short(records(pages[1])) == [(0, 51, 3), (1, 54, 3)]
    # speed: the highest speedMax is 3, so functions 71..74 (auto and 1-3)
    assert short(records(pages[2])) == [(0, 71, 3), (1, 72, 3), (2, 73, 3), (3, 74, 3)]
    # swing: the highest dirMax is 2, so 82 and 83
    assert short(records(pages[3])) == [(0, 82, 3), (1, 83, 3)]
    # page 0 does not depend on the config
    assert len(records(pages[0])) == 12


def test_arc_positions_stay_fixed_when_a_mode_is_missing():
    config = {"auto": {"modeEnable": 1, "speedMax": 0}, "wind": {"modeEnable": 1, "speedMax": 0}}
    pages = by_page(arc(fast_config_map=config))
    assert short(records(pages[1])) == [(3, 50, 3), (4, 53, 3)]
    assert short(records(pages[2])) == [(0, 71, 3)]


def test_arc_pages_with_nothing_to_show_are_not_written():
    config = {"cool": {"modeEnable": 1, "speedMin": 0, "speedMax": 0, "dirMin": 0, "dirMax": 0}}
    pages = by_page(arc(fast_config_map=config))
    assert sorted(pages) == [0, 1, 2]              # dirMax 0 -> upper bound 81, no swing key
    assert short(records(pages[2])) == [(0, 71, 3)]
    none = by_page(arc(fast_config_map={"cool": {"modeEnable": 0}}))
    assert sorted(none) == [0]
    # an empty or unreadable config means "everything"
    for empty in (None, {}, "", "not json"):
        assert sorted(by_page(arc(fast_config_map=empty))) == [0, 1, 2, 3]


def test_arc_custom_on_off_remote_writes_only_the_two_named_keys():
    pages = arc(custom_keys=frozenset({"OFF_remote", "ON_remote", "other"}), fast_config_bin=b"")
    assert [page_number(p) for p in pages] == [0]
    main = records(pages[0])
    assert short(main) == [(ON, 5, 2), (OFF, 6, 2)]
    assert [r[3].rstrip(b"\0") for r in main] == [b"ON_remote", b"OFF_remote"]
    assert_well_formed(pages)


def test_arc_custom_on_off_with_one_key_or_a_long_name():
    only_on = arc(custom_keys=frozenset({"ON"}), fast_config_bin=b"")
    assert short(records(only_on[0])) == [(ON, 5, 2)]
    long_name = "ON" + "x" * 30
    cut = arc(custom_keys=frozenset({long_name}), fast_config_bin=b"")
    assert records(cut[0])[0][3].rstrip(b"\0") == long_name[:16].encode()
    assert arc(custom_keys=frozenset({"volume"}), fast_config_bin=b"") == ()


def test_arc_with_fast_config_data_ignores_learned_keys():
    normal = arc()
    assert arc(custom_keys=frozenset({"ON"})) == normal                 # data presence unknown
    assert arc(custom_keys=frozenset({"ON"}), fast_config_bin=b"\x01\x02") == normal
    assert arc(fast_config_bin=b"") == normal                           # no learned keys at all
    assert_well_formed(normal)


def test_arc_rejects_a_bad_remote_id():
    with pytest.raises(ValueError):
        ac.build_arc_pages(remote_index=1, device_type=1, remote_id=b"x", name="AC", key_map=[])
