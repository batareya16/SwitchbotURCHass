"""Encrypted raw-HCI management against a scripted ATT peer, including failure boundaries."""
import struct

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from test_hci_inventory import Peer, PEER, TABLE, hci

pytestmark = pytest.mark.skipif(hci is None, reason="add-on absent")

KEY = bytes.fromhex("00112233445566778899aabbccddeeff")
IV = bytes.fromhex("2cd84b0b02f6115938f43787ced2bd95")
KEY_ID = 0x95


def crypt(key, iv, data):
    cipher = Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor()
    return cipher.update(data) + cipher.finalize()


class ManagementPeer(Peer):
    WRITE_PROPERTIES = 0x0C

    def __init__(self, client, commands=(), replies=None):
        super().__init__(client.handle_pdu)
        self.commands = list(commands)
        self.received = []
        self.buffer = bytearray()
        self.replies = replies or [b"\x01"] * len(self.commands)
        self.handshakes = 0

    def notify(self, raw):
        self.deliver(b"\x1b\x13\x00" + raw)

    def send(self, pdu):
        if pdu[0] != 0x52:
            if pdu[0] == 0x12 and pdu[3:9] == bytes.fromhex("570000000f63"):
                self.sent.append(pdu)
                self.notify(TABLE)
                self.deliver(b"\x13")
                return
            return super().send(pdu)
        self.sent.append(pdu)
        assert pdu[1:3] == b"\x11\x00"
        frame = pdu[3:]
        if frame == bytes([0x57, 0, 0, 0, 0x0F, 0x21, 3, KEY_ID]):
            self.handshakes += 1
            self.notify(bytes([1, 0, 0, 0]) + IV)
            return
        self.buffer.extend(frame)
        index = len(self.received)
        assert index < len(self.commands), "a command was unexpectedly repeated"
        expected = self.commands[index]
        if len(self.buffer) < len(expected) + 4:
            return
        assert self.buffer[:4] == bytes([0x57, KEY_ID]) + IV[:2]
        assert crypt(KEY, IV, bytes(self.buffer[4:])) == expected
        self.buffer.clear()
        self.received.append(expected)
        # A stale session and a periodic status must not consume the real command reply.
        self.notify(bytes([1, KEY_ID, 0xAA, 0xBB, 1]))
        status = bytes.fromhex("3c2d01010132320f00010001002d2d01")
        self.notify(bytes([1, KEY_ID]) + IV[:2] + crypt(KEY, IV, status))
        reply = self.replies[index]
        if reply is not None:
            self.notify(bytes([1, KEY_ID]) + IV[:2] + crypt(KEY, IV, reply))


def connected_client(commands=(), replies=None):
    client = hci.AttManagementClient(PEER, None)
    peer = ManagementPeer(client, commands, replies)
    client.send = peer.send
    return client, peer


def test_set_key_associate_and_large_bind_share_one_handshake():
    commands = [bytes.fromhex("0f200901") + KEY,
                bytes.fromhex("0f2008011271da7d1a000000000000"),
                b"\x0f\x62\x06" + bytes(range(245)) * 3]
    client, peer = connected_client(commands)
    result = client.execute_steps(KEY, KEY_ID, [
        {"kind": "command", "plaintext": command.hex(), "accepted_codes": [1]}
        for command in commands], crypt)
    assert result["ok"] and result["strict_accepted_codes"]
    assert result["responses"] == ["01", "01", "01"]
    assert peer.received == commands and peer.handshakes == 1
    chunks = [pdu[3:] for pdu in peer.sent if pdu[0] == 0x52]
    assert len(chunks[-2]) == 509
    assert len(chunks[-1]) == len(commands[-1]) + 4 - 509


