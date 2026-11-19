"""IR audio, water heater, robot and camera pages follow the official app's layout.

Expectations are derived by hand from the app's handlers in urc-bundle.js (keys are the app's
WOxxxTAG_ ids; positions are the WORWSTAG_ values: A0 B1 C2 D3 ON4 OFF5 LEFT6 RIGHT7 UP8 DOWN9
OK10 BACK11 HOME12 SOUNDOFF14 VOLADD15 VOLDEL16).
"""
import pytest

from conftest import INTEGRATION, load

commands = load(INTEGRATION / "commands.py")
misc = load(INTEGRATION / "ir_pages_misc.py")

REMOTE_ID = bytes.fromhex("0300000e0e0e0e0e0e0e0e")
HEADER = 3 + 2 + 2          # 0F 62 06, length, crc
PAGE_BODY = 5 + 11 + 64     # index/type/ctrl/mode/icon, id, name
RECORD = 36


def full_records(packet):
    body = packet[HEADER:]
    count = body[PAGE_BODY + 2]
    start = PAGE_BODY + 3
    assert len(body) == start + count * RECORD
    return [
        (body[start + i * RECORD], int.from_bytes(body[start + i * RECORD + 1:start + i * RECORD + 3], "big"),
         body[start + i * RECORD + 3], body[start + i * RECORD + 4:start + (i + 1) * RECORD])
        for i in range(count)
    ]


def short(packet):
    return [(pos, fun, kind) for pos, fun, kind, _ in full_records(packet)]


def page_numbers(pages):
    return [packet[HEADER + PAGE_BODY + 1] for packet in pages]


def ref(start, length):
    return start.to_bytes(4, "big") + length.to_bytes(2, "big") + bytes(26)


def build(type_id, key_map, **extra):
    return misc.LAYOUT_TYPES[type_id](
        remote_index=5, device_type=type_id, remote_id=REMOTE_ID, name="Misc", key_map=key_map, **extra
    )


def test_layout_types_cover_every_assigned_type_and_custom_variant():
    assert set(misc.LAYOUT_TYPES) == {8, 22, 11, 24, 12, 25, 13, 26}
    assert misc.LAYOUT_TYPES[11] is misc.LAYOUT_TYPES[24]
    assert misc.LAYOUT_TYPES[12] is misc.LAYOUT_TYPES[25]
    assert misc.LAYOUT_TYPES[13] is misc.LAYOUT_TYPES[26]
    assert misc.LAYOUT_TYPES[8] is misc.LAYOUT_TYPES[22]


# ---- audio (11) ------------------------------------------------------------------------------

# ON 2, OFF 4, Volume+ 13, Volume- 17, Mute 15, OK 5, Last 25, Number1 12, Number0 30,
# Play 21, Power 11, Stop 6
AUDIO_KEYS = [
    (2, 0, 10), (4, 10, 10), (13, 20, 10), (17, 30, 10), (15, 40, 10), (5, 50, 10), (25, 60, 10),
    (12, 70, 10), (30, 80, 10), (21, 90, 10), (11, 100, 10), (6, 110, 10),
]


def test_audio_main_page_positions_functions_and_soft_keys():
    pages = build(11, AUDIO_KEYS)
    assert page_numbers(pages) == [0, 1, 4]
    assert short(pages[0]) == [
        (4, 115, 1), (5, 115, 1),      # ON / OFF have no function case in the app: default 115
        (15, 15, 1), (16, 16, 1),      # volume
        (14, 19, 1),                   # mute on SOUNDOFF
        (10, 11, 1),                   # OK
        (1, 27, 1),                    # Last sits on B itself
        (0, 39, 4),                    # A opens the digits: shown
        (3, 100, 4),                   # D opens playback/power: shown
        (2, 28, 254),                  # Next is missing: hidden placeholder on C
    ]
    records = full_records(pages[0])
    assert records[0][3] == ref(0, 10) and records[6][3] == ref(60, 10)
    # the soft key records carry their own function bytes, the C placeholder Next's
    assert records[7][3] == bytes([0, 39]) + bytes(30)
    assert records[8][3] == bytes([0, 100]) + bytes(30)
    assert records[9][3] == bytes([0, 28]) + bytes(30)


def test_audio_sub_pages_number_their_keys_in_key_map_order():
    pages = build(11, AUDIO_KEYS)
    assert short(pages[1]) == [(0, 41, 1), (1, 40, 1)]                 # Number1, Number0
    # Play 21, Power 11 (an ordinary key because ON/OFF exist), Stop 6
    assert short(pages[2]) == [(0, 21, 1), (1, 105, 1), (2, 23, 1)]


