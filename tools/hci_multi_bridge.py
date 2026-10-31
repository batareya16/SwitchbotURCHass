#!/usr/bin/env python3
"""Serve the WoRWS native channel on several addresses from one controller.

`spike_multi_address.py` proved the hard half: a Bluetooth 5 controller will advertise one
address per advertising set, and the remote connects to it. It stopped there, so the remote
hung up after a couple of seconds with reason 0x13 — nothing answered its ATT discovery.

This adds the other half. Taking the controller on the HCI user channel means the kernel's
Bluetooth stack is detached from it, so everything it used to do has to happen here:

  * HCI commands and events, as in the spike
  * ACL data in both directions, with fragment reassembly and controller buffer credits
  * L2CAP on the fixed ATT channel, CID 0x0004 — fixed CIDs need no channel setup, which is
    why this is a few hundred lines rather than a protocol stack

ATT itself is not reimplemented: `FastAttProtocol` from the add-on is already a pure
`handle(pdu) -> bytes | None` with a `sender` callable, and it carries every hard-won detail
about what WoRWS expects during its two-second discovery budget. It is imported from
bridge.py as-is, one instance per connection.

There is no LE pairing anywhere in this path: the remote encrypts at the application layer,
so no SMP is needed.

    python3 hci_multi_bridge.py hci1 8A:88:1B:E0:1F:92 DA:71:16:E0:1F:92

WARNING: the adapter belongs to this script while it runs, and is handed back on exit.
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import pathlib
import struct
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from spike_multi_address import (  # noqa: E402  - a sibling script, not a package
    EV_CMD_COMPLETE,
    EV_DISCONN_COMPLETE,
    EV_LE_META,
    LE_ADV_SET_TERMINATED,
    LE_CONNECTION_COMPLETE,
    LE_ENHANCED_CONNECTION_COMPLETE,
    OP_LE_SET_EXT_ADV_ENABLE,
    OP_LE_SET_EVENT_MASK,
    OP_READ_BD_ADDR,
    OP_RESET,
    OP_SET_EVENT_MASK,
    UserChannel,
    configure_set,
    set_powered,
)

HCI_ACL_PKT = 0x02
EV_NUM_COMPLETED_PACKETS = 0x13
OP_LE_READ_BUFFER_SIZE = 0x2002
OP_READ_BUFFER_SIZE = 0x1005
ATT_CID = 0x0004

# Packet Boundary flag in the ACL handle field.
PB_FIRST = 0x00    # first fragment of a higher-layer message, host to controller
PB_CONTINUE = 0x01

_LOG = logging.getLogger("multi-bridge")


def load_bridge():
    """Import the add-on module without installing it as a package.

    Both halves of the device side come from there: `FastAttProtocol` answers ATT, and
    `SwitchBotDevice` answers the application protocol on top of it — the get-random handshake
    the remote sends first, the AES-CTR decryption of the command that follows, and the one-byte
    acknowledgement the remote waits for before it stops retrying.
    """
    here = pathlib.Path(__file__).resolve().parent
    for candidate in (
        here / "bridge.py",
        here.parent / "addons" / "switchbot_urc_bridge" / "bridge.py",
        # Where the add-on's Dockerfile puts it inside its own image.
        pathlib.Path("/bridge.py"),
    ):
        if candidate.is_file():
            # bridge.py now imports its own hci_multi module, so its directory has to be
            # importable before it is executed.
            if str(candidate.parent) not in sys.path:
                sys.path.insert(0, str(candidate.parent))
            spec = importlib.util.spec_from_file_location("urc_bridge", candidate)
            module = importlib.util.module_from_spec(spec)
            # bridge.py reads its configuration from the environment at import time; give it
            # enough to import cleanly without starting anything.
            os.environ.setdefault("ADAPTER", "hci0")
            os.environ.setdefault("DISCOVERY", "false")
            try:
                spec.loader.exec_module(module)
            except ModuleNotFoundError as err:
                raise SystemExit(
                    f"bridge.py needs {err.name}, which is missing here. Run this inside the\n"
                    f"add-on's own image, or install it: pip3 install --break-system-packages "
                    f"{err.name}"
                ) from None
            return module
    raise SystemExit(
        "Could not find bridge.py, which holds the ATT layer this script serves.\n"
        "Either copy bridge.py next to this script, or run this inside the add-on's own\n"
        "image, where it lives at /bridge.py and the cryptography module is installed."
    )


class Link:
    """One live connection: ACL reassembly plus the ATT state machine serving it."""

    def __init__(self, handle: int, address: str, protocol) -> None:
        self.handle = handle
        self.address = address
        self.protocol = protocol
        self.pending = bytearray()
        self.expected = 0
        self.device = None

    def feed(self, payload: bytes, first: bool):
        """Reassemble L2CAP B-frames; yield each complete ATT PDU."""
        if first:
            if self.pending:
                _LOG.warning("dropping %d incomplete bytes on handle %d",
                             len(self.pending), self.handle)
            self.pending = bytearray(payload)
            if len(self.pending) >= 4:
                self.expected = struct.unpack_from("<H", self.pending)[0] + 4
            else:
                self.expected = 0
        else:
            self.pending.extend(payload)
            if not self.expected and len(self.pending) >= 4:
                self.expected = struct.unpack_from("<H", self.pending)[0] + 4
        while self.expected and len(self.pending) >= self.expected:
            frame = bytes(self.pending[:self.expected])
            del self.pending[:self.expected]
            cid = struct.unpack_from("<H", frame, 2)[0]
            if cid == ATT_CID:
                yield frame[4:]
            else:
                # Nothing else is expected on this link; the kernel used to answer signalling
                # on CID 0x0005, and WoRWS has never needed it from the peripheral side.
                _LOG.debug("ignoring L2CAP CID 0x%04x on handle %d", cid, self.handle)
            self.expected = (
                struct.unpack_from("<H", self.pending)[0] + 4 if len(self.pending) >= 4 else 0
            )


class AclWriter:
    """Fragment ATT PDUs into ACL packets and respect the controller's buffer credits."""

    def __init__(self, channel: UserChannel, payload_size: int, credits: int) -> None:
        self.channel = channel
        self.payload_size = max(27, payload_size)
        self.credits = max(1, credits)
        self.inflight = 0

    def completed(self, count: int) -> None:
        self.inflight = max(0, self.inflight - count)

    def send(self, handle: int, data: bytes) -> None:
        frame = struct.pack("<HH", len(data), ATT_CID) + data
        boundary = PB_FIRST
        while frame:
            chunk, frame = frame[:self.payload_size], frame[self.payload_size:]
            header = handle | (boundary << 12)
            self.channel.sock.send(
                bytes([HCI_ACL_PKT]) + struct.pack("<HH", header, len(chunk)) + chunk)
            self.inflight += 1
            boundary = PB_CONTINUE
            if self.inflight >= self.credits:
                # Out of controller buffers: let events in, which is where the credits come
                # back. Dropping here instead would lose a command reply the remote waits for.
                self._drain()

    def _drain(self, timeout: float = 1.0) -> None:
        deadline = time.monotonic() + timeout
        while self.inflight >= self.credits and time.monotonic() < deadline:
            for code, params in self.channel.events(0.05):
                if code == EV_NUM_COMPLETED_PACKETS and params:
                    for index in range(params[0]):
                        _handle, count = struct.unpack_from("<HH", params, 1 + index * 4)
                        self.completed(count)