def test_delete_then_verify_table_runs_in_same_session():
    delete = bytes.fromhex("0f6204020372001571da7d1a000000000000")
    client, peer = connected_client([delete])
    result = client.execute_steps(KEY, KEY_ID, [
        {"kind": "query", "subcmd": 7},
        {"kind": "command", "plaintext": delete.hex(), "accepted_codes": [1]},
        {"kind": "query", "subcmd": 7}], crypt)
    assert result["responses"] == [TABLE.hex(), "01", TABLE.hex()]
    assert peer.received == [delete] and peer.handshakes == 1


def test_rejection_stops_every_later_command():
    first, second = b"\x0f\x62\x06\x01", b"\x0f\x62\x06\x02"
    client, peer = connected_client([first, second], [b"\x04", b"\x01"])
    with pytest.raises(RuntimeError, match="step 1 rejected"):
        client.execute_steps(KEY, KEY_ID, [
            {"kind": "command", "plaintext": command.hex(), "accepted_codes": [1]}
            for command in [first, second]], crypt)
    assert client.responses == ["04"]
    assert peer.received == [first]


def test_lost_ack_is_never_resent():
    command = b"\x0f\x62\x04\x02"
    client, peer = connected_client([command], [None])
    with pytest.raises(TimeoutError):
        client.execute_steps(KEY, KEY_ID, [{"kind": "command", "plaintext": command.hex(),
                                            "timeout": 0.001}], crypt)
    assert peer.received == [command]
    assert client.command_started and not client.responses


def test_empty_capability_probe_does_handshake_without_mutation():
    client, peer = connected_client()
    result = client.execute_steps(KEY, KEY_ID, [], crypt)
    assert result["strict_accepted_codes"] and result["responses"] == []
    assert peer.handshakes == 1 and not client.command_started


def test_all_queries_skip_handshake_and_support_other_subcommands():
    client, peer = connected_client()
    result = client.execute_steps(KEY, KEY_ID, [
        {"kind": "query", "subcmd": 4}, {"kind": "query", "subcmd": 6}], crypt)
    assert result["responses"] == [TABLE.hex(), TABLE.hex()]
    assert not peer.handshakes and not client.command_started


def test_status_poll_accepts_the_status_record():
    client, peer = connected_client([b"\x02"])
    result = client.execute_steps(KEY, KEY_ID, [{"kind": "command", "plaintext": "02"}], crypt)
    assert result["responses"] == ["3c2d01010132320f00010001002d2d01"]


def test_four_byte_envelope_ack_is_supported():
    client, peer = connected_client([b"\x0f\x62\x04\x02"], [b""])
    result = client.execute_steps(KEY, KEY_ID, [{"kind": "command", "plaintext": "0f620402"}], crypt)
    assert result["responses"] == ["01"]


def test_frame_chunking_uses_negotiated_mtu_instead_of_assuming_512():
    command = bytes(range(120))
    client, peer = connected_client([command])
    def send(pdu):
        if pdu == b"\x02\x00\x02":
            client.handle_pdu(b"\x03\x40\x00")
        else:
            peer.send(pdu)
    client.send = send
    result = client.execute_steps(KEY, KEY_ID, [{"kind": "command", "plaintext": command.hex()}], crypt)
    assert result["responses"] == ["01"]
    assert peer.received == [command]
    assert all(len(pdu) <= 64 for pdu in peer.sent)


def test_handshake_rejection_stops_before_any_mutation():
    client, peer = connected_client([b"\x0f\x62\x04\x02"])
    def send(pdu):
        if pdu[0] == 0x52:
            peer.notify(bytes([2, 0, 0, 0]) + IV)
        else:
            peer.send(pdu)
    client.send = send
    with pytest.raises(RuntimeError, match="handshake rejected"):
        client.execute_steps(KEY, KEY_ID, [{"kind": "command", "plaintext": "0f620402"}], crypt)
    assert not client.command_started and not peer.received


