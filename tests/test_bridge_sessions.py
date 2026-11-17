"""Bridge reception, address persistence, and raw HCI management tests."""
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


def test_startup_preserves_the_same_saved_pool_through_a_restart(bridge, tmp_path, monkeypatch):
    path = tmp_path / "addresses.json"
    monkeypatch.setattr(bridge, "_ADDRESS_STORE", path)
    monkeypatch.setattr(bridge.signal, "signal", lambda *_: None)
    radio = bridge.hci_multi
    own = "8A:88:1B:E0:1F:92"
    manual = "DA:71:16:E0:1F:93"
    adapter = ["hci0", 0]
    limit = [4]
    monkeypatch.setattr(radio, "resolve_adapter", lambda _: (*adapter, own))
    monkeypatch.setattr(radio, "probe_capabilities", lambda _: (True, 4))

    class Channel:
        def command(self, opcode, payload=b""):
            if opcode == radio.OP_READ_BD_ADDR:
                return radio.address_bytes(own)
            if opcode == radio.OP_LE_READ_BUFFER_SIZE:
                return b"\x1b\x00\x08"
            if opcode == radio.OP_LE_READ_ADV_SETS:
                return b"\x04"
            if opcode == radio.OP_LE_SET_EXT_ADV_ENABLE and payload[0] and payload[1] > limit[0]:
                raise radio.HciCommandError(opcode, radio.STATUS_CONNECTION_LIMIT)
            return b""

    def simulated_start(server):
        server._initialise_controller(Channel())

    monkeypatch.setattr(radio.MultiAddressServer, "start", simulated_start)

    class StartupComplete(Exception):
        pass

    class Broker:
        def set_control_handler(self, handler, **kwargs):
            self.serving = kwargs["capabilities"]["serving"]
            raise StartupComplete

    def start(configured):
        broker = Broker()
        with pytest.raises(StartupComplete):
            bridge.run_multi_address(adapter[0], configured, broker, "")
        return broker.serving

    first = start([manual])
    assert first == [manual, own, "C0:88:1B:E0:1F:92", "C1:88:1B:E0:1F:92"]
    assert json.loads(path.read_text()) == first

    adapter[:] = ["hci1", 1]
    assert start([]) == first

    limit[0] = 3
    assert start([]) == first[:3]
    assert json.loads(path.read_text()) == first

    limit[0] = 4
    assert start([]) == first


def test_interrupted_address_write_leaves_the_previous_pool(bridge, tmp_path, monkeypatch):
    path = tmp_path / "addresses.json"
    monkeypatch.setattr(bridge, "_ADDRESS_STORE", path)
    first = ["8A:88:1B:E0:1F:92"]
    bridge._remember_addresses(first)

    def fail_replace(*_args):
        raise OSError("simulated interruption")

    monkeypatch.setattr(type(path), "replace", fail_replace)
    bridge._remember_addresses([*first, "DA:71:16:E0:1F:93"])
    assert bridge._recall_addresses() == first
    assert list(tmp_path.iterdir()) == [path]


PRESS = bytes.fromhex("57f00306bb30e0eb030008012c")


def test_open_press_is_acknowledged_before_mqtt_and_deduplicated(bridge, monkeypatch):
    events = []
    monkeypatch.setattr(bridge.time, "monotonic", lambda: 100.0)
    device = bridge.SwitchBotDevice(
        lambda ack: events.append(ack),
        lambda label, raw, remote_id, slot: events.append((label, raw, remote_id, slot)),
    )

    device.on_write(PRESS)
    device.on_write(PRESS)

    assert events == [
        b"\x01",
        ("BRIGHTER", PRESS.hex(), "bb30e0eb", 3),
        b"\x01",
    ]


@pytest.mark.parametrize("mode", ["raw", "timeout", "invalid", "rejected", "command", "empty"])
def test_mqtt_all_management_stays_on_raw_hci(bridge, monkeypatch, mode):
    published = []
    ready = threading.Event()
    actions = []
    raw_calls = []
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
    monkeypatch.setattr(bridge.time, "sleep", lambda _: None)
    mqtt.set_control_handler(lambda action: actions.append(action) or True,
                             adapter_name="hci0", adapter_address="8A:88:1B:E0:1F:92",
                             management_runner=reader)
    payload = {"request_id": "read-1", "address": "B0:E9:FE:53:11:45", "key": bytes(range(16)).hex(),
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
    assert not actions


def test_startup_exits_when_raw_hci_is_unsupported(bridge, monkeypatch):
    monkeypatch.setenv("ADAPTER", "hci0")
    monkeypatch.setattr(bridge, "Mqtt", lambda *_: None)
    monkeypatch.setattr(bridge.hci_multi, "resolve_adapter", lambda _: ("hci0", 0, ""))
    monkeypatch.setattr(bridge.hci_multi, "probe_capabilities", lambda _: (False, 1))

    with pytest.raises(SystemExit, match="raw HCI bridge on hci0:.*requires a compatible Bluetooth 5"):
        bridge.main()


def test_startup_reports_controller_error_without_fallback(bridge, monkeypatch):
    monkeypatch.setenv("ADAPTER", "hci0")
    monkeypatch.setattr(bridge, "Mqtt", lambda *_: None)
    monkeypatch.setattr(bridge.hci_multi, "resolve_adapter", lambda _: ("hci0", 0, ""))
    monkeypatch.setattr(bridge.hci_multi, "probe_capabilities", lambda _: (True, 4))

    def fail_to_claim(_server):
        raise OSError("controller busy")

    monkeypatch.setattr(bridge.hci_multi.MultiAddressServer, "start", fail_to_claim)
    with pytest.raises(SystemExit, match="raw HCI bridge on hci0: controller busy"):
        bridge.main()
