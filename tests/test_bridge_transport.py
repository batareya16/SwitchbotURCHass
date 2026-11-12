"""Tests for the pieces the raw-HCI bridge had to implement itself.

Taking the controller on the HCI user channel detaches the kernel's Bluetooth stack, so ACL
fragmentation, L2CAP framing and session handling became this add-on's problem. They are only
exercised by a real remote otherwise, which makes them exactly the parts worth pinning down.
"""
import struct
import threading

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
        writer.completed(0x18, 1)
        assert writer.inflight == 0

    def test_completed_never_goes_below_zero(self):
        writer = hci.AclWriter(FakeChannel(), 27, 2)
        writer.completed(0x18, 5)
        assert writer.inflight == 0

    def test_a_tiny_payload_size_is_raised_to_the_le_minimum(self):
        assert hci.AclWriter(FakeChannel(), 1, 1).payload_size == 27

    def test_buffer_exhaustion_queues_fragments_until_completion(self):
        writer = hci.AclWriter(FakeChannel(), 27, 1)
        writer.send(0x18, bytes(range(60)))
        assert len(writer.channel.sock.sent) == 1
        assert len(writer.pending) == 2
        writer.completed(0x18, 1)
        assert len(writer.channel.sock.sent) == 2
        writer.completed(0x18, 1)
        assert len(writer.channel.sock.sent) == 3
        assert writer.inflight == 1

    def test_disconnect_discards_old_fragments_and_releases_buffers(self):
        writer = hci.AclWriter(FakeChannel(), 27, 1)
        writer.send(0x18, bytes(range(60)))
        writer.send(0x19, b"\x13")
        writer.disconnected(0x18)
        assert writer.inflight == 1
        assert not writer.pending
        last_header = struct.unpack_from("<H", writer.channel.sock.sent[-1], 1)[0]
        assert last_header & 0xFFF == 0x19

    def test_late_completion_from_disconnected_handle_cannot_free_another_s_buffers(self):
        writer = hci.AclWriter(FakeChannel(), 27, 1)
        writer.send(0x18, b"old")
        writer.disconnected(0x18)
        writer.send(0x19, b"first")
        writer.send(0x19, b"second")
        writer.completed(0x18, 8)
        assert len(writer.channel.sock.sent) == 2
        assert len(writer.pending) == 1


def event_packet(code, params):
    return hci.HCI_EVENT_PKT, bytes([code, len(params)]) + params


class TestCommandInterleaving:
    def test_acl_and_connection_events_survive_a_command(self):
        channel = object.__new__(hci.UserChannel)
        channel.sock = FakeSocket()
        channel.spare = []
        opcode = hci.OP_LE_SET_EXT_ADV_ENABLE
        acl = (hci.HCI_ACL_PKT, b"queued press")
        connected = event_packet(hci.EV_LE_META, bytes([1, 0, 24, 0, 1, 0]) + bytes(12))
        disconnected = event_packet(hci.EV_DISCONN_COMPLETE, bytes([0, 25, 0, 0x13]))
        credits = event_packet(hci.EV_NUM_COMPLETED_PACKETS, bytes([1, 24, 0, 1, 0]))
        reply = event_packet(hci.EV_CMD_COMPLETE, struct.pack("<BHB", 1, opcode, 0))
        packets = iter([acl, connected, disconnected, credits, reply])
        channel._receive = lambda timeout: next(packets)
        assert channel.command(opcode) == b""
        assert [channel.read(0) for _ in range(4)] == [acl, connected, disconnected, credits]

    def test_error_reply_does_not_discard_a_press(self):
        channel = object.__new__(hci.UserChannel)
        channel.sock = FakeSocket()
        channel.spare = []
        opcode = hci.OP_LE_SET_EXT_ADV_ENABLE
        acl = (hci.HCI_ACL_PKT, b"press")
        reply = event_packet(hci.EV_CMD_STATUS, struct.pack("<BBH", 0x0C, 1, opcode))
        packets = iter([acl, reply])
        channel._receive = lambda timeout: next(packets)
        with pytest.raises(hci.HciCommandError):
            channel.command(opcode)
        assert channel.read(0) == acl


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(hci, "resolve_adapter", lambda _: ("hci0", 0, "8A:88:1B:E0:1F:92"))
    class Protocol:
        def __init__(self, callback):
            pass
        def begin_session(self):
            pass
        def notify(self, data):
            pass
        def session_summary(self):
            return "test"
    result = hci.MultiAddressServer(
        "hci0", ["8A:88:1B:E0:1F:92", "DA:71:16:E0:1F:92"],
        protocol_factory=Protocol, device_factory=lambda *_: None, conn_min=6, conn_max=12)
    result.writer = hci.AclWriter(FakeChannel(), 27, 8)
    result.own_public = result.addresses[0]
    result.advertising_sets = 4
    return result


