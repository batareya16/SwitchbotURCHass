"""Native Remote Studio profile changes must preserve layouts and fail before writing."""

import csv

import pytest
from conftest import INTEGRATION, load


c = load(INTEGRATION / "commands.py")
physical = load(INTEGRATION / "physical_layout.py")
bindings = load(INTEGRATION / "bindings.py")


def test_native_builder_keeps_selected_profile_and_uses_its_page_link():
    pages = c.build_custom_native_pages(
        remote_index=2, name="Light", device_id="AA:BB:CC:DD:EE:FF",
        icon_name="light", event_remote_id="12345678",
        main_buttons={"ON": "ON", "OFF": "OFF", "C": "COLOR_1"},
        page_buttons={3: ["COLOR_1", "COLOR_2"]}, template="BULB",
    )

    assert [page for page, _ in pages] == [0, 3]
    assert pages[0][1][8] == c.NATIVE_DEVTYPE["BULB"]
    main_records = [pages[0][1][90 + index * 36:126 + index * 36]
                    for index in range(pages[0][1][89])]
    assert any(record[0] == c.TAG["C"] and int.from_bytes(record[1:3], "big") == 330
               and record[3] == 0 for record in main_records)


def test_native_profile_switch_keeps_draft_when_page_is_unsupported():
    remote = {"device_type": "FAN", "remote_id": "12345678",
              "device_id": "AA:BB:CC:DD:EE:FF"}
    draft = physical.draft_for(remote)
    draft["template"] = "BULB"
    before = physical.native_layout(physical.validate(remote, physical.draft_for(remote)))

    try:
        physical.validate(remote, draft)
    except ValueError as err:
        assert "does not support page" in str(err)
    else:
        raise AssertionError("incompatible pages should be rejected")

    assert draft["template"] == "BULB"
    assert len(draft["pages"]) == 5
    assert before["template"] == "FAN"


def test_studio_menu_names_are_saved_without_changing_native_commands():
    remote = {"device_type": "STRIP", "device_id": "AA:BB:CC:DD:EE:FF"}
    draft = physical.draft_for(remote)
    before = physical.native_layout(draft)
    physical.rename_menu_item(draft, 4, None, " Living room colors ")
    physical.rename_menu_item(draft, 4, 0, "Movie night")
    saved = physical.draft_for({**remote, "physical_layout": draft})
    assert saved["pages"][1]["title"] == "Living room colors"
    assert saved["pages"][1]["buttons"][0]["title"] == "Movie night"
    assert physical.native_layout(saved) == before
    physical.rename_menu_item(saved, 4, 0, "")
    assert saved["pages"][1]["buttons"][0]["title"] == ""
    with pytest.raises(ValueError, match="not found"):
        physical.rename_menu_item(saved, 4, 99, "No such row")


def test_native_glyphs_round_trip_without_changing_key_commands_or_page_link():
    remote = {"device_type": "STRIP", "device_id": "AA:BB:CC:DD:EE:FF"}
    draft = physical.draft_for(remote)
    main, colors = draft["pages"]
    white = next(key for key in main["buttons"] if key["index"] == c.TAG["A"])
    white["glyph"] = 0x0142
    colors["link_glyph"] = 0x014B
    colors["buttons"][0]["glyph"] = 0x0141
    layout = physical.native_layout(physical.validate(remote, draft))
    rebuilt = physical.draft_for({**remote, "custom_layout": layout})
    assert physical.native_layout(rebuilt)["glyphs"] == layout["glyphs"]

    args = dict(remote_index=2, name="Strip", device_id=remote["device_id"],
                icon_name="strip", event_remote_id="12345678", template="STRIP",
                main_buttons=layout["main_buttons"],
                page_buttons={int(page): rows for page, rows in layout["pages"].items()})
    original = dict(c.build_custom_native_pages(**args))
    updated = dict(c.build_custom_native_pages(**args, glyphs=layout["glyphs"]))
    assert original.keys() == updated.keys() == {0, 4}

    changed = set()
    for page, packet in updated.items():
        assert c.crc16_modbus(packet[7:]) == int.from_bytes(packet[5:7], "big")
        assert packet[7:90] == original[page][7:90]
        for offset in range(90, len(packet), 36):
            record = packet[offset:offset + 36]
            old = original[page][offset:offset + 36]
            assert record[0] == old[0]
            assert record[3:] == old[3:]
            if record[1:3] != old[1:3]:
                identity = f"p{page}_k{record[0]}"
                assert int.from_bytes(record[1:3], "big") == layout["glyphs"][identity]
                changed.add(identity)
    assert changed == layout["glyphs"].keys()


def test_all_supported_profiles_can_rebuild_their_stock_editable_layout():
    for template in c.NATIVE_PROFILE_LAYOUTS:
        device_type = c.native_profile_device_type(template)
        if device_type is None:
            continue
        layout = c.editable_layout_from_native_profile(device_type)
        pages = c.build_custom_native_pages(
            remote_index=1, name="Test", device_id="AA:BB:CC:DD:EE:FF",
            icon_name="light", event_remote_id="12345678",
            main_buttons=layout["main_buttons"],
            page_buttons={int(page): actions for page, actions in layout["pages"].items()},
            template=template,
        )
        assert pages[0][1][8] == c.NATIVE_DEVTYPE[device_type]


