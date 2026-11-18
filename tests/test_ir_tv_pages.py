"""IR TV pages follow the official app's layout: firmware function ids, fixed main positions."""
from conftest import INTEGRATION, load

commands = load(INTEGRATION / "commands.py")

REMOTE_ID = bytes.fromhex("0300000e0e0e0e0e0e0e0e")
HEADER = 3 + 2 + 2          # 0F 62 06, length, crc
PAGE_BODY = 5 + 11 + 64     # index/type/ctrl/mode/icon, id, name
RECORD = 36


def records(packet):
    body = packet[HEADER:]
    count = body[PAGE_BODY + 2]
    start = PAGE_BODY + 3
    assert len(body) == start + count * RECORD
    return [(body[start + i * RECORD], int.from_bytes(body[start + i * RECORD + 1:start + i * RECORD + 3], "big"),
             body[start + i * RECORD + 3], body[start + i * RECORD + 4:start + (i + 1) * RECORD])
            for i in range(count)]


def build(key_map, **extra):
    return commands.build_tv_pages(remote_index=5, device_type=2, remote_id=REMOTE_ID, name="TV",
                                   key_map=key_map, **extra)


def test_main_page_uses_firmware_functions_on_fixed_positions():
    # Power 11, Volume up 9, Volume down 1, OK 41, Number1 15, Play 34
    pages = build([(11, 0, 100), (9, 100, 50), (1, 150, 50), (41, 200, 10), (15, 210, 20), (34, 230, 20)])
    assert [packet[HEADER + PAGE_BODY + 1] for packet in pages] == [0, 1, 2]
    main = {(pos, fun, kind) for pos, fun, kind, _ in records(pages[0])}
    assert (commands.TAG["VOLADD"], 15, 1) in main
    assert (commands.TAG["VOLDEL"], 16, 1) in main
    assert (commands.TAG["OK"], 11, 1) in main
    # power is on ON and OFF with the same code reference
    power = [r for r in records(pages[0]) if r[1] == 105]
    assert [r[0] for r in power] == [commands.TAG["ON"], commands.TAG["OFF"]]
    assert power[0][3] == power[1][3] == (0).to_bytes(4, "big") + (100).to_bytes(2, "big") + bytes(26)
    # soft keys: A (digits) and B (playback) open sub-pages, C and D have nothing
    soft = {pos: kind for pos, fun, kind, _ in records(pages[0]) if fun in (39, 20, 210, 100)}
    assert soft == {0: 4, 1: 4, 2: 254, 3: 254}
    assert len(records(pages[0])) == 3 + 4 + 2


def test_sub_pages_number_their_keys_from_zero():
    pages = build([(11, 0, 10), (15, 10, 5), (17, 15, 5), (34, 20, 5)])
    digits = records(pages[1])
    assert [(pos, fun) for pos, fun, _, _ in digits] == [(0, 41), (1, 42)]
    assert [(pos, fun) for pos, fun, _, _ in records(pages[2])] == [(0, 21)]


def test_a_custom_key_is_referenced_by_name_and_packets_are_well_formed():
    pages = build([(11, 0, 10), (9, 10, 5)], custom_keys=frozenset({"9"}))
    volume = next(r for r in records(pages[0]) if r[1] == 15)
    assert volume[2] == 2 and volume[3].rstrip(b"\0") == b"9"
    for packet in pages:
        length = int.from_bytes(packet[3:5], "big")
        assert len(packet) == HEADER + length
        assert int.from_bytes(packet[5:7], "big") == commands.crc16_modbus(packet[HEADER:])


def test_unknown_keys_are_left_out():
    pages = build([(11, 0, 10), (999, 10, 5)])
    assert all(fun != 999 for _, fun, _, _ in records(pages[0]))
