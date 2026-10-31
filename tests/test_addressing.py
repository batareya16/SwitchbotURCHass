"""Tests for the native address allocator.

The allocator decides what Remote Studio offers and what it writes to the remote, so its edge
cases are the ones that would otherwise be found by binding a tile to an address nothing serves.
"""
import pytest

from conftest import INTEGRATION, load

a = load(INTEGRATION / "addressing.py", "urc_addressing")


DONGLE = "8A:88:1B:E0:1F:92"     # the Bluetooth 5 dongle: a public address
BUILTIN = "DC:A6:32:0F:2D:8A"    # the Pi's own radio, no extended advertising


def dongle(sets=4, serving=None):
    # `serving=[]` means "serving nothing", which is not the same as "not specified".
    return a.Bridge(
        "hci0", DONGLE, advertising_sets=sets,
        serving=[DONGLE] if serving is None else list(serving),
    )


def builtin():
    return a.Bridge("hci1", BUILTIN, advertising_sets=5, extended_advertising=False)


class TestAddressForm:
    @pytest.mark.parametrize("value", ["DA:71:16:E0:1F:92", "da7116e01f92", "DA-71-16-E0-1F-92"])
    def test_accepts_every_separator_and_case(self, value):
        assert a.is_valid(value)

    @pytest.mark.parametrize("value", ["", "DA:71:16", "ZZ:71:16:E0:1F:92", "DA:71:16:E0:1F:92:AA"])
    def test_refuses_malformed(self, value):
        assert not a.is_valid(value)

    def test_static_random_needs_the_top_two_bits_set(self):
        assert a.is_static_random("C0:00:00:00:00:01")
        assert a.is_static_random("FF:FF:FF:FF:FF:FF")
        # 8A is 10xxxxxx, the reserved combination: a public address, not a random one.
        assert not a.is_static_random(DONGLE)
        assert not a.is_static_random("3F:00:00:00:00:01")   # 00 = non-resolvable private
        assert not a.is_static_random("7F:00:00:00:00:01")   # 01 = resolvable private

    def test_formats_back_with_colons(self):
        assert a.format_address("da7116e01f92") == "DA:71:16:E0:1F:92"


class TestCandidates:
    def test_own_address_comes_first(self):
        assert dongle().candidates()[0] == DONGLE

    def test_derived_addresses_are_valid_static_random(self):
        derived = dongle().candidates()[1:]
        assert derived, "a Bluetooth 5 controller must offer more than its own address"
        assert all(a.is_static_random(item) for item in derived)

    def test_derived_addresses_keep_the_controller_s_lower_octets(self):
        for item in dongle().candidates()[1:]:
            assert item[3:] == DONGLE[3:]

    def test_candidates_are_unique(self):
        items = dongle().candidates()
        assert len(items) == len(set(items))

    def test_a_controller_without_extended_advertising_offers_only_its_own(self):
        assert builtin().candidates() == [BUILTIN]


class TestCapacity:
    def test_capacity_is_the_number_of_advertising_sets(self):
        assert dongle(sets=4).capacity == 4

    def test_without_extended_advertising_capacity_is_one(self):
        # The kernel reports five manageable instances, but they all carry one address.
        assert builtin().capacity == 1

    def test_capacity_is_summed_across_controllers(self):
        assert a.capacity([dongle(sets=4), builtin()]) == 5

    def test_free_slots_counts_what_is_already_bound(self):
        assert a.free_slots([dongle(sets=4)], [DONGLE]) == 3
        assert a.free_slots([dongle(sets=4)], [DONGLE, "C0:88:1B:E0:1F:92"]) == 2

    def test_free_slots_never_goes_negative(self):
        used = [DONGLE] + [f"C{index:X}:88:1B:E0:1F:92" for index in range(8)]
        assert a.free_slots([dongle(sets=4)], used) == 0

    def test_one_controller_does_not_lend_capacity_to_another(self):
        # The dongle is full; the built-in radio still has its own single address free.
        used = [DONGLE] + [item for item in dongle().candidates()[1:4]]
        assert a.free_slots([dongle(sets=4), builtin()], used) == 1


class TestAllocate:
    def test_gives_the_first_free_address(self):
        [got] = a.allocate([dongle()], used=[DONGLE])
        assert got.address != DONGLE
        assert a.is_static_random(got.address)
        assert got.bridge.adapter == "hci0"
        assert got.is_new_to_bridge is True

    def test_reuses_the_controller_address_when_nothing_is_bound(self):
        [got] = a.allocate([dongle(serving=[])], used=[])
        assert got.address == DONGLE
        assert got.is_new_to_bridge is True

    def test_marks_an_address_the_bridge_already_serves(self):
        [got] = a.allocate([dongle(serving=[DONGLE])], used=[])
        assert got.address == DONGLE
        assert got.is_new_to_bridge is False

    def test_allocates_several_without_repeating(self):
        got = a.allocate([dongle(sets=4)], used=[DONGLE], count=3)
        assert len({item.address for item in got}) == 3
        assert DONGLE not in {item.address for item in got}

    def test_fills_one_controller_before_starting_the_next(self):
        got = a.allocate([dongle(sets=4), builtin()], used=[], count=5)
        adapters = [item.bridge.adapter for item in got]
        assert adapters == ["hci0"] * 4 + ["hci1"]
        assert got[-1].address == BUILTIN

    def test_the_five_remote_split_the_user_asked_about(self):
        # Four on the dongle and one on the second adapter.
        got = a.allocate([dongle(sets=4), builtin()], used=[], count=5)
        assert sum(1 for item in got if item.bridge.adapter == "hci0") == 4
        assert sum(1 for item in got if item.bridge.adapter == "hci1") == 1

    def test_refuses_beyond_capacity_and_says_how_many_fit(self):
        with pytest.raises(ValueError) as err:
            a.allocate([dongle(sets=4)], used=[DONGLE], count=4)
        assert "Only 3" in str(err.value)
        assert "another Bluetooth adapter" in str(err.value)

    def test_refuses_when_everything_is_taken(self):
        used = [DONGLE] + [item for item in dongle().candidates()[1:4]]
        with pytest.raises(ValueError) as err:
            a.allocate([dongle(sets=4)], used=used)
        assert "Only 0" in str(err.value)

    def test_refuses_a_nonsensical_count(self):
        with pytest.raises(ValueError):
            a.allocate([dongle()], used=[], count=0)

    def test_used_addresses_match_whatever_the_separator(self):
        [got] = a.allocate([dongle()], used=["8a881be01f92"])
        assert got.address != DONGLE

    def test_no_bridges_at_all(self):
        with pytest.raises(ValueError) as err:
            a.allocate([], used=[])
        assert "0 controller(s)" in str(err.value)


