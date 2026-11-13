"""Native Remote Studio profile changes must preserve layouts and fail before writing."""

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
