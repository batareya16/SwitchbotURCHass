"""A page without keys must never reach the remote, except the header of a new IR install.

The remote's screen list writes such a page at the position equal to its slot byte, whatever
row is there. After a reorder that overwrote another remote's row, hid it and shifted every tile.
"""
import asyncio
import sys
import types

import pytest

from conftest import INTEGRATION, load

c = load(INTEGRATION / "commands.py")
cloud_ir = load(INTEGRATION / "cloud_ir.py")


def _client_module():
    for name, attrs in {
        "bleak": ("BleakClient", "BleakScanner"),
        "bleak.backends": (),
        "bleak.backends.device": ("BLEDevice",),
        "bleak_retry_connector": ("establish_connection",),
    }.items():
        module = sys.modules.get(name) or types.ModuleType(name)
        for attr in attrs:
            if not hasattr(module, attr):
                setattr(module, attr, type(attr, (), {}))
        sys.modules[name] = module
    return load(INTEGRATION / "client.py")


def _page(keys, *, slot=5, device_type=0x02, control_type=1):
    return c.build_create(
        remote_index=slot, device_type=device_type, control_type=control_type, control_mode=0,
        icon=0, device_id="0102030405AA", name="Remote", ble_key_type=2, keys=keys,
    )


KEY = {"keyIndex": 4, "keyFun": 105}


def test_record_count_is_read_from_every_page_builder():
    assert c.page_record_count(_page([])) == 0
    assert c.page_record_count(_page([KEY, {**KEY, "keyIndex": 5}])) == 2
    # A four-byte device type moves the count byte by three.
    assert c.page_record_count(_page([KEY], device_type=0x00113640)) == 1
    assert c.page_record_count(_page([], device_type=0x00113640)) == 0
    assert c.page_record_count(c.build_ir_empty_remote(
        remote_index=6, device_type=2, remote_id=bytes(11), name="X")) == 0
    hid = c.build_hid_edit_page(
        remote_index=5, device_type_name="UNIVERSAL_BLE", device_id="021793376454",
        name="Mi Box S", keys=[{"index": 0, "hid_usage": b"\x08\x37"}])
    assert c.page_record_count(hid) == 1


def test_other_commands_are_not_pages():
    assert c.page_record_count(c.build_ir_sync(1, 1)) is None
    assert c.page_record_count(bytes.fromhex("0f620402")) is None
    # A damaged page (length does not add up) is left to the remote's own CRC check.
    assert c.page_record_count(_page([KEY])[:-3]) is None


def test_empty_pages_are_refused_unless_they_open_an_ir_install():
    empty = _page([])
    full = _page([KEY])
    start, end = c.build_ir_sync(1, 1), c.build_ir_sync(1, 3)
    assert c.refused_empty_pages([full]) == []
    assert c.refused_empty_pages([empty]) == [0]
    assert c.refused_empty_pages([full, empty, full]) == [1]
    assert c.refused_empty_pages([empty, start, full, end]) == []
    # Only the sync START right after it makes an empty page an install header.
    assert c.refused_empty_pages([empty, end]) == [0]
    assert c.refused_empty_pages([start, empty]) == [1]


@pytest.mark.parametrize("device_type", cloud_ir.BLANK_REMOTE_TYPES)
def test_blank_ir_install_passes_and_writes_keys_after_the_header(device_type):
    stages = cloud_ir.blank_profile(device_type, "New").build_install(
        remote_index=6, name="New", remote_count=1)
    packets = [packet for _stage, packet, _accepted in stages]
    assert c.refused_empty_pages(packets) == []
    pages = [packet for packet in packets[1:] if c.page_record_count(packet) is not None]
    assert pages and all(c.page_record_count(packet) > 0 for packet in pages)


def test_client_refuses_before_anything_is_sent():
    client_module = _client_module()
    client = client_module.UrcClient.__new__(client_module.UrcClient)

    async def proxy(*_args):
        pytest.fail("an empty page must not reach the add-on")

    client._management_proxy = proxy
    client._force_preferred_adapter = True
    empty = _page([])

    with pytest.raises(client_module.UrcEmptyPageRefused, match="without keys"):
        asyncio.run(client.send_command(empty))
    with pytest.raises(client_module.UrcEmptyPageRefused):
        asyncio.run(client.send_command_with_preflight_query(empty))
    with pytest.raises(client_module.UrcEmptyPageRefused):
        asyncio.run(client.send_command_sequence([c.build_ir_sync(1, 1), empty]))
