"""Recreating an edited IR/HID tile must preserve its physical buttons and type."""

import pytest

from conftest import INTEGRATION, load


c = load(INTEGRATION / "commands.py")
physical = load(INTEGRATION / "physical_layout.py")


def test_hid_pairing_uses_the_generated_profile_identifier_in_both_commands():
    timestamp = 1791812216
    first = c.new_hid_device_id("UNIVERSAL_BLE", timestamp, set())
    assert first == "021791812216"
    raw_id = bytes.fromhex("1622819117020000000000")
    assert c.build_hid_pair(first) == bytes.fromhex("0f620e01") + raw_id
    assert c.build_hid_pair_status(first) == bytes.fromhex("0f630e") + raw_id
    assert c.new_hid_device_id("UNIVERSAL_BLE", timestamp, {raw_id}) == "121791812216"


def test_default_hid_button_layout_writes_the_profile_commands():
    for device_type in c.DEVTYPE:
        remote = {
            "device_type": device_type, "device_id": "001122334455",
            "name": "TV", "icon": "tv", "buttons": physical.default_hid_buttons(device_type),
        }
        draft = physical.draft_for(remote)
        uploads, (packet,) = physical.compile_pages(remote, draft, 1)
        records = {packet[offset]: packet[offset + 1:offset + 4]
                   for offset in range(90, len(packet), 36)}
        assert not uploads
        assert packet[8:10] == bytes((c.DEVTYPE[device_type], c.CTRL_HID))
        assert packet[89] == len(records) == len(remote["buttons"])
        assert records[c.TAG["ON"]] == bytes.fromhex("006906")
        assert records[c.TAG["UP"]] == bytes.fromhex("000906")
        assert records[c.TAG["VOLADD"]] == bytes.fromhex("000f06")
        assert c.TAG["KATA"] not in records
        if device_type == "UNIVERSAL_BLE":
            assert records[c.TAG["A"]] == bytes.fromhex("083706")
        if device_type == "GOOGLE_TV":
            assert all(c.TAG[key] not in records for key in "ABCD")


def test_generic_ir_keeps_every_command_and_reserves_kata_only_on_main():
    keys = [(index + 1, index, 1) for index in range(90)]
    pages = c.build_ir_pages(
        remote_index=0, device_type=2, remote_id=bytes(11), name="TV", key_map=keys,
    )
    assert len(pages) == 5
    assert sum(packet[89] for packet in pages) == len(keys)
    assert c.KATA_POSITION not in pages[0][90::36]
    assert c.KATA_POSITION in pages[1][90::36]
    assert [int.from_bytes(packet[pos + 4:pos + 8], "big")
            for packet in pages for pos in range(90, len(packet), 36)] == list(range(90))


@pytest.mark.parametrize("kind,device_type", [("hid", "UNIVERSAL_BLE"), ("ir", "IR_2")])
def test_kata_is_hidden_from_saved_layouts_and_rejected_on_new_writes(kind, device_type):
    regular_key = {"index": 4, "transport": "ir", "code_hex": "01"}
    reserved_key = {**regular_key, "index": c.KATA_POSITION}
    layout = {"kind": kind, "pages": [{"index": 0, "buttons": [regular_key, reserved_key]}]}
    remote = {"device_type": device_type, "device_id": "001122334455", "physical_layout": layout}
    if kind == "ir":
        packets = c.build_ir_pages(
            remote_index=0, device_type=2, remote_id=c.id_to_bytes(remote["device_id"]),
            name="TV", key_map=[(5, 0, 1)],
        )
        remote["physical_packets"] = [packet.hex() for packet in packets]
    assert physical.draft_for(remote)["pages"][0]["buttons"] == [regular_key]
    with pytest.raises(ValueError, match="KATA is reserved"):
        physical.validate(remote, layout)


