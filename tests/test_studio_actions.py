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
    module("homeassistant.exceptions", HomeAssistantError=Exception)
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
    async def _validate_actions(_hass, actions):
        return actions

    module("homeassistant.helpers.script", Script=object,
           async_validate_actions_config=_validate_actions)
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


@pytest.mark.parametrize("verified", [True, False])
def test_scene_save_updates_ha_only_after_physical_readback(studio, verified):
    scenes = studio.studio_scenes
    existing = {"index": 4, "name": "Sleep", "icon": 21, "color": 6}
    new = {"index": 0, "name": "Movie", "icon": 18, "color": 6}
    entry = types.SimpleNamespace(domain="switchbot_urc", options={"remotes": ["other"]})

    def frame(*rows):
        packet = scenes.build_scene_list([scenes.Scene(**row) for row in rows])
        return b"\x01\0\0\0" + packet[3:7] + packet[7:]

    async def query(subcommand):
        assert subcommand == 4
        return frame(existing)

    async def sequence(commands, *, readback_subcommand):
        assert readback_subcommand == 4
        assert commands == [scenes.build_scene_list([scenes.Scene(**new), scenes.Scene(**existing)])]
        return [b"\x01", frame(new, existing) if verified else frame(existing)]

    runtime = {"client": types.SimpleNamespace(query=query, send_command_sequence=sequence)}
    hass = types.SimpleNamespace(
        data={"switchbot_urc": {"entry": runtime}},
        config_entries=types.SimpleNamespace(
            async_get_entry=lambda _: entry,
            async_update_entry=lambda item, *, options: setattr(item, "options", options),
        ),
        states={"scene.movie": object()},
    )
    results, errors = [], []
    connection = types.SimpleNamespace(
        send_result=lambda _, payload: results.append(payload),
        send_error=lambda _, code, message: errors.append((code, message)),
    )
    asyncio.run(scenes.ws_save_scene(hass, connection, {
        "id": 1, "entry_id": "entry", "expected": [existing], "delete": False,
        "name": "Movie", "icon": 18, "color": 6, "entity_id": "scene.movie",
    }))
    assert entry.options["remotes"] == ["other"]
    assert bool(results) == verified
    assert bool(errors) != verified
    if verified:
        assert entry.options["scene_bindings"]["0"]["actions"] == [
            {"action": "scene.turn_on", "target": {"entity_id": "scene.movie"}}
        ]
    else:
        assert "scene_bindings" not in entry.options


def test_scene_actions_update_without_rewriting_the_remote_and_execute(studio, monkeypatch):
    scenes = studio.studio_scenes
    row = {"index": 0, "name": "Movie", "icon": 18, "color": 6}
    packet = scenes.build_scene_list([scenes.Scene(**row)])
    frame = b"\x01\0\0\0" + packet[3:7] + packet[7:]
    entry = types.SimpleNamespace(domain="switchbot_urc", options={})

    async def query(_):
        return frame

    async def write(*args, **kwargs):
        pytest.fail("Changing HA actions must not write the device scene list")

    hass = types.SimpleNamespace(
        data={"switchbot_urc": {"entry": {"client": types.SimpleNamespace(
            query=query, send_command_sequence=write)}}},
        config_entries=types.SimpleNamespace(
            async_get_entry=lambda _: entry,
            async_update_entry=lambda item, *, options: setattr(item, "options", options)),
    )
    errors, results, runs = [], [], []
    connection = types.SimpleNamespace(
        send_error=lambda *args: errors.append(args),
        send_result=lambda *args: results.append(args))

    class ActionScript:
        def __init__(self, _hass, actions, *args, **kwargs):
            assert actions == ACTIONS

        async def async_run(self, variables):
            runs.append(variables)

    monkeypatch.setattr(scenes, "Script", ActionScript)

    async def exercise():
        await scenes.ws_save_scene(hass, connection, {
            "id": 1, "entry_id": "entry", "expected": [row], "delete": False,
            **row, "entity_id": "", "actions": ACTIONS,
        })
        await scenes._run_scene_actions(hass, entry, 0)

    asyncio.run(exercise())
    assert not errors
    assert results
    assert entry.options["scene_bindings"]["0"]["actions"] == ACTIONS
    assert runs == [{"scene_index": 0, "scene_name": "Movie"}]


def test_existing_scene_entity_binding_loads_as_actions(studio):
    scenes = studio.studio_scenes
    row = scenes.Scene(3, "Sleep", 21, 6)
    result = scenes._result({3: row}, {"3": {"scene": vars(row), "entity_id": "script.sleep"}})
    assert result["scenes"][0]["actions"] == [
        {"action": "script.turn_on", "target": {"entity_id": "script.sleep"}}
    ]


