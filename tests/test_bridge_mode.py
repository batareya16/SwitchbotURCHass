"""Tests for choosing between the single-address and multi-address paths.

The add-on now decides this itself rather than being told by an option, so the decision has to
be right for a Bluetooth 4 radio, a Bluetooth 5 one, a hand-pinned list and a list that no
longer fits — all without a radio present.
"""
import pytest

from conftest import ADDON, load

pytestmark = pytest.mark.skipif(
    not (ADDON / "hci_multi.py").is_file(),
    reason="the bridge add-on is published as its own repository and is not checked out here",
)

hci = load(ADDON / "hci_multi.py", "urc_hci_multi") if (ADDON / "hci_multi.py").is_file() else None

OWN = "8A:88:1B:E0:1F:92"
SECOND = "DA:71:16:E0:1F:92"
THIRD = "C0:88:1B:E0:1F:92"


def test_fresh_controller_gets_a_deterministic_address_pool():
    assert hci.address_pool(OWN, [], 4) == [
        OWN, THIRD, "C1:88:1B:E0:1F:92", "C2:88:1B:E0:1F:92",
    ]


def test_custom_and_previously_active_addresses_keep_their_order():
    legacy = "8A:88:1B:E0:1F:91"
    seeds = [legacy, SECOND, "da-71-16-e0-1f-92", "nonsense", THIRD]
    assert hci.address_pool(OWN, seeds, 4) == [legacy, SECOND, THIRD, OWN]
    assert hci.address_pool(OWN, seeds, 3) == [legacy, SECOND, THIRD]


def test_startup_reports_only_addresses_the_controller_enabled(monkeypatch):
    monkeypatch.setattr(hci, "resolve_adapter", lambda _: ("hci0", 0, ""))
    seeds = ["8A:88:1B:E0:1F:91", SECOND, THIRD]
    server = hci.MultiAddressServer(
        "hci0", seeds, protocol_factory=None, device_factory=None,
        conn_min=6, conn_max=12, auto_fill=True,
    )
    enable_counts = []

    class Channel:
        def command(self, opcode, payload=b""):
            if opcode == hci.OP_READ_BD_ADDR:
                return hci.address_bytes(OWN)
            if opcode == hci.OP_LE_READ_BUFFER_SIZE:
                return b"\x1b\x00\x08"
            if opcode == hci.OP_LE_READ_ADV_SETS:
                return b"\x04"
            if opcode == hci.OP_LE_SET_EXT_ADV_ENABLE and payload[0]:
                enable_counts.append(payload[1])
                if payload[1] == 4:
                    raise hci.HciCommandError(opcode, hci.STATUS_CONNECTION_LIMIT)
            return b""

    server._initialise_controller(Channel())
    assert enable_counts == [4, 3]
    assert server.capabilities()["advertising_sets"] == 3
    assert server.capabilities()["serving"] == seeds
    assert server.serves_address(SECOND)
    assert not server.serves_address(OWN)
    server.channel = None
    assert not server.serves_address(SECOND)