def test_profile_metadata_exposes_renderable_main_and_subpage_layout():
    metadata = c.native_profile_metadata("FAN")

    assert metadata["value"] == "FAN"
    assert metadata["main_keys"]
    assert all({"index", "position", "function", "label", "actionable"} <= key.keys()
               for key in metadata["main_keys"])
    assert metadata["subpages"]
    assert all(page["link_index"] == page["index"] - 1 for page in metadata["subpages"])
    assert metadata["main_positions"] == sorted(metadata["main_positions"])


def test_every_native_type_choice_has_firmware_artwork_mapping():
    for profile_name in c.NATIVE_PROFILE_LAYOUTS:
        device_type = c.native_profile_device_type(profile_name)
        if device_type is None:
            continue
        metadata = c.native_profile_metadata(profile_name)
        assert metadata["artwork_id"] is not None, profile_name

    # TRV artwork is selected by the firmware's control-mode table, not device type.
    assert c.native_profile_metadata("TRV")["artwork_id"] == 0x13


def test_native_picker_matches_v48_artwork_tables():
    docs = INTEGRATION.parents[1] / "docs"
    with (docs / "native-default-artwork-map.csv").open() as stream:
        defaults = {int(row["device_type"], 16): int(row["artwork_profile_id"], 16)
                    for row in csv.DictReader(stream)}
    with (docs / "native-control-mode-map.csv").open() as stream:
        modes = {int(row["control_mode_code"], 16): int(row["artwork_profile_id"], 16)
                 for row in csv.DictReader(stream)}
    for profile in c.native_type_picker_options():
        device = c.NATIVE_DEVTYPE[profile["device_type"]]
        mode = profile["control_mode"]
        expected = modes[mode] if mode else defaults.get(device, 0)
        assert profile["artwork_id"] == expected, profile["value"]
        assert (INTEGRATION / "frontend" / "artwork" / f"profile-{expected:02x}.png").is_file()


def test_native_type_options_follow_official_handler_control_modes():
    options = {item["value"]: item for item in c.native_type_options()}

    assert options["BOT_PRESS"]["control_mode"] == 1
    assert options["BOT_SWITCH"]["control_mode"] == 2
    assert options["CURTAIN_GROUP"]["control_mode"] == 3
    assert options["CURTAIN_LEFT"]["control_mode"] == 4
    assert options["CURTAIN_RIGHT"]["control_mode"] == 5
    assert options["TRV"]["control_mode"] == 6
    assert options["FLOOR_LAMP"]["profile"] == "STRIP"
    assert options["FLOOR_LAMP"]["control_mode"] == 3


def test_catalog_variant_uses_same_wire_fields_on_create_and_edit():
    for name, wire_fields in (
        ("BOT_PRESS", bytes.fromhex("48000101")),
        ("CURTAIN_RIGHT", bytes.fromhex("63000501")),
        ("VACUUM_K20", bytes.fromhex("13000001")),
        ("FLOOR_LAMP", bytes.fromhex("72000301")),
    ):
        selected = c.native_type_metadata(name)
        device_type = selected["device_type"]
        remote = {"device_type": device_type, "native_type": name,
                  "device_id": "AA:BB:CC:DD:EE:FF"}
        draft = physical.native_layout(physical.validate(remote, physical.draft_for(remote)))
        fields = {"remote_index": 1, "name": "Test", "device_id": remote["device_id"],
                  "device_type_name": device_type, "event_remote_id": "12345678"}
        created, *_ = c.build_native_pages(
            **fields, control_mode=selected["control_mode"], icon_name=selected["icon_name"])
        (_, edited), *_ = c.build_custom_native_pages(
            **fields, template=draft["template"], control_mode=draft["control_mode"],
            icon_name=draft["icon_name"], main_buttons=draft["main_buttons"],
            page_buttons={int(page): keys for page, keys in draft["pages"].items()})
        assert created[8:8 + len(wire_fields)] == edited[8:8 + len(wire_fields)] == wire_fields


def test_floor_lamp_type_is_recovered_from_main_page_and_legacy_artwork_test():
    remote = {"device_type": "STRIP", "native_type": "STRIP",
              "device_id": "AA:BB:CC:DD:EE:FF"}
    main, colors = c.build_native_pages(device_type_name="STRIP", remote_index=1,
                                        name="Test", device_id=remote["device_id"])
    floor = c.rewrite_native_page_control_mode(main, c.NATIVE_FLOOR_LAMP_CONTROL_MODE)
    remote["physical_packets"] = [colors.hex(), floor.hex()]
    draft = physical.draft_for(remote)
    assert draft["native_type"] == "FLOOR_LAMP"
    assert draft["template"] == "STRIP"
    assert physical.validate(remote, draft)["control_mode"] == 3

    remote["physical_packets"] = [main.hex(), colors.hex()]
    remote["icon_variant_backup_packet"] = main.hex()
    assert physical.native_appearance(remote)["native_type"] == "FLOOR_LAMP"
    remote["floor_lamp_test_applied"] = False
    assert physical.native_appearance(remote)["native_type"] == "STRIP"


