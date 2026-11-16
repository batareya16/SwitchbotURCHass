"""Recreating an edited IR/HID tile must preserve its physical buttons and type."""

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
