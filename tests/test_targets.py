"""Tests for the record of which bridges a WoRWS can send native presses to."""
import pytest

from conftest import INTEGRATION, load

targets = load(INTEGRATION / "targets.py", "urc_targets")

DONGLE = "8A:88:1B:E0:1F:92"
SECOND = "DA:71:16:E0:1F:92"


class Entry:
    def __init__(self, data, options=None):
        self.data = data
        self.options = options or {}


class Hass:
    class config_entries:
        @staticmethod
        def async_update_entry(entry, data=None, options=None):
            entry.data = data
            if options is not None:
                entry.options = options


def target(address, **extra):
    return {"device_id": address, **extra}


def test_removing_press_keys_preserves_addresses_and_management_credentials():
    first = target(DONGLE, name="First")
    second = target(SECOND, name="Second")
    old_first = {**first, "target_key": "00" * 16, "target_key_id": "01"}
    old_second = {**second, "target_key": "11" * 16, "target_key_id": "01"}
    management = {"key": "22" * 16, "key_id": "95"}
    entry = Entry(
        {**management, "native_target": old_first, "native_targets": [old_first, old_second]},
        {"native_key_id": "01", "native_device_id": DONGLE},
    )

    targets.remove_saved_press_keys(Hass, entry)

    assert entry.data == {**management, "native_target": first, "native_targets": [first, second]}
    assert entry.options == {"native_device_id": DONGLE}


class TestReading:
    def test_a_configuration_from_before_the_list_existed(self):
        entry = Entry({"native_target": target(DONGLE)})
        assert [item["device_id"] for item in targets.all_targets(entry)] == [DONGLE]

    def test_nothing_configured(self):
        assert targets.all_targets(Entry({})) == []
        assert targets.target_for(Entry({}), {}) == {}

    def test_an_entry_without_an_address_is_ignored(self):
        assert targets.all_targets(Entry({"native_target": {"name": "Bridge"}})) == []

    def test_the_list_wins_over_the_single_key(self):
        entry = Entry({"native_target": target(DONGLE), "native_targets": [target(SECOND)]})
        assert [item["device_id"] for item in targets.all_targets(entry)] == [SECOND]


class TestChoosing:
    def test_matches_the_address_a_remote_was_bound_to(self):
        entry = Entry({"native_targets": [target(DONGLE), target(SECOND)]})
        chosen = targets.target_for(entry, {"physical_device_id": "da7116e01f92"})
        assert chosen["device_id"] == SECOND

    def test_matching_ignores_separators_and_case(self):
        entry = Entry({"native_targets": [target(DONGLE), target(SECOND)]})
        for written in ("DA:71:16:E0:1F:92", "da7116e01f92", "DA-71-16-E0-1F-92"):
            assert targets.target_for(entry, {"physical_device_id": written})["device_id"] == SECOND

    def test_an_unknown_address_falls_back_to_the_first_bridge(self):
        entry = Entry({"native_targets": [target(DONGLE), target(SECOND)]})
        assert targets.target_for(entry, {"physical_device_id": "aabbccddeeff"})["device_id"] == DONGLE

    def test_a_remote_with_no_recorded_address_takes_the_first(self):
        entry = Entry({"native_targets": [target(DONGLE), target(SECOND)]})
        assert targets.target_for(entry, {})["device_id"] == DONGLE
        assert targets.target_for(entry, None)["device_id"] == DONGLE


class TestWriting:
    def test_adding_a_second_bridge_keeps_the_first(self):
        entry = Entry({"native_target": target(DONGLE)})
        targets.remember_target(Hass, entry, target(SECOND))
        assert [item["device_id"] for item in targets.all_targets(entry)] == [DONGLE, SECOND]

    def test_the_legacy_key_still_points_at_the_first_bridge(self):
        entry = Entry({"native_target": target(DONGLE)})
        targets.remember_target(Hass, entry, target(SECOND))
        assert entry.data["native_target"]["device_id"] == DONGLE

    def test_the_same_address_is_replaced_not_duplicated(self):
        entry = Entry({"native_targets": [target(DONGLE, name="Old")]})
        targets.remember_target(Hass, entry, target("8a881be01f92", name="New"))
        stored = targets.all_targets(entry)
        assert len(stored) == 1
        assert stored[0]["name"] == "New"

    def test_a_stored_bridge_is_a_copy(self):
        original = target(SECOND, name="Bridge")
        entry = Entry({})
        targets.remember_target(Hass, entry, original)
        original["name"] = "Changed"
        assert targets.all_targets(entry)[0]["name"] == "Bridge"

    def test_a_bridge_without_an_address_is_refused(self):
        with pytest.raises(ValueError):
            targets.remember_target(Hass, Entry({}), {"name": "Bridge"})


class TestForgetting:
    def test_removes_by_address(self):
        entry = Entry({"native_targets": [target(DONGLE), target(SECOND)]})
        assert targets.forget_target(Hass, entry, "da-71-16-e0-1f-92") is True
        assert [item["device_id"] for item in targets.all_targets(entry)] == [DONGLE]

    def test_an_unknown_address_changes_nothing(self):
        entry = Entry({"native_targets": [target(DONGLE)]})
        assert targets.forget_target(Hass, entry, "AA:BB:CC:DD:EE:FF") is False
        assert len(targets.all_targets(entry)) == 1

    def test_forgetting_the_last_one_leaves_an_empty_record(self):
        entry = Entry({"native_targets": [target(DONGLE)]})
        assert targets.forget_target(Hass, entry, DONGLE) is True
        assert targets.all_targets(entry) == []
        assert entry.data["native_target"] == {}
