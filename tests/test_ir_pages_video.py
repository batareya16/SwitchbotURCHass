"""IPTV, set-top box and DVD pages follow the official app's layout (urc-bundle.js).

Expectations are derived by hand from the app's handlers: getXxx_fun_key_name (cloud key id ->
function id), getXxxKeyIndex (page-0 position), checkIsXxxDefaultSupport (page membership) and
getDefaultKeysCmd (soft keys A-D, Power on ON and OFF).
"""
import pytest
from conftest import INTEGRATION, load

commands = load(INTEGRATION / "commands.py")
video = load(INTEGRATION / "ir_pages_video.py")

REMOTE_ID = bytes.fromhex("0300000e0e0e0e0e0e0e0e")
HEADER = 3 + 2 + 2          # 0F 62 06, length, crc
PAGE_BODY = 5 + 11 + 64     # index/type/ctrl/mode/icon, id, name
RECORD = 36

A, B, C, D, ON, OFF = 0, 1, 2, 3, 4, 5
LEFT, RIGHT, UP, DOWN, OK, BACK, HOME, SOUNDOFF, VOLADD, VOLDEL, CHUP, CHDOWN = 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18


def code(start, length):
    return start.to_bytes(4, "big") + length.to_bytes(2, "big") + bytes(26)


def fn_payload(function):
    return function.to_bytes(2, "big") + bytes(30)


def records(packet):
    body = packet[HEADER:]
    count = body[PAGE_BODY + 2]
    start = PAGE_BODY + 3
    assert len(body) == start + count * RECORD
    return [
        (body[start + i * RECORD], int.from_bytes(body[start + i * RECORD + 1:start + i * RECORD + 3], "big"),
         body[start + i * RECORD + 3], body[start + i * RECORD + 4:start + (i + 1) * RECORD])
        for i in range(count)
    ]


def page_numbers(pages):
    return [packet[HEADER + PAGE_BODY + 1] for packet in pages]


def check_packets(pages):
    for packet in pages:
        length = int.from_bytes(packet[3:5], "big")
        assert packet[:3] == b"\x0f\x62\x06"
        assert len(packet) == HEADER + length
        assert int.from_bytes(packet[5:7], "big") == commands.crc16_modbus(packet[HEADER:])


def build(builder, device_type, key_map, **extra):
    pages = builder(remote_index=5, device_type=device_type, remote_id=REMOTE_ID, name="Video",
                    key_map=key_map, **extra)
    check_packets(pages)
    return pages


def iptv(key_map, device_type=3, **extra):
    return build(video.build_iptv_pages, device_type, key_map, **extra)


def tvbox(key_map, device_type=4, **extra):
    return build(video.build_tvbox_pages, device_type, key_map, **extra)


def dvd(key_map, device_type=5, **extra):
    return build(video.build_dvd_pages, device_type, key_map, **extra)


def test_layout_types_cover_every_video_type_and_its_custom_variant():
    assert set(video.LAYOUT_TYPES) == {3, 4, 5, 17, 18, 19}
    assert video.LAYOUT_TYPES[3] is video.LAYOUT_TYPES[17] is video.build_iptv_pages
    assert video.LAYOUT_TYPES[4] is video.LAYOUT_TYPES[18] is video.build_tvbox_pages
    assert video.LAYOUT_TYPES[5] is video.LAYOUT_TYPES[19] is video.build_dvd_pages


def test_header_carries_type_remote_id_page_and_count():
    pages = dvd([(11, 0, 10), (8, 10, 5)], device_type=19, icon=9)
    body = pages[0][HEADER:]
    assert body[:5] == bytes([5, 19, 1, 0, 9])
    assert body[5:16] == REMOTE_ID
    assert body[16:16 + 5] == b"Video" and body[16 + 63] == 0
    assert body[PAGE_BODY + 1] == 0
    assert body[PAGE_BODY + 2] == len(records(pages[0]))


def test_bad_arguments_are_rejected():
    for builder in (video.build_iptv_pages, video.build_tvbox_pages, video.build_dvd_pages):
        with pytest.raises(ValueError):
            builder(remote_index=0, device_type=3, remote_id=b"short", name="x", key_map=[(1, 0, 1)])


