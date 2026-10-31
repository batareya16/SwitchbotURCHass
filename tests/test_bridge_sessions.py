"""Tests for matching an encrypted press to the session it was encrypted with.

The remote asks for several randoms in a row and then sends a frame for each, so the newest
IV is often not the right one. Keeping only the newest dropped real presses; keeping none of
them published noise as a button press. Both were observed on hardware.
"""
import os
import sys
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