def test_ir_recreate_rewrites_saved_pages_and_uploads_custom_ir_code():
    device_id = "00112233445566778899aa"
    source = c.build_ir_pages(
        remote_index=2, device_type=2, remote_id=bytes.fromhex(device_id),
        name="TV", key_map=[(5, 0, 3)], icon=0,
    )
    remote = {
        "device_type": "IR_2", "device_id": device_id, "name": "TV",
        "physical_packets": [packet.hex() for packet in source],
    }
    remote["physical_layout"] = physical.draft_for(remote)
    remote["physical_layout"]["pages"][0]["buttons"].append({
        "index": 6, "transport": "ir", "code_hex": "01020304",
    })

    stages, pages, draft = physical.compile_recreate(
        remote, slot=2, device_type=2, control_type=c.CTRL_IR,
        name="Edited TV", icon_name="strip",
    )
    names = [stage for stage, _, _ in stages]
    assert names.index("ir_transfer_init") < names.index("delete old key pages")
    assert names.index("delete old key pages") < next(
        index for index, stage in enumerate(names) if stage.startswith("write page")
    )
    assert draft["kind"] == "ir"
    for packet in pages:
        assert packet[8] == 2  # IR device type is unchanged
        assert packet[11] == c.ICON["strip"]
        assert packet[23:32] == b"Edited TV"  # stored display name
        c.rewrite_ir_page(packet, remote_index=2, name="Edited TV")
    assert any(packet[:4] == bytes.fromhex("0f620401") for _, packet, _ in stages)


def test_ir_menu_uses_its_cached_link_record_when_the_page_moves():
    device_id = "00112233445566778899aa"
    fn = 210
    link = {"keyIndex": 0, "keyFun": fn, "key_type": 4}
    main = c.build_create(1, 2, c.CTRL_IR, 0, 0, device_id, "TV", 1, [link])
    submenu = c.build_create(1, 2, c.CTRL_IR, 0, 0, device_id, "TV", 1,
                             [{"keyIndex": 0, "keyFun": 25}], page_index=1)
    remote = {"device_type": "IR_2", "device_id": device_id,
              "physical_packets": [main.hex(), submenu.hex()]}
    draft = physical.draft_for(remote)
    assert draft["pages"][0]["buttons"] == []
    assert draft["pages"][1]["link_record"] == main[90:].hex()

    # Older saved drafts lacked link metadata. Restore it from the installed record.
    del draft["pages"][1]["link_record"]
    remote["physical_layout"] = draft
    draft = physical.draft_for(remote)
    assert draft["pages"][1]["link_record"] == main[90:].hex()
    draft["pages"][1]["index"] = 2
    uploads, packets = physical.compile_pages(remote, draft, 1)
    assert not uploads
    assert packets[0][90:] == b"\x01" + main[91:]


def test_hid_recreate_preserves_custom_ir_key_and_device_type():
    device_id = "001122334455"
    original = c.build_hid_edit_page(
        remote_index=1, device_type_name="GOOGLE_TV", device_id=device_id,
        name="TV", keys=[{"index": 4, "hid_usage": bytes.fromhex("0069")}],
    )
    remote = {
        "device_type": "GOOGLE_TV", "device_id": device_id, "name": "TV",
        "physical_packets": [original.hex()],
    }
    remote["physical_layout"] = {
        "kind": "hid", "pages": [{"index": 0, "buttons": [
            {"index": 4, "transport": "hid", "function": 105},
        ]}],
    }
    remote["physical_layout"]["pages"][0]["buttons"].append({
        "index": 5, "transport": "ir", "code_hex": "aabbccdd",
    })

    stages, pages, draft = physical.compile_recreate(
        remote, slot=1, device_type=0xF3, control_type=c.CTRL_HID,
        name="Edited TV", icon_name="floorlamp",
    )
    names = [stage for stage, _, _ in stages]
    assert names.index("ir_transfer_init") < names.index("delete old key pages")
    assert names[-1] == "write page 0"
    assert draft["kind"] == "hid"
    [page] = pages
    assert page[8] == 0xF3  # GOOGLE_TV remains GOOGLE_TV
    assert page[9] == c.CTRL_HID
    assert page[11] == c.ICON["floorlamp"]
    assert page[23:32] == b"Edited TV"
    assert page[91:94] == original[91:94]  # key index, function and HID record type
    assert page[90 + 36 + 3] == 2  # second key remains a named custom IR key


@pytest.mark.parametrize("glyph,expected_function", [(None, 0x07D3), (105, 105)])
def test_hid_ir_replaces_an_inherited_zero_function(glyph, expected_function):
    remote = {"device_type": "GOOGLE_TV", "device_id": "001122334455", "name": "TV"}
    key = {"index": 0, "transport": "ir", "function": 0, "code_hex": "aabbccdd"}
    if glyph is not None:
        key["glyph"] = glyph
    draft = {"kind": "hid", "pages": [{"index": 0, "buttons": [key]}]}
    uploads, pages = physical.compile_pages(remote, draft, slot=1)
    assert uploads
    record = pages[0][90:126]
    assert record[:4] == b"\x00" + expected_function.to_bytes(2, "big") + b"\x02"
    assert record[4:].rstrip(b"\0") == b"0"


