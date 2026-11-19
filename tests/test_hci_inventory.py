"""Exercise the raw central reader against a scripted WoRWS ATT peer."""
import struct

import pytest

from conftest import ADDON, load

pytestmark = pytest.mark.skipif(not (ADDON / "hci_multi.py").is_file(), reason="add-on absent")
hci = load(ADDON / "hci_multi.py") if (ADDON / "hci_multi.py").is_file() else None

TABLE = bytes.fromhex("01000000000f1ee00100f3049765819117030000000000")
PEER = "B0:E9:FE:53:11:45"


class Peer:
    WRITE_PROPERTIES = 0x08
    def __init__(self, deliver):
        self.deliver = deliver
        self.sent = []

    def send(self, pdu):
        self.sent.append(pdu)
        if pdu == b"\x02\x00\x02":
            reply = b"\x03\x00\x02"
        elif pdu[0] == 0x08:
            start = struct.unpack_from("<H", pdu, 1)[0]
            if start == 1:
                reply = (b"\x09\x15" + struct.pack("<HBH", 0x10, self.WRITE_PROPERTIES, 0x11)
                         + hci.AttManagementClient.WRITE_UUID
                         + struct.pack("<HBH", 0x12, 0x10, 0x13) + hci.AttManagementClient.NOTIFY_UUID)
            elif start == 0x13:
                reply = b"\x09\x07" + struct.pack("<HBHH", 0x20, 2, 0x21, 0x2A00)
            else:
                reply = b"\x01\x08" + struct.pack("<H", start) + b"\x0a"
        elif pdu[0] == 0x04:
            assert pdu == struct.pack("<BHH", 4, 0x14, 0x1F)
            reply = b"\x05\x01" + struct.pack("<HH", 0x14, 0x2902)
        elif pdu == struct.pack("<BHH", 0x12, 0x14, 1):
            reply = b"\x13"
        elif pdu == struct.pack("<BH", 0x12, 0x11) + bytes.fromhex("570000000f6307"):
            # The notification can precede the ATT write response.
            self.deliver(b"\x1b\x13\x00" + TABLE)
            reply = b"\x13"
        else:
            raise AssertionError(f"unexpected request: {pdu.hex()}")
        self.deliver(reply)


def test_inventory_discovers_handles_and_accepts_notification_before_write_response():
    client = hci.AttManagementClient(PEER, None)
    peer = Peer(client.handle_pdu)
    client.send = peer.send
    assert client.query([(7, 1)]) == [TABLE.hex()]
    assert all(bytes.fromhex("0f2103") not in pdu for pdu in peer.sent)
    assert peer.sent[-1][3:] == bytes.fromhex("570000000f6307")


@pytest.mark.parametrize(("subcommand", "record_size", "count"), [(4, 67, 10), (5, 80, 7)])
def test_long_read_collects_continuation_notifications(subcommand, record_size, count):
    client = hci.AttManagementClient(PEER, None)
    body = bytes([count]) + bytes(count * record_size)
    frame = b"\x01\x00\x00\x00" + len(body).to_bytes(2, "big") + bytes(2) + body

    class LongReadPeer(Peer):
        def send(self, pdu):
            if pdu[3:] == bytes.fromhex("570000000f63") + bytes([subcommand]):
                self.deliver(b"\x1b\x13\x00" + frame[:509])
                self.deliver(b"\x1b\x13\x00" + frame[509:])
                self.deliver(b"\x13")
            else:
                super().send(pdu)

    client.send = LongReadPeer(client.handle_pdu).send
    assert client.query([(subcommand, 1)]) == [frame.hex()]


def test_concurrent_peer_mtu_request_is_answered_separately():
    client = hci.AttManagementClient(PEER, lambda _: None)
    assert client.handle_pdu(b"\x02\xf7\x00") == b"\x03\x00\x02"
    assert not client.replies


def test_missing_management_characteristics_fails_before_writes():
    client = hci.AttManagementClient(PEER, None)
    sent = []
    def send(pdu):
        sent.append(pdu)
        client.handle_pdu(b"\x03\x00\x02" if pdu[0] == 2 else b"\x01\x08\x01\x00\x0a")
    client.send = send
    with pytest.raises(RuntimeError, match="characteristics"):
        client.query([(7, 1)])
    assert not any(pdu[0] == 0x12 for pdu in sent)