# ---- IPTV ---------------------------------------------------------------------------------


IPTV_KEYS = [
    (1, 0, 100),     # Power
    (5, 100, 50),    # Volume add
    (3, 150, 10),    # Mute
    (9, 160, 10),    # Channel add: the app writes it nowhere
    (25, 170, 10),   # Number1
    (8, 180, 10),    # TV power
    (14, 190, 10),   # List
    (12, 200, 10),   # Menu
    (17, 210, 10),   # OK
]


def test_iptv_main_page_uses_firmware_functions_on_fixed_positions():
    pages = iptv(IPTV_KEYS)
    assert page_numbers(pages) == [0, 1]
    assert [(pos, fun, kind) for pos, fun, kind, _ in records(pages[0])] == [
        (VOLADD, 15, 1),      # 5
        (SOUNDOFF, 19, 1),    # 3
        (B, 802, 1),          # 8: TV power sits on the B position, function [3, 34]
        (C, 116, 1),          # 14: List sits on the C position
        (HOME, 118, 1),       # 12
        (OK, 11, 1),          # 17
        (A, 39, 4),           # digits present
        (D, 100, 254),        # Power only goes to ON/OFF, nothing else for the D page
        (ON, 105, 1),
        (OFF, 105, 1),
    ]
    main = records(pages[0])
    assert main[0][3] == code(100, 50)
    # Power is written twice, the same code reference, and is not on a sub-page
    assert main[-2][3] == main[-1][3] == code(0, 100)


def test_iptv_soft_keys_carry_their_function_id_in_the_payload():
    main = records(iptv(IPTV_KEYS)[0])
    soft = {pos: payload for pos, fun, kind, payload in main if pos in (A, D)}
    assert soft[A] == fn_payload(39)
    assert soft[D] == fn_payload(100)


def test_iptv_digits_go_to_page_one_numbered_from_zero():
    pages = iptv([(1, 0, 10), (25, 10, 5), (43, 15, 5), (29, 20, 5)])    # Number1, Number0, Number3
    assert page_numbers(pages) == [0, 1]
    assert [(pos, fun, kind) for pos, fun, kind, _ in records(pages[1])] == [(0, 41, 1), (1, 40, 1), (2, 43, 1)]


def test_iptv_missing_tv_power_and_list_leave_hidden_placeholders():
    pages = iptv([(5, 0, 10), (45, 10, 10)])     # Volume add, Back
    assert page_numbers(pages) == [0]
    assert [(pos, fun, kind, payload) for pos, fun, kind, payload in records(pages[0])] == [
        (VOLADD, 15, 1, code(0, 10)),
        (BACK, 12, 1, code(10, 10)),
        (A, 39, 254, fn_payload(39)),
        (D, 100, 254, fn_payload(100)),
        (B, 802, 254, fn_payload(802)),
        (C, 116, 254, fn_payload(116)),
    ]


def test_iptv_power_with_tv_on_puts_only_tv_on_on_the_d_page():
    pages = iptv([(1, 0, 10), (6, 10, 5), (5, 15, 5)])    # Power, TV on, Volume add
    assert page_numbers(pages) == [0, 4]
    main = {pos: (fun, kind) for pos, fun, kind, _ in records(pages[0])}
    assert main[D] == (100, 4)
    assert main[ON] == main[OFF] == (105, 1)
    assert [(pos, fun, kind, payload) for pos, fun, kind, payload in records(pages[1])] == [
        (0, 800, 1, code(10, 5))     # [3, 32]
    ]


def test_iptv_on_off_keys_take_on_off_and_power_goes_to_the_d_page():
    pages = iptv([(1, 0, 10), (2, 10, 5), (4, 15, 5), (10, 20, 5)])    # Power, On, Off, TV off
    assert page_numbers(pages) == [0, 4]
    main = records(pages[0])
    assert (ON, 5, 1, code(10, 5)) in [(p, f, k, pl) for p, f, k, pl in main]
    assert (OFF, 6, 1, code(15, 5)) in [(p, f, k, pl) for p, f, k, pl in main]
    assert [pos for pos, fun, _, _ in main if fun == 105] == []       # no second Power on ON/OFF
    assert sum(1 for pos, _, _, _ in main if pos == ON) == 1
    assert [(pos, fun) for pos, fun, _, _ in records(pages[1])] == [(0, 105), (1, 801)]