def test_hid_ir_glyph_changes_only_the_visible_function():
    remote = {"device_type": "GOOGLE_TV", "device_id": "001122334455", "name": "TV"}
    draft = {"kind": "hid", "pages": [{"index": 0, "buttons": [
        {"index": 0, "transport": "ir", "code_hex": "aabbccdd", "glyph": 105},
        {"index": 4, "transport": "hid", "function": 25},
    ]}]}
    uploads, pages = physical.compile_pages(remote, draft, slot=1)
    assert uploads
    first = pages[0][90:126]
    assert first[:4] == bytes([0, 0, 105, 2])
    assert first[4:].rstrip(b"\0") == b"0"
    assert pages[0][126:130] == bytes([4, 0, 25, 6])
    key = draft["pages"][0]["buttons"][0]
    key["glyph"] = 0
    with pytest.raises(ValueError, match="nonzero"):
        physical.validate(remote, draft)
    key["glyph"] = 105
    key["transport"] = "hid"
    key["function"] = 25
    with pytest.raises(ValueError, match="screen icon"):
        physical.validate(remote, draft)


def test_ir_remote_keys_take_a_screen_icon_as_their_function():
    cloud_ir = load(INTEGRATION / "cloud_ir.py")
    blank = cloud_ir.blank_profile(2, "Empty")
    packets = blank.build_pages(remote_index=5, name="Empty")
    remote = {"device_type": "IR_2", "device_id": "001122334455", "name": "Empty",
              "physical_packets": [bytes(packet).hex() for packet in packets]}
    key = {"index": 4, "transport": "ir", "code_hex": "aabbccdd"}
    draft = {"kind": "ir", "pages": [{"index": 0, "buttons": []},
                                     {"index": 1, "buttons": [key]}]}
    # no icon chosen: the generic function, so the key shows its own name
    _, pages = physical.compile_pages(remote, draft, slot=1)
    assert pages[1][90:93] == bytes([4, 0, 115])
    # a chosen icon becomes the function id the remote draws the picture from
    key["glyph"] = 105
    _, pages = physical.compile_pages(remote, draft, slot=1)
    assert pages[1][90:93] == bytes([4, 0, 105])
    key["glyph"] = 0
    with pytest.raises(ValueError, match="nonzero"):
        physical.validate(remote, draft)
    # a stored command keeps the record it came with and takes no icon
    key.update(glyph=105, transport="stored", record="00" * 36)
    with pytest.raises(ValueError, match="screen icon"):
        physical.validate(remote, draft)


def test_an_a_to_d_key_can_show_an_icon_with_no_command():
    cloud_ir = load(INTEGRATION / "cloud_ir.py")
    packets = cloud_ir.blank_profile(2, "Empty").build_pages(remote_index=5, name="Empty")
    remote = {"device_type": "IR_2", "device_id": "001122334455", "name": "Empty",
              "physical_packets": [bytes(packet).hex() for packet in packets]}
    icon = {"index": 2, "transport": "icon", "glyph": 115}
    draft = {"kind": "ir", "pages": [{"index": 0, "buttons": [icon]}]}
    uploads, pages = physical.compile_pages(remote, draft, slot=1)
    assert not uploads                                   # no command, so no IR code is sent
    # a shown softkey (type 4) carrying only the picture, like the keys that open a page
    assert pages[0][90:126] == (bytes([2, 0, 115, 4]) + (115).to_bytes(2, "big")).ljust(36, b"\0")
    for bad in ({"index": 5}, {"glyph": None}, {"glyph": 0}):
        broken = {"index": 2, "transport": "icon", "glyph": 115, **bad}
        with pytest.raises(ValueError):
            physical.validate(remote, {"kind": "ir", "pages": [{"index": 0, "buttons": [broken]}]})
    # it is reserved like any other Main command once that position opens a page
    with pytest.raises(ValueError, match="reserved"):
        physical.validate(remote, {"kind": "ir", "pages": [
            {"index": 0, "buttons": [icon]}, {"index": 3, "buttons": [
                {"index": 0, "transport": "ir", "code_hex": "aa"}]}]})