def test_audio_missing_last_gets_a_placeholder_with_the_apps_odd_payload():
    pages = build(11, [(2, 0, 10), (4, 10, 10)])
    assert page_numbers(pages) == [0]
    placeholders = {pos: (fun, kind, payload[:2]) for pos, fun, kind, payload in full_records(pages[0])
                    if kind == 254}
    # A (digits) and D (page 4) are hidden soft keys; B and C are placeholders for Last and Next.
    assert placeholders == {
        0: (39, 254, bytes([0, 39])), 3: (100, 254, bytes([0, 100])),
        1: (27, 254, bytes([0, 39])),          # the app copies A's bytes into B's placeholder
        2: (28, 254, bytes([0, 28])),
    }


def test_audio_power_alone_goes_on_on_and_off_and_leaves_page_four():
    # Power 11, Volume+ 13, Play 21 (no ON/OFF keys)
    pages = build(11, [(11, 0, 100), (13, 100, 50), (21, 150, 50)])
    assert page_numbers(pages) == [0, 4]
    assert short(pages[0]) == [
        (15, 15, 1),
        (0, 39, 254),                  # no digits
        (3, 100, 4),                   # Play is still behind D
        (1, 27, 254), (2, 28, 254),    # no Last / Next
        (4, 105, 1), (5, 105, 1),      # Power on ON and OFF
    ]
    records = full_records(pages[0])
    assert records[-2][3] == records[-1][3] == ref(0, 100)
    assert short(pages[1]) == [(0, 21, 1)]                              # Power is not repeated


def test_audio_power_alone_with_nothing_else_hides_d_and_writes_one_page():
    pages = build(11, [(11, 0, 10)])
    assert page_numbers(pages) == [0]
    assert short(pages[0]) == [
        (0, 39, 254), (3, 100, 254), (1, 27, 254), (2, 28, 254), (4, 105, 1), (5, 105, 1),
    ]


def test_audio_on_without_off_keeps_power_as_an_ordinary_page_four_key():
    pages = build(11, [(2, 0, 10), (11, 10, 10)])
    assert page_numbers(pages) == [0, 4]
    assert (3, 100, 4) in short(pages[0])
    assert short(pages[1]) == [(0, 105, 1)]
    assert [r for r in short(pages[0]) if r[1] == 105] == []


def test_audio_custom_keys_are_named_and_a_custom_power_still_goes_on_on_and_off():
    pages = build(11, [(13, 0, 10), (11, 10, 10)], custom_keys=frozenset({"13", "11"}))
    volume = next(r for r in full_records(pages[0]) if r[1] == 15)
    assert volume[2] == 2 and volume[3].rstrip(b"\0") == b"13"
    power = [r for r in full_records(pages[0]) if r[1] == 105]
    assert [r[0] for r in power] == [4, 5]
    assert all(r[2] == 2 and r[3].rstrip(b"\0") == b"11" for r in power)


def test_audio_custom_only_keys_follow_the_key_map():
    # Number 5 (id 20) exists only as a separately uploaded key
    pages = build(11, [(13, 0, 10)], custom_keys=frozenset({"20"}))
    assert page_numbers(pages) == [0, 1]
    assert short(pages[1]) == [(0, 45, 2)]
    assert (0, 39, 4) in short(pages[0])


def test_audio_custom_type_uses_the_same_layout_with_its_own_header_type():
    pages = build(24, AUDIO_KEYS)
    assert short(pages[0]) == short(build(11, AUDIO_KEYS)[0])
    assert pages[0][HEADER + 1] == 24 and pages[0][HEADER] == 5 and pages[0][HEADER + 2] == commands.CTRL_IR


# ---- water heater (12) -----------------------------------------------------------------------

# On 2, Off 4, Temp+ 5, Mode 6, Schedule 15, Power 1
WH_KEYS = [(2, 0, 10), (4, 10, 10), (5, 20, 10), (6, 30, 10), (15, 40, 10), (1, 50, 10)]


def test_water_heater_main_page_and_page_four():
    pages = build(12, WH_KEYS)
    assert page_numbers(pages) == [0, 4]
    assert short(pages[0]) == [
        (4, 5, 1), (5, 6, 1),          # On / Off
        (15, 60, 1),                   # temperature up on VOLADD
        (0, 56, 1),                    # Mode on A
        (3, 100, 4),                   # D: Schedule and Power behind it
        (1, 154, 254),                 # Heat missing: placeholder on B
        (2, 62, 254),                  # KeepWarm missing: placeholder on C
    ]
    assert short(pages[1]) == [(0, 92, 1), (1, 105, 1)]
    placeholder = full_records(pages[0])[5]
    assert placeholder[3] == bytes([0, 154]) + bytes(30)


def test_water_heater_power_alone_moves_to_on_and_off():
    # Power 1, Temp- 7, Heat 11, KeepWarm 8
    pages = build(12, [(1, 0, 100), (7, 100, 10), (11, 110, 10), (8, 120, 10)])
    assert page_numbers(pages) == [0]
    assert short(pages[0]) == [
        (16, 61, 1), (1, 154, 1), (2, 62, 1),
        (3, 100, 254),                 # nothing behind D once Power left it
        (0, 56, 254),                  # Mode missing
        (4, 105, 1), (5, 105, 1),
    ]
    records = full_records(pages[0])
    assert records[-1][3] == records[-2][3] == ref(0, 100)


