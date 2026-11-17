"""Tests for the path a saved Home Assistant action takes back to the panel.

Studio reported actions appearing only after switching tabs, and earlier ones not loading at
all. These exercise the serialisation the panel reads, with Home Assistant stubbed out, so the
question "does the backend hand the actions over" can be answered without a running instance.
"""
import asyncio
import sys
import types

import pytest

from conftest import INTEGRATION


def _stub_homeassistant():
    """Enough of Home Assistant for studio.py to import, and nothing more."""
    for name in list(sys.modules):
        if name.startswith("homeassistant"):
            del sys.modules[name]

    def module(name, **attrs):
        mod = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        sys.modules[name] = mod
        return mod

    module("homeassistant")
    module("homeassistant.core", HomeAssistant=object, callback=lambda f: f, Event=object)
    module("homeassistant.config_entries", ConfigEntry=object)
    websocket = types.SimpleNamespace(
        require_admin=lambda f: f,
        websocket_command=lambda schema: (lambda f: f),
        async_response=lambda f: f,
        async_register_command=lambda *a, **k: None,
        ActiveConnection=object,
    )
    panel = types.SimpleNamespace(async_register_panel=lambda *a, **k: None)
    bluetooth = types.SimpleNamespace(
        async_ble_device_from_address=lambda *a, **k: None,
        async_scanner_devices_by_address=lambda *a, **k: [],
        BluetoothServiceInfoBleak=object, async_register_callback=lambda *a, **k: None,
        BluetoothChange=object, BluetoothScanningMode=object, async_last_service_info=lambda *a, **k: None)
    module("homeassistant.components.bluetooth", **vars(bluetooth))
    module("homeassistant.components", websocket_api=websocket, panel_custom=panel,
           bluetooth=bluetooth,
           http=types.SimpleNamespace(HomeAssistantView=object, StaticPathConfig=object),
           frontend=types.SimpleNamespace(async_register_built_in_panel=lambda *a, **k: None))
    module("homeassistant.components.panel_custom", **vars(panel))
    module("homeassistant.components.websocket_api", **vars(websocket))
    module("homeassistant.components.http", HomeAssistantView=object, StaticPathConfig=object)
    module("homeassistant.components.frontend", async_register_built_in_panel=lambda *a, **k: None)
    module("homeassistant.helpers")
    module("homeassistant.helpers.script", Script=object,
           async_validate_actions_config=lambda *a, **k: None)
    module("homeassistant.helpers.aiohttp_client", async_get_clientsession=lambda *a: None)
    module("homeassistant.helpers.entity_registry", async_get=lambda *a: None)
    module("homeassistant.helpers.device_registry", async_get=lambda *a: None)
    module("homeassistant.util", dt=types.SimpleNamespace(utcnow=lambda: None))
    # studio.py reaches the BLE stack through its siblings; none of it is exercised here.
    module("bleak", BleakScanner=object, BleakClient=object, BLEDevice=object)
    module("bleak.backends", device=types.SimpleNamespace(BLEDevice=object))
    module("bleak.backends.device", BLEDevice=object)
    module("bleak_retry_connector", establish_connection=lambda *a, **k: None,
           BleakClientWithServiceCache=object, BleakNotFoundError=Exception)
    module("cryptography")
    module("cryptography.hazmat")
    module("cryptography.hazmat.primitives")
    module("cryptography.hazmat.primitives.ciphers", Cipher=object,
           algorithms=types.SimpleNamespace(AES=object),
           modes=types.SimpleNamespace(CTR=object))


@pytest.fixture(scope="module")
def studio():
    _stub_homeassistant()
    import importlib.util
    package = "switchbot_urc"
    if package not in sys.modules:
        pkg = types.ModuleType(package)
        pkg.__path__ = [str(INTEGRATION)]
        sys.modules[package] = pkg
    spec = importlib.util.spec_from_file_location(
        f"{package}.studio", INTEGRATION / "studio.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{package}.studio"] = module
    try:
        spec.loader.exec_module(module)
    except Exception as err:  # noqa: BLE001
        pytest.skip(f"studio.py needs more of Home Assistant than is stubbed: {err}")
    return module


ACTIONS = [{"action": "light.turn_on", "target": {"entity_id": "light.hall"}}]


