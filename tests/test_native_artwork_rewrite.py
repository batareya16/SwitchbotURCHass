"""The temporary artwork test must change only the profile byte and its CRC."""

import pytest

from conftest import INTEGRATION, load


c = load(INTEGRATION / "commands.py")


def test_rewrite_native_page_control_mode_preserves_all_other_page_data():
    packet = c.build_create(
        remote_index=3,
        device_type=0x72,
        control_type=c.CTRL_NATIVE,
        control_mode=0,
        icon=5,
        device_id="00:1A:7D:DA:71:15",
        name="Floor lamp",
        ble_key_type=0,
        keys=[{"keyIndex": c.TAG["ON"], "keyFun": 5}],
    )

    rewritten = c.rewrite_native_page_control_mode(packet, c.NATIVE_WASHER_CONTROL_MODE)

    assert rewritten[:5] == packet[:5]
    assert rewritten[7:10] == packet[7:10]
    assert rewritten[10] == c.NATIVE_WASHER_CONTROL_MODE
    assert rewritten[11:] == packet[11:]
    assert int.from_bytes(rewritten[5:7], "big") == c.crc16_modbus(rewritten[7:])
    assert c.rewrite_native_page_control_mode(rewritten, 0) == packet


def test_rewrite_native_page_control_mode_handles_four_byte_device_type():
    packet = c.build_create(
        remote_index=3,
        device_type=bytes.fromhex("0010d0b0"),
        control_type=c.CTRL_NATIVE,
        control_mode=0,
        icon=5,
        device_id="00:1A:7D:DA:71:15",
        name="Floor lamp",
        ble_key_type=0,
        keys=[],
    )

    rewritten = c.rewrite_native_page_control_mode(packet, 7)

    assert rewritten[13] == 7
    assert rewritten[:5] == packet[:5]
    assert rewritten[7:13] == packet[7:13]
    assert rewritten[14:] == packet[14:]


def test_rewrite_native_page_control_mode_rejects_invalid_packets():
    packet = c.build_create(
        remote_index=0,
        device_type=0x72,
        control_type=c.CTRL_NATIVE,
        control_mode=0,
        icon=1,
        device_id="00:1A:7D:DA:71:15",
        name="Light",
        ble_key_type=0,
        keys=[],
    )
    damaged = bytearray(packet)
    damaged[-1] ^= 0x01

    with pytest.raises(ValueError, match="length or CRC"):
        c.rewrite_native_page_control_mode(bytes(damaged), 7)
    with pytest.raises(ValueError, match="0F6206"):
        c.rewrite_native_page_control_mode(b"\x0f\x62\x04", 7)
