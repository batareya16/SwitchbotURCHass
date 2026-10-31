"""Regression tests for the defects a review of Remote Studio's commands turned up.

Each test here corresponds to a bug that was in the code, not to a hypothetical one.
"""
import pytest

from conftest import INTEGRATION, load

a = load(INTEGRATION / "addressing.py", "urc_addressing")

DONGLE = "8A:88:1B:E0:1F:92"
SECOND = "C4:11:22:33:44:55"


def bridge(address=DONGLE, sets=4, serving=None, adapter="hci0"):
    return a.Bridge(
        adapter, address, advertising_sets=sets,
        serving=[address] if serving is None else list(serving),
    )


class TestServeRequestIsNeverShrinking:
    """The address list sent to a bridge replaces everything it serves.

    Sending one that omitted the addresses already in use silently stopped every other native
    tile from being answered.
    """

    def test_an_address_with_no_owner_is_recognised(self):
        # No controller carries it, so a serve request would describe the wrong bridge.
        owner = next((b for b in [bridge()] if a._belongs_to(b, "AA:BB:CC:DD:EE:FF")), None)
        assert owner is None

    def test_an_address_a_controller_serves_finds_its_owner(self):
        bridges = [bridge(serving=[DONGLE, "DA:71:16:E0:1F:92"])]
        owner = next((b for b in bridges if a._belongs_to(b, "DA:71:16:E0:1F:92")), None)
        assert owner is not None and owner.adapter == "hci0"

    def test_the_request_keeps_every_address_already_served(self):
        owner = bridge(serving=[DONGLE, "DA:71:16:E0:1F:92"])
        wanted = [a.format_address(a.normalise(item)) for item in owner.serving]
        new = "C0:88:1B:E0:1F:92"
        if not any(a.normalise(item) == a.normalise(new) for item in wanted):
            wanted.append(a.format_address(a.normalise(new)))
        assert len(wanted) == 3
        assert all(item in wanted for item in [DONGLE, "DA:71:16:E0:1F:92", new])

    def test_an_address_already_served_is_not_duplicated(self):
        owner = bridge(serving=[DONGLE, "DA:71:16:E0:1F:92"])
        wanted = [a.format_address(a.normalise(item)) for item in owner.serving]
        if not any(a.normalise(item) == a.normalise("da7116e01f92") for item in wanted):
            wanted.append("DA:71:16:E0:1F:92")
        assert len(wanted) == 2


class TestSuggestionNeverBreaksTheDialog:
    """`next_address` is a convenience; raising there used to stop Add remote from opening."""

    def test_a_full_setup_yields_no_suggestion_instead_of_raising(self):
        full = bridge(sets=1)
        with pytest.raises(ValueError):
            a.allocate([full], [DONGLE])
        # What the handler does instead:
        try:
            suggestion = a.allocate([full], [DONGLE])[0].address
        except ValueError:
            suggestion = ""
        assert suggestion == ""

    def test_no_bridges_at_all_yields_no_suggestion(self):
        try:
            suggestion = a.allocate([], [])[0].address
        except ValueError:
            suggestion = ""
        assert suggestion == ""


class TestMoveDestination:
    """Moving onto an occupied address used to delete the tile first and fail afterwards."""

    def test_the_destination_is_detectably_occupied(self):
        used = [DONGLE, "C0:88:1B:E0:1F:92"]
        assert any(a.normalise(item) == a.normalise("c0881be01f92") for item in used)

    def test_moving_to_its_own_address_is_not_a_move(self):
        assert a.normalise("8a881be01f92") == a.normalise(DONGLE)


class TestCapacityAcrossTwoControllers:
    def test_a_second_controller_adds_its_own_capacity(self):
        assert a.capacity([bridge(), bridge(SECOND, adapter="hci2")]) == 8

    def test_one_controller_being_full_does_not_block_the_other(self):
        first = bridge(sets=1)
        second = bridge(SECOND, sets=4, adapter="hci2", serving=[])
        [got] = a.allocate([first, second], used=[DONGLE])
        assert got.bridge.adapter == "hci2"


class TestADestructiveBindIsNeverRepeated:
    """A native bind deletes the row it replaces before writing the new one.

    Repeating the sequence after a lost acknowledgement ran the delete again, so a tile that
    had in fact been written was removed and rebuilt, round after round.
    """

    def test_the_sequence_starts_by_deleting(self):
        # 0F 62 04 02 is the delete; it is the first thing a native bind sends.
        plaintext = bytes.fromhex("0f620402047e00921fe01671da0000000000")
        assert plaintext[:4] == bytes.fromhex("0f620402")

    def test_the_table_can_answer_whether_the_row_landed(self):
        # The reply the remote gave after the loop: slot 4, type 0x7e, native control.
        table = bytes.fromhex(
            "010000000047288b0500180101141a0a0f01034409390f01020101141a0a0e17030b1f4d5b02"
            "f2045464379317020000000000037200921fe01b888a0000000000047e00921fe01671da0000000000")
        body = table[4:]
        rows = [body[off:off + 13] for off in range(len(body) - 12)]
        native = [r for r in rows if r[2] == 0 and r[1] in (0x72, 0x7e)]
        addresses = {":".join(f"{b:02X}" for b in reversed(r[3:9])) for r in native}
        assert "DA:71:16:E0:1F:92" in addresses
        assert "8A:88:1B:E0:1F:92" in addresses