def test_a_native_a_to_d_key_can_show_an_icon_with_no_action():
    layout = c.custom_native_layout({"ON": "ON"}, {}, template="FAN", icon_only={"B": 70})
    main = {item["keyIndex"]: item for item in layout[0]}
    assert main[c.TAG["B"]]["keyFun"] == 70 and not main[c.TAG["B"]]["cmd"]
    pages = c.build_custom_native_pages(
        remote_index=3, name="Fan", device_id="AA:BB:CC:DD:EE:FF", icon_name="light",
        event_remote_id="12345678", main_buttons={"ON": "ON"}, page_buttons={},
        template="FAN", icon_only={"B": 70},
    )
    body = pages[0][1][7:]
    count = body[82]
    records = {body[83 + 36 * i]: body[83 + 36 * i:83 + 36 * (i + 1)] for i in range(count)}
    record = records[c.TAG["B"]]
    assert record[1:3] == (70).to_bytes(2, "big") and record[4:6] == (70).to_bytes(2, "big")
    # a position that already has an action or opens a page cannot also be icon-only
    for bad in ({"ON": "ON", "B": "ON"}, ):
        with pytest.raises(ValueError, match="already"):
            c.custom_native_layout(bad, {}, template="FAN", icon_only={"B": 70})
    with pytest.raises(ValueError, match="already"):
        c.custom_native_layout({"ON": "ON"}, {2: ["ON"]}, template="FAN", icon_only={"B": 70})
    with pytest.raises(ValueError, match="A-D"):
        c.custom_native_layout({"ON": "ON"}, {}, template="FAN", icon_only={"ON": 70})


def test_a_native_icon_only_key_survives_draft_validation_and_layout():
    remote = {"device_type": "LOCK", "device_id": "001122334455", "name": "Lock", "icon": "lock"}
    draft = physical.draft_for(remote)
    main = next(page for page in draft["pages"] if page["index"] == 0)
    free = 0                                             # a LOCK has no key or page on A–D
    main["buttons"].append({"index": free, "transport": "icon", "glyph": 70})
    valid = physical.validate(remote, draft)
    layout = physical.native_layout(valid)
    assert layout["icon_only"] == {"ABCD"[free]: 70}
    assert "ABCD"[free] not in layout["main_buttons"]
    # saved and read back, the key is still an icon-only key
    again = physical.draft_for({**remote, "custom_layout": layout})
    keys = next(page for page in again["pages"] if page["index"] == 0)["buttons"]
    assert {"index": free, "transport": "icon", "glyph": 70} in keys
    for bad in (0, None):
        main["buttons"][-1]["glyph"] = bad
        with pytest.raises(ValueError):
            physical.validate(remote, draft)


def _blank_ir_remote(device_type):
    cloud_ir = load(INTEGRATION / "cloud_ir.py")
    packets = cloud_ir.blank_profile(device_type, "Empty").build_pages(remote_index=5, name="Empty")
    return {"device_type": f"IR_{device_type}", "device_id": "001122334455", "name": "Empty",
            "physical_packets": [bytes(packet).hex() for packet in packets]}


def _main_records(pages):
    body = pages[0][7:]
    return {body[83 + 36 * i]: body[83 + 36 * i:83 + 36 * (i + 1)] for i in range(body[82])}


