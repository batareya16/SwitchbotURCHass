"""Tests for matching an encrypted press to the session it was encrypted with.

The remote asks for several randoms in a row and then sends a frame for each, so the newest
IV is often not the right one. Keeping only the newest dropped real presses; keeping none of
them published noise as a button press. Both were observed on hardware.
"""
import os
import json
import sys
import threading
import types

import pytest

from conftest import ADDON, load

pytestmark = pytest.mark.skipif(
    not (ADDON / "bridge.py").is_file(),
    reason="the bridge add-on is published as its own repository and is not checked out here",
)


@pytest.fixture(scope="module")
def bridge():
    sys.modules.setdefault("paho", types.ModuleType("paho"))
    sys.path.insert(0, str(ADDON))
    os.environ.setdefault("ADAPTER", "hci0")
    try:
        return load(ADDON / "bridge.py", "urc_bridge_module")
    except Exception as err:  # noqa: BLE001
        pytest.skip(f"bridge.py needs more than is available here: {err}")


KEY = bytes.fromhex("00112233445566778899aabbccddeeff")
HANDSHAKE = bytes.fromhex("570000000f210301")
# A real press, from the add-on log: BRIGHTER on the tile with remote_id bb30e0eb.
PRESS = bytes.fromhex("f00306bb30e0eb030008012c")


def device(bridge):
    seen = {"notifies": [], "buttons": []}
    dev = bridge.SwitchBotDevice(
        KEY,
        seen["notifies"].append,
        lambda label, ph, remote_id, slot: seen["buttons"].append((label, remote_id, slot)),
    )
    return dev, seen


def frame(bridge, dev, iv, plain=PRESS):
    return bytes([0x57, 0x01]) + iv[:2] + bridge.aes_ctr(KEY, iv, plain)


class TestPipelinedHandshakes:
    def test_every_random_the_remote_asked_for_is_kept(self, bridge):
        dev, _ = device(bridge)
        for _ in range(4):
            dev.on_write(HANDSHAKE)
        assert len(dev._sessions) == 4

    def test_a_press_from_the_newest_session_arrives(self, bridge):
        dev, seen = device(bridge)
        dev.on_write(HANDSHAKE)
        dev.on_write(frame(bridge, dev, dev._iv))
        assert [b[0] for b in seen["buttons"]] == ["BRIGHTER"]

    def test_a_press_from_an_earlier_session_still_arrives(self, bridge):
        # This is the one that was being dropped: four randoms, then a frame for the second.
        dev, seen = device(bridge)
        for _ in range(4):
            dev.on_write(HANDSHAKE)
        older = list(dev._sessions.values())[1]
        dev.on_write(frame(bridge, dev, older))
        assert [b[0] for b in seen["buttons"]] == ["BRIGHTER"]
        assert seen["buttons"][0][1] == "bb30e0eb"

    def test_each_press_is_acknowledged_in_its_own_session(self, bridge):
        dev, seen = device(bridge)
        for _ in range(3):
            dev.on_write(HANDSHAKE)
        older = list(dev._sessions.values())[0]
        seen["notifies"].clear()
        dev.on_write(frame(bridge, dev, older))
        ack = seen["notifies"][-1]
        # 01 <keyId> <the frame's own nonce> <ciphertext>
        assert ack[2:4] == older[:2]

    def test_the_store_does_not_grow_without_end(self, bridge):
        dev, _ = device(bridge)
        for _ in range(40):
            dev.on_write(HANDSHAKE)
        assert len(dev._sessions) <= 16


class TestFramesThatAreNotPresses:
    def test_a_session_never_issued_is_refused(self, bridge):
        dev, seen = device(bridge)
        dev.on_write(HANDSHAKE)
        # Straight from the log: nonce b150, for a session this connection never handed out.
        dev.on_write(bytes.fromhex("5701b15078cea310c39637db75cd02c0"))
        assert seen["buttons"] == []

    def test_a_frame_that_decrypts_to_nonsense_is_not_published(self, bridge):
        dev, seen = device(bridge)
        dev.on_write(HANDSHAKE)
        # Right session, wrong contents: it cannot be read as a bridge event.
        dev.on_write(frame(bridge, dev, dev._iv, plain=bytes(12)))
        assert seen["buttons"] == []

    def test_a_frame_before_any_handshake_is_refused(self, bridge):
        dev, seen = device(bridge)
        dev.on_write(bytes.fromhex("5701b15078cea310c39637db75cd02c0"))
        assert seen["buttons"] == []