def test_empty_discovery_page_cannot_spin_forever():
    client = hci.AttManagementClient(PEER, None)
    client.send = lambda pdu: client.handle_pdu(b"\x03\x00\x02" if pdu[0] == 2 else b"\x09\x15")
    with pytest.raises(RuntimeError, match="discovery"):
        client.query([(7, 1)])


def test_rejected_subscription_does_not_send_a_query():
    client = hci.AttManagementClient(PEER, None)
    peer = Peer(client.handle_pdu)
    def send(pdu):
        if pdu[0] == 0x12:
            client.handle_pdu(b"\x01\x12\x14\x00\x03")
        else:
            peer.send(pdu)
    client.send = send
    with pytest.raises(RuntimeError, match="rejected"):
        client.query([(7, 1)])
    assert not any(bytes.fromhex("0f6307") in pdu for pdu in peer.sent)


def test_notification_from_another_handle_is_ignored():
    client = hci.AttManagementClient(PEER, None)
    peer = Peer(client.handle_pdu)
    def send(pdu):
        if pdu[0] == 0x12:
            client.handle_pdu(b"\x1b\x55\x00" + TABLE)
        peer.send(pdu)
    client.send = send
    assert client.query([(7, 1)]) == [TABLE.hex()]


def test_disconnect_wakes_waiter_with_a_connection_error():
    client = hci.AttManagementClient(PEER, lambda _: None)
    client.fail("peer disconnected")
    with pytest.raises(ConnectionError, match="peer disconnected"):
        client._wait(client.replies, 5)


def test_server_reads_without_releasing_or_resetting_the_controller(monkeypatch):
    monkeypatch.setattr(hci, "resolve_adapter", lambda _: ("hci0", 0, "8A:88:1B:E0:1F:92"))
    monkeypatch.setattr(hci, "set_powered", lambda *_: pytest.fail("must not release controller"))
    server = hci.MultiAddressServer("hci0", ["8A:88:1B:E0:1F:92"],
                                   protocol_factory=None, device_factory=None, conn_min=6, conn_max=12)
    commands = []
    peer = Peer(lambda pdu: server._central_client.handle_pdu(pdu))
    class Writer:
        def send(self, handle, pdu):
            assert handle == 24
            peer.send(pdu)
        def disconnected(self, handle):
            assert handle == 24
    class Channel:
        def command(self, opcode, payload=b"", **kwargs):
            commands.append((opcode, payload))
            if opcode == hci.OP_LE_CREATE_CONN:
                assert len(payload) == 25
                assert payload[6:12] == hci.address_bytes(PEER)
                # The remote goes silent for seconds while it writes flash; a 4 s link
                # supervision timeout dropped installs with "disconnected: 0x08".
                assert int.from_bytes(payload[19:21], "little") >= 2000
                server._on_event(hci.EV_LE_META, bytes([1, 0, 24, 0, 0, 0])
                                 + hci.address_bytes(PEER) + bytes(7))
            elif opcode == hci.OP_DISCONNECT:
                server._on_event(hci.EV_DISCONN_COMPLETE, bytes([0, 24, 0, 0x13]))
            return b""
    server.channel = Channel()
    server.writer = Writer()
    # A different peripheral connection must survive the entire read.
    peripheral = hci.Link(25, server.addresses[0], None, object())
    server.links[25] = peripheral
    result = server.query_inventory(PEER, [{"kind": "query", "subcmd": 7, "timeout": 1}])
    assert result["responses"] == [TABLE.hex()]
    assert result["transport"] == "raw_hci"
    assert server.links[25] is peripheral
    assert server._central_client is None and server._central_link is None
    assert hci.OP_RESET not in [opcode for opcode, _ in commands]


@pytest.mark.parametrize("steps", [[], [{"kind": "command", "plaintext": "02"}],
                                  [{"kind": "query", "subcmd": 6}]])
def test_server_restricts_raw_management_to_readonly_inventory(steps):
    server = object.__new__(hci.MultiAddressServer)
    with pytest.raises(ValueError, match="only inventory"):
        server.query_inventory(PEER, steps)


