"""Native Remote Studio profile changes must preserve layouts and fail before writing."""

import csv

import pytest
from conftest import INTEGRATION, load


c = load(INTEGRATION / "commands.py")
physical = load(INTEGRATION / "physical_layout.py")


def test_ir_preview_gives_stock_softkeys_only_for_reconstructed_layout():
    tv = {"device_type": "IR_2", "imported_from_cloud": True}
    preview = physical.ir_screen_preview(tv)
    assert preview["softkeys"] == (39, 20, 210, 100)
    # rows carry the firmware picture the page builders wrote: no catalog-tag translation
    assert "catalog_glyphs" not in preview
    assert physical.ir_screen_preview({**tv, "device_type": "IR_16"}) == preview
    assert physical.ir_screen_preview({
        **tv, "physical_layout": {"kind": "ir", "pages": []},
    }) is None


def test_plaintext_bridge_bind_only_writes_pages_with_tagged_commands():
    common = dict(remote_index=3, name="Lamp", device_id="AA:BB:CC:DD:EE:FF",
                  event_remote_id="12345678", device_type_name="STRIP")
    stock = c.build_native_bind_sequence(**common)
    custom = c.build_custom_native_bind_sequence(
        **common, template="STRIP", icon_name="strip",
        main_buttons={"ON": "ON"}, page_buttons={4: ["OFF"]},
    )
    assert {packet[88] for _, packet in stock} == {0, 4}
    assert {packet[88] for _, packet in custom} == {0, 4}
    for _, packet in (*stock, *custom):
        assert packet[:3] == bytes.fromhex("0f6206")
        assert bytes.fromhex("57f003") in packet


def test_native_row_deletion_clears_the_vacated_position_after_compaction():
    previous = {"pages": [
        {"index": 0, "buttons": [{"index": 4}]},
        {"index": 4, "buttons": [{"index": 0}, {"index": 1}, {"index": 2}]},
    ]}
    updated = {"pages": [previous["pages"][0],
                         {"index": 4, "buttons": [{"index": 0}, {"index": 1}]}]}

    assert physical.removed_native_keys(previous, updated) == [(4, 2)]
    assert physical.removed_native_keys(updated, {"pages": [previous["pages"][0]]}) == [
        (0, 3), (4, 0), (4, 1),
    ]
    assert physical.removed_native_keys(updated, updated) == []
    assert c.build_delete_native_key(
        remote_index=3, device_type=0x72, device_id=bytes.fromhex("1571da7d1a000000000000"),
        page=4, index=2,
    ) == bytes.fromhex("0f6204010372001571da7d1a0000000000000402")
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


def test_native_profile_switch_preserves_all_custom_menu_pages():
    remote = {"device_type": "FAN", "remote_id": "12345678",
              "device_id": "AA:BB:CC:DD:EE:FF"}
    draft = physical.draft_for(remote)
    draft["template"] = "BULB"
    before = physical.draft_for(remote)
    edited = physical.validate(remote, draft)
    assert edited["pages"] == before["pages"]
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
    colors["link_glyph"] = 119
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


@pytest.mark.parametrize("glyph", [118, 2104, 331])
def test_native_submenu_rejects_icons_that_are_not_page_links(glyph):
    remote = {"device_type": "STRIP", "device_id": "AA:BB:CC:DD:EE:FF"}
    draft = physical.draft_for(remote)
    colors = next(page for page in draft["pages"] if page["index"] == 4)
    colors["link_glyph"] = glyph
    with pytest.raises(ValueError, match="Native menu icon"):
        physical.validate(remote, draft)

    layout = physical.native_layout(draft)
    with pytest.raises(ValueError, match="Native menu icon"):
        c.build_custom_native_pages(
            remote_index=2, name="Strip", device_id=remote["device_id"],
            icon_name="strip", event_remote_id="12345678", template="STRIP",
            main_buttons=layout["main_buttons"],
            page_buttons={4: layout["pages"]["4"]}, glyphs=layout["glyphs"],
        )

    del colors["link_glyph"]
    reset = physical.native_layout(physical.validate(remote, draft))
    assert "p0_k3" not in reset["glyphs"]


