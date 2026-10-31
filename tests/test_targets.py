"""Tests for the record of which bridges a WoRWS can send native presses to.

This is what decides which key a tile is bound with and which bridge serves it, so a mistake
here binds a remote to an address nothing answers on.
"""
import pytest

from conftest import INTEGRATION, load

targets = load(INTEGRATION / "targets.py", "urc_targets")

DONGLE = "8A:88:1B:E0:1F:92"
SECOND = "DA:71:16:E0:1F:92"
KEY = "00" * 16
OTHER_KEY = "ff" * 16


class Entry:
    def __init__(self, data):
        self.data = data


class Hass:
    class config_entries:
        @staticmethod
        def async_update_entry(entry, data=None):
            entry.data = data


def target(address, key=KEY, **extra):
    return {"device_id": address, "target_key": key, **extra}


class TestReading:
    def test_a_configuration_from_before_the_list_existed(self):
        entry = Entry({"native_target": target(DONGLE)})
        assert [item["device_id"] for item in targets.all_targets(entry)] == [DONGLE]

    def test_nothing_configured(self):
        assert targets.all_targets(Entry({})) == []
        assert targets.target_for(Entry({}), {}) == {}

    def test_an_entry_without_an_address_is_ignored(self):
        assert targets.all_targets(Entry({"native_target": {"target_key": KEY}})) == []

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
        targets.remember_target(Hass, entry, target(SECOND, OTHER_KEY))
        assert [item["device_id"] for item in targets.all_targets(entry)] == [DONGLE, SECOND]

    def test_the_legacy_key_still_points_at_the_first_bridge(self):
        entry = Entry({"native_target": target(DONGLE)})
        targets.remember_target(Hass, entry, target(SECOND))
        assert entry.data["native_target"]["device_id"] == DONGLE

    def test_the_same_address_is_replaced_not_duplicated(self):
        entry = Entry({"native_targets": [target(DONGLE, KEY)]})
        targets.remember_target(Hass, entry, target("8a881be01f92", OTHER_KEY))
        stored = targets.all_targets(entry)
        assert len(stored) == 1
        assert stored[0]["target_key"] == OTHER_KEY

    def test_a_stored_bridge_is_a_copy(self):
        original = target(SECOND)
        entry = Entry({})
        targets.remember_target(Hass, entry, original)
        original["target_key"] = "changed"
        assert targets.all_targets(entry)[0]["target_key"] == KEY

    def test_a_bridge_without_an_address_is_refused(self):
        with pytest.raises(ValueError):
            targets.remember_target(Hass, Entry({}), {"target_key": KEY})


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