def test_late_connection_winning_the_cancel_race_is_disconnected():
    import threading
    server = object.__new__(hci.MultiAddressServer)
    server._io_lock = threading.RLock()
    client = hci.AttManagementClient(PEER, lambda _: None)
    server._central_client = client
    commands = []
    class Channel:
        def command(self, opcode, payload=b""):
            commands.append(opcode)
            if opcode == hci.OP_LE_CREATE_CONN_CANCEL:
                client.handle = 24
                client.connected.set()
                raise hci.HciCommandError(opcode, 0x0C)
            if opcode == hci.OP_DISCONNECT:
                client.fail("disconnected", disconnected=True)
    server.channel = Channel()
    server._close_management(client, True)
    assert commands == [hci.OP_LE_CREATE_CONN_CANCEL, hci.OP_DISCONNECT]
    assert server._central_client is None


def test_cleanup_command_failure_keeps_the_connection_guard():
    import threading
    server = object.__new__(hci.MultiAddressServer)
    server._io_lock = threading.RLock()
    client = hci.AttManagementClient(PEER, lambda _: None)
    client.handle = 24
    server._central_client = client
    class Channel:
        def command(self, *args):
            raise TimeoutError("controller did not acknowledge disconnect")
    server.channel = Channel()
    with pytest.raises(TimeoutError, match="disconnect"):
        server._close_management(client, True)
    assert server._central_client is client
    assert client.closing


def test_protocol_error_does_not_claim_the_radio_connection_is_closed():
    client = hci.AttManagementClient(PEER, lambda _: None)
    for _ in range(65):
        client.handle_pdu(b"\x13")
    assert "unsolicited" in client.error
    assert not client.closed.is_set()
    client.fail("actual disconnect", disconnected=True)
    assert client.closed.is_set()


def test_notification_timeout_names_the_query_stage():
    client = hci.AttManagementClient(PEER, None)
    peer = Peer(client.handle_pdu)
    def send(pdu):
        if pdu[0] == 0x12 and pdu[3:] == bytes.fromhex("570000000f6307"):
            client.handle_pdu(b"\x13")
        else:
            peer.send(pdu)
    client.send = send
    with pytest.raises(TimeoutError, match="query_0F6307"):
        client.query([(7, 0)])


@pytest.mark.parametrize("response", [b"\x05\x01", b"\x05\x03\x14\x00\x02\x29",
                                     b"\x05\x01\x13\x00\x02\x29"])
def test_invalid_descriptor_discovery_is_rejected_before_subscribing(response):
    client = hci.AttManagementClient(PEER, None)
    peer = Peer(client.handle_pdu)
    def send(pdu):
        if pdu[0] == 4:
            client.handle_pdu(response)
        else:
            peer.send(pdu)
    client.send = send
    with pytest.raises(RuntimeError, match="descriptor discovery"):
        client.query([(7, 1)])
    assert not any(pdu[0] == 0x12 for pdu in peer.sent)


def test_indication_is_confirmed_and_delivered_as_notification():
    client = hci.AttManagementClient(PEER, lambda _: None)
    assert client.handle_pdu(b"\x1d\x13\x00" + TABLE) == b"\x1e"
    assert client.notifications.popleft() == (0x13, TABLE)


def test_late_central_connection_is_closed_after_a_failed_cleanup():
    server = object.__new__(hci.MultiAddressServer)
    client = hci.AttManagementClient(PEER, lambda _: None)
    client.closing = True
    server._central_client = client
    server._central_link = None
    server.links = {}
    server._pending_set_addresses = {}
    server.writer = None
    server._enable_frame = b""
    sent = []
    class Channel:
        def command(self, opcode, payload=b""):
            sent.append(opcode)
            if opcode == hci.OP_DISCONNECT:
                server._on_event(hci.EV_DISCONN_COMPLETE, bytes([0, 24, 0, 0x13]))
    server.channel = Channel()
    server._on_event(hci.EV_LE_META, bytes([1, 0, 24, 0, 0, 0])
                     + hci.address_bytes(PEER) + bytes(7))
    assert hci.OP_DISCONNECT in sent
    assert client.closed.is_set()
    assert server._central_client is None and server._central_link is None
    assert not server.links