def test_device_details_distinguish_floor_lamp_and_strip_with_same_target():
    device_id = c.id_to_bytes("AA:BB:CC:DD:EE:FF")
    def record(header):
        return bytes.fromhex(header) + device_id + bytes(64)

    body = b"\x03" + record("0272000005") + record("0372000301") + record("04f2040001")
    raw = b"\x01\x00\x00\x00" + len(body).to_bytes(2, "big") + bytes(2) + body
    details = c.parse_device_appearances(raw)
    assert details == {(2, 0x72, device_id): (0, 5), (3, 0x72, device_id): (3, 1)}
    with pytest.raises(ValueError, match="Incomplete"):
        c.parse_device_appearances(raw[:-1])

    main, *_ = c.build_native_pages(device_type_name="STRIP", remote_index=3,
                                   name="Floor lamp", device_id=device_id.hex())
    remote = {"device_type": "STRIP", "device_id": device_id.hex(),
              "physical_packets": [main.hex()], "native_type": "STRIP",
              "native_appearance_readback": {"slot": 3, "device_type": 0x72,
                                             "mode": 3, "icon": 1}}
    assert physical.draft_for(remote)["native_type"] == "FLOOR_LAMP"
    remote["native_appearance_readback"]["mode"] = 0
    assert physical.draft_for(remote)["native_type"] == "STRIP"
    remote["native_appearance_readback"]["icon"] = 3
    draft = physical.draft_for(remote)
    assert draft["native_type"] == "STRIP"
    assert c.native_artwork_id(0x72, draft["control_mode"]) == 0x16
    assert draft["template"] == "STRIP"
    edited = physical.validate(remote, draft)
    assert (edited["control_mode"], c.ICON[edited["icon_name"]]) == (0, 3)


def test_picker_omits_extended_device_types_and_local_builder_rejects_them():
    options = {item["value"]: item for item in c.native_type_picker_options()}
    assert options["FLOOR_LAMP"]["artwork_id"] == 0x15
    assert all(c.NATIVE_DEVTYPE[item["device_type"]] <= 0xFF for item in options.values())
    assert "RGBICWW_FLOOR_LAMP" not in options
    with pytest.raises(ValueError, match="one-byte native device type"):
        c.build_native_pages(device_type_name="STRIP_3", remote_index=1,
                             name="Test", device_id="AA:BB:CC:DD:EE:FF")


def test_physical_validation_names_main_positions_missing_from_selected_profile():
    remote = {"device_type": "FAN", "remote_id": "12345678",
              "device_id": "AA:BB:CC:DD:EE:FF"}
    draft = physical.draft_for(remote)
    profile = c.native_profile_metadata("BULB")
    unsupported = next(index for index in range(19)
                       if index not in profile["main_positions"])
    draft["template"] = "BULB"
    draft["pages"][0]["buttons"].append({
        "index": unsupported, "transport": "native", "function": 5,
    })

    try:
        physical.validate(remote, draft)
    except ValueError as err:
        assert "has no Main-page position" in str(err)
    else:
        raise AssertionError("unsupported button positions must be rejected before writing")


def test_button_action_migrations_follow_moved_keys_without_overwriting_actions():
    binding = {"button_actions": {"p0_k2": [{"action": "light.turn_on"}],
                                  "p0_k3": [{"action": "light.turn_off"}]}}
    migrations = bindings.plan_button_identity_migrations(
        binding, [{"from": "p0_k2", "to": "p0_k4"}])

    migrated = bindings.migrate_button_action_identities(binding, migrations)
    assert migrated["button_actions"] == {
        "p0_k3": [{"action": "light.turn_off"}],
        "p0_k4": [{"action": "light.turn_on"}],
    }
    try:
        bindings.plan_button_identity_migrations(
            binding, [{"from": "p0_k2", "to": "p0_k3"}])
    except ValueError as err:
        assert "overwrite" in str(err)
    else:
        raise AssertionError("a migration must not overwrite existing destination actions")


def test_compacting_rows_removes_deleted_action_then_moves_following_actions():
    binding = {"button_actions": {
        "p2_k0": [{"action": "script.deleted"}],
        "p2_k1": [{"action": "script.first"}],
        "p2_k2": [{"action": "script.second"}],
    }}
    removals = ["p2_k0"]
    migrations = bindings.plan_button_identity_migrations(binding, [
        {"from": "p2_k1", "to": "p2_k0"},
        {"from": "p2_k2", "to": "p2_k1"},
    ], removals)

    migrated = bindings.migrate_button_action_identities(binding, migrations, removals)
    assert migrated["button_actions"] == {
        "p2_k0": [{"action": "script.first"}],
        "p2_k1": [{"action": "script.second"}],
    }