def test_studio_creates_bridge_remote_without_saved_credentials(studio, monkeypatch):
    from switchbot_urc import studio_remotes

    address = "DA:71:16:E0:1F:93"
    entry = types.SimpleNamespace(entry_id="entry", domain=studio_remotes.DOMAIN,
                                  data={}, options={})
    entries = types.SimpleNamespace(
        async_get_entry=lambda _: entry,
        async_update_entry=lambda item, **changes: vars(item).update(changes),
    )
    hass = types.SimpleNamespace(data={}, config_entries=entries)
    captured = {}
    connection = types.SimpleNamespace(
        send_result=lambda _, result: captured.update(result),
        send_error=lambda _, code, message: pytest.fail(f"{code}: {message}"),
    )
    controller = studio_remotes.addressing.Bridge(
        adapter="hci0", address=address, advertising_sets=1,
        serving=[address], extended_advertising=True,
    )

    async def read_table(*_args):
        return []

    async def confirm(_hass, _controller, selected):
        return selected == address

    async def bind(_client, stages, *, device_id):
        assert device_id == address
        assert [packet[:3] for _, packet in stages] == [bytes.fromhex("0f6206")]

    monkeypatch.setattr(studio_remotes, "_client", lambda *_: object())
    monkeypatch.setattr(studio_remotes, "_bridges", lambda _: [controller])
    monkeypatch.setattr(studio_remotes, "read_device_table", read_table)
    monkeypatch.setattr(studio_remotes, "_confirm_bridge_address", confirm)
    monkeypatch.setattr(studio_remotes.install, "bind_native_once", bind)
    asyncio.run(studio_remotes.ws_remote_create(hass, connection, {
        "id": 1, "entry_id": entry.entry_id, "name": "Lamp", "native_type": "PLUG",
    }))

    (remote,) = entry.options["remotes"]
    assert remote["physical_device_id"] == address
    assert captured["remote_id"] == remote["remote_id"]
    assert entry.data == {}


@pytest.mark.parametrize("readback_received", [True, False])
def test_layout_write_reads_back_in_the_same_bridge_session(studio, readback_received):
    from switchbot_urc.client import UrcClient

    requests = []
    raw_table = bytes.fromhex("01000000000140bf00")

    async def manage(_address, _key, _key_id, steps):
        requests.append(steps)
        if readback_received:
            return {"ok": True, "responses": ["01", raw_table.hex()]}
        return {"ok": False, "responses": ["01"], "failed_stage": "command",
                "stage_detail": "query_0F6307", "error": "timed out"}

    client = UrcClient(types.SimpleNamespace(address="B0:E9:FE:53:11:45"),
                       types.SimpleNamespace(key=bytes(16), key_id=95), management_proxy_cb=manage)
    client._force_preferred_adapter = True
    responses = asyncio.run(client.send_command_sequence(
        [bytes.fromhex("0f6206")], accepted_codes=[frozenset({1})], readback_subcommand=7,
    ))

    assert len(requests) == 1
    assert [step["kind"] for step in requests[0]] == ["command", "query"]
    assert requests[0][1]["subcmd"] == 7
    assert responses == ([b"\x01", raw_table] if readback_received else [b"\x01"])


def binding(remote_id="abc123", **actions):
    return {"remote_id": remote_id, "enabled": True, "button_actions": dict(actions)}


