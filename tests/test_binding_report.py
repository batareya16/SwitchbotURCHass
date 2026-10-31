"""Tests for the report that says why an action ran for a given press.

A press is matched to its actions by `remote_id` alone. When one remote's button drives
another's light, the cause is in what these two columns actually hold — so the report has to be
right about the shapes that cause it.
"""
import pathlib

import pytest

from conftest import INTEGRATION

SOURCE = (INTEGRATION / "studio_manage.py").read_text()
START = SOURCE.index("def _binding_report(entry)")
END = SOURCE.index("\n\n@websocket_api.require_admin", START)
_NS: dict = {"Any": object}
exec(compile(SOURCE[START:END], "studio_manage._binding_report", "exec"), _NS)
report = _NS["_binding_report"]


class Entry:
    def __init__(self, options):
        self.options = options


def remote(name, **extra):
    return {"name": name, "device_type": "STRIP", **extra}


class TestSharedIdentity:
    """Two remotes with no id of their own fall back to their address — and can share it."""

    def test_it_is_reported(self):
        out = report(Entry({"remotes": [
            remote("Strip", device_id="8A881BE01F92"),
            remote("Ambience", device_id="8A881BE01F92"),
        ], "bindings": []}))
        assert any("share the identity" in p for p in out["problems"])

    def test_both_names_are_named(self):
        out = report(Entry({"remotes": [
            remote("Strip", device_id="8A881BE01F92"),
            remote("Ambience", device_id="8A881BE01F92"),
        ], "bindings": []}))
        assert "Strip" in out["problems"][0] and "Ambience" in out["problems"][0]

    def test_a_remote_without_its_own_id_is_flagged(self):
        out = report(Entry({"remotes": [remote("Strip", device_id="8A881BE01F92")],
                            "bindings": []}))
        assert out["remotes"][0]["has_remote_id"] is False

    def test_different_addresses_do_not_collide(self):
        out = report(Entry({"remotes": [
            remote("Strip", device_id="8A881BE01F92"),
            remote("Ambience", device_id="DA7116E01F92"),
        ], "bindings": []}))
        assert out["problems"] == []


class TestBindings:
    def test_two_bindings_for_one_remote_are_reported(self):
        out = report(Entry({"remotes": [remote("Strip", remote_id="bb30e0eb")], "bindings": [
            {"remote_id": "bb30e0eb", "entity_id": "light.one"},
            {"remote_id": "bb30e0eb", "entity_id": "light.two"},
        ]}))
        assert any("only the first runs" in p for p in out["problems"])

    def test_a_binding_with_no_remote_is_reported(self):
        out = report(Entry({"remotes": [remote("Strip", remote_id="bb30e0eb")],
                            "bindings": [{"remote_id": "gone", "entity_id": "light.old"}]}))
        assert any("no remote" in p for p in out["problems"])
        assert out["bindings"][0]["orphan"] is True

    def test_the_buttons_a_binding_covers_are_listed(self):
        out = report(Entry({"remotes": [remote("Strip", remote_id="bb30e0eb")], "bindings": [
            {"remote_id": "bb30e0eb", "button_actions": {"p0_k5": [{}], "p0_k4": [{}]}},
        ]}))
        assert out["bindings"][0]["buttons"] == ["p0_k4", "p0_k5"]

    def test_a_healthy_pair_reports_nothing(self):
        out = report(Entry({"remotes": [
            remote("Strip", remote_id="bb30e0eb", device_id="8A881BE01F92"),
            remote("Ambience", remote_id="6091fad4", device_id="DA7116E01F92"),
        ], "bindings": [
            {"remote_id": "bb30e0eb", "entity_id": "light.hall", "mappings": {"p0_k4": "turn_on"}},
            {"remote_id": "6091fad4", "button_actions": {"p0_k5": [{}]}},
        ]}))
        assert out["problems"] == []


class TestJunk:
    def test_entries_that_are_not_dicts_are_skipped(self):
        out = report(Entry({"remotes": ["nonsense", None], "bindings": ["also nonsense"]}))
        assert out["remotes"] == [] and out["bindings"] == []

    def test_nothing_configured_at_all(self):
        out = report(Entry({}))
        assert out == {"remotes": [], "bindings": [], "problems": []}