def test_water_heater_custom_key_and_custom_type():
    pages = build(25, WH_KEYS, custom_keys=frozenset({"5"}))
    temp = next(r for r in full_records(pages[0]) if r[1] == 60)
    assert temp[0] == 15 and temp[2] == 2 and temp[3].rstrip(b"\0") == b"5"
    assert pages[0][HEADER + 1] == 25


# ---- robot vacuum (13) -----------------------------------------------------------------------

# ON 1, OFF 3, Up 5, Down 7, Left 9, Right 11, OK 2, Charge 15, Mode 4, Automate 6
RBT_KEYS = [
    (1, 0, 10), (3, 10, 10), (5, 20, 10), (7, 30, 10), (9, 40, 10), (11, 50, 10), (2, 60, 10),
    (15, 70, 10), (4, 80, 10), (6, 90, 10),
]


def test_robot_main_page_uses_two_byte_function_ids_for_charge_and_automate():
    pages = build(13, RBT_KEYS)
    assert page_numbers(pages) == [0, 4]
    assert short(pages[0]) == [
        (4, 5, 1), (5, 6, 1),
        (8, 9, 1), (9, 10, 1), (6, 7, 1), (7, 8, 1), (10, 11, 1),
        (0, 900, 1),                   # Charge on A, [3, 132]
        (1, 56, 1),                    # Mode on B
        (3, 100, 4),                   # D opens Automate
        (2, 92, 254),                  # Schedule missing: placeholder on C
    ]
    assert short(pages[1]) == [(0, 904, 1)]                             # Automate, [3, 136]
    placeholder = full_records(pages[0])[-1]
    assert placeholder[3] == bytes([0, 92]) + bytes(30)
    assert full_records(pages[0])[7][3] == ref(70, 10)


def test_robot_without_charge_or_automate_hides_d_and_adds_a_placeholder_on_a():
    pages = build(13, [(1, 0, 10), (3, 10, 10), (4, 20, 10), (37, 30, 10)])
    assert page_numbers(pages) == [0]
    assert short(pages[0]) == [
        (4, 5, 1), (5, 6, 1), (1, 56, 1), (2, 92, 1),
        (3, 100, 254),
        (0, 900, 254),
    ]
    assert full_records(pages[0])[-1][3] == bytes([3, 132]) + bytes(30)


def test_robot_has_no_power_key_and_custom_type_matches():
    # key 11 is Right for a robot, not Power; a key map with no power concept writes no ON/OFF twins
    pages = build(26, [(11, 0, 10)])
    assert short(pages[0])[0] == (7, 8, 1)
    assert [r for r in short(pages[0]) if r[0] in (4, 5)] == []
    assert pages[0][HEADER + 1] == 26


# ---- camera / SLR (8) ------------------------------------------------------------------------

def test_camera_has_one_page_with_keys_on_a_b_c():
    pages = build(8, [(1, 0, 10), (4, 10, 10)])               # Shutter, Timer
    assert page_numbers(pages) == [0]
    assert short(pages[0]) == [
        (0, 153, 1), (2, 90, 1),
        (3, 100, 254),
        (1, 116, 254),                 # Menu missing: placeholder on B
    ]
    assert full_records(pages[0])[0][3] == ref(0, 10)


def test_camera_full_key_map_and_unknown_keys():
    pages = build(22, [(2, 0, 10), (1, 10, 10), (4, 20, 10), (999, 30, 10), (11, 40, 10)])
    assert short(pages[0]) == [(1, 116, 1), (0, 153, 1), (2, 90, 1), (3, 100, 254)]
    assert pages[0][HEADER + 1] == 22


# ---- common ----------------------------------------------------------------------------------

@pytest.mark.parametrize("type_id", sorted(misc.LAYOUT_TYPES))
def test_packets_are_well_formed_and_header_matches(type_id):
    pages = build(type_id, [(1, 0, 10), (2, 10, 10), (4, 20, 10)], icon=7)
    assert pages
    for packet in pages:
        assert packet[:3] == b"\x0f\x62\x06"
        length = int.from_bytes(packet[3:5], "big")
        assert len(packet) == HEADER + length
        assert int.from_bytes(packet[5:7], "big") == commands.crc16_modbus(packet[HEADER:])
        body = packet[HEADER:]
        assert body[:5] == bytes([5, type_id, commands.CTRL_IR, 0, 7])
        assert body[5:16] == REMOTE_ID
        assert body[16:80].rstrip(b"\0") == b"Misc"
        assert body[80] == 0


def test_validation_errors():
    with pytest.raises(ValueError):
        misc.LAYOUT_TYPES[11](remote_index=0, device_type=11, remote_id=b"short", name="x",
                              key_map=[(2, 0, 1)])
    with pytest.raises(ValueError):
        build(11, [])
    with pytest.raises(ValueError):
        build(11, [(2, 0, 0)])