class TestOneButton:
    def test_a_bound_button_carries_its_actions(self, studio):
        record = studio._button_record(
            remote_id="abc123", remote_slot=3, page=0, index=5, function=6,
            position="OFF", label="OFF", binding=binding(p0_k5=ACTIONS))
        assert record["actions"] == ACTIONS
        assert record["has_override"] is True

    def test_an_unbound_button_has_none(self, studio):
        record = studio._button_record(
            remote_id="abc123", remote_slot=3, page=0, index=5, function=6,
            position="OFF", label="OFF", binding=binding(p0_k4=ACTIONS))
        assert record["actions"] == []
        assert record["has_override"] is False

    def test_a_deliberately_silenced_button_is_an_override_with_no_actions(self, studio):
        record = studio._button_record(
            remote_id="abc123", remote_slot=3, page=0, index=5, function=6,
            position="OFF", label="OFF", binding=binding(p0_k5=[]))
        assert record["actions"] == []
        assert record["has_override"] is True

    def test_no_binding_at_all(self, studio):
        record = studio._button_record(
            remote_id="abc123", remote_slot=3, page=0, index=5, function=6,
            position="OFF", label="OFF", binding=None)
        assert record["actions"] == []
        assert record["has_override"] is False

    def test_the_button_id_is_page_and_index(self, studio):
        record = studio._button_record(
            remote_id="abc123", remote_slot=3, page=2, index=7, function=6,
            position="", label="Button 8", binding=None)
        assert record["button_id"] == "p2_k7"

    def test_a_submenu_button_carries_its_actions_too(self, studio):
        record = studio._button_record(
            remote_id="abc123", remote_slot=3, page=2, index=7, function=6,
            position="", label="Button 8", binding=binding(p2_k7=ACTIONS))
        assert record["actions"] == ACTIONS

    def test_rubbish_stored_for_a_button_does_not_leak_out(self, studio):
        record = studio._button_record(
            remote_id="abc123", remote_slot=3, page=0, index=5, function=6,
            position="OFF", label="OFF", binding=binding(p0_k5="not a list"))
        assert record["actions"] == []


class TestWholeRemote:
    def test_every_bound_button_on_a_remote_keeps_its_actions(self, studio):
        remote = {
            "remote_id": "abc123", "name": "Bridge", "device_type": "STRIP",
            "device_id": "8A881BE01F92", "index": 3,
            "physical_layout": {"kind": "native", "pages": [
                {"index": 0, "buttons": [
                    {"index": 4, "transport": "native", "function": 5},
                    {"index": 5, "transport": "native", "function": 6},
                ]},
            ]},
        }
        pages = studio.remote_pages(remote, binding(p0_k4=ACTIONS))
        buttons = {item["button_id"]: item for item in pages[0]["buttons"]}
        assert buttons["p0_k4"]["actions"] == ACTIONS
        assert buttons["p0_k5"]["actions"] == []

    def test_the_binding_is_matched_on_the_remote_identity(self, studio):
        remote = {
            "remote_id": "abc123", "name": "Bridge", "device_type": "STRIP",
            "device_id": "8A881BE01F92", "index": 3,
            "physical_layout": {"kind": "native", "pages": [
                {"index": 0, "buttons": [{"index": 4, "transport": "native", "function": 5}]},
            ]},
        }
        [page] = studio.remote_pages(remote, binding(p0_k4=ACTIONS))
        assert page["buttons"][0]["remote_id"] == "abc123"


class TestSubmenuRowsAreNotPhysicalKeys:
    """A submenu is a list drawn on the screen; its indexes are rows, not keys.

    The stock-profile page builder named them after the physical layout, so Page D showed
    A, B, C, D, ON, OFF, LEFT, RIGHT, UP, DOWN … next to its real entries.
    """

    def _pages(self, studio):
        remote = {"remote_id": "abc123", "name": "Strip", "device_type": "STRIP",
                  "device_id": "8A881BE01F92", "index": 3}
        return studio._remote_pages(remote, None)

    def test_the_main_page_still_names_its_keys(self, studio):
        pages = self._pages(studio)
        if not pages:
            pytest.skip("this device type has no stock profile to lay out")
        main = next(page for page in pages if page["index"] == 0)
        assert any(button["position"] for button in main["buttons"])

    def test_no_submenu_row_claims_a_physical_position(self, studio):
        pages = self._pages(studio)
        if not pages:
            pytest.skip("this device type has no stock profile to lay out")
        submenus = [page for page in pages if page["index"]]
        if not submenus:
            pytest.skip("this stock profile has no submenu")
        for page in submenus:
            for button in page["buttons"]:
                assert button["position"] == "", (
                    f"page {page['index']} row {button['button_index']} "
                    f"claims to be {button['position']}")

    def test_an_unnamed_submenu_row_is_called_a_row(self, studio):
        pages = self._pages(studio)
        submenus = [page for page in pages if page["index"]]
        if not submenus:
            pytest.skip("this stock profile has no submenu")
        labels = [button["label"] for page in submenus for button in page["buttons"]]
        assert not any(label in {"UP", "DOWN", "LEFT", "RIGHT", "OK", "BACK"}
                       for label in labels)
