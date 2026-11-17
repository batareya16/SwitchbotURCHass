"""Verify the V48 scene-list wire format and the activation counters."""

import pytest

from conftest import INTEGRATION, load

scenes = load(INTEGRATION / "scenes.py")


def test_write_keeps_scene_slots_and_multibyte_names():
    first = scenes.Scene(1, "Кино", 18, 6)
    last = scenes.Scene(9, "Sleep", 21, 7)
    packet = scenes.build_scene_list([last, first])
    assert packet[:5] == bytes.fromhex("0f62090087")
    assert packet[7] == 2
    assert packet[8:17] == b"\x01" + "Кино".encode()
    assert packet[72:76] == bytes([0, 18, 6, 9])
    response = bytes.fromhex("01000000") + packet[3:5] + b"\x00\x00" + packet[7:]
    assert scenes.parse_scene_list(response) == {1: first, 9: last}
    with pytest.raises(ValueError, match="incomplete"):
        scenes.parse_scene_list(response[:-1])


def test_empty_list_and_duplicate_slots():
    assert scenes.build_scene_list([]) == bytes.fromhex("0f6209000140bf00")
    assert scenes.parse_scene_list(bytes.fromhex("010000000001000000")) == {}
    row = scenes.Scene(0, "Morning", 1, 3)
    with pytest.raises(ValueError, match="unique"):
        scenes.build_scene_list([row, row])
    with pytest.raises(ValueError, match="UTF-8"):
        scenes.build_scene_list([scenes.Scene(0, "я" * 32, 1, 3)])


def advertisement(sequence, index, key, *, kind=2, other_key=0):
    return bytes.fromhex("b0e9fe531145") + bytes(
        [sequence, 0x34, index, 0, kind, key, other_key, 0, 0, 0, 0]
    )


def test_scene_activation_uses_a_fresh_key_counter():
    tracker = scenes.ScenePressTracker()
    assert tracker.feed(advertisement(11, 3, 0x20, kind=0)) is None
    pressed = advertisement(12, 3, 0x21)
    assert tracker.feed(pressed) == 3
    assert tracker.feed(pressed) is None
    # Other firmware paths can increment the sequence with the old scene still latched.
    assert tracker.feed(advertisement(13, 3, 0x21)) is None
    assert tracker.feed(advertisement(14, 3, 0x22)) == 3
    assert tracker.feed(advertisement(15, 5, 0x22, other_key=0x21)) == 5


def test_cached_scene_is_baseline_and_counters_wrap():
    tracker = scenes.ScenePressTracker()
    assert tracker.feed(advertisement(255, 3, 0x3F)) is None
    assert tracker.feed(advertisement(1, 3, 0x21)) == 3
