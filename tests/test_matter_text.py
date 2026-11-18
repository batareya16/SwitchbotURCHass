"""Matter text remote: write format against the official app's builder, and A-D press decoding."""

import pytest

from conftest import INTEGRATION, load

commands = load(INTEGRATION / "commands.py")
matter = load(INTEGRATION / "matter_text.py")


def app_body(index, device_id, name, captions):
    """The byte list `getEditMatterNameCmdMatter` in urc-bundle.js builds, written out by hand.

    ``[t,39,3,0,0] + id11 + name64 + [0,0]`` then ``[4,0] + [0,1] + [5] + c1 + [1] + [0,2] + [5]
    + c2 + [2] + [0,3] + [5] + c3 + [3] + [0,4] + [5] + c4``.
    """
    ident = (bytes.fromhex(device_id)[::-1] + bytes(11))[:11]
    title = bytearray((name.encode() + bytes(64))[:64])
    title[63] = 0
    fields = []
    for caption in captions:
        field = bytearray((caption.encode() + bytes(32))[:32])
        field[31] = 0
        fields.append(bytes(field))
    body = bytearray([index, 39, 3, 0, 0]) + ident + bytes(title) + bytes([0, 0])
    body += bytes([4, 0, 0, 1, 5]) + fields[0]
    body += bytes([1, 0, 2, 5]) + fields[1]
    body += bytes([2, 0, 3, 5]) + fields[2]
    body += bytes([3, 0, 4, 5]) + fields[3]
    return bytes(body)


def test_create_packet_matches_the_official_app_bytes():
    captions = ("Lamp", "Вентилятор", "Music", "Scene D")
    packet = matter.build_matter_create(
        remote_index=5, device_id="4d5400000001", name="Accessory", captions=captions
    )
    body = app_body(5, "4d5400000001", "Accessory", captions)
    assert packet[:3] == bytes.fromhex("0f6206")
    assert packet[3:5] == len(body).to_bytes(2, "big")
    assert packet[5:7] == commands.crc16_modbus(body).to_bytes(2, "big")
    assert packet[7:] == body


def test_icon_changes_only_the_icon_byte_and_crc():
    args = dict(remote_index=2, device_id="4d5400000001", name="T", captions=("a", "b", "c", "d"))
    plain = matter.build_matter_create(**args)
    washer = matter.build_matter_create(**args, icon=commands.ICON["washer"])
    assert washer[7 + 4] == 14 and plain[7 + 4] == 0
    assert washer[7:11] == plain[7:11] and washer[12:] == plain[12:]
    assert washer[5:7] == commands.crc16_modbus(washer[7:]).to_bytes(2, "big")
    assert commands.rewrite_native_page_icon(plain, 14) == washer


def test_caption_update_keeps_slot_and_id():
    first = matter.build_matter_create(
        remote_index=2, device_id="4d5400000001", name="T", captions=("a", "b", "c", "d"))
    second = matter.build_matter_create(
        remote_index=2, device_id="4d5400000001", name="T", captions=("a", "b", "c", "E"))
    assert first[7:7 + 91] == second[7:7 + 91]
    assert first != second


@pytest.mark.parametrize("captions, message", [
    (("a", "b", "c"), "four captions"),
    (("a", "", "c", "d"), "button B"),
    (("a", "b", "c", "я" * 16), "limit is 31"),
    (("a", "b\0", "c", "d"), "invalid"),
])
def test_captions_are_validated(captions, message):
    with pytest.raises(ValueError, match=message):
        matter.normalize_captions(captions)


def test_caption_limit_is_bytes_not_characters():
    matter.normalize_captions(("я" * 15, "x" * 31, "c", "d"))
    with pytest.raises(ValueError):
        matter.normalize_captions(("я" * 16, "b", "c", "d"))


def test_device_id_avoids_ids_already_in_the_table():
    first = matter.new_device_id(set(), commands.id_to_bytes)
    second = matter.new_device_id({commands.id_to_bytes(first)}, commands.id_to_bytes)
    assert first != second
    assert len(commands.id_to_bytes(second)) == 11


def test_matter_row_detection():
    assert matter.is_matter_row((3, 0x27, 3, b"\0" * 11))
    assert not matter.is_matter_row((3, 0x27, 0, b"\0" * 11))
    assert not matter.is_matter_row((3, 0x72, 3, b"\0" * 11))


def advert(sequence, a=0, b=0, c=0, d=0, *, category=3):
    payload = bytearray(17)
    payload[:6] = bytes.fromhex("b0e9fe531145")
    payload[6] = sequence
    payload[10] = category
    payload[13:17] = bytes([a, b, c, d])
    return bytes(payload)


def test_each_letter_is_decoded_from_its_own_counter():
    tracker = matter.MatterPressTracker()
    assert tracker.feed(advert(1, 0x21, 0x22, 0x23, 0x24)) is None  # baseline
    assert tracker.feed(advert(2, 0x21, 0x22, 0x23, 0x25)) == 3
    assert tracker.feed(advert(3, 0x21, 0x23, 0x23, 0x25)) == 1
    assert tracker.feed(advert(4, 0x22, 0x23, 0x23, 0x25)) == 0
    assert tracker.feed(advert(5, 0x22, 0x23, 0x24, 0x25)) == 2


def test_repeats_stale_counters_and_other_categories_are_ignored():
    tracker = matter.MatterPressTracker()
    tracker.feed(advert(1, 0x21))
    pressed = advert(2, 0x22)
    assert tracker.feed(pressed) == 0
    assert tracker.feed(pressed) is None  # repeat of one announcement
    assert tracker.feed(advert(3, 0x22)) is None  # new sequence, counters latched
    assert tracker.feed(advert(4, 0x23, category=2)) is None  # scene event, not Matter
    assert tracker.feed(advert(5, 0x25)) is None  # skipped one counter value: not a single press


def test_counter_wraps_from_31_to_1_and_zero_state_is_not_a_press():
    tracker = matter.MatterPressTracker()
    tracker.feed(advert(10, c=0x3F))
    assert tracker.feed(advert(11, c=0x21)) == 2
    tracker.feed(advert(12, c=0x21))
    assert tracker.feed(advert(13, c=0x02)) is None  # state bits clear


def test_wrong_size_and_zero_sequence_payloads_are_ignored():
    tracker = matter.MatterPressTracker()
    assert tracker.feed(b"\0" * 16) is None
    assert tracker.feed(advert(0, 0x21)) is None
    assert tracker.previous is None


def test_named_ir_transfer_accepts_the_devices_real_acknowledgements():
    stages = commands.build_hid_ir_transfer(
        device_id="4684019217020000000000", key_name="3", code=bytes(range(40)))
    names = [name for name, _packet, _accepted in stages]
    assert names[0] == "ir_transfer_init" and names[-1] == "ir_transfer_finish"
    accepted = {name: codes for name, _packet, codes in stages}
    assert accepted["ir_transfer_init"] == frozenset({0x01, 0x10})  # the device answers 10 00
    assert accepted["ir_transfer_part_0"] == frozenset({0x00, 0x01})
    assert accepted["ir_transfer_finish"] == frozenset({0x00, 0x01})