def test_native_menu_rows_sharing_a_function_have_independent_actions():
    packets = dict(c.build_custom_native_pages(
        remote_index=3, name="Light", device_id="AA:BB:CC:DD:EE:FF",
        icon_name="strip", event_remote_id="12345678", template="STRIP",
        main_buttons={"ON": "ON"}, page_buttons={4: ["PAUSE", "PAUSE"]},
        glyphs={"p4_k0": 0x0141, "p4_k1": 0x0142},
    ))
    first_action = [{"action": "light.turn_on"}]
    second_action = [{"action": "light.turn_off"}]
    binding = {
        "remote_id": "12345678", "profile": "light", "mappings": {"ON": "turn_on"},
        "button_actions": {"p4_k0": first_action, "p4_k1": second_action},
    }
    packet = packets[4]
    assert packet[89] == 2
    for index, actions in enumerate((first_action, second_action)):
        offset = 90 + index * 36
        record = packet[offset:offset + 36]
        assert int.from_bytes(record[1:3], "big") == 0x0141 + index
        command = record[4:17]
        assert command[:3] == c.BRIDGE_EVENT_MAGIC_V3
        assert command[9:] == bytes([4, index, 0, 22])
        event = {
            "remote_id": command[4:8].hex(),
            "button_id": f"p{command[9]}_k{command[10]}",
            "button_function": 22, "button_name": "PAUSE",
        }
        assert bindings.resolve_binding_action(binding, event) is None
        assert bindings.resolve_button_action_sequence(binding, event) == actions


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


def test_vacuum_softkeys_round_trip_with_bridge_events_and_custom_glyphs():
    remote = {"device_type": "VACUUM_S1_MINI", "remote_id": "12345678",
              "device_id": "AA:BB:CC:DD:EE:FF"}
    draft = physical.draft_for(remote)
    original_buttons = list(draft["pages"][0]["buttons"])
    for index in range(4):
        draft["pages"][0]["buttons"].append({
            "index": index, "transport": "native", "function": 321 + index,
            "glyph": 0x0141,
        })
    layout = physical.native_layout(physical.validate(remote, draft))
    pages = c.build_custom_native_pages(
        remote_index=3, name="Vacuum", device_id=remote["device_id"],
        icon_name=layout["icon_name"], event_remote_id=remote["remote_id"],
        main_buttons=layout["main_buttons"], page_buttons={},
        template=layout["template"], glyphs=layout["glyphs"],
    )
    assert len(pages) == 1
    packet = pages[0][1]
    assert packet[8] == c.NATIVE_DEVTYPE["VACUUM_S1_MINI"]
    assert packet[89] == len(original_buttons) + 4
    records = {packet[offset]: packet[offset:offset + 36]
               for offset in range(90, len(packet), 36)}
    for index in range(4):
        record = records[index]
        assert int.from_bytes(record[1:3], "big") == 0x0141
        assert record[4:17] == (
            c.BRIDGE_EVENT_MAGIC_V3 + bytes([0xFE]) + bytes.fromhex("12345678")
            + bytes([3, 0, index]) + (321 + index).to_bytes(2, "big")
        )
    saved = physical.draft_for({**remote, "custom_layout": layout,
                                "icon": layout["icon_name"]})
    assert physical.native_layout(saved) == layout
    assert all(key in saved["pages"][0]["buttons"] for key in original_buttons)


def test_all_native_profiles_offer_abcd_without_creating_subpages():
    for template in c.NATIVE_PROFILE_LAYOUTS:
        assert {0, 1, 2, 3} <= set(c.native_profile_metadata(template)["main_positions"])
    assert set(c.custom_native_layout({"ON": "ON"}, {}, template="VACUUM")) == {0}


def test_vacuum_can_bind_four_custom_menus_with_distinct_page_events():
    remote = {"device_type": "VACUUM_S1_MINI", "remote_id": "12345678",
              "device_id": "AA:BB:CC:DD:EE:FF"}
    draft = physical.draft_for(remote)
    for page in range(1, 5):
        draft["pages"].append({"index": page, "title": f"Menu {page}", "buttons": [
            {"index": 0, "transport": "native", "function": 5},
            {"index": 1, "transport": "native", "function": 6},
        ]})
    layout = physical.native_layout(physical.validate(remote, draft))
    packets = c.build_custom_native_pages(
        remote_index=3, name="Vacuum", device_id=remote["device_id"],
        icon_name=layout["icon_name"], event_remote_id=remote["remote_id"],
        main_buttons=layout["main_buttons"],
        page_buttons={int(page): values for page, values in layout["pages"].items()},
        template=layout["template"],
    )
    assert [page for page, packet in packets] == [0, 1, 2, 3, 4]
    main = packets[0][1]
    records = {main[offset]: main[offset:offset + 36]
               for offset in range(90, len(main), 36)}
    for page, packet in packets[1:]:
        link = records[page - 1]
        assert int.from_bytes(link[1:3], "big") == c.NATIVE_MENU_FUNCTIONS[page]
        assert link[4:6] == c.s16(c.NATIVE_MENU_FUNCTIONS[page])
        assert packet[88] == page
        assert packet[94:107] == (c.BRIDGE_EVENT_MAGIC_V3 + bytes([0xFE])
                                 + bytes.fromhex("12345678") + bytes([3, page, 0, 0, 5]))
    assert c.native_profile_metadata("VACUUM")["pages"] == [0, 1, 2, 3, 4]