def test_advertising_rearms_only_after_an_incoming_peripheral_disconnect():
    server = object.__new__(hci.MultiAddressServer)
    server._central_link = None
    server._central_client = None
    server.links = {}
    server._pending_set_addresses = {}
    server._enable_frame = b"\x01\x01\x00\x00\x00\x00"
    commands = []
    class Channel:
        def command(self, opcode, payload=b"", **kwargs):
            commands.append(opcode)
    class Writer:
        def disconnected(self, _handle):
            pass
    class Protocol:
        def session_summary(self):
            return "test"
    server.channel = Channel()
    server.writer = Writer()

    # The add-on's outgoing management link must not trigger an advertising enable.
    client = hci.AttManagementClient(PEER, lambda _: None)
    client.handle = 24
    client.closing = True
    server._central_client = client
    server._central_link = hci.Link(24, PEER, client, None)
    server._on_event(hci.EV_DISCONN_COMPLETE, bytes([0, 24, 0, 0x13]))
    assert hci.OP_LE_SET_EXT_ADV_ENABLE not in commands

    # A remote connected to the fake hub consumes its advertising set, so re-arm it.
    server.links[25] = hci.Link(25, PEER, Protocol(), object())
    server._on_event(hci.EV_DISCONN_COMPLETE, bytes([0, 25, 0, 0x13]))
    assert commands == [hci.OP_LE_SET_EXT_ADV_ENABLE]


def test_connection_guard_refuses_new_query_without_overwriting_old_attempt():
    import threading
    server = object.__new__(hci.MultiAddressServer)
    server._io_lock = threading.RLock()
    server._management_lock = threading.Lock()
    server.channel = object()
    server._central_link = None
    old = hci.AttManagementClient(PEER, lambda _: None)
    old.closing = True
    server._central_client = old
    with pytest.raises(RuntimeError, match="still closing"):
        server.query_inventory(PEER, [{"kind": "query", "subcmd": 7}])
    assert server._central_client is old


def test_acl_routes_inventory_and_button_traffic_to_separate_protocols():
    server = object.__new__(hci.MultiAddressServer)
    client = hci.AttManagementClient(PEER, lambda _: None)
    server._central_link = hci.Link(24, PEER, client, None)
    presses, sent = [], []
    class Peripheral:
        def handle(self, pdu):
            presses.append(pdu)
            return b"\x13"
    class Writer:
        def send(self, handle, pdu):
            sent.append((handle, pdu))
    server.links = {25: hci.Link(25, "DA:71:16:E0:1F:92", Peripheral(), object())}
    server.writer = Writer()
    def receive(handle, pdu):
        l2cap = struct.pack("<HH", len(pdu), hci.ATT_CID) + pdu
        server._on_acl(struct.pack("<HH", handle, len(l2cap)) + l2cap)
    receive(24, b"\x1b\x13\x00" + TABLE)
    receive(25, b"\x12\x03\x00\x57\x0f\x49\x01\x01")
    assert client.notifications.popleft() == (0x13, TABLE)
    assert presses == [b"\x12\x03\x00\x57\x0f\x49\x01\x01"]
    assert sent == [(25, b"\x13")]


def test_controller_refusal_does_not_leave_a_permanent_connection_guard():
    import threading
    server = object.__new__(hci.MultiAddressServer)
    server._io_lock = threading.RLock()
    server._management_lock = threading.Lock()
    server._central_client = None
    server._central_link = None
    server.conn_min, server.conn_max = 6, 12
    commands = []
    class Channel:
        def command(self, opcode, payload=b""):
            commands.append(opcode)
            raise hci.HciCommandError(opcode, 0x0C)
    server.channel = Channel()
    for _ in range(2):
        with pytest.raises(hci.HciCommandError):
            server.query_inventory(PEER, [{"kind": "query", "subcmd": 7}])
        assert server._central_client is None
    assert commands == [hci.OP_LE_CREATE_CONN, hci.OP_LE_CREATE_CONN]


def test_bulk_upload_is_not_throttled_like_a_short_command():
    client = hci.AttManagementClient(PEER, None)
    client.write_handle, client.write_properties, client.mtu = 0x11, 0x04, 23
    sent = []
    client.send = sent.append
    waits = []
    client.closed = types_namespace = type("E", (), {
        "wait": lambda _self, timeout: waits.append(timeout) or False})()
    client.write_frame(bytes(100))
    assert len(sent) == 5 and set(waits) == {hci.AttManagementClient.CHUNK_PAUSE}
    waits.clear()
    sent.clear()
    client.write_frame(bytes(4106))
    assert len(sent) == 206 and len(waits) == 205
    assert set(waits) == {hci.AttManagementClient.BULK_CHUNK_PAUSE}
    assert hci.AttManagementClient.BULK_CHUNK_PAUSE < hci.AttManagementClient.CHUNK_PAUSE
