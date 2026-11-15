"""Refresh must reconcile physical target addresses and stale Native metadata."""
import ast
import asyncio
import logging

from conftest import INTEGRATION, load

c = load(INTEGRATION / "commands.py")
physical = load(INTEGRATION / "physical_layout.py")
source = ast.parse((INTEGRATION / "studio_physical.py").read_text())
functions = ast.Module(body=[node for node in source.body if isinstance(
    node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
        "_refresh_native_appearances", "_adopt_native_remotes", "_drop_absent_remotes",
    }], type_ignores=[])
namespace = {"c": c, "physical": physical, "_LOGGER": logging.getLogger(__name__)}
exec(compile(functions, "studio_physical.py", "exec"), namespace)


def test_refresh_matches_moved_target_and_repairs_cached_type_and_slot():
    address = "8A:88:1B:E0:1F:91"
    device_id = c.id_to_bytes(address)
    table = [(3, 0x72, c.CTRL_NATIVE, device_id)]
    body = b"\x01" + bytes([3, 0x72, 0, 0, 3]) + device_id + bytes(64)
    raw = b"\x01\x00\x00\x00" + len(body).to_bytes(2, "big") + bytes(2) + body
    remote = {"index": "8", "device_type": "FLOOR_LAMP", "remote_id": "12345678",
              "device_id": "AA:BB:CC:DD:EE:FF", "physical_device_id": address}
    remotes = [remote]

    class Client:
        async def query(self, subcommand, **kwargs):
            assert subcommand == 5
            return raw

    assert namespace["_adopt_native_remotes"](table, remotes, []) == 0
    error = asyncio.run(namespace["_refresh_native_appearances"](Client(), table, remotes))
    assert error is None
    assert remote["index"] == 3
    assert c.NATIVE_DEVTYPE[remote["device_type"]] == 0x72
    assert remote["native_appearance_readback"] == {
        "slot": 3, "device_type": 0x72, "mode": 0, "icon": 3,
    }
    assert physical.native_appearance(remote)["native_type"] == "FLOOR_LAMP"
    assert namespace["_drop_absent_remotes"](table, remotes) == 0
    assert remote["remote_id"] == "12345678"


def test_match_uses_unique_physical_id_when_slot_is_missing():
    device_id = c.id_to_bytes("AA:BB:CC:DD:EE:FF")
    remote = {"device_id": device_id.hex()}
    identity = (4, 0x72, device_id)
    assert physical.match_native_appearance(remote, {identity: (0, 3)}, 0x75) == identity


def test_match_never_uses_slot_alone_when_target_address_differs():
    remote = {"index": 3, "device_id": "AA:BB:CC:DD:EE:FF"}
    identity = (3, 0x72, c.id_to_bytes("00:11:22:33:44:55"))
    assert physical.match_native_appearance(remote, {identity: (0, 3)}, 0x72) is None


def test_shared_target_uses_slot_even_when_cached_type_is_stale():
    device_id = c.id_to_bytes("AA:BB:CC:DD:EE:FF")
    remote = {"index": "3", "device_id": device_id.hex()}
    identity = (3, 0x72, device_id)
    appearances = {identity: (0, 3), (2, 0x75, device_id): (0, 1)}
    assert physical.match_native_appearance(remote, appearances, 0x75) == identity
    remote.pop("index")
    assert physical.match_native_appearance(remote, appearances, 0x7d) is None
