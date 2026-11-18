"""Studio's text remote: create, caption rewrite, serialisation and the press event."""
import asyncio
import importlib.util
import sys
import types

import pytest

from conftest import INTEGRATION, load
from test_studio_actions import _stub_homeassistant

commands = load(INTEGRATION / "commands.py")
matter = load(INTEGRATION / "matter_text.py")


@pytest.fixture(scope="module")
def studio():
    _stub_homeassistant()
    package = "switchbot_urc"
    if package not in sys.modules:
        pkg = types.ModuleType(package)
        pkg.__path__ = [str(INTEGRATION)]
        sys.modules[package] = pkg
    for name in [n for n in sys.modules if n.startswith(f"{package}.") and n.split(".")[1].startswith("studio")]:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(f"{package}.studio", INTEGRATION / "studio.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{package}.studio"] = module
    try:
        spec.loader.exec_module(module)
    except Exception as err:  # noqa: BLE001
        pytest.skip(f"studio.py needs more of Home Assistant than is stubbed: {err}")
    return module


def table_response(rows):
    body = bytes([len(rows)])
    for slot, device_type, control, identity in rows:
        body += bytes([slot, device_type, control]) + identity
    return b"\x01\0\0\0" + len(body).to_bytes(2, "big") + b"\0\0" + body


class FakeRemote:
    """Stores what the create command installs, like the device table does."""

    def __init__(self, rows, *, keep_type=True, reply=b"\x01"):
        self.rows = list(rows)
        self.sent = []
        self.keep_type = keep_type
        self.reply = reply

    async def query(self, subcommand):
        assert subcommand == 7
        return table_response(self.rows)

    async def send_command(self, packet):
        self.sent.append(packet)
        body = packet[7:]
        slot, device_type, control = body[0], body[1], body[2]
        identity = body[5:16]
        self.rows = [row for row in self.rows if row[0] != slot]
        if self.reply == b"\x01":
            self.rows.append((slot, device_type if self.keep_type else 0x72, control, identity))
        return self.reply


def make(studio, client, remotes=()):
    entry = types.SimpleNamespace(
        entry_id="entry", domain="switchbot_urc", title="Remote",
        data={"address": "B0:E9:FE:53:11:45"}, options={"remotes": list(remotes)},
    )
    hass = types.SimpleNamespace(
        data={"switchbot_urc": {"entry": {"client": client}}}, states={},
        config_entries=types.SimpleNamespace(
            async_get_entry=lambda _: entry,
            async_entries=lambda _: [entry],
            async_update_entry=lambda item, *, options: setattr(item, "options", options),
        ),
    )
    out = {"results": [], "errors": []}
    connection = types.SimpleNamespace(
        send_result=lambda _, payload=None: out["results"].append(payload),
        send_error=lambda _, code, message: out["errors"].append((code, message)),
    )
    return hass, entry, connection, out


NATIVE_ROW = (0, 0x72, 0, bytes.fromhex("1571da7d1a000000000000"))
CAPTIONS = ["Lamp", "Fan", "Music", "Scene D"]


def run(coro):
    return asyncio.run(coro)


def test_create_writes_the_app_packet_and_verifies_the_table(studio):
    client = FakeRemote([NATIVE_ROW])
    hass, entry, connection, out = make(studio, client)
    msg = {"id": 1, "entry_id": "entry", "name": "Accessory", "captions": CAPTIONS}
    run(studio.studio_matter.ws_save_matter(hass, connection, msg))
    assert out["errors"] == []
    remote = entry.options["remotes"][0]
    packet = client.sent[0]
    assert packet[:3] == bytes.fromhex("0f6206")
    assert packet[7] == 1 and packet[8:11] == bytes([0x27, 3, 0])
    assert remote["device_type"] == "MATTER_TEXT" and remote["matter_captions"] == CAPTIONS
    assert remote["index"] == 1
    assert out["results"][0]["slot"] == 1
    assert remote["device_id"].startswith("4d54")


def test_create_fails_loudly_when_the_remote_rewrites_the_type(studio):
    client = FakeRemote([NATIVE_ROW], keep_type=False)
    hass, entry, connection, out = make(studio, client)
    run(studio.studio_matter.ws_save_matter(hass, connection, {
        "id": 1, "entry_id": "entry", "name": "Accessory", "captions": CAPTIONS}))
    assert out["errors"] and "Matter type" in out["errors"][0][1]
    assert entry.options["remotes"] == []


def test_rejected_write_is_reported_and_nothing_is_saved(studio):
    client = FakeRemote([NATIVE_ROW], reply=b"\x05")
    hass, entry, connection, out = make(studio, client)
    run(studio.studio_matter.ws_save_matter(hass, connection, {
        "id": 1, "entry_id": "entry", "name": "Accessory", "captions": CAPTIONS}))
    assert out["errors"] and entry.options["remotes"] == []


