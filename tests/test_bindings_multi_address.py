"""Tests that Home Assistant actions stay attached to the right tile across several addresses.

Several native tiles now live on several BLE addresses, and tiles move between addresses and
shift slots when another is deleted. What must survive all of that is the link between a press
and the action somebody bound to it.
"""
import pytest

from conftest import INTEGRATION, load

b = load(INTEGRATION / "bindings.py", "urc_bindings")

WORWS = "B0:E9:FE:53:11:45"
FIRST = "bb30e0eb"    # the tile on the controller's own address
SECOND = "6091fad4"   # the tile on an extended advertising set


def press(remote_id, button_id="p0_k5", slot=3, address=WORWS, **extra):
    return {
        "remote_id": remote_id, "button_id": button_id, "remote_slot": slot,
        "worws_address": address, "button": "OFF", **extra,
    }


def binding(remote_id, actions):
    return {"remote_id": remote_id, "enabled": True, "button_actions": actions}


class TestTilesStayIndependent:
    def test_each_tile_runs_only_its_own_action(self):
        first = binding(FIRST, {"p0_k5": [{"service": "light.turn_on"}]})
        second = binding(SECOND, {"p0_k5": [{"service": "switch.turn_on"}]})
        assert b.resolve_button_action_sequence(first, press(FIRST)) == [
            {"service": "light.turn_on"}]
        assert b.resolve_button_action_sequence(first, press(SECOND)) is None
        assert b.resolve_button_action_sequence(second, press(SECOND)) == [
            {"service": "switch.turn_on"}]

    def test_the_same_button_position_on_two_tiles_does_not_collide(self):
        # Both tiles have a p0_k5; only the remote_id separates them.
        first = binding(FIRST, {"p0_k5": [{"service": "light.toggle"}]})
        assert b.resolve_button_action_sequence(first, press(SECOND, "p0_k5")) is None


class TestMovingAndReordering:
    """A tile keeps its remote_id when it moves address or changes slot."""

    def test_a_different_slot_changes_nothing(self):
        bound = binding(FIRST, {"p0_k5": [{"service": "light.turn_on"}]})
        # Deleting another remote compacts the table, so this tile arrives from slot 2, not 3.
        assert b.resolve_button_action_sequence(bound, press(FIRST, slot=2)) == [
            {"service": "light.turn_on"}]

    def test_nothing_in_the_match_depends_on_the_bridge_address(self):
        bound = binding(FIRST, {"p0_k5": [{"service": "light.turn_on"}]})
        moved = press(FIRST)
        moved["bridge_address"] = "C0:88:1B:E0:1F:92"
        assert b.resolve_button_action_sequence(bound, moved) is not None


class TestWhichIntegrationOwnsThePress:
    def test_a_press_from_this_remote_is_accepted(self):
        assert b.event_matches_remote_address(WORWS, press(FIRST)) is True

    def test_a_press_from_another_remote_is_rejected(self):
        assert b.event_matches_remote_address("AA:BB:CC:DD:EE:FF", press(FIRST)) is False

    def test_the_match_is_on_the_remote_not_the_bridge(self):
        # Two add-on instances serve two controllers but one WoRWS; both must be accepted.
        from_first_bridge = press(FIRST, address=WORWS)
        from_second_bridge = press(SECOND, address=WORWS)
        assert b.event_matches_remote_address(WORWS, from_first_bridge)
        assert b.event_matches_remote_address(WORWS, from_second_bridge)

    @pytest.mark.parametrize("written", ["B0:E9:FE:53:11:45", "b0e9fe531145", "B0-E9-FE-53-11-45"])
    def test_the_address_match_ignores_formatting(self, written):
        assert b.event_matches_remote_address(WORWS, press(FIRST, address=written))

    def test_an_event_without_a_source_is_still_accepted(self):
        # An add-on instance with no remote_address configured sends no source address.
        event = press(FIRST)
        event.pop("worws_address")
        assert b.event_matches_remote_address(WORWS, event) is True


class TestDisabledAndMissing:
    def test_a_disabled_binding_runs_nothing(self):
        bound = binding(FIRST, {"p0_k5": [{"service": "light.turn_on"}]})
        bound["enabled"] = False
        assert b.resolve_button_action_sequence(bound, press(FIRST)) is None

    def test_an_empty_sequence_means_deliberately_silenced(self):
        bound = binding(FIRST, {"p0_k5": []})
        assert b.resolve_button_action_sequence(bound, press(FIRST)) == []

    def test_an_unbound_button_falls_through_to_the_preset(self):
        bound = binding(FIRST, {"p0_k5": [{"service": "light.turn_on"}]})
        assert b.resolve_button_action_sequence(bound, press(FIRST, "p1_k2")) is None