@pytest.mark.parametrize("steps", [
    [{"kind": "command", "plaintext": "0f6206"}, {"kind": "query", "subcmd": 256}],
    [{"kind": "command", "plaintext": "zz"}],
    [{"kind": "command", "plaintext": "02", "accepted_codes": []}],
    [{"kind": "command", "plaintext": "02", "timeout": float("nan")}],
    [{"kind": "unexpected"}],
])
def test_whole_transaction_is_validated_before_connecting(steps):
    server = object.__new__(hci.MultiAddressServer)
    result = server.manage_remote(PEER, KEY.hex(), KEY_ID, steps, crypt=crypt)
    assert not result["ok"] and result["failed_stage"] == "validation"


def test_handshake_failure_and_post_write_failure_have_distinct_retry_classification(monkeypatch):
    monkeypatch.setattr(hci, "resolve_adapter", lambda _: ("hci0", 0, "8A:88:1B:E0:1F:92"))
    for wrote, expected in [(False, "handshake"), (True, "command")]:
        server = hci.MultiAddressServer("hci0", ["8A:88:1B:E0:1F:92"],
            protocol_factory=None, device_factory=None, conn_min=6, conn_max=12)
        class Channel:
            def command(self, opcode, payload):
                if opcode == hci.OP_LE_CREATE_CONN:
                    server._central_client.connected.set()
        server.channel = Channel()
        def fail(client):
            client.stage = "handshake" if not wrote else "query_0F6307"
            client.command_started = wrote
            if wrote:
                client.responses = ["01"]
            raise TimeoutError("no response")
        server._close_management = lambda *args: None
        result = server._run_management_session(PEER, fail, report_errors=True)
        assert result["failed_stage"] == expected
        assert result["command_started"] == wrote
        assert result["responses"] == (["01"] if wrote else [])


@pytest.mark.parametrize("ack,ok", [(b"\x01", True), (b"\x04", False), (None, False)])
def test_full_server_transaction_keeps_controller_and_closes_its_link(monkeypatch, ack, ok):
    monkeypatch.setattr(hci, "resolve_adapter", lambda _: ("hci0", 0, "8A:88:1B:E0:1F:92"))
    monkeypatch.setattr(hci, "set_powered", lambda *_: pytest.fail("management released the adapter"))
    server = hci.MultiAddressServer("hci0", ["8A:88:1B:E0:1F:92"],
        protocol_factory=None, device_factory=None, conn_min=6, conn_max=12)
    command = bytes.fromhex("0f6204020372001571da7d1a000000000000")
    commands = []
    peers = []
    class Writer:
        def send(self, handle, pdu):
            assert handle == 24
            peers[0].send(pdu)
        def disconnected(self, handle):
            assert handle == 24
    class Channel:
        def command(self, opcode, payload=b"", **kwargs):
            commands.append(opcode)
            if opcode == hci.OP_LE_CREATE_CONN:
                peers.append(ManagementPeer(server._central_client, [command], [ack]))
                server._on_event(hci.EV_LE_META, bytes([1, 0, 24, 0, 0, 0])
                                 + hci.address_bytes(PEER) + bytes(7))
            elif opcode == hci.OP_DISCONNECT:
                server._on_event(hci.EV_DISCONN_COMPLETE, bytes([0, 24, 0, 0x13]))
            return b""
    server.channel, server.writer = Channel(), Writer()
    result = server.manage_remote(PEER, KEY.hex(), KEY_ID, [{"kind": "command",
        "plaintext": command.hex(), "accepted_codes": [1], "timeout": 0.001}], crypt=crypt)
    assert result["ok"] == ok
    assert result["responses"] == ([] if ack is None else [ack.hex()])
    if not ok:
        assert result["failed_stage"] == "command" and result["command_started"]
    assert peers[0].received == [command]
    assert commands.count(hci.OP_LE_CREATE_CONN) == 1
    assert commands.count(hci.OP_DISCONNECT) == 1
    assert hci.OP_RESET not in commands
    assert server._central_client is None and server._central_link is None