def test_iptv_custom_keys_are_referenced_by_name():
    pages = iptv([(1, 0, 10), (5, 10, 5)], custom_keys=frozenset({"1", "5"}))
    main = records(pages[0])
    volume = next(r for r in main if r[1] == 15)
    assert volume[2] == 2 and volume[3] == b"5" + bytes(31)
    power = [r for r in main if r[1] == 105]
    assert [r[0] for r in power] == [ON, OFF]
    assert power[0][2] == power[1][2] == 2 and power[0][3] == b"1" + bytes(31)


def test_iptv_key_only_uploaded_separately_is_still_placed():
    pages = iptv([(5, 0, 10)], custom_keys=frozenset({"8"}))    # TV power only in custom_keys
    main = records(pages[0])
    assert (B, 802, 2, b"8" + bytes(31)) in main
    assert all(kind != 254 or pos != B for pos, _, kind, _ in main)


def test_iptv_unknown_and_unsupported_keys_are_left_out():
    pages = iptv([(5, 0, 10), (9, 10, 5), (11, 15, 5), (999, 20, 5)])
    assert {fun for _, fun, _, _ in records(pages[0])} == {15, 39, 100, 802, 116}


# ---- Set-top box --------------------------------------------------------------------------


def test_tvbox_main_page_uses_firmware_functions_on_fixed_positions():
    pages = tvbox([
        (1, 0, 100),     # Power
        (41, 100, 10),   # Channel add
        (43, 110, 10),   # Channel delete
        (18, 120, 10),   # Fav
        (25, 130, 10),   # Back
        (12, 140, 10),   # Menu
        (14, 150, 10),   # Three-code key: the app writes it nowhere
        (29, 160, 10),   # Left
        (11, 170, 10),   # Number5
    ])
    assert page_numbers(pages) == [0, 1]
    assert [(pos, fun, kind) for pos, fun, kind, _ in records(pages[0])] == [
        (CHUP, 17, 1),
        (CHDOWN, 18, 1),
        (C, 109, 1),         # Fav lives on C
        (BACK, 12, 1),
        (HOME, 118, 1),
        (LEFT, 7, 1),
        (A, 39, 4),
        (D, 100, 254),
        (B, 802, 254),       # no TV power key: hidden placeholder
        (ON, 105, 1),
        (OFF, 105, 1),
    ]
    assert [(pos, fun) for pos, fun, _, _ in records(pages[1])] == [(0, 45)]


def test_tvbox_d_page_holds_list_tv_on_off_and_power_when_it_is_not_alone():
    pages = tvbox([(1, 0, 10), (2, 10, 5), (4, 15, 5), (16, 20, 5), (6, 25, 5), (10, 30, 5)])
    assert page_numbers(pages) == [0, 4]
    main = {pos: (fun, kind) for pos, fun, kind, _ in records(pages[0])}
    assert main[ON] == (5, 1) and main[OFF] == (6, 1)
    assert main[D] == (100, 4)
    assert main[C] == (109, 254)      # Fav absent
    d_page = records(pages[1])
    assert [(pos, fun) for pos, fun, _, _ in d_page] == [(0, 105), (1, 116), (2, 800), (3, 801)]


def test_tvbox_power_alone_keeps_the_d_page_hidden_but_list_shows_it():
    pages = tvbox([(1, 0, 10)])
    assert page_numbers(pages) == [0]
    assert {pos: kind for pos, _, kind, _ in records(pages[0])}[D] == 254
    pages = tvbox([(1, 0, 10), (16, 10, 5)])
    assert page_numbers(pages) == [0, 4]
    assert [(pos, fun) for pos, fun, _, _ in records(pages[1])] == [(0, 116)]
    assert {pos: kind for pos, _, kind, _ in records(pages[0])}[D] == 4