def test_custom_menu_cannot_silently_drop_an_empty_page_or_overwrite_its_key():
    remote = {"device_type": "VACUUM_S1_MINI", "device_id": "AA:BB:CC:DD:EE:FF"}
    draft = physical.draft_for(remote)
    draft["pages"].append({"index": 1, "buttons": []})
    with pytest.raises(ValueError, match="Page 1 must have"):
        physical.validate(remote, draft)
    draft["pages"][1]["buttons"].append({"index": 0, "transport": "native", "function": 5})
    draft["pages"][0]["buttons"].append({"index": 0, "transport": "native", "function": 6})
    with pytest.raises(ValueError, match="reserved for page links"):
        physical.validate(remote, draft)


def test_every_native_type_choice_has_firmware_artwork_mapping():
    for profile_name in c.NATIVE_PROFILE_LAYOUTS:
        device_type = c.native_profile_device_type(profile_name)
        if device_type is None:
            continue
        metadata = c.native_profile_metadata(profile_name)
        assert metadata["artwork_id"] is not None, profile_name

    # TRV artwork uses wire icon 6 from the firmware illustration table.
    assert c.native_profile_metadata("TRV")["artwork_id"] == 0x13


def test_native_picker_matches_v48_artwork_tables():
    docs = INTEGRATION.parents[1] / "docs"
    with (docs / "native-default-artwork-map.csv").open() as stream:
        defaults = {int(row["device_type"], 16): int(row["artwork_profile_id"], 16)
                    for row in csv.DictReader(stream)}
    with (docs / "native-icon-map.csv").open() as stream:
        modes = {int(row["icon_code"], 16): int(row["artwork_profile_id"], 16)
                 for row in csv.DictReader(stream)}
    for profile in c.native_type_picker_options():
        device = c.NATIVE_DEVTYPE[profile["device_type"]]
        icon = profile["icon_code"]
        mode = profile["control_mode"]
        expected = modes[icon] if icon else (
            {3: 2, 4: 3, 5: 4}.get(mode, 3) if device in (0x63, 0x7B)
            else defaults.get(device, 0))
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
    assert options["FLOOR_LAMP"]["control_mode"] == 0
    assert options["FLOOR_LAMP"]["icon_code"] == 3