def test_transient_connection_failed_to_be_established_retries_before_writing(monkeypatch):
    monkeypatch.setattr(hci, "resolve_adapter", lambda _: ("hci0", 0, "8A:88:1B:E0:1F:92"))
    delays = []
    monkeypatch.setattr(hci.time, "sleep", delays.append)
    server = hci.MultiAddressServer("hci0", ["8A:88:1B:E0:1F:92"],
        protocol_factory=None, device_factory=None, conn_min=6, conn_max=12)
    command = bytes.fromhex("0f6204020372001571da7d1a000000000000")
    attempts = []
    peers = []

    class Writer:
        def send(self, handle, pdu):
            assert handle == 24
            peers[0].send(pdu)

        def disconnected(self, handle):
            assert handle == 24

    class Channel:
        def command(self, opcode, payload=b"", **kwargs):
            if opcode == hci.OP_LE_CREATE_CONN:
                attempts.append(payload)
                if len(attempts) < 4:
                    server._on_event(hci.EV_LE_META, bytes([1, 0x3e]) + bytes(17))
                else:
                    peers.append(ManagementPeer(server._central_client, [command], [b"\x01"]))
                    server._on_event(hci.EV_LE_META, bytes([1, 0, 24, 0, 0, 0])
                                     + hci.address_bytes(PEER) + bytes(7))
            elif opcode == hci.OP_DISCONNECT:
                server._on_event(hci.EV_DISCONN_COMPLETE, bytes([0, 24, 0, 0x13]))
            return b""

    server.channel, server.writer = Channel(), Writer()
    result = server.manage_remote(PEER, KEY.hex(), KEY_ID, [{
        "kind": "command", "plaintext": command.hex(), "accepted_codes": [1],
    }], crypt=crypt)

    assert result["ok"]
    assert len(attempts) == 4
    assert all(struct.unpack_from("<HH", payload) == (0x0060, 0x0060) for payload in attempts)
    assert delays == [0.15, 0.3, 0.6]
    assert peers[0].received == [command]
    assert server._central_client is None and server._central_link is None


def test_connect_retry_limit_is_bounded_and_leaves_bridge_available(monkeypatch):
    monkeypatch.setattr(hci, "resolve_adapter", lambda _: ("hci0", 0, "8A:88:1B:E0:1F:92"))
    monkeypatch.setattr(hci.time, "sleep", lambda _: None)
    server = hci.MultiAddressServer("hci0", ["8A:88:1B:E0:1F:92"],
        protocol_factory=None, device_factory=None, conn_min=6, conn_max=12)
    attempts = []

    class Channel:
        def command(self, opcode, payload=b"", **kwargs):
            attempts.append(opcode)
            if opcode == hci.OP_LE_CREATE_CONN:
                server._on_event(hci.EV_LE_META, bytes([1, 0x3e]) + bytes(17))
            return b""

    server.channel = Channel()
    result = server.manage_remote(PEER, KEY.hex(), KEY_ID, [{
        "kind": "command", "plaintext": "0f620402", "accepted_codes": [1],
    }], crypt=crypt)

    assert not result["ok"] and result["failed_stage"] == "connect"
    assert attempts.count(hci.OP_LE_CREATE_CONN) == hci.MANAGEMENT_CONNECT_ATTEMPTS
    assert not any(opcode == hci.OP_DISCONNECT for opcode in attempts)
    assert server._central_client is None and server._central_link is None


def test_central_send_preserves_disconnect_reason_for_prewrite_retry(monkeypatch):
    import threading

    monkeypatch.setattr(hci, "resolve_adapter", lambda _: ("hci0", 0, "8A:88:1B:E0:1F:92"))
    server = hci.MultiAddressServer("hci0", ["8A:88:1B:E0:1F:92"],
        protocol_factory=None, device_factory=None, conn_min=6, conn_max=12)
    client = hci.AttManagementClient(PEER, lambda _: None)
    client.handle = 24
    client.fail("central disconnected: 0x3e", disconnected=True)
    server._io_lock = threading.RLock()
    server._central_client = client
    server.writer = object()

    with pytest.raises(ConnectionError, match="central disconnected: 0x3e"):
        server._central_send(client, b"mtu")
