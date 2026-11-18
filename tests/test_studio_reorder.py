"""Reordering the remote's tiles with the official sortDevice command (0F 62 0A)."""
import pytest

from conftest import INTEGRATION, load
from test_studio_matter import make, run, studio, table_response  # noqa: F401  (studio is a fixture)

commands = load(INTEGRATION / "commands.py")

ROWS = [
    (0, 0x18, commands.CTRL_IR, bytes.fromhex("01141a0a0f01034409390f")),
    (1, 0x02, commands.CTRL_IR, bytes.fromhex("01141a0a0e17030b1f4d5b")),
    (2, 0xF2, commands.CTRL_HID, bytes.fromhex("5464379317020000000000")),
    (3, 0x72, commands.CTRL_NATIVE, bytes.fromhex("911fe01b888a0000000000")),
    (4, 0x72, commands.CTRL_NATIVE, bytes.fromhex("921fe01671da0000000000")),
]


def test_command_layout_matches_what_the_firmware_parses():
    rows = [(1, 0x72, 0, ROWS[3][3]), (0, 0x18, commands.CTRL_IR, ROWS[0][3])]
    packet = commands.build_sort_devices(rows)
    body = packet[7:]
    assert packet[:3] == bytes.fromhex("0f620a")
    assert packet[3:5] == len(body).to_bytes(2, "big") and len(body) == 1 + 14 * 2
    assert packet[5:7] == commands.crc16_modbus(body).to_bytes(2, "big")
    assert body[0] == 2
    # [destination slot][device type][id kind][id11]; IR is matched by id (1), the rest by MAC (0)
    assert body[1:15] == bytes([1, 0x72, 0]) + ROWS[3][3]
    assert body[15:29] == bytes([0, 0x18, 1]) + ROWS[0][3]


@pytest.mark.parametrize("rows, message", [
    ([(0, 0x72, 0, ROWS[3][3])], "between 2 and 25"),
    ([(0, 0x72, 0, ROWS[3][3]), (0, 0x72, 0, ROWS[4][3])], "exactly once"),
    ([(0, 0x72, 0, ROWS[3][3]), (1, 0x72, 0, ROWS[3][3])], "same id"),
    ([(0, 0x72, 0, b"\x01\x02"), (1, 0x72, 0, ROWS[4][3])], "11-byte"),
])
def test_a_list_that_is_not_a_clean_permutation_is_refused(rows, message):
    with pytest.raises(ValueError, match=message):
        commands.build_sort_devices(rows)


class Client:
    """Applies a sort command the way ARM 0x58ac does: the matching entry moves to its new slot."""

    def __init__(self, rows, *, reply=b"\x01", apply=True):
        self.rows, self.sent, self.reply, self.apply = list(rows), [], reply, apply

    async def query(self, subcommand):
        assert subcommand == 7
        return table_response(self.rows)

    async def send_command_with_preflight_query(self, command, *, subcommand, preflight_check):
        assert preflight_check(table_response(self.rows)), "the preflight must see the table the panel saw"
        self.sent.append(command)
        if self.reply == b"\x01" and self.apply:
            count = command[7]
            moved = []
            for i in range(count):
                record = command[8 + 14 * i:8 + 14 * (i + 1)]
                dest, ident = record[0], record[3:]
                row = next(r for r in self.rows if r[3] == ident)
                moved.append((dest, row[1], row[2], row[3]))
            self.rows = sorted(moved)
        return table_response(self.rows), self.reply


def msg(order, rows=ROWS):
    return {"id": 1, "entry_id": "entry", "order": order,
            "expected": [{"slot": r[0], "device_type": r[1], "control_type": r[2], "device_id": r[3].hex()}
                         for r in rows]}


def setup(studio, rows=ROWS, remotes=(), **kwargs):
    client = Client(rows, **kwargs)
    hass, entry, connection, out = make(studio, client, list(remotes))
    hass.data["switchbot_urc"]["entry"]["client"] = client
    return hass, entry, connection, out, client


def reorder(studio, hass, connection, message):
    run(studio.studio_remotes.ws_reorder_table(hass, connection, message))


def test_reorder_sends_one_command_reads_the_table_back_and_moves_saved_records(studio):
    remote = {"index": 4, "name": "Second strip", "device_type": "STRIP",
              "device_id": "DA:71:16:E0:1F:92", "remote_id": "abcd1234", "buttons": []}
    hass, entry, connection, out, client = setup(studio, remotes=[remote])
    # move the last tile to the top
    reorder(studio, hass, connection, msg([4, 0, 1, 2, 3]))
    assert out["errors"] == []
    assert len(client.sent) == 1
    assert [r[3] for r in client.rows] == [ROWS[4][3], ROWS[0][3], ROWS[1][3], ROWS[2][3], ROWS[3][3]]
    assert entry.options["remotes"][0]["index"] == 0  # the saved record followed its tile
    assert [row["slot"] for row in out["results"][0]["rows"]] == [0, 1, 2, 3, 4]


def test_a_table_that_changed_since_the_panel_read_it_is_never_reordered(studio):
    hass, entry, connection, out, client = setup(studio)
    stale = [r for r in ROWS[:4]] + [(4, 0x72, 0, bytes.fromhex("aa1fe01671da0000000000"))]
    reorder(studio, hass, connection, msg([1, 0, 2, 3, 4], stale))
    assert out["errors"] and "read it again" in out["errors"][0][1]
    assert client.sent == []


def test_only_clean_changes_are_sent(studio):
    hass, entry, connection, out, client = setup(studio)
    reorder(studio, hass, connection, msg([0, 1, 2, 3, 4]))
    assert out["errors"] and "unchanged" in out["errors"][0][1]
    reorder(studio, hass, connection, msg([1, 0, 2, 3]))
    assert "exactly once" in out["errors"][1][1]
    assert client.sent == []


def test_rows_sharing_a_bluetooth_address_cannot_be_ordered(studio):
    twin = bytes.fromhex("911fe01b888a0100000000")  # same six-byte address as slot 3, other tail
    rows = ROWS[:4] + [(4, 0x72, commands.CTRL_NATIVE, twin)]
    hass, entry, connection, out, client = setup(studio, rows=rows)
    reorder(studio, hass, connection, msg([1, 0, 2, 3, 4], rows))
    assert out["errors"] and "share one Bluetooth address" in out["errors"][0][1]
    assert client.sent == []


def test_a_rejected_or_ignored_order_is_reported(studio):
    hass, entry, connection, out, client = setup(studio, reply=b"\x02")
    reorder(studio, hass, connection, msg([1, 0, 2, 3, 4]))
    assert out["errors"] and "rejected" in out["errors"][0][1]

    hass, entry, connection, out, client = setup(studio, apply=False)
    reorder(studio, hass, connection, msg([1, 0, 2, 3, 4]))
    assert out["errors"] and "did not take the new order" in out["errors"][0][1]
