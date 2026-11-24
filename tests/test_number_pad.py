"""The "123" key opens the remote's number pad (window 6), not a list.

WoRWS V48, decoded (evidence/mixed-v48/number-pad-window.md), not run: the pad draws 1–9 and 0 in a
phone grid with four keys under it, and each key sends the first IR command whose function is its own
id (40–49 for the digits, 203/200/201/202 under them). The TV and audio windows open it from A, the
other IR windows from a key whose function is 39; any other menu function opens a list.
"""
import base64

import pytest

from conftest import INTEGRATION, load

c = load(INTEGRATION / "commands.py")
cloud_ir = load(INTEGRATION / "cloud_ir.py")
glyphs = load(INTEGRATION / "ir_glyphs.py")
physical = load(INTEGRATION / "physical_layout.py")

PAD = glyphs.NUMBER_PAD_FUNCTIONS


def _stock_remote(device_type):
    tags = glyphs._IR_TAG_FUNCTIONS[glyphs._profile(f"IR_{device_type}")]
    key_map = ";".join(f"{tag}:{index * 4}:4" for index, tag in enumerate(tags))
    item = {"code": base64.b64encode(bytes(400)).decode(), "keyMap": key_map}
    profile = cloud_ir.profile_from_cloud(item, remote_id="01-202611190101-12345678", name="R",
                                          remote_type=device_type)
    packets = profile.build_pages(remote_index=0, name="R")
    return {"device_type": f"IR_{device_type}", "device_id": "001122334455", "name": "R",
            "physical_packets": [bytes(packet).hex() for packet in packets]}


def _blank_remote(device_type):
    packets = cloud_ir.blank_profile(device_type, "Empty").build_pages(remote_index=5, name="Empty")
    return {"device_type": f"IR_{device_type}", "device_id": "001122334455", "name": "Empty",
            "physical_packets": [bytes(packet).hex() for packet in packets]}


def _records(packet):
    body = packet[7:]
    return [body[83 + 36 * i:83 + 36 * (i + 1)] for i in range(body[82])]


def _function(record):
    return int.from_bytes(record[1:3], "big")


def _pad_key(function, code="aa"):
    return {"index": 0, "transport": "ir", "code_hex": code, "glyph": function}


@pytest.mark.parametrize("device_type", [2, 3, 4, 5, 11])
def test_stock_digit_pages_are_read_as_the_number_pad(device_type):
    draft = physical.draft_for(_stock_remote(device_type))
    pad = next(page for page in draft["pages"] if page["index"] == 1)
    assert pad["number_pad"] is True
    for key in pad["buttons"]:
        assert key["index"] == PAD.index(physical._key_function(key))
    # it is saved back unchanged
    physical.validate(_stock_remote(device_type), draft)


def test_a_list_behind_a_menu_function_other_than_39_stays_a_list():
    draft = physical.draft_for(_stock_remote(10))           # air purifier: A opens a list (70)
    assert "number_pad" not in next(page for page in draft["pages"] if page["index"] == 1)


def test_a_number_pad_page_is_written_with_the_39_link_and_the_pad_ids():
    remote = _blank_remote(2)
    draft = {"kind": "ir", "pages": [{"index": 0, "buttons": []}, {"index": 1, "number_pad": True,
             "buttons": [_pad_key(40, "0a"), _pad_key(41, "1a"), _pad_key(203, "3d")]}]}
    uploads, pages = physical.compile_pages(remote, draft, slot=3)
    link = next(record for record in _records(pages[0]) if record[0] == 0)
    assert _function(link) == 39 and link[3] == 4
    pad = {_function(record): record for record in _records(pages[1])}
    assert set(pad) == {40, 41, 203}
    assert all(record[3] == 2 for record in pad.values())          # named IR commands
    assert pad[41][0] == 0 and pad[40][0] == 9 and pad[203][0] == 10
    assert any(stage.startswith("ir_transfer") for stage, _packet, _accepted in uploads)


def test_list_links_never_use_39_and_a_pad_on_another_key_does():
    remote = _blank_remote(5)                                  # DVD: generic IR window
    draft = {"kind": "ir", "pages": [
        {"index": 0, "buttons": []},
        {"index": 1, "buttons": [{"index": 0, "transport": "ir", "code_hex": "aa"}]},
        {"index": 3, "number_pad": True, "buttons": [_pad_key(45)]}]}
    _, pages = physical.compile_pages(remote, draft, slot=1)
    links = {record[0]: _function(record) for record in _records(pages[0]) if record[0] < 4}
    assert links[0] == 100 and links[2] == 39


