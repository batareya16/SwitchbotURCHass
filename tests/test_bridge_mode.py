"""Tests for choosing between the single-address and multi-address paths.

The add-on now decides this itself rather than being told by an option, so the decision has to
be right for a Bluetooth 4 radio, a Bluetooth 5 one, a hand-pinned list and a list that no
longer fits — all without a radio present.
"""
import pytest

from conftest import ADDON, load

pytestmark = pytest.mark.skipif(
    not (ADDON / "hci_multi.py").is_file(),
    reason="the bridge add-on is published as its own repository and is not checked out here",
)

hci = load(ADDON / "hci_multi.py", "urc_hci_multi") if (ADDON / "hci_multi.py").is_file() else None

OWN = "8A:88:1B:E0:1F:92"
SECOND = "DA:71:16:E0:1F:92"
THIRD = "C0:88:1B:E0:1F:92"


class TestBluetooth4:
    def test_serves_only_its_own_address(self):
        multi, addresses, why = hci.plan_mode(False, 5, OWN, [], [])
        assert multi is False
        assert addresses == [OWN]
        assert "extended advertising" in why

    def test_says_so_when_more_were_configured(self):
        multi, addresses, why = hci.plan_mode(False, 5, OWN, [OWN, SECOND], [])
        assert multi is False
        assert addresses == [OWN]
        assert "can only ever serve one" in why

    def test_a_single_configured_address_is_not_a_complaint(self):
        _multi, _addresses, why = hci.plan_mode(False, 5, OWN, [OWN], [])
        assert "can only ever serve one" not in why


class TestBluetooth5:
    def test_its_own_address_alone_is_enough_to_start(self):
        multi, addresses, _why = hci.plan_mode(True, 4, OWN, [], [])
        assert multi is True
        assert addresses == [OWN]

    def test_addresses_added_at_run_time_come_back(self):
        multi, addresses, _why = hci.plan_mode(True, 4, OWN, [], [SECOND])
        assert multi is True
        assert addresses == [OWN, SECOND]

    def test_a_pinned_list_is_honoured(self):
        _multi, addresses, _why = hci.plan_mode(True, 4, OWN, [SECOND, THIRD], [])
        assert addresses == [OWN, SECOND, THIRD]

    def test_the_controller_s_own_address_always_comes_first(self):
        # Tiles bound before any of this existed point at it, so it must never be dropped.
        _multi, addresses, _why = hci.plan_mode(True, 4, OWN, [SECOND], [THIRD])
        assert addresses[0] == OWN

    def test_duplicates_across_the_sources_are_collapsed(self):
        _multi, addresses, _why = hci.plan_mode(
            True, 4, OWN, ["8a881be01f92", SECOND], ["DA-71-16-E0-1F-92"])
        assert addresses == [OWN, SECOND]

    def test_rubbish_in_the_option_is_ignored(self):
        _multi, addresses, _why = hci.plan_mode(True, 4, OWN, ["", "nonsense", SECOND], [])
        assert addresses == [OWN, SECOND]


class TestMoreAddressesThanSets:
    def test_keeps_what_fits_and_names_what_does_not(self):
        multi, addresses, why = hci.plan_mode(True, 2, OWN, [SECOND, THIRD], [])
        assert multi is True
        assert addresses == [OWN, SECOND]
        assert THIRD in why
        assert "cannot be served" in why

    def test_never_drops_the_controller_s_own_address(self):
        _multi, addresses, _why = hci.plan_mode(True, 1, OWN, [SECOND, THIRD], [])
        assert addresses == [OWN]


class TestNothingUsable:
    def test_no_address_at_all_means_no_multi_address(self):
        multi, addresses, why = hci.plan_mode(True, 4, "", [], [])
        assert multi is False
        assert addresses == []
        assert "no usable address" in why
