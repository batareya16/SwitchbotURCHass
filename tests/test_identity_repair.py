"""Tests for the two things that let a deleted remote keep driving a light.

A remote is matched by `remote_id or device_id`. Deleting one used to leave its bindings
behind, and remotes without an id of their own shared the bridge address — so the leftover
binding started answering for whichever remote still held that address.
"""
import pathlib

import pytest

from conftest import INTEGRATION

SOURCE = (INTEGRATION / "studio_remotes.py").read_text()


def _extract(name: str, end_marker: str):
    start = SOURCE.index(f"def {name}(")
    end = SOURCE.index(end_marker, start)
    namespace: dict = {}
    import copy
    import logging
    import uuid
    namespace.update({"deepcopy": copy.deepcopy, "uuid": uuid, "Any": object,
                      "_LOGGER": logging.getLogger("test")})
    exec(compile(SOURCE[start:end], name, "exec"), namespace)
    return namespace[name]


forget_remote = _extract("_forget_remote", "\n\n@websocket_api.require_admin")
ensure_distinct = _extract("ensure_distinct_identities", "\ndef _forget_remote(")


class Entry:
    def __init__(self, options):
        self.options = options


class Hass:
    class config_entries:
        @staticmethod
        def async_update_entry(entry, options=None):
            entry.options = options


DESK = {"name": "Desk lamp", "remote_id": "aa11bb22", "device_id": "8A881BE01F92"}
STRIP = {"name": "Strip", "remote_id": "bb30e0eb", "device_id": "8A881BE01F92"}


class TestDeletingARemote:
    def test_its_bindings_go_with_it(self):
        entry = Entry({"remotes": [DESK, STRIP], "bindings": [
            {"remote_id": "aa11bb22", "entity_id": "light.desk"},
            {"remote_id": "bb30e0eb", "entity_id": "light.hall"},
        ]})
        assert forget_remote(Hass, entry, "aa11bb22") == 1
        assert [b["entity_id"] for b in entry.options["bindings"]] == ["light.hall"]
        assert [r["name"] for r in entry.options["remotes"]] == ["Strip"]

    def test_nothing_else_is_touched(self):
        entry = Entry({"remotes": [DESK, STRIP], "bindings": [
            {"remote_id": "bb30e0eb", "entity_id": "light.hall"},
        ]})
        assert forget_remote(Hass, entry, "aa11bb22") == 0
        assert len(entry.options["bindings"]) == 1

    def test_a_shared_identity_keeps_the_survivor_s_actions(self):
        # Two remotes with no id of their own: deleting one must not take the other's actions.
        first = {"name": "Desk lamp", "device_id": "8A881BE01F92"}
        second = {"name": "Strip", "device_id": "8A881BE01F92"}
        entry = Entry({"remotes": [first, second], "bindings": [
            {"remote_id": "8A881BE01F92", "entity_id": "light.shared"},
        ]})
        assert forget_remote(Hass, entry, "8A881BE01F92") == 0
        assert len(entry.options["bindings"]) == 1

    def test_deleting_the_last_holder_does_remove_them(self):
        only = {"name": "Desk lamp", "device_id": "8A881BE01F92"}
        entry = Entry({"remotes": [only], "bindings": [
            {"remote_id": "8A881BE01F92", "entity_id": "light.desk"},
        ]})
        assert forget_remote(Hass, entry, "8A881BE01F92") == 1
        assert entry.options["bindings"] == []