class TestReconnectSessions:
    def make_device(self, bridge, history, address="8A:88:1B:E0:1F:91"):
        seen = {"notifies": [], "buttons": []}
        dev = bridge.SwitchBotDevice(
            KEY, seen["notifies"].append,
            lambda *event: seen["buttons"].append(event),
            session_history=history, target_address=lambda: address,
        )
        return dev, seen

    def test_queued_press_is_recovered_before_new_handshake(self, bridge):
        history = bridge.NativeSessionHistory()
        old, _ = self.make_device(bridge, history)
        old.on_write(HANDSHAKE)
        queued = frame(bridge, old, old._iv)
        new, seen = self.make_device(bridge, history)
        new.on_write(queued)
        assert len(seen["buttons"]) == 1
        ack = seen["notifies"][-1]
        assert ack[1:4] == queued[1:4]
        assert bridge.aes_ctr(KEY, old._iv, ack[4:]) == b"\x01"

    def test_delivered_frame_is_only_acknowledged_after_reconnect(self, bridge):
        history = bridge.NativeSessionHistory()
        old, original = self.make_device(bridge, history)
        old.on_write(HANDSHAKE)
        queued = frame(bridge, old, old._iv)
        old.on_write(queued)
        assert len(original["buttons"]) == 1
        new, seen = self.make_device(bridge, history)
        new.on_write(HANDSHAKE)
        new.on_write(queued)
        new.on_write(queued)
        assert seen["buttons"] == []
        assert len(seen["notifies"]) == 3

    def test_target_addresses_do_not_share_sessions(self, bridge):
        history = bridge.NativeSessionHistory()
        old, _ = self.make_device(bridge, history)
        old.on_write(HANDSHAKE)
        new, seen = self.make_device(bridge, history, "8A:88:1B:E0:1F:92")
        new.on_write(frame(bridge, old, old._iv))
        assert seen == {"notifies": [], "buttons": []}

    def test_same_button_in_a_new_session_is_a_new_press(self, bridge):
        history = bridge.NativeSessionHistory()
        old, _ = self.make_device(bridge, history)
        old.on_write(HANDSHAKE)
        old.on_write(frame(bridge, old, old._iv))
        new, seen = self.make_device(bridge, history)
        new.on_write(HANDSHAKE)
        new.on_write(frame(bridge, new, new._iv))
        assert len(seen["buttons"]) == 1

    def test_unknown_session_and_wrong_key_id_remain_unacknowledged(self, bridge):
        history = bridge.NativeSessionHistory()
        old, _ = self.make_device(bridge, history)
        old.on_write(HANDSHAKE)
        new, seen = self.make_device(bridge, history)
        queued = frame(bridge, old, old._iv)
        new.on_write(queued[:1] + b"\x02" + queued[2:])
        new.on_write(bytes.fromhex("5701b15078cea310c39637db75cd02c0"))
        assert seen == {"notifies": [], "buttons": []}

    def test_expired_sessions_cannot_recover_a_press(self, bridge, monkeypatch):
        now = [100.0]
        monkeypatch.setattr(bridge.time, "monotonic", lambda: now[0])
        history = bridge.NativeSessionHistory()
        old, _ = self.make_device(bridge, history)
        old.on_write(HANDSHAKE)
        queued = frame(bridge, old, old._iv)
        now[0] += 61
        new, seen = self.make_device(bridge, history)
        new.on_write(queued)
        assert seen == {"notifies": [], "buttons": []}

    def test_history_and_frame_limits_are_bounded(self, bridge):
        history = bridge.NativeSessionHistory()
        for target in range(40):
            for session in range(40):
                history.issue(str(target), session.to_bytes(16, "big"), 1)
        assert len(history._targets) == 32
        assert all(len(sessions) == 32 for sessions in history._targets.values())
        iv = (39).to_bytes(16, "big")
        for command in range(65):
            history.remember("39", iv, bytes([command]))
        assert iv not in history.candidates("39", 1)