class TestDescribe:
    def test_says_nothing_is_set_up(self):
        assert "No native bridge" in a.describe([], [])

    def test_counts_what_is_left(self):
        text = a.describe([dongle(sets=4)], [DONGLE])
        assert "3 more native remote(s) fit" in text
        assert "hci0 holds 1 of 4" in text

    def test_explains_a_controller_without_bluetooth_5(self):
        assert "no Bluetooth 5" in a.describe([builtin()], [])


class TestRealWorldShapes:
    """Shapes that actually occur once a second address is in use."""

    def test_a_derived_address_is_the_controller_s_capacity_not_a_new_controller(self):
        # DA:71:16:… is served by the dongle; it must not look like another adapter.
        # The address is not one this code would derive — it was configured by hand — so only
        # what the add-on reports it is serving can tell us whose capacity it uses.
        bridge = dongle(sets=4, serving=[DONGLE, "DA:71:16:E0:1F:92"])
        assert "DA:71:16:E0:1F:92" not in bridge.candidates()
        assert a.free_slots([bridge], [DONGLE, "DA:71:16:E0:1F:92"]) == 2

    def test_capacity_does_not_grow_when_a_second_address_is_bound(self):
        bridge = dongle(sets=4)
        before = a.capacity([bridge])
        bridge.serving = [DONGLE, "DA:71:16:E0:1F:92"]
        assert a.capacity([bridge]) == before

    def test_five_remotes_over_two_dongles(self):
        second = a.Bridge("hci2", "C4:11:22:33:44:55", advertising_sets=4, serving=[])
        got = a.allocate([dongle(sets=4), second], used=[], count=5)
        assert [item.bridge.adapter for item in got] == ["hci0"] * 4 + ["hci2"]
        assert len({item.address for item in got}) == 5


    def test_a_hand_picked_address_still_counts_against_its_controller(self):
        bridge = dongle(sets=4, serving=[DONGLE, "DA:71:16:E0:1F:92"])
        assert a.describe([bridge], [DONGLE, "DA:71:16:E0:1F:92"]).startswith("2 more")

    def test_allocation_skips_past_a_hand_picked_address(self):
        bridge = dongle(sets=4, serving=[DONGLE, "DA:71:16:E0:1F:92"])
        got = a.allocate([bridge], used=[DONGLE, "DA:71:16:E0:1F:92"], count=2)
        assert len(got) == 2
        with pytest.raises(ValueError):
            a.allocate([bridge], used=[DONGLE, "DA:71:16:E0:1F:92"], count=3)


class TestMoving:
    """Re-pointing a tile at another address, which is how a replaced dongle is recovered."""

    def test_releasing_an_address_frees_it(self):
        assert a.without([DONGLE, "C0:88:1B:E0:1F:92"], "c0881be01f92") == [DONGLE]

    def test_releasing_ignores_separators_and_case(self):
        assert a.without(["DA:71:16:E0:1F:92"], "da-71-16-e0-1f-92") == []

    def test_releasing_an_address_that_is_not_there_changes_nothing(self):
        used = [DONGLE]
        assert a.without(used, "AA:BB:CC:DD:EE:FF") == used

    def test_a_tile_on_a_full_controller_can_still_move(self):
        bridge = dongle(sets=2)
        used = [DONGLE, "C0:88:1B:E0:1F:92"]
        # Full, so nothing new fits...
        with pytest.raises(ValueError):
            a.allocate([bridge], used)
        # ...but the tile leaving DONGLE frees it, so its own move is possible.
        [got] = a.allocate([bridge], a.without(used, DONGLE))
        assert got.address == DONGLE

    def test_moving_onto_a_replacement_controller(self):
        # The dongle was swapped: a new controller address, and the old tile must follow it.
        replacement = a.Bridge("hci0", "C4:11:22:33:44:55", advertising_sets=4, serving=[])
        [got] = a.allocate([replacement], a.without([DONGLE], DONGLE))
        assert got.address == "C4:11:22:33:44:55"
        assert got.bridge.adapter == "hci0"

    def test_a_move_does_not_pick_an_address_another_tile_holds(self):
        bridge = dongle(sets=4)
        used = [DONGLE, "C0:88:1B:E0:1F:92", "C1:88:1B:E0:1F:92"]
        [got] = a.allocate([bridge], a.without(used, DONGLE))
        assert got.address not in {"C0:88:1B:E0:1F:92", "C1:88:1B:E0:1F:92"}