def test_catalog_variant_uses_same_wire_fields_on_create_and_edit():
    for name, wire_fields in (
        ("BOT_PRESS", bytes.fromhex("48000100")),
        ("CURTAIN_RIGHT", bytes.fromhex("63000500")),
        ("VACUUM_K20", bytes.fromhex("13000000")),
        ("FLOOR_LAMP", bytes.fromhex("72000003")),
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
    floor = c.rewrite_native_page_icon(main, 3)
    remote["physical_packets"] = [colors.hex(), floor.hex()]
    draft = physical.draft_for(remote)
    assert draft["native_type"] == "FLOOR_LAMP"
    assert draft["template"] == "STRIP"
    assert physical.validate(remote, draft)["control_mode"] == 0

    remote["physical_packets"] = [main.hex(), colors.hex()]
    remote["icon_variant_backup_packet"] = main.hex()
    assert physical.native_appearance(remote)["native_type"] == "STRIP"
    remote["floor_lamp_test_applied"] = False
    assert physical.native_appearance(remote)["native_type"] == "STRIP"


def test_device_details_distinguish_floor_lamp_and_strip_with_same_target():
    device_id = c.id_to_bytes("AA:BB:CC:DD:EE:FF")
    def record(header):
        return bytes.fromhex(header) + device_id + bytes(64)

    body = b"\x03" + record("0272000005") + record("0372000003") + record("04f2040001")
    raw = b"\x01\x00\x00\x00" + len(body).to_bytes(2, "big") + bytes(2) + body
    details = c.parse_device_appearances(raw)
    assert details == {(2, 0x72, device_id): (0, 5), (3, 0x72, device_id): (0, 3)}
    with pytest.raises(ValueError, match="Incomplete"):
        c.parse_device_appearances(raw[:-1])

    main, *_ = c.build_native_pages(device_type_name="STRIP", remote_index=3,
                                   name="Floor lamp", device_id=device_id.hex())
    remote = {"device_type": "STRIP", "device_id": device_id.hex(),
              "physical_packets": [main.hex()], "native_type": "STRIP",
              "native_appearance_readback": {"slot": 3, "device_type": 0x72,
                                             "mode": 0, "icon": 3}}
    assert physical.draft_for(remote)["native_type"] == "FLOOR_LAMP"
    remote["native_appearance_readback"]["icon"] = 5
    assert physical.draft_for(remote)["native_type"] == "STRIP"
    remote["native_appearance_readback"]["icon"] = 3
    draft = physical.draft_for(remote)
    assert draft["native_type"] == "FLOOR_LAMP"
    assert c.native_artwork_id(0x72, draft["icon_code"], draft["control_mode"]) == 0x15
    assert draft["template"] == "STRIP"
    edited = physical.validate(remote, draft)
    assert (edited["control_mode"], c.ICON[edited["icon_name"]]) == (0, 3)


def test_native_appearance_match_normalizes_saved_slot_and_resolves_duplicate_target_ids():
    device_id = c.id_to_bytes("AA:BB:CC:DD:EE:FF")
    appearances = {
        (2, 0x72, device_id): (0, 5),
        (3, 0x72, device_id): (0, 3),
    }
    remote = {"index": "3", "device_type": "STRIP", "device_id": device_id.hex()}

    assert physical.match_native_appearance(remote, appearances, 0x72) == (
        3, 0x72, device_id
    )
    remote["index"] = "8"
    assert physical.match_native_appearance(remote, appearances, 0x72) is None


def test_native_appearance_match_uses_unique_id_when_cached_slot_is_stale():
    device_id = c.id_to_bytes("AA:BB:CC:DD:EE:FF")
    appearances = {(3, 0x72, device_id): (0, 3)}
    remote = {"index": 2, "device_type": "STRIP", "device_id": device_id.hex()}

    assert physical.match_native_appearance(remote, appearances, 0x72) == (
        3, 0x72, device_id
    )


def test_picker_omits_extended_device_types_and_local_builder_rejects_them():
    options = {item["value"]: item for item in c.native_type_picker_options()}
    assert options["FLOOR_LAMP"]["artwork_id"] == 0x15
    assert all(c.NATIVE_DEVTYPE[item["device_type"]] <= 0xFF for item in options.values())
    assert "RGBICWW_FLOOR_LAMP" not in options
    with pytest.raises(ValueError, match="one-byte native device type"):
        c.build_native_pages(device_type_name="STRIP_3", remote_index=1,
                             name="Test", device_id="AA:BB:CC:DD:EE:FF")


def test_vacuum_can_write_every_main_key_except_kata():
    remote = {"device_type": "VACUUM_S1_MINI", "remote_id": "12345678",
              "device_id": "AA:BB:CC:DD:EE:FF"}
    draft = physical.draft_for(remote)
    positions = {index for name, index in c.TAG.items() if name != "KATA"}
    for template in c.NATIVE_PROFILE_LAYOUTS:
        assert set(c.native_profile_metadata(template)["main_positions"]) == positions
    draft["pages"][0]["buttons"] = [
        {"index": index, "transport": "native", "function": 22} for index in sorted(positions)
    ]
    layout = physical.native_layout(physical.validate(remote, draft))
    args = dict(remote_index=3, name="Vacuum", device_id=remote["device_id"],
                icon_name=layout["icon_name"], event_remote_id=remote["remote_id"],
                main_buttons=layout["main_buttons"], page_buttons={},
                template=layout["template"], device_type_name=remote["device_type"])
    packet = dict(c.build_custom_native_pages(**args))[0]
    records = {packet[offset]: packet[offset:offset + 36]
               for offset in range(90, len(packet), 36)}
    assert set(records) == positions
    assert records[c.TAG["VOLADD"]][13:17] == bytes([0, c.TAG["VOLADD"], 0, 22])

    draft["pages"][0]["buttons"][0]["index"] = c.TAG["KATA"]
    with pytest.raises(ValueError, match="KATA is reserved"):
        physical.validate(remote, draft)
    args["main_buttons"] = {"KATA": "PAUSE"}
    with pytest.raises(ValueError, match="KATA is reserved"):
        c.build_custom_native_pages(**args)


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


def test_icon_selects_artwork_after_published_dsp_row_shift():
    # Ghidra executes source-row copies, +1 publication and native argument loads.
    # The previous fixture injected the unshifted source row into the renderer.
    assert c.native_artwork_id(0x72, 1, 3) == 0x0C
    assert c.native_artwork_id(0x72, 3, 0) == 0x15
    assert c.native_artwork_id(0x72, 5, 0) == 0x16
    assert c.native_artwork_id(0x72, 0, 0) == 0x16
    assert c.native_artwork_id(0x63, 0, 3) == 2
    assert c.native_artwork_id(0x63, 0, 5) == 4


def test_stale_floor_lamp_label_cannot_override_bulb_readback():
    remote = {"device_type": "STRIP", "native_type": "FLOOR_LAMP",
              "device_id": "AA:BB:CC:DD:EE:FF",
              "native_appearance_readback": {"mode": 3, "icon": 1}}
    appearance = physical.native_appearance(remote)
    assert appearance["native_type"] != "FLOOR_LAMP"
    assert (appearance["control_mode"], appearance["icon_code"]) == (3, 1)
    assert c.native_artwork_id(0x72, appearance["icon_code"], appearance["control_mode"]) == 0x0C


@pytest.mark.parametrize("device_type,control_type,name", [
    (0xF2, c.CTRL_HID, "UNIVERSAL_BLE"),
    (0x18, c.CTRL_IR, "IR_24"),
])
def test_hid_ir_preview_uses_wire_icon_in_cached_main_page(device_type, control_type, name):
    packet = c.build_create(
        remote_index=3, device_type=device_type, control_type=control_type,
        control_mode=0, icon=3, device_id="AA:BB:CC:DD:EE:FF",
        name="Test", ble_key_type=0, keys=[])
    remote = {"device_type": name, "icon": "light", "icon_code": 1,
              "physical_packets": [packet.hex()]}
    assert physical.remote_artwork_id(remote) == 0x15
    remote["physical_packets"] = [c.rewrite_native_page_icon(packet, 14).hex()]
    assert physical.remote_artwork_id(remote) == 0x28
    remote["physical_packets"] = []
    assert physical.remote_artwork_id(remote) == 0x0C


def test_device_specific_artwork_defaults_match_entire_v48_table():
    with (INTEGRATION.parents[1] / "docs" / "native-default-artwork-map.csv").open() as stream:
        for row in csv.DictReader(stream):
            device_type = int(row["device_type"], 16)
            assert c.native_artwork_id(device_type, 0) == int(row["artwork_profile_id"], 16)


def test_firmware_execution_report_matches_shared_artwork_resolver():
    with (INTEGRATION.parents[1] / "docs" / "artwork-firmware-verification.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 115
    for row in rows:
        if row["status"] == "opaque_flix":
            assert row["case"] == "native-catalog-ROLLER_SHADE"
            continue
        assert c.native_artwork_id(int(row["device_type"], 16),
                                   int(row["icon"], 16), int(row["mode"], 16)) == int(row["profile"], 16)


def test_types_set_up_alike_share_one_card_and_a_tile_keeps_its_own_type():
    twins = c.native_type_twins()
    assert twins["PLUG_JP"] == "PLUG" and twins["LOCK_PRO"] == "LOCK" and twins["CURTAIN_3"] == "CURTAIN"
    options = {item["value"]: item for item in c.native_type_picker_options()}
    assert "PLUG_JP" not in options and "LOCK_LITE" not in options
    assert options["AIR_PURIFIER_US"]["title"] == "Air purifier"
    assert set(options["AIR_PURIFIER_US"]["twin_types"]) == {"AIR_PURIFIER_JP", "AIR_PURIFIER_US_PRO",
                                                            "AIR_PURIFIER_JP_PRO"}
    assert "PLUG_JP" in options["PLUG"]["equivalent_types"]
    # every card of a group is the same in Studio: layout, screen mode, picture and icon
    for alias, canonical in twins.items():
        one, other = c.native_type_metadata(alias), c.native_type_metadata(canonical)
        assert (one["profile"], one["control_mode"], one["artwork_id"], one["icon_code"]) == \
               (other["profile"], other["control_mode"], other["artwork_id"], other["icon_code"])
    # a Japan outlet on the remote stays a Japan outlet (its own device-type byte)
    remote = {"device_type": "PLUG_JP", "remote_id": "1", "device_id": "AA:BB:CC:DD:EE:FF"}
    assert physical.native_appearance(remote)["native_type"] == "PLUG_JP"
