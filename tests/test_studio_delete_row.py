"""Studio deletes a device-table row it has no record of, after proving the device still holds it."""
from conftest import INTEGRATION, load
from test_studio_matter import make, run, studio, table_response  # noqa: F401  (studio is a fixture)

commands = load(INTEGRATION / "commands.py")

ROWS = [
    (0, 0x18, commands.CTRL_IR, bytes.fromhex("01141a0a0f01034409390f")),
    (1, 0x72, commands.CTRL_NATIVE, bytes.fromhex("911fe01b888a0000000000")),
    (2, 0x02, commands.CTRL_NATIVE, bytes.fromhex("100e0e0000020000000000")),
]


class Client:
    def __init__(self, rows, *, drops=True, reply=b"\x01"):
        self.rows, self.sent, self.drops, self.reply = list(rows), [], drops, reply

    async def query(self, subcommand):
        assert subcommand == 7
        return table_response(self.rows)

    async def send_command_with_preflight_query(self, command, *, subcommand, preflight_check):
        assert preflight_check(table_response(self.rows)), "the preflight must see the row"
        self.sent.append(command)
        if self.drops and self.reply == b"\x01":
            slot = command[4]
            self.rows = [row for row in self.rows if row[0] != slot]
            self.rows = [(i, *row[1:]) for i, row in enumerate(self.rows)]  # the firmware compacts
        return table_response(self.rows), self.reply


def delete(studio, hass, connection, row):
    run(studio.studio_remotes.ws_delete_table_row(hass, connection, {
        "id": 1, "entry_id": "entry", "slot": row[0], "device_type": row[1],
        "control_type": row[2], "device_id": row[3].hex()}))


def setup(studio, remotes=(), **kwargs):
    client = Client(ROWS, **kwargs)
    hass, entry, connection, out = make(studio, client, list(remotes))
    hass.data["switchbot_urc"]["entry"]["client"] = client
    return hass, entry, connection, out, client


def test_row_without_a_studio_record_is_deleted_with_the_exact_delete_command(studio):
    hass, entry, connection, out, client = setup(studio)
    delete(studio, hass, connection, ROWS[2])
    assert out["errors"] == []
    assert client.sent == [commands.build_delete(
        remote_index=2, device_type=0x02, control_type=0, device_id=ROWS[2][3].hex())]
    assert out["results"][0] == {"slot": 2, "rows": 2, "forgot_record": False}


def test_a_row_that_changed_since_the_panel_read_it_is_not_deleted(studio):
    hass, entry, connection, out, client = setup(studio)
    stale = (2, 0x02, commands.CTRL_NATIVE, bytes.fromhex("100e0e0000990000000000"))
    delete(studio, hass, connection, stale)
    assert out["errors"] and "no longer on the remote" in out["errors"][0][1]
    assert client.sent == []


def test_a_rejected_or_ignored_delete_is_reported(studio):
    hass, entry, connection, out, client = setup(studio, reply=b"\x05")
    delete(studio, hass, connection, ROWS[2])
    assert out["errors"] and "rejected" in out["errors"][0][1]

    hass, entry, connection, out, client = setup(studio, drops=False)
    delete(studio, hass, connection, ROWS[2])
    assert out["errors"] and "still lists" in out["errors"][0][1]


def test_the_saved_record_of_the_deleted_row_is_forgotten_with_its_actions(studio):
    record = {"index": 2, "name": "Test", "device_type": "STRIP", "remote_id": "abcd1234",
              "device_id": "02000e0e0e10", "physical_device_id": "02:00:00:0E:0E:10",
              "buttons": []}
    hass, entry, connection, out, client = setup(studio, remotes=[record])
    entry.options["bindings"] = [{"remote_id": "abcd1234", "buttons": {}}]
    delete(studio, hass, connection, ROWS[2])
    assert out["errors"] == []
    assert out["results"][0]["forgot_record"] is True
    assert entry.options["remotes"] == [] and entry.options["bindings"] == []