class TestTheSessionLabelIsOnlyAHint:
    """The remote has been seen labelling a frame with a session it never asked for.

    Two bytes are not proof, so every remembered session is tried and the one whose plaintext
    reads as a bridge event wins. Nothing that reads as nothing is ever published.
    """

    def test_a_mislabelled_frame_is_still_recovered(self, bridge):
        dev, seen = device(bridge)
        for _ in range(3):
            dev.on_write(HANDSHAKE)
        real = list(dev._sessions.values())[0]
        body = bridge.aes_ctr(KEY, real, PRESS)
        # Encrypted under the first session, but labelled with a name nobody issued.
        dev.on_write(bytes([0x57, 0x01]) + bytes.fromhex("4b1a") + body)
        assert [b[0] for b in seen["buttons"]] == ["BRIGHTER"]

    def test_it_is_acknowledged_in_the_session_that_actually_decrypted_it(self, bridge):
        dev, seen = device(bridge)
        for _ in range(3):
            dev.on_write(HANDSHAKE)
        real = list(dev._sessions.values())[0]
        body = bridge.aes_ctr(KEY, real, PRESS)
        seen["notifies"].clear()
        dev.on_write(bytes([0x57, 0x01]) + bytes.fromhex("4b1a") + body)
        assert seen["notifies"][-1][2:4] == real[:2]

    def test_a_frame_no_session_can_read_is_still_refused(self, bridge):
        dev, seen = device(bridge)
        for _ in range(3):
            dev.on_write(HANDSHAKE)
        # Straight from the log, and genuinely undecryptable here.
        dev.on_write(bytes.fromhex("57014b1a0f5ac09768b3c7e386f78b90"))
        assert seen["buttons"] == []

    def test_the_named_session_is_preferred_when_it_works(self, bridge):
        dev, seen = device(bridge)
        for _ in range(3):
            dev.on_write(HANDSHAKE)
        named = list(dev._sessions.values())[2]
        dev.on_write(frame(bridge, dev, named))
        assert seen["notifies"][-1][2:4] == named[:2]


@pytest.mark.parametrize("mode", ["raw", "timeout", "invalid", "rejected", "command", "empty"])
def test_mqtt_all_management_stays_on_raw_hci(bridge, monkeypatch, mode):
    published = []
    ready = threading.Event()
    actions = []
    raw_calls = []
    bluez_calls = []
    class Client:
        def subscribe(self, *args, **kwargs):
            pass
        def publish(self, topic, payload, **kwargs):
            if topic.endswith("/manage_result"):
                published.append(json.loads(payload))
                ready.set()
    mqtt = object.__new__(bridge.Mqtt)
    mqtt._client = Client()
    def reader(address, key_hex, key_id, steps):
        raw_calls.append((address, steps))
        if mode == "timeout":
            raise TimeoutError("raw connection failed")
        if mode == "invalid":
            return None
        if mode == "rejected":
            return {"ok": False, "failed_stage": "inventory", "error": "ATT rejected"}
        return {"ok": True, "responses": ["0100000000000000"], "transport": "raw_hci"}
    def bluez(*args):
        bluez_calls.append(args)
        return {"ok": True, "responses": ["01"]}
    monkeypatch.setattr(bridge, "run_remote_management", bluez)
    monkeypatch.setattr(bridge.time, "sleep", lambda _: None)
    mqtt.set_control_handler(lambda action: actions.append(action) or True,
                             adapter_name="hci0", adapter_address="8A:88:1B:E0:1F:92",
                             management_runner=reader)
    payload = {"request_id": "read-1", "address": "B0:E9:FE:53:11:45", "key": KEY.hex(),
               "key_id": 0x95, "steps": [{"kind": "query", "subcmd": 7}]}
    if mode == "command":
        payload["steps"] = [{"kind": "command", "plaintext": "02"}]
    if mode == "empty":
        payload["steps"] = []
    message = types.SimpleNamespace(topic="switchbot_urc/bridge/manage", payload=json.dumps(payload))
    mqtt._client.on_message(mqtt._client, None, message)
    assert ready.wait(2)
    assert published[0]["ok"] == (mode in {"raw", "command", "empty"})
    if mode in {"timeout", "invalid"}:
        assert published[0]["failed_stage"] == "bridge"
        assert published[0]["transport"] == "raw_hci"
    assert len(raw_calls) == 1
    assert not bluez_calls
    assert not actions