def test_only_one_text_remote_and_caption_edit_keeps_slot_and_id(studio):
    client = FakeRemote([NATIVE_ROW])
    hass, entry, connection, out = make(studio, client)
    base = {"entry_id": "entry", "name": "Accessory", "captions": CAPTIONS}
    run(studio.studio_matter.ws_save_matter(hass, connection, {"id": 1, **base}))
    run(studio.studio_matter.ws_save_matter(hass, connection, {"id": 2, **base}))
    assert "already has a text remote" in out["errors"][0][1]

    remote_id = entry.options["remotes"][0]["remote_id"]
    first = client.sent[0]
    run(studio.studio_matter.ws_save_matter(hass, connection, {
        "id": 3, "entry_id": "entry", "remote_id": remote_id,
        "captions": ["Lamp", "Fan", "Radio", "Scene D"]}))
    assert len(out["errors"]) == 1
    second = client.sent[1]
    assert second[7:7 + 91] == first[7:7 + 91]  # slot, type, id and name unchanged
    assert second != first
    assert entry.options["remotes"][0]["matter_captions"][2] == "Radio"


def test_serialised_remote_exposes_captions_and_a_to_d_buttons(studio, monkeypatch):
    remote = {"index": 1, "name": "Accessory", "device_type": "MATTER_TEXT",
              "device_id": "4d5400000001", "remote_id": "abcd1234", "buttons": [],
              "matter_captions": CAPTIONS}
    hass, entry, _, _ = make(studio, FakeRemote([]), [remote])
    monkeypatch.setattr(studio, "_repair_identities", lambda *_: None)
    monkeypatch.setattr(studio.er, "async_get", lambda _: types.SimpleNamespace(
        async_get_entity_id=lambda *_: None))
    row = studio._serialize_entry(hass, entry)["remotes"][0]
    assert row["matter"] == {"captions": CAPTIONS, "max_bytes": 31}
    buttons = row["pages"][0]["buttons"]
    assert [b["position"] for b in buttons] == list("ABCD")
    assert [b["button_id"] for b in buttons] == ["p0_k0", "p0_k1", "p0_k2", "p0_k3"]
    assert [b["button_function"] for b in buttons] == [1, 2, 3, 4]
    assert row["reachability"]["level"] == "full" and "advertisements" in row["reachability"]["text"]
    assert row["can_move"] is False


def test_press_fires_the_standard_button_event_for_the_text_remote(studio, monkeypatch):
    fired = []
    registered = {}
    remote = {"index": 1, "name": "Accessory", "device_type": "MATTER_TEXT",
              "device_id": "4d5400000001", "remote_id": "abcd1234", "buttons": [],
              "matter_captions": CAPTIONS}
    hass, entry, _, _ = make(studio, FakeRemote([]), [remote])
    hass.bus = types.SimpleNamespace(async_fire=lambda name, data: fired.append((name, data)))
    module = studio.studio_matter
    monkeypatch.setattr(module.bluetooth, "async_last_service_info", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(module.bluetooth, "async_register_callback",
                        lambda hass_, callback, matcher, mode: registered.setdefault("cb", callback),
                        raising=False)
    monkeypatch.setattr(module.bluetooth, "BluetoothCallbackMatcher", lambda **k: k, raising=False)
    monkeypatch.setattr(module.bluetooth, "BluetoothScanningMode",
                        types.SimpleNamespace(PASSIVE="passive"), raising=False)
    module.listen_for_matter(hass, entry, {})
    receive = registered["cb"]

    def packet(sequence, *counters, category=3):
        payload = bytearray(17)
        payload[:6] = bytes.fromhex("b0e9fe531145")
        payload[6], payload[10] = sequence, category
        payload[13:17] = bytes(counters)
        return types.SimpleNamespace(manufacturer_data={0x0969: bytes(payload)})

    receive(packet(1, 0x21, 0x21, 0x21, 0x21), None)
    assert fired == []
    receive(packet(2, 0x21, 0x21, 0x22, 0x21), None)
    name, data = fired[0]
    assert name == "switchbot_urc_button"
    assert (data["remote_id"], data["button_id"], data["button"], data["button_name"]) == (
        "abcd1234", "p0_k2", "C", "Music")
    assert data["address"] == "B0:E9:FE:53:11:45" and data["button_function"] == 3
    # A press from a different physical remote is ignored.
    other = bytearray(packet(3, 0x21, 0x21, 0x23, 0x21).manufacturer_data[0x0969])
    other[:6] = bytes.fromhex("112233445566")
    receive(types.SimpleNamespace(manufacturer_data={0x0969: bytes(other)}), None)
    assert len(fired) == 1
