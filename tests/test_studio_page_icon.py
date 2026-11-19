"""Studio rewrites the wire icon of an installed HID remote from its saved pages."""
import types

from conftest import INTEGRATION, load
from test_studio_matter import make, run, studio, table_response  # noqa: F401  (studio is a fixture)

commands = load(INTEGRATION / "commands.py")

DEVICE_ID = "0200000e0e0f"


def hid_page(icon=0, slot=2):
    return commands.build_create(
        remote_index=slot, device_type=0xF2, control_type=commands.CTRL_HID, control_mode=0,
        icon=icon, device_id=DEVICE_ID, name="HID", ble_key_type=6, keys=[])


class FakeClient:
    def __init__(self, rows):
        self.rows, self.sent, self.reply = rows, [], b"\x01"

    async def query(self, subcommand):
        assert subcommand == 7
        return table_response(self.rows)

    async def send_command_sequence(self, packets, **kwargs):
        self.sent.extend(packets)
        return [self.reply for _ in packets]


def setup(studio, *, slot=2, row_slot=2, packets=None):
    packets = [hid_page(slot=slot).hex()] if packets is None else packets
    remote = {"index": slot, "name": "HID", "device_type": "UNIVERSAL_BLE", "device_id": DEVICE_ID,
              "remote_id": "hid1", "icon": "light", "buttons": [], "physical_packets": packets}
    row = (row_slot, 0xF2, commands.CTRL_HID, commands.id_to_bytes(DEVICE_ID))
    client = FakeClient([row])
    hass, entry, connection, out = make(studio, client, [remote])
    hass.data["switchbot_urc"]["entry"]["client"] = client
    return hass, entry, connection, out, client


def update(studio, hass, connection, icon):
    run(studio.studio_manage.ws_page_icon_update(hass, connection, {
        "id": 1, "entry_id": "entry", "remote_id": "hid1", "icon": icon}))


def test_hid_icon_is_rewritten_in_place_and_remembered(studio):
    hass, entry, connection, out, client = setup(studio)
    update(studio, hass, connection, "washer")
    assert out["errors"] == []
    assert len(client.sent) == 1
    assert client.sent[0] == commands.rewrite_native_page_icon(hid_page(), 14)
    assert client.sent[0][7] == 2  # same slot
    saved = entry.options["remotes"][0]
    assert (saved["icon"], saved["icon_code"]) == ("washer", 14)
    assert saved["physical_packets"] == [client.sent[0].hex()]

    update(studio, hass, connection, "device")
    assert client.sent[1] == hid_page()  # icon 0 gives the type's own picture back


def test_stale_saved_pages_are_never_sent(studio):
    hass, entry, connection, out, client = setup(studio, slot=1, row_slot=2)
    update(studio, hass, connection, "washer")
    assert out["errors"] and "refresh" in out["errors"][0][1]
    assert client.sent == []


def test_missing_pages_and_rejections_are_reported(studio):
    hass, entry, connection, out, client = setup(studio, packets=[])
    update(studio, hass, connection, "washer")
    assert out["errors"] and "no saved pages" in out["errors"][0][1]

    hass, entry, connection, out, client = setup(studio)
    client.reply = b"\x05"
    update(studio, hass, connection, "washer")
    assert out["errors"] and "rejected" in out["errors"][0][1]
    assert "icon_code" not in entry.options["remotes"][0]