class TestIdentityIsUnique:
    """A binding is matched on remote_id alone, so two tiles must never share one."""

    def test_a_collision_would_merge_two_tiles_actions(self):
        # Why the generator checks: with the same id, one tile's binding answers the other.
        bound = binding(FIRST, {"p0_k5": [{"service": "light.turn_on"}]})
        clash = press(FIRST)          # a different tile that happened to get the same id
        clash["remote_slot"] = 4
        assert b.resolve_button_action_sequence(bound, clash) is not None


class TestOnePressRunsOneAction:
    """Two lights came on from one press: the preset branch acted and kept looking.

    The dispatcher is Home Assistant code, so what is pinned here is the decision it makes for
    each binding — that only the binding belonging to the pressed remote answers, and that a
    second binding for the same remote is an extra, not a second action.
    """

    def test_a_press_matches_only_its_own_remote_s_preset(self):
        first = {"remote_id": FIRST, "enabled": True, "entity_id": "light.one",
                 "mappings": {"p0_k5": "turn_on"}}
        second = {"remote_id": SECOND, "enabled": True, "entity_id": "light.two",
                  "mappings": {"p0_k5": "turn_on"}}
        assert b.resolve_binding_action(second, press(SECOND)) == "turn_on"
        assert b.resolve_binding_action(first, press(SECOND)) is None

    def test_two_bindings_for_one_remote_both_claim_the_press(self):
        # Why the dispatcher keeps only the first: on their own, both say yes.
        one = {"remote_id": FIRST, "enabled": True, "entity_id": "light.one",
               "mappings": {"p0_k5": "turn_on"}}
        two = {"remote_id": FIRST, "enabled": True, "entity_id": "light.two",
               "mappings": {"p0_k5": "turn_on"}}
        assert b.resolve_binding_action(one, press(FIRST)) == "turn_on"
        assert b.resolve_binding_action(two, press(FIRST)) == "turn_on"

    def test_an_override_wins_over_the_preset_on_the_same_remote(self):
        binding_with_both = {
            "remote_id": FIRST, "enabled": True, "entity_id": "light.one",
            "mappings": {"p0_k5": "turn_on"},
            "button_actions": {"p0_k5": [{"action": "scene.turn_on"}]},
        }
        assert b.resolve_button_action_sequence(binding_with_both, press(FIRST)) == [
            {"action": "scene.turn_on"}]

    def test_a_disabled_binding_claims_nothing_either_way(self):
        off = {"remote_id": FIRST, "enabled": False, "entity_id": "light.one",
               "mappings": {"p0_k5": "turn_on"},
               "button_actions": {"p0_k5": [{"action": "scene.turn_on"}]}}
        assert b.resolve_binding_action(off, press(FIRST)) is None
        assert b.resolve_button_action_sequence(off, press(FIRST)) is None


class TestABindingOnlyAnswersItsOwnRemote:
    """Belt and braces for the one thing that must never happen.

    Both resolvers already compare remote ids, so a cross-remote match should be impossible.
    The dispatcher now refuses one anyway and logs it, because "impossible" was the assumption
    being debugged.
    """

    def test_the_resolvers_agree_on_who_owns_a_press(self):
        for binding in (
            {"remote_id": FIRST, "enabled": True, "entity_id": "light.one",
             "mappings": {"p0_k5": "turn_on"}},
            {"remote_id": FIRST, "enabled": True,
             "button_actions": {"p0_k5": [{"action": "light.turn_on"}]}},
        ):
            assert b.resolve_binding_action(binding, press(SECOND)) is None
            assert b.resolve_button_action_sequence(binding, press(SECOND)) is None

    def test_an_empty_remote_id_matches_nothing_real(self):
        orphan = {"remote_id": "", "enabled": True, "entity_id": "light.one",
                  "mappings": {"p0_k5": "turn_on"}}
        assert b.resolve_binding_action(orphan, press(FIRST)) is None

    def test_a_binding_with_both_kinds_still_belongs_to_one_remote(self):
        binding = {"remote_id": FIRST, "enabled": True, "entity_id": "light.one",
                   "mappings": {"p0_k5": "turn_on"},
                   "button_actions": {"p0_k5": [{"action": "scene.turn_on"}]}}
        assert b.resolve_button_action_sequence(binding, press(FIRST)) is not None
        assert b.resolve_button_action_sequence(binding, press(SECOND)) is None
        assert b.resolve_binding_action(binding, press(SECOND)) is None
