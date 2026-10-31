"""Tests for the pieces the raw-HCI bridge had to implement itself.

Taking the controller on the HCI user channel detaches the kernel's Bluetooth stack, so ACL
fragmentation, L2CAP framing and session handling became this add-on's problem. They are only
exercised by a real remote otherwise, which makes them exactly the parts worth pinning down.
"""
import struct

import pytest

from conftest import ADDON, load

pytestmark = pytest.mark.skipif(
    not (ADDON / "hci_multi.py").is_file(),
    reason="the bridge add-on is published as its own repository and is not checked out here",
)

hci = (
    load(ADDON / "hci_multi.py", "urc_hci_multi")
    if (ADDON / "hci_multi.py").is_file() else None
)


class TestAdvertisement:
    def test_fits_a_legacy_packet(self):
        assert len(hci.advertisement_for("DA:71:16:E0:1F:92", 6, 0x50)) == 31

    def test_carries_the_set_s_own_address(self):
        payload = hci.advertisement_for("DA:71:16:E0:1F:92", 6, 0x50)
        assert bytes.fromhex("DA7116E01F92") in payload

    def test_each_address_gets_a_different_payload(self):
        first = hci.advertisement_for("DA:71:16:E0:1F:92", 6, 0x50)
        second = hci.advertisement_for("8A:88:1B:E0:1F:92", 6, 0x50)
        assert first != second

    def test_structures_tile_the_payload_exactly(self):
        payload = hci.advertisement_for("DA:71:16:E0:1F:92", 6, 0x50)
        offset, kinds = 0, []
        while offset < len(payload):
            kinds.append(payload[offset + 1])
            offset += 1 + payload[offset]
        assert offset == len(payload), "a scanner would read past the end"
        # Flags, manufacturer data, FD3D service data, connection interval range.
        assert kinds == [0x01, 0xFF, 0x16, 0x12]

    def test_the_address_goes_on_the_wire_little_endian(self):
        assert hci.address_bytes("DA:71:16:E0:1F:92") == bytes.fromhex("921FE01671DA")

    def test_refuses_an_address_that_is_not_six_bytes(self):
        with pytest.raises(ValueError):
            hci.address_bytes("DA:71:16")


class FakeSocket:
    def __init__(self):
        self.sent = []

    def send(self, data):
        self.sent.append(data)


class FakeChannel:
    def __init__(self):
        self.sock = FakeSocket()

    def events(self, _timeout):
        return iter(())


def att_frame(payload, cid=None):
    return struct.pack("<HH", len(payload), cid if cid is not None else hci.ATT_CID) + payload


class TestAclFragmentation:
    def test_a_small_pdu_is_one_packet(self):
        writer = hci.AclWriter(FakeChannel(), 27, 4)
        writer.send(0x18, b"\x13")
        assert len(writer.channel.sock.sent) == 1

    def test_a_large_pdu_is_split_and_flagged(self):
        writer = hci.AclWriter(FakeChannel(), 27, 8)
        writer.send(0x18, bytes(range(60)))
        packets = writer.channel.sock.sent
        assert len(packets) == 3
        for index, packet in enumerate(packets):
            assert packet[0] == hci.HCI_ACL_PKT
            header, length = struct.unpack_from("<HH", packet, 1)
            assert header & 0x0FFF == 0x18
            assert (header >> 12) & 0x03 == (hci.PB_FIRST if index == 0 else hci.PB_CONTINUE)
            assert length == len(packet) - 5

    def test_the_fragments_rebuild_the_original(self):
        writer = hci.AclWriter(FakeChannel(), 27, 8)
        writer.send(0x18, bytes(range(60)))
        rebuilt = b"".join(packet[5:] for packet in writer.channel.sock.sent)
        length, cid = struct.unpack_from("<HH", rebuilt)
        assert (length, cid) == (60, hci.ATT_CID)
        assert rebuilt[4:] == bytes(range(60))

    def test_credits_are_counted(self):
        writer = hci.AclWriter(FakeChannel(), 27, 2)
        writer.send(0x18, b"\x13")
        assert writer.inflight == 1
        writer.completed(1)
        assert writer.inflight == 0

    def test_completed_never_goes_below_zero(self):
        writer = hci.AclWriter(FakeChannel(), 27, 2)
        writer.completed(5)
        assert writer.inflight == 0

    def test_a_tiny_payload_size_is_raised_to_the_le_minimum(self):
        assert hci.AclWriter(FakeChannel(), 1, 1).payload_size == 27


class TestReassembly:
    def link(self):
        return hci.Link(0x18, "DA:71:16:E0:1F:92", protocol=None, device=None)

    def test_one_packet_one_pdu(self):
        assert list(self.link().feed(att_frame(b"\x01\x02"), True)) == [b"\x01\x02"]

    def test_a_pdu_split_across_packets(self):
        frame = att_frame(bytes(range(60)))
        link = self.link()
        out = list(link.feed(frame[:27], True))
        out += list(link.feed(frame[27:54], False))
        out += list(link.feed(frame[54:], False))
        assert out == [bytes(range(60))]

    def test_two_pdus_in_one_packet(self):
        both = att_frame(b"\x01\x02\x03") + att_frame(b"\x04\x05")
        assert list(self.link().feed(both, True)) == [b"\x01\x02\x03", b"\x04\x05"]

    def test_a_frame_on_another_channel_is_skipped_without_losing_the_next(self):
        mixed = att_frame(b"\xaa\xbb", cid=0x0005) + att_frame(b"\x09")
        assert list(self.link().feed(mixed, True)) == [b"\x09"]

    def test_a_new_first_fragment_discards_an_incomplete_one(self):
        link = self.link()
        assert list(link.feed(att_frame(bytes(60))[:10], True)) == []
        assert list(link.feed(att_frame(b"\x09"), True)) == [b"\x09"]

    def test_a_header_split_across_packets(self):
        frame = att_frame(b"\x01\x02\x03")
        link = self.link()
        assert list(link.feed(frame[:2], True)) == []
        assert list(link.feed(frame[2:], False)) == [b"\x01\x02\x03"]


class TestEventMask:
    def test_advertising_set_terminated_is_not_masked_off(self):
        # Without this subevent nothing names the set a connection arrived on, and the whole
        # multi-address feature becomes unobservable.
        bit = hci.LE_ADV_SET_TERMINATED - 1
        assert (hci.LE_EVENT_MASK[bit // 8] >> (bit % 8)) & 1

    def test_connection_events_are_enabled(self):
        for subevent in (hci.LE_CONNECTION_COMPLETE, hci.LE_ENHANCED_CONNECTION_COMPLETE):
            bit = subevent - 1
            assert (hci.LE_EVENT_MASK[bit // 8] >> (bit % 8)) & 1


class TestCommandErrors:
    def test_the_status_survives_for_callers_that_care(self):
        error = hci.HciCommandError(0x203B, hci.STATUS_UNKNOWN_COMMAND)
        assert error.opcode == 0x203B
        assert error.status == hci.STATUS_UNKNOWN_COMMAND
        assert isinstance(error, OSError)
        assert "0x203b" in str(error)