def test_ir_install_passes_the_chosen_icon_to_the_profile_and_keeps_its_own_otherwise():
    import asyncio

    from switchbot_urc import install as package_install  # noqa: PLC0415

    class Profile:
        remote_id = bytes.fromhex("0300000e0e0e0e0e0e0e0e")
        device_type = 2
        icon = 4
        code_bank = b""
        key = "demo"
        remote_id_text = ""

        def __init__(self):
            self.kwargs = None

        def build_install(self, **kwargs):
            self.kwargs = kwargs
            page = commands.build_ir_pages(
                remote_index=kwargs["remote_index"], device_type=2, remote_id=self.remote_id,
                name="TV", key_map=[(1, 0, 10)], icon=kwargs.get("icon", self.icon))[0]
            return [("ir_page_0", page, frozenset({1}))]

    class Client:
        async def query(self, _subcommand):
            return table_response([])

        async def send_command_sequence(self, commands_, **_kwargs):
            return [b"\x01" for _ in commands_]

    def run_install(**extra):
        profile = Profile()
        errors, _, record = asyncio.run(package_install.install_ir_profile(
            Client(), profile, name="TV", replace_existing=False, remotes=[], targets=[], **extra))
        return errors, profile.kwargs, record

    errors, kwargs, record = run_install(icon_name="washer")
    assert errors == {} and kwargs["icon"] == 14
    assert (record["icon"], record["icon_code"]) == ("washer", 14)

    errors, kwargs, record = run_install()
    assert errors == {} and "icon" not in kwargs
    assert record["icon_code"] == 4  # the profile's own icon
    # The sync boundary counts the remotes sent now (one), never the device-table size.
    assert kwargs["remote_count"] == 1

    async def three_remotes(self, _subcommand):
        return table_response([(slot, 0x72, 0, bytes([slot]) * 11) for slot in range(3)])

    Client.query = three_remotes
    errors, kwargs, _ = run_install()
    assert errors == {} and kwargs["remote_index"] == 3 and kwargs["remote_count"] == 1


def test_imported_ir_pages_are_never_rewritten_to_change_an_icon(studio):
    hass, entry, connection, out, client = setup(studio)
    entry.options["remotes"][0]["imported_from_cloud"] = True
    update(studio, hass, connection, "washer")
    assert out["errors"] and "imported from the SwitchBot account" in out["errors"][0][1]
    assert client.sent == []


def test_device_gives_back_the_icon_the_remote_had_before_studio_changed_it(studio):
    packets = [commands.rewrite_native_page_icon(hid_page(), 10).hex()]  # the remote started with icon 10
    hass, entry, connection, out, client = setup(studio, packets=packets)
    update(studio, hass, connection, "washer")
    saved = entry.options["remotes"][0]
    assert saved["icon_code"] == 14 and saved["icon_code_original"] == 10
    update(studio, hass, connection, "device")
    assert out["errors"] == []
    assert client.sent[1] == commands.rewrite_native_page_icon(hid_page(), 10)
    saved = entry.options["remotes"][0]
    assert (saved["icon"], saved["icon_code"], saved["icon_code_original"]) == ("tv", 10, 10)
    assert out["results"][-1]["icon_code"] == 10


def test_serialised_remotes_say_which_picture_type_default_or_original_gives_back(studio, monkeypatch):
    import types

    # An HID remote the app made with icon 10 (tv) and Studio then changed to the washer.
    changed = commands.rewrite_native_page_icon(hid_page(), 14).hex()
    hid = {"index": 2, "name": "HID", "device_type": "UNIVERSAL_BLE", "device_id": DEVICE_ID,
           "remote_id": "hid1", "icon": "washer", "buttons": [], "physical_packets": [changed],
           "icon_code_original": 10}
    matter = {"index": 3, "name": "Text", "device_type": "MATTER_TEXT", "device_id": "4d5400000001",
              "remote_id": "mt1", "buttons": [], "matter_captions": ["a", "b", "c", "d"], "icon_code": 14}
    hass, entry, _, _ = make(studio, FakeClient([]), [hid, matter])
    monkeypatch.setattr(studio, "_repair_identities", lambda *_: None)
    monkeypatch.setattr(studio.er, "async_get", lambda _: types.SimpleNamespace(
        async_get_entity_id=lambda *_: None))
    rows = {row["remote_id"]: row for row in studio._serialize_entry(hass, entry)["remotes"]}
    # "Original" is the remembered icon 10 (TV, picture 0x24), not the washer it shows now
    assert rows["hid1"]["icon"] == "washer" and rows["hid1"]["default_artwork_id"] == 0x24
    # the text remote's "Type default" is the firmware's own text-remote picture
    assert rows["mt1"]["default_artwork_id"] == 0x1B