def test_a_cached_link_is_kept_only_while_it_opens_what_the_page_is():
    remote = _stock_remote(5)
    draft = physical.draft_for(remote)
    pad = next(page for page in draft["pages"] if page["index"] == 1)
    assert physical._link_function(pad) == 39
    _, pages = physical.compile_pages(remote, draft, slot=0)
    assert _function(next(r for r in _records(pages[0]) if r[0] == 0)) == 39
    # the same page as a list must not keep the 39 link, which would open the pad
    pad.pop("number_pad")
    pad["buttons"] = [{"index": 0, "transport": "ir", "code_hex": "aa"}]
    _, pages = physical.compile_pages(remote, draft, slot=0)
    assert _function(next(r for r in _records(pages[0]) if r[0] == 0)) == 100


def test_pages_the_remote_would_not_open_are_refused():
    tv, light, purifier = _blank_remote(2), _blank_remote(14), _blank_remote(10)
    row = {"index": 0, "transport": "ir", "code_hex": "aa"}
    cases = [
        (tv, {"index": 1, "buttons": [row]}, "opens the number pad"),
        (tv, {"index": 2, "number_pad": True, "buttons": [_pad_key(41)]}, "cannot open a number pad"),
        (light, {"index": 1, "buttons": [row]}, "cannot open a page"),
        (light, {"index": 1, "number_pad": True, "buttons": [_pad_key(41)]}, "cannot open a number pad"),
        (tv, {"index": 1, "number_pad": True, "buttons": [row]}, "only the digits"),
        (tv, {"index": 1, "number_pad": True, "buttons": [_pad_key(41), _pad_key(41, "bb")]}, "twice"),
    ]
    for remote, page, message in cases:
        with pytest.raises(ValueError, match=message):
            physical.validate(remote, {"kind": "ir", "pages": [{"index": 0, "buttons": []}, page]})
    # a pad id elsewhere on the remote would be what the pad sends
    with pytest.raises(ValueError, match="number pad icon"):
        physical.validate(purifier, {"kind": "ir", "pages": [
            {"index": 0, "buttons": []},
            {"index": 1, "number_pad": True, "buttons": [_pad_key(42)]},
            {"index": 4, "buttons": [{"index": 0, "transport": "ir", "code_hex": "aa", "glyph": 41}]}]})
    hid = {"device_type": "UNIVERSAL_BLE", "device_id": "001122334455", "buttons": ["ON"]}
    with pytest.raises(ValueError, match="IR remote"):
        physical.validate(hid, {"kind": "hid", "pages": [{"index": 0, "buttons": []}, {
            "index": 1, "number_pad": True, "buttons": [{"index": 0, "transport": "hid", "function": 1}]}]})


def test_an_older_list_under_a_tv_a_key_opens_as_the_pad_with_its_rows_set_aside():
    remote = _blank_remote(2)
    remote["physical_layout"] = {"kind": "ir", "pages": [{"index": 0, "buttons": []}, {"index": 1, "buttons": [
        {"index": 0, "transport": "ir", "code_hex": "aa", "glyph": 105},
        {"index": 1, "transport": "ir", "code_hex": "bb", "glyph": 42}]}]}
    pad = physical.draft_for(remote)["pages"][1]
    assert pad["number_pad"] is True
    assert {key["index"]: key["glyph"] for key in pad["buttons"]} == {1: 42, 14: 105}


def test_window_tables():
    assert glyphs.number_pad_positions("IR_2") == {0} and glyphs.number_pad_always("IR_TV")
    assert glyphs.number_pad_positions("IR_24") == {0}            # custom audio
    assert glyphs.number_pad_positions("IR_5") == {0, 1, 2, 3}
    assert glyphs.number_pad_positions("IR_14") == frozenset()    # light
    assert glyphs.list_page_positions("IR_6") == {2, 3}
    assert glyphs.list_link_functions("IR_5") == (100, 20, 210, 100)
    assert glyphs.list_link_functions("IR_11") == (39, 27, 28, 100)


def test_the_panel_and_the_integration_agree_on_the_number_pad_and_windows():
    import re
    source = (INTEGRATION / "frontend" / "switchbot-urc-panel.js").read_text()

    def numbers(pattern):
        return [int(value) for value in re.findall(r"\d+", re.search(pattern, source, re.S).group(1))]

    assert numbers(r"const NUMBER_PAD_FUNCTIONS = \[(.*?)\]") == list(PAD)
    assert set(numbers(r"const IR_TV_WINDOW = new Set\(\[(.*?)\]\)")) == glyphs._TV_WINDOW
    assert set(numbers(r"const IR_AUDIO_WINDOW = new Set\(\[(.*?)\]\)")) == glyphs._AUDIO_WINDOW
    assert set(numbers(r"const IR_INFRARED_WINDOW = new Set\(\[(.*?)\]\)")) == glyphs._INFRARED_WINDOW
    fixed = re.search(r"const IR_FIXED_LIST_POSITIONS = \{(.*?)\};", source, re.S).group(1)
    for type_, positions in re.findall(r"(\d+): \[([\d, ]+)\]", fixed):
        assert glyphs.list_page_positions(f"IR_{type_}") == {int(v) for v in positions.split(",")}