def connected(server, handle):
    server._on_event(hci.EV_LE_META, bytes([1, 0]) + struct.pack("<H", handle)
                     + bytes([1, 0]) + bytes(12))


def named_set(server, handle, adv_handle):
    server._on_event(hci.EV_LE_META, bytes([0x12, 0, adv_handle])
                     + struct.pack("<H", handle) + b"\x00")


class TestConnectionIdentity:
    def test_interleaved_events_name_only_their_own_connection(self, server):
        named_set(server, 24, 0)
        connected(server, 25)
        assert server.links[25].address == "?"
        connected(server, 24)
        named_set(server, 25, 1)
        assert server.links[24].address == server.addresses[0]
        assert server.links[25].address == server.addresses[1]

    def test_reused_handle_does_not_inherit_an_old_target(self, server):
        connected(server, 24)
        named_set(server, 24, 1)
        server._on_event(hci.EV_DISCONN_COMPLETE, bytes([0, 24, 0, 0x13]))
        connected(server, 24)
        assert server.links[24].address == "?"

    def test_appending_a_target_does_not_reconfigure_connected_sets(self, server):
        connected(server, 24)
        named_set(server, 24, 0)
        configured = []
        server._configure_set = lambda handle, address: configured.append((handle, address))
        class Channel:
            spare = []
            def command(self, *args):
                return b""
        server.channel = Channel()
        added = "DA:71:17:E0:1F:92"
        server.set_addresses([*server.addresses, added])
        assert configured == [(2, added)]

    def test_connected_target_cannot_be_reordered(self, server):
        connected(server, 24)
        named_set(server, 24, 0)
        class Channel:
            spare = []
        server.channel = Channel()
        with pytest.raises(RuntimeError, match="connected target"):
            server.set_addresses(list(reversed(server.addresses)))


class TestControllerOwnership:
    def test_failed_initialisation_returns_controller_to_bluez(self, server, monkeypatch):
        powered = []
        monkeypatch.setattr(hci, "set_powered", lambda index, value: powered.append(value) or "ok")
        class Channel:
            closed = False
            def command(self, opcode, *args, **kwargs):
                if opcode == hci.OP_RESET:
                    raise TimeoutError("reset failed")
            def close(self):
                self.closed = True
        channel = Channel()
        monkeypatch.setattr(hci, "UserChannel", lambda _: channel)
        with pytest.raises(TimeoutError, match="reset failed"):
            server._claim()
        assert powered == [False, True]
        assert channel.closed
        assert server.channel is None

    def test_pause_waits_until_the_event_loop_finishes_reading(self, server, monkeypatch):
        reading, allow_read, pausing, powered = (threading.Event() for _ in range(4))
        monkeypatch.setattr(hci, "set_powered", lambda *_: powered.set() or "ok")
        class Channel:
            def read(self, timeout):
                reading.set()
                assert allow_read.wait(2)
            def command(self, *args, **kwargs):
                pass
            def close(self):
                pass
        server.channel = Channel()
        def read():
            with server._io_lock:
                server._serve_once()
        def pause():
            pausing.set()
            server.pause()
        reader = threading.Thread(target=read)
        control = threading.Thread(target=pause)
        reader.start()
        assert reading.wait(2)
        control.start()
        assert pausing.wait(2)
        try:
            assert not powered.wait(0.03), "controller released while another thread was reading it"
        finally:
            allow_read.set()
            reader.join(2)
            control.join(2)
        assert not reader.is_alive() and not control.is_alive()
        assert powered.is_set()
        assert server.channel is None


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


class TestAddressFormatting:
    """`set_addresses` formats every address it is given, so this must exist and be right."""

    @pytest.mark.parametrize("written", [
        "DA:71:16:E0:1F:92", "da7116e01f92", "DA-71-16-E0-1F-92", "da:71:16:e0:1f:92",
    ])
    def test_every_form_normalises_to_one(self, written):
        assert hci.format_address(written) == "DA:71:16:E0:1F:92"

    def test_round_trips_through_the_wire_order(self):
        formatted = hci.format_address("da7116e01f92")
        assert hci.address_bytes(formatted) == bytes.fromhex("921FE01671DA")