def test_ir_slot_zero_stays_visible_and_refresh_loads_its_profile(studio):
    physical = studio.studio_physical
    remote_id = "01-202610150103-68095715"
    device_id = bytes.fromhex("01141a0a0f01034409390f")
    table = [(0, 0x18, physical.c.CTRL_IR, device_id)]
    remotes = []

    assert asyncio.run(physical._adopt_ir_remotes(None, table, remotes, [])) == 1
    (remote,) = remotes
    assert remote["index"] == 0
    assert remote["name"] == "IR remote (slot 0)"
    assert remote["ir_profile_pending"]
    assert physical._drop_absent_remotes(table, remotes) == 0
    stable_id = remote["remote_id"]

    async def query_ir(ids, _source):
        assert ids == [remote_id]
        return [{"code": "AQID", "keyMap": "1:0:3"}]

    cloud = types.SimpleNamespace(get_ir_remotes=query_ir)
    metadata = [{"remoteID": remote_id, "remoteName": "IR appliance"}]
    assert asyncio.run(physical._adopt_ir_remotes(cloud, table, remotes, metadata)) == 0
    assert remotes == [remote]
    assert remote["remote_id"] == stable_id
    assert remote["name"] == "IR appliance"
    assert "ir_profile_pending" not in remote
    assert bytes.fromhex(remote["physical_packets"][0])[7:9] == b"\x00\x18"


def test_bridge_address_only_status_uses_cached_adapter(studio, monkeypatch):
    from switchbot_urc.client import UrcClient

    def unexpected_sysfs_read(*_args):
        pytest.fail("bridge identity lookup must not read sysfs")

    monkeypatch.setattr(UrcClient, "_list_local_adapters", unexpected_sysfs_read)
    monkeypatch.setattr(UrcClient, "_adapter_sysfs_address", unexpected_sysfs_read)
    client = UrcClient(
        types.SimpleNamespace(address="B0:E9:FE:53:11:45"),
        types.SimpleNamespace(),
        local_adapter_addresses={"hci0": "dca6320f2d8a", "hci1": "8a881be01f92"},
    )

    client.prefer_adapter("", "8A:88:1B:E0:1F:92")

    assert client._preferred_adapter == "hci1"
    assert client._force_preferred_adapter


def test_bridge_refreshes_unknown_adapter_once_for_repeated_status(studio, monkeypatch):
    import importlib.util

    core = sys.modules["homeassistant.core"]
    for name in ("ServiceCall", "ServiceResponse", "SupportsResponse"):
        monkeypatch.setattr(core, name, object, raising=False)
    config_validation = types.ModuleType("homeassistant.helpers.config_validation")
    config_validation.boolean = bool
    config_validation.ensure_list = list
    config_validation.string = str
    monkeypatch.setitem(sys.modules, config_validation.__name__, config_validation)
    const = types.ModuleType("homeassistant.const")
    const.Platform = str
    monkeypatch.setitem(sys.modules, const.__name__, const)
    exceptions = types.ModuleType("homeassistant.exceptions")
    exceptions.ConfigEntryNotReady = RuntimeError
    exceptions.HomeAssistantError = RuntimeError
    monkeypatch.setitem(sys.modules, exceptions.__name__, exceptions)
    spec = importlib.util.spec_from_file_location(
        "switchbot_urc.integration_test", INTEGRATION / "__init__.py"
    )
    spec.submodule_search_locations = None
    integration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(integration)
    client = integration.UrcClient(
        types.SimpleNamespace(address="B0:E9:FE:53:11:45"), types.SimpleNamespace()
    )
    store = {"entry": {"client": client}}
    reads = []

    def read_adapters():
        reads.append(1)
        return {"hci2": "8a881be01f92"}

    monkeypatch.setattr(integration.UrcClient, "read_local_adapter_addresses", read_adapters)

    async def check():
        hass = types.SimpleNamespace(
            data={studio.DOMAIN: store},
            async_create_task=asyncio.create_task,
            async_add_executor_job=asyncio.to_thread,
        )
        status = {"adapter_address": "8A:88:1B:E0:1F:92"}
        integration._apply_bridge_identity(hass, status)
        integration._apply_bridge_identity(hass, status)
        await store["_bridge_adapter_refresh"]
        integration._apply_bridge_identity(hass, status)

    asyncio.run(check())
    assert reads == [1]
    assert client._preferred_adapter == "hci2"


def test_layout_apply_waits_for_other_studio_mutations(studio, monkeypatch):
    def resolve(*_args):
        resolved.append(True)
        raise ValueError("Stop before writing")

    resolved = []
    monkeypatch.setattr(studio.studio_physical, "resolve", resolve)
    hass = types.SimpleNamespace(data={})
    connection = types.SimpleNamespace(send_error=lambda *_: None)

    async def check():
        async with studio.studio_remotes.remote_management_lock(hass):
            task = asyncio.create_task(studio.studio_physical.ws_physical_apply(
                hass, connection, {"id": 1, "entry_id": "entry"}
            ))
            await asyncio.sleep(0)
            assert not resolved
        await task
        assert resolved == [True]

    asyncio.run(check())


def test_studio_logs_a_failed_identity_repair(studio, monkeypatch, caplog):
    def repair_failed(*_args):
        raise ValueError("invalid stored identity")

    monkeypatch.setattr(studio.studio_remotes, "ensure_distinct_identities", repair_failed)
    hass = types.SimpleNamespace(data={})
    entry = types.SimpleNamespace(entry_id="entry")

    studio._repair_identities(hass, entry)

    assert "could not give every remote its own identity" in caplog.text
    assert "invalid stored identity" in caplog.text


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