class TestGivingEveryRemoteItsOwnIdentity:
    def test_a_remote_without_one_gets_one(self):
        entry = Entry({"remotes": [{"name": "Strip", "device_id": "8A881BE01F92"}],
                       "bindings": []})
        assert ensure_distinct(Hass, entry) == 1
        assert entry.options["remotes"][0]["remote_id"]

    def test_its_bindings_follow_it(self):
        entry = Entry({"remotes": [{"name": "Strip", "device_id": "8A881BE01F92"}],
                       "bindings": [{"remote_id": "8A881BE01F92", "entity_id": "light.hall"}]})
        ensure_distinct(Hass, entry)
        new_id = entry.options["remotes"][0]["remote_id"]
        assert entry.options["bindings"][0]["remote_id"] == new_id

    def test_remotes_that_shared_an_address_get_different_ids(self):
        entry = Entry({"remotes": [
            {"name": "Desk lamp", "device_id": "8A881BE01F92"},
            {"name": "Strip", "device_id": "8A881BE01F92"},
        ], "bindings": []})
        assert ensure_distinct(Hass, entry) == 2
        ids = {r["remote_id"] for r in entry.options["remotes"]}
        assert len(ids) == 2

    def test_a_shared_binding_is_left_alone_rather_than_guessed(self):
        entry = Entry({"remotes": [
            {"name": "Desk lamp", "device_id": "8A881BE01F92"},
            {"name": "Strip", "device_id": "8A881BE01F92"},
        ], "bindings": [{"remote_id": "8A881BE01F92", "entity_id": "light.shared"}]})
        ensure_distinct(Hass, entry)
        assert entry.options["bindings"][0]["remote_id"] == "8A881BE01F92"

    def test_remotes_that_already_have_ids_are_untouched(self):
        entry = Entry({"remotes": [dict(DESK), dict(STRIP)], "bindings": []})
        assert ensure_distinct(Hass, entry) == 0

    def test_a_new_id_never_collides_with_an_existing_one(self):
        entry = Entry({"remotes": [dict(STRIP), {"name": "New", "device_id": "DA7116E01F92"}],
                       "bindings": []})
        ensure_distinct(Hass, entry)
        ids = [r["remote_id"] for r in entry.options["remotes"]]
        assert len(set(ids)) == len(ids)


def _cleanup(entry):
    """The rule `ws_bindings_cleanup` applies, lifted out of its Home Assistant wrapper."""
    import copy
    options = copy.deepcopy(dict(entry.options))
    identities = {
        str(item.get("remote_id") or item.get("device_id") or "")
        for item in options.get("remotes", []) if isinstance(item, dict)
    }
    bindings = [item for item in options.get("bindings", []) if isinstance(item, dict)]
    kept = [item for item in bindings if str(item.get("remote_id", "")) in identities]
    removed = [item for item in bindings if item not in kept]
    options["bindings"] = kept
    return removed, options


class TestRemovingLeftoverActions:
    """What the "Remove them" button does, for a configuration that did not repair itself."""

    def test_a_binding_whose_remote_is_gone_is_removed(self):
        removed, options = _cleanup(Entry({
            "remotes": [dict(STRIP)],
            "bindings": [
                {"remote_id": "bb30e0eb", "entity_id": "light.hall"},
                {"remote_id": "aa11bb22", "remote_name": "Desk lamp", "entity_id": "light.desk"},
            ],
        }))
        assert [r["entity_id"] for r in removed] == ["light.desk"]
        assert [b["entity_id"] for b in options["bindings"]] == ["light.hall"]

    def test_a_remote_matched_by_its_address_still_counts_as_existing(self):
        removed, _ = _cleanup(Entry({
            "remotes": [{"name": "Strip", "device_id": "8A881BE01F92"}],
            "bindings": [{"remote_id": "8A881BE01F92", "entity_id": "light.hall"}],
        }))
        assert removed == []

    def test_nothing_is_removed_when_every_binding_has_its_remote(self):
        removed, _ = _cleanup(Entry({
            "remotes": [dict(DESK), dict(STRIP)],
            "bindings": [
                {"remote_id": "aa11bb22", "entity_id": "light.desk"},
                {"remote_id": "bb30e0eb", "entity_id": "light.hall"},
            ],
        }))
        assert removed == []

    def test_a_binding_with_no_remote_id_at_all_is_removed(self):
        removed, _ = _cleanup(Entry({
            "remotes": [dict(STRIP)],
            "bindings": [{"entity_id": "light.mystery"}],
        }))
        assert len(removed) == 1

    def test_an_empty_configuration_is_left_alone(self):
        removed, options = _cleanup(Entry({})) 
        assert removed == [] and options["bindings"] == []