def test_a_fixed_picture_window_gets_its_own_a_to_d_ids_and_ignores_icons():
    ids = {14: (91, 311, 312, 100), 6: (90, 89, 70, 100), 11: (39, 27, 28, 100), 1: (59, 70, 80, 100)}
    for device_type, stock in ids.items():
        remote = _blank_ir_remote(device_type)
        # a command on a position that can hold one gets the position's own id, whatever the icon
        free = 0
        draft = {"kind": "ir", "pages": [{"index": 0, "buttons": [
            {"index": free, "transport": "ir", "code_hex": "aabb", "glyph": 105}]}]}
        if device_type == 1:                              # an air conditioner has no command keys
            draft["pages"][0]["buttons"] = []
            draft["pages"].append({"index": 2, "buttons": [{"index": 0, "transport": "ir", "code_hex": "aa"}]})
            _, pages = physical.compile_pages(remote, draft, slot=1)
            assert _main_records(pages)[1][1:3] == stock[1].to_bytes(2, "big")   # the link to page B
            with pytest.raises(ValueError, match="only opens a page"):
                physical.validate(remote, {"kind": "ir", "pages": [{"index": 0, "buttons": [
                    {"index": 0, "transport": "ir", "code_hex": "aa"}]}]})
            continue
        _, pages = physical.compile_pages(remote, draft, slot=1)
        assert _main_records(pages)[free][1:3] == stock[free].to_bytes(2, "big")
        # a page behind D is linked with D's own id, so the key stays visible
        draft["pages"].append({"index": 4, "buttons": [{"index": 0, "transport": "ir", "code_hex": "aa"}]})
        _, pages = physical.compile_pages(remote, draft, slot=1)
        assert _main_records(pages)[3][1:3] == stock[3].to_bytes(2, "big")
    # an icon-only key and a chosen icon on A–D are dropped, not written
    remote = _blank_ir_remote(14)
    checked = physical.validate(remote, {"kind": "ir", "pages": [{"index": 0, "buttons": [
        {"index": 1, "transport": "icon", "glyph": 105},
        {"index": 2, "transport": "ir", "code_hex": "aa", "glyph": 105}]}]})
    assert checked["pages"][0]["buttons"] == [{"index": 2, "transport": "ir", "code_hex": "aa"}]
    # D only opens a page on a light remote, so it cannot hold a command
    with pytest.raises(ValueError, match="only opens a page"):
        physical.validate(remote, {"kind": "ir", "pages": [{"index": 0, "buttons": [
            {"index": 3, "transport": "ir", "code_hex": "aa"}]}]})


def test_a_command_key_on_a_tv_window_refuses_menu_shortcut_icons():
    remote = _blank_ir_remote(2)
    for glyph in (39, 100, 210):
        with pytest.raises(ValueError, match="menu shortcut"):
            physical.validate(remote, {"kind": "ir", "pages": [{"index": 0, "buttons": [
                {"index": 0, "transport": "ir", "code_hex": "aa", "glyph": glyph}]}]})
    ok = physical.validate(remote, {"kind": "ir", "pages": [{"index": 0, "buttons": [
        {"index": 0, "transport": "ir", "code_hex": "aa", "glyph": 105}]}]})
    assert ok["pages"][0]["buttons"][0]["glyph"] == 105
    # rows of a menu may use any icon
    physical.validate(remote, {"kind": "ir", "pages": [
        {"index": 0, "buttons": []},
        {"index": 1, "buttons": [{"index": 0, "transport": "ir", "code_hex": "aa", "glyph": 39}]}]})


def test_the_panel_and_the_integration_agree_on_the_fixed_types_and_shortcut_icons():
    import re
    glyphs = load(INTEGRATION / "ir_glyphs.py")
    source = (INTEGRATION / "frontend" / "switchbot-urc-panel.js").read_text()
    def literal(name):
        text = re.search(rf"const {name} = new Set\(\[(.*?)\]\)", source, re.S).group(1)
        return {int(value) for value in re.findall(r"\d+", text)}
    assert literal("IR_FIXED_SOFTKEY_TYPES") == set(glyphs.FIXED_SOFTKEY_TYPES)
    assert literal("MENU_SHORTCUT_ICONS") == set(glyphs.MENU_SHORTCUT_FUNCTIONS)


def test_every_native_page_builder_call_passes_the_icon_only_keys():
    for name, expected in (("studio_manage.py", 2), ("studio_physical.py", 1)):
        assert (INTEGRATION / name).read_text().count("icon_only=") == expected, name


def test_an_ir_remote_is_not_saved_with_an_empty_main_page():
    # A page with no records is not kept by the remote, which then opens the screen it showed
    # before; so the layout is refused instead of written.
    remote = _blank_ir_remote(2)
    with pytest.raises(ValueError, match="1–18 buttons"):
        physical.validate(remote, {"kind": "ir", "pages": [{"index": 0, "buttons": []}]})
    # a Main with no keys is fine when menus hold the rows
    physical.validate(remote, {"kind": "ir", "pages": [
        {"index": 0, "buttons": []},
        {"index": 1, "buttons": [{"index": 0, "transport": "ir", "code_hex": "aa"}]}]})