def test_tvbox_digits_page_and_tv_power_on_b():
    pages = tvbox([(8, 0, 10), (23, 10, 5), (3, 15, 5)], device_type=18)    # TV power, Number0, Number1
    assert page_numbers(pages) == [0, 1]
    assert pages[0][HEADER + 1] == 18
    main = records(pages[0])
    assert (B, 802, 1, code(0, 10)) in main
    assert [(pos, fun) for pos, fun, _, _ in records(pages[1])] == [(0, 40), (1, 41)]


def test_tvbox_custom_power_is_referenced_by_name_on_on_and_off():
    pages = tvbox([(1, 0, 10), (37, 10, 5)], custom_keys=frozenset({"1"}))
    power = [r for r in records(pages[0]) if r[1] == 105]
    assert [r[0] for r in power] == [ON, OFF]
    assert power[0][2] == power[1][2] == 2 and power[0][3] == power[1][3] == b"1" + bytes(31)


# ---- DVD ----------------------------------------------------------------------------------


DVD_KEYS = [
    (11, 0, 100),    # Power
    (1, 100, 10),    # Mute
    (2, 110, 10),    # Menu
    (8, 120, 10),    # Volume add
    (6, 130, 10),    # Volume delete
    (22, 140, 10),   # Three-code key: the app writes it nowhere
    (20, 150, 10),   # Back
    (18, 160, 10),   # OK
    (33, 170, 10),   # Take out
    (26, 180, 10),   # Number1
    (17, 190, 10),   # Play
    (29, 200, 10),   # Pause
    (4, 210, 10),    # Stop
    (24, 220, 10),   # List
]


def test_dvd_main_page_has_power_on_on_and_off_and_eject_on_c():
    pages = dvd(DVD_KEYS)
    assert page_numbers(pages) == [0, 1, 2, 4]
    assert [(pos, fun, kind) for pos, fun, kind, _ in records(pages[0])] == [
        (SOUNDOFF, 19, 1),
        (HOME, 118, 1),
        (VOLADD, 15, 1),
        (VOLDEL, 16, 1),
        (BACK, 12, 1),
        (OK, 11, 1),
        (C, 111, 1),          # Take out lives on C
        (A, 39, 4),
        (B, 20, 4),           # transport keys present
        (D, 100, 4),          # List present
        (ON, 105, 1),
        (OFF, 105, 1),
    ]
    main = records(pages[0])
    assert main[-2][3] == main[-1][3] == code(0, 100)
    assert main[0][3] == code(100, 10)


def test_dvd_sub_pages_number_their_keys_from_zero_in_key_map_order():
    pages = dvd(DVD_KEYS)
    assert [(pos, fun) for pos, fun, _, _ in records(pages[1])] == [(0, 41)]
    assert [(pos, fun, kind, payload) for pos, fun, kind, payload in records(pages[2])] == [
        (0, 21, 1, code(190, 10)),     # Play
        (1, 22, 1, code(200, 10)),     # Pause
        (2, 23, 1, code(210, 10)),     # Stop
    ]
    assert [(pos, fun) for pos, fun, _, _ in records(pages[3])] == [(0, 116)]
    # the four transport extras map to their own firmware ids
    pages = dvd([(11, 0, 10), (15, 10, 5), (19, 15, 5), (21, 20, 5), (25, 25, 5)])
    assert [fun for _, fun, _, _ in records(pages[1])] == [25, 26, 27, 28]


def test_dvd_without_optional_keys_hides_a_b_d_and_leaves_c_placeholder():
    pages = dvd([(11, 0, 100), (8, 100, 10)])
    assert page_numbers(pages) == [0]
    assert [(pos, fun, kind, payload) for pos, fun, kind, payload in records(pages[0])] == [
        (VOLADD, 15, 1, code(100, 10)),
        (A, 39, 254, fn_payload(39)),
        (B, 20, 254, fn_payload(20)),
        (D, 100, 254, fn_payload(100)),
        (C, 111, 254, fn_payload(111)),
        (ON, 105, 1, code(0, 100)),
        (OFF, 105, 1, code(0, 100)),
    ]