def read_buffer_size(channel: UserChannel) -> tuple[int, int]:
    """LE buffers if the controller has its own, otherwise the shared BR/EDR ones."""
    payload = channel.command(OP_LE_READ_BUFFER_SIZE)
    length, count = struct.unpack_from("<HB", payload)
    if length and count:
        return length, count
    payload = channel.command(OP_READ_BUFFER_SIZE)
    acl_length, _sco, acl_count, _sco_count = struct.unpack_from("<HBHH", payload)
    return acl_length, acl_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("adapter")
    parser.add_argument("addresses", nargs="+")
    parser.add_argument("--seconds", type=float, default=600.0)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--device-key", default=os.environ.get("DEVICE_KEY", "00112233445566778899aabbccddeeff"),
        help="the 32-hex device key, matching the add-on's own DEVICE_KEY")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s")
    bridge = load_bridge()
    try:
        device_key = bytes.fromhex(args.device_key)
        if len(device_key) != 16:
            raise ValueError
    except ValueError:
        print("--device-key must be exactly 32 hexadecimal characters")
        return 2
    index = int(args.adapter.removeprefix("hci"))

    if not args.yes:
        print(f"This takes {args.adapter} away from BlueZ for {args.seconds:.0f}s. "
              f"Continue? [y/N] ", end="", flush=True)
        if input().strip().lower() not in ("y", "yes"):
            return 1

    outcome = set_powered(index, False)
    if outcome != "ok":
        print(f"Could not power {args.adapter} down: {outcome}")
        return 1

    channel = None
    try:
        channel = UserChannel(index)
        channel.command(OP_RESET)
        channel.command(OP_SET_EVENT_MASK, bytes.fromhex("ffffffffffffff3f"))
        channel.command(OP_LE_SET_EVENT_MASK, bytes.fromhex("ffffffff00000000"))
        own_public = ":".join(
            f"{byte:02X}" for byte in reversed(channel.command(OP_READ_BD_ADDR)[:6]))
        payload_size, credits = read_buffer_size(channel)
        _LOG.info("%s: own public address %s, ACL payload %d B, %d buffers",
                  args.adapter, own_public, payload_size, credits)

        def same(a: str, b: str) -> bool:
            return a.replace(":", "").upper() == b.replace(":", "").upper()

        for handle, address in enumerate(args.addresses):
            configure_set(channel, handle, address, public=same(address, own_public))
            _LOG.info("set %d serving %s", handle, address)

        enable = bytes([0x01, len(args.addresses)])
        for handle in range(len(args.addresses)):
            enable += struct.pack("<BHB", handle, 0, 0)
        channel.command(OP_LE_SET_EXT_ADV_ENABLE, enable)

        writer = AclWriter(channel, payload_size, credits)
        links: dict[int, Link] = {}
        pending_address = {"value": None}
        deadline = time.monotonic() + args.seconds
        _LOG.info("serving ATT on %d address(es); press a native tile", len(args.addresses))

        while time.monotonic() < deadline:
            packet = channel.read(min(1.0, deadline - time.monotonic()))
            if packet is None:
                continue
            kind, body = packet
            if kind == HCI_ACL_PKT:
                header, length = struct.unpack_from("<HH", body)
                handle, boundary = header & 0x0FFF, (header >> 12) & 0x03
                link = links.get(handle)
                if link is None:
                    continue
                for pdu in link.feed(body[4:4 + length], boundary != PB_CONTINUE):
                    _LOG.debug("ATT RX %s", pdu.hex())
                    response = link.protocol.handle(pdu)
                    if response is not None:
                        _LOG.debug("ATT TX %s", response.hex())
                        writer.send(handle, response)
                continue

            code, params = body[0], body[2:2 + body[1]]
            if code == EV_LE_META and params:
                subevent = params[0]
                if subevent in (LE_CONNECTION_COMPLETE, LE_ENHANCED_CONNECTION_COMPLETE):
                    status = params[1]
                    handle = struct.unpack_from("<H", params, 2)[0]
                    peer = ":".join(f"{b:02X}" for b in reversed(params[6:12]))
                    if status:
                        _LOG.warning("connection failed with status 0x%02x", status)
                        continue
                    link_box: dict[str, object] = {}

                    def on_button(label, plain_hex, remote_id, remote_slot, box=link_box):
                        # Where the add-on publishes to MQTT. Printing it is enough to prove the
                        # whole path, and it names the address the press came in on, which is
                        # the point of running several at once.
                        current = box.get("link")
                        _LOG.info(">>> BUTTON %s on %s (remote=%s slot=%s) %s",
                                  label, getattr(current, "address", "?"),
                                  remote_id, remote_slot, plain_hex)

                    # The two refer to each other, so the protocol reaches its device through
                    # this box. A plain closure would capture the loop variable and send an older
                    # connection's writes to the newest device.
                    protocol = bridge.FastAttProtocol(
                        lambda value, box=link_box: box["device"].on_write(value))
                    device = bridge.SwitchBotDevice(device_key, protocol.notify, on_button)
                    link_box["device"] = device
                    protocol.begin_session()
                    protocol.sender = lambda data, h=handle: writer.send(h, data)
                    link = Link(handle, pending_address["value"] or "?", protocol)
                    link.device = device  # keep it alive for as long as the connection
                    link_box["link"] = link
                    links[handle] = link
                    _LOG.info("connected handle=%d peer=%s", handle, peer)
                    # BlueZ used to start this exchange as the reverse GATT client; without it
                    # WoRWS correctly refuses anything larger than the default ATT MTU of 23.
                    writer.send(handle, b"\x02\x00\x02")
                elif subevent == LE_ADV_SET_TERMINATED:
                    status, adv_handle, connection = struct.unpack_from("<BBH", params, 1)
                    address = args.addresses[adv_handle] if adv_handle < len(args.addresses) else "?"
                    pending_address["value"] = address
                    if connection in links:
                        links[connection].address = address
                    _LOG.info("  …that connection arrived on set %d = %s", adv_handle, address)
            elif code == EV_DISCONN_COMPLETE:
                handle = struct.unpack_from("<H", params, 1)[0]
                link = links.pop(handle, None)
                if link is not None:
                    _LOG.info("disconnected handle=%d reason=0x%02x address=%s summary=%s",
                              handle, params[3], link.address, link.protocol.session_summary())
                # A connectable set stops advertising once used; arm them all again.
                try:
                    channel.command(OP_LE_SET_EXT_ADV_ENABLE, enable)
                except (OSError, TimeoutError) as err:
                    _LOG.warning("could not re-arm the advertising sets: %s", err)
            elif code == EV_NUM_COMPLETED_PACKETS and params:
                for item in range(params[0]):
                    _handle, count = struct.unpack_from("<HH", params, 1 + item * 4)
                    writer.completed(count)
            elif code == EV_CMD_COMPLETE:
                continue
        return 0
    except KeyboardInterrupt:
        print()
        return 0
    except (OSError, TimeoutError) as error:
        _LOG.error("failed: %s", error)
        return 1
    finally:
        if channel is not None:
            try:
                channel.command(OP_LE_SET_EXT_ADV_ENABLE, bytes([0x00, 0x00]), timeout=1.0)
            except (OSError, TimeoutError):
                pass
            channel.close()
        _LOG.info("%s returned to BlueZ: %s", args.adapter, set_powered(index, True))


if __name__ == "__main__":
    raise SystemExit(main())
