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