def test_dvd_without_power_writes_no_on_off():
    pages = dvd([(8, 0, 10)])
    positions = [pos for pos, _, _, _ in records(pages[0])]
    assert ON not in positions and OFF not in positions


def test_dvd_custom_keys_and_custom_power():
    pages = dvd([(11, 0, 10), (8, 10, 5), (17, 15, 5)], device_type=19, custom_keys=frozenset({"11", "17"}))
    main = records(pages[0])
    power = [r for r in main if r[1] == 105]
    assert [r[0] for r in power] == [ON, OFF] and power[0][2] == 2 and power[0][3] == b"11" + bytes(30)
    transport = records(pages[1])
    assert transport[0][:3] == (0, 21, 2) and transport[0][3] == b"17" + bytes(30)


def test_dvd_unknown_keys_are_left_out():
    pages = dvd([(11, 0, 10), (999, 10, 5), (22, 15, 5)])
    assert {fun for _, fun, _, _ in records(pages[0])} == {39, 20, 100, 111, 105}


# ---- Learned / custom keys from the cloud's keyDetail ----------------------------------------


def name_payload(text):
    return text.encode() + bytes(32 - len(text))


def listing(pages, index):
    return [(pos, fun, kind, payload) for pos, fun, kind, payload in records(pages[index])]


def test_empty_key_map_still_gets_soft_keys_and_placeholders():
    pages = iptv([])
    assert page_numbers(pages) == [0]
    assert listing(pages, 0) == [
        (A, 39, 254, fn_payload(39)),
        (D, 100, 254, fn_payload(100)),
        (B, 802, 254, fn_payload(802)),
        (C, 116, 254, fn_payload(116)),
    ]
    assert [(pos, fun, kind) for pos, fun, kind, _ in records(tvbox([])[0])] == [
        (A, 39, 254), (D, 100, 254), (B, 802, 254), (C, 109, 254),
    ]
    assert [(pos, fun, kind) for pos, fun, kind, _ in records(dvd([])[0])] == [
        (A, 39, 254), (B, 20, 254), (D, 100, 254), (C, 111, 254),
    ]


def test_iptv_text_keys_go_to_the_d_page_with_function_115_and_show_d():
    pages = iptv([], learned_keys=(("Netflix", "text"), ("Apps", "text")))
    assert page_numbers(pages) == [0, 4]
    assert listing(pages, 0) == [
        (A, 39, 254, fn_payload(39)),
        (D, 100, 4, fn_payload(100)),       # page 4 has keys
        (B, 802, 254, fn_payload(802)),
        (C, 116, 254, fn_payload(116)),
    ]
    assert listing(pages, 1) == [
        (0, 115, 2, name_payload("Netflix")),
        (1, 115, 2, name_payload("Apps")),
    ]


def test_d_page_takes_at_most_fifteen_records():
    texts = tuple((f"K{i}", "text") for i in range(17))
    pages = iptv([], learned_keys=texts)
    d_page = listing(pages, 1)
    assert len(d_page) == 15
    assert [pos for pos, *_ in d_page] == list(range(15))
    assert d_page[-1][3] == name_payload("K14")
    # the key-map keys of the page count against the cap: TV on is record 0, text keys follow
    pages = iptv([(6, 0, 10)], learned_keys=texts)
    d_page = listing(pages, 1)
    assert len(d_page) == 15
    assert d_page[0] == (0, 800, 1, code(0, 10))
    assert d_page[1][3] == name_payload("K0") and d_page[-1][3] == name_payload("K13")
    # same cap on the other two types
    assert len(listing(tvbox([(16, 0, 10)], learned_keys=texts), 1)) == 15
    assert len(listing(dvd([(24, 0, 10)], learned_keys=texts), 1)) == 15


def test_learned_default_key_only_in_key_detail_goes_to_its_own_page_as_a_name_reference():
    pages = iptv([], learned_keys=(("5", "key"), ("25", "key")))    # Volume add, Number1
    assert page_numbers(pages) == [0, 1]
    assert listing(pages, 0) == [
        (VOLADD, 15, 2, name_payload("5")),
        (A, 39, 4, fn_payload(39)),
        (D, 100, 254, fn_payload(100)),
        (B, 802, 254, fn_payload(802)),
        (C, 116, 254, fn_payload(116)),
    ]
    assert listing(pages, 1) == [(0, 41, 2, name_payload("25"))]


def test_learned_keys_keep_their_order_and_custom_keys_without_order_are_sorted():
    ordered = iptv([], learned_keys=(("43", "key"), ("25", "key")))
    assert [fun for _, fun, _, _ in records(ordered[1])] == [40, 41]
    reverse = iptv([], learned_keys=(("25", "key"), ("43", "key")))
    assert [fun for _, fun, _, _ in records(reverse[1])] == [41, 40]
    legacy = iptv([], custom_keys=frozenset({"43", "25"}))
    assert [fun for _, fun, _, _ in records(legacy[1])] == [41, 40]


def test_learned_key_replaces_a_key_map_key_with_a_name_reference_once():
    pages = iptv([(5, 0, 10)], learned_keys=(("5", "key"),))
    volume = [r for r in records(pages[0]) if r[1] == 15]
    assert volume == [(VOLADD, 15, 2, name_payload("5"))]


def test_tvbox_learned_power_and_text_key():
    pages = tvbox([], learned_keys=(("1", "key"), ("Remote", "text")))
    assert page_numbers(pages) == [0, 4]
    main = listing(pages, 0)
    assert main == [
        (A, 39, 254, fn_payload(39)),
        (D, 100, 4, fn_payload(100)),
        (B, 802, 254, fn_payload(802)),
        (C, 109, 254, fn_payload(109)),
        (ON, 105, 2, name_payload("1")),
        (OFF, 105, 2, name_payload("1")),
    ]
    # Power is not repeated on the D page, only the text key is
    assert listing(pages, 1) == [(0, 115, 2, name_payload("Remote"))]


def test_tvbox_power_alone_in_key_detail_keeps_d_hidden():
    pages = tvbox([], learned_keys=(("1", "key"),))
    assert page_numbers(pages) == [0]
    assert {pos: kind for pos, _, kind, _ in records(pages[0])}[D] == 254


def test_a_text_key_named_like_a_function_uses_that_function_id():
    # Number("16") is the set-top box List key, so the D-page text key gets [0, 116]
    pages = tvbox([], learned_keys=(("16", "text"),))
    assert listing(pages, 1) == [(0, 116, 2, name_payload("16"))]


def test_dvd_learned_keys_follow_the_dvd_rules():
    pages = dvd([], learned_keys=(("11", "key"), ("Subtitle", "text"), ("24", "key")))
    assert page_numbers(pages) == [0, 4]
    assert listing(pages, 0) == [
        (A, 39, 254, fn_payload(39)),
        (B, 20, 254, fn_payload(20)),
        (D, 100, 4, fn_payload(100)),
        (C, 111, 254, fn_payload(111)),
        (ON, 105, 2, name_payload("11")),
        (OFF, 105, 2, name_payload("11")),
    ]
    # Power (a default DVD key) stays off the D page; the text key and the learned List go there
    assert listing(pages, 1) == [
        (0, 115, 2, name_payload("Subtitle")),
        (1, 116, 2, name_payload("24")),
    ]


def test_dvd_learned_transport_key_opens_the_b_page():
    pages = dvd([(11, 0, 10)], learned_keys=(("17", "key"), ("4", "key")))    # Play, Stop
    assert page_numbers(pages) == [0, 2]
    assert {pos: kind for pos, _, kind, _ in records(pages[0])}[B] == 4
    assert listing(pages, 1) == [
        (0, 21, 2, name_payload("17")),
        (1, 23, 2, name_payload("4")),
    ]


def test_key_names_lose_slashes_and_are_cut_to_31_bytes():
    pages = iptv([], learned_keys=(("A/B" + "x" * 40, "text"),))
    assert listing(pages, 1)[0][3] == b"AB" + b"x" * 29 + b"\0"
