#!/usr/bin/env python3
"""Prove whether one controller can offer several native bridge addresses at once.

Each native tile on the WoRWS connects to one fixed BLE address and the firmware keeps the
target key per address, so several tiles need several addresses. BlueZ cannot give an
advertising instance its own address — none of the kernel's advertising commands carries an
address field — but the controller itself can: Bluetooth 5 has one random address per
advertising set.

Reaching that means taking the controller away from BlueZ through the HCI user channel and
driving it directly. This script does only the part that decides whether the idea works at all:

  * open the user channel, which requires the adapter to be down and unused
  * configure one extended advertising set per address, each with its own random address
  * advertise a payload a WoRWS recognises, built from that set's own address
  * report every connection with the advertising set it arrived on

It implements no ATT. A connection reaching the right set is the whole result; serving it is the
existing bridge's job, and `FastAttProtocol` is already transport-agnostic enough to be fed from
here later.

Pass the address your bridge already uses first, so the tiles bound to it keep working, and a
fresh static random address for each new tile:

    python3 spike_multi_address.py hci1 8A:88:1B:E0:1F:92 DA:71:16:E0:1F:92

WARNING: while this runs, the adapter belongs to this script. Home Assistant and the add-on
cannot use it. It is restored on exit, including on Ctrl-C.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import select
import socket
import struct
import time

HCI_CHANNEL_USER = 1
HCI_COMMAND_PKT = 0x01
HCI_EVENT_PKT = 0x04

OP_RESET = 0x0C03
OP_SET_EVENT_MASK = 0x0C01
OP_LE_SET_EVENT_MASK = 0x2001
OP_LE_READ_ADV_SETS = 0x203B
OP_LE_SET_EXT_ADV_PARAMS = 0x2036
OP_LE_SET_ADV_SET_RANDOM_ADDR = 0x2035
OP_LE_SET_EXT_ADV_DATA = 0x2037
OP_LE_SET_EXT_ADV_ENABLE = 0x2039
OP_READ_BD_ADDR = 0x1009

# The Bluetooth Management API, used only to power the controller down before claiming it.
# `hciconfig` is gone from current BlueZ images, and this is what it would have called anyway.
HCI_CHANNEL_CONTROL = 3
HCI_DEV_NONE = 0xFFFF
MGMT_OP_SET_POWERED = 0x0005
MGMT_EV_CMD_COMPLETE = 0x0001
MGMT_EV_CMD_STATUS = 0x0002

EV_DISCONN_COMPLETE = 0x05
EV_CMD_COMPLETE = 0x0E
EV_CMD_STATUS = 0x0F
EV_LE_META = 0x3E
LE_CONNECTION_COMPLETE = 0x01
LE_ENHANCED_CONNECTION_COMPLETE = 0x0A
LE_ADV_SET_TERMINATED = 0x12

# The same connection interval range the add-on asks WoRWS for.
CONN_MIN, CONN_MAX = 6, 0x50


def address_bytes(address: str) -> bytes:
    raw = bytes.fromhex(address.replace(":", "").replace("-", ""))
    if len(raw) != 6:
        raise ValueError(f"{address!r} is not a six-byte Bluetooth address")
    return raw[::-1]  # little-endian on the wire


def advertisement_for(address: str) -> bytes:
    """The idle-WoStrip payload, carrying this set's own address.

    Mirrors `native_strip_advertisement` and `raw_native_advertisement` in the add-on, plus the
    Flags structure the kernel used to add for us and which nobody adds on the user channel.
    """
    mac = bytes.fromhex(address.replace(":", "").replace("-", ""))
    manufacturer = list(mac) + [0x01, 0xE4, 0x22] + [0x00] * 4
    flags = bytes([0x02, 0x01, 0x06])
    company = bytes([1 + 2 + len(manufacturer), 0xFF, 0x69, 0x09, *manufacturer])
    service = bytes([1 + 2 + 1, 0x16, 0x3D, 0xFD, 0x72])
    interval = bytes([0x05, 0x12, *struct.pack("<HH", CONN_MIN, CONN_MAX)])
    payload = flags + company + service + interval
    if len(payload) > 31:
        raise ValueError("advertisement does not fit a legacy PDU")
    return payload


def set_powered(index: int, powered: bool, timeout: float = 5.0) -> str:
    """Power the controller on or off through the kernel, returning a short outcome."""
    af_bluetooth = getattr(socket, "AF_BLUETOOTH", 31)
    btproto_hci = getattr(socket, "BTPROTO_HCI", 1)
    sock_type = socket.SOCK_RAW | getattr(socket, "SOCK_CLOEXEC", 0)
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.socket(af_bluetooth, sock_type, btproto_hci)
    if fd < 0:
        return f"socket failed: {os.strerror(ctypes.get_errno())}"
    address = struct.pack("=HHH", af_bluetooth, HCI_DEV_NONE, HCI_CHANNEL_CONTROL)
    if libc.bind(fd, address, len(address)) < 0:
        error = ctypes.get_errno()
        os.close(fd)
        return f"control channel unavailable: {os.strerror(error)}"
    sock = socket.socket(af_bluetooth, sock_type, btproto_hci, fileno=fd)
    try:
        sock.settimeout(timeout)
        sock.send(struct.pack("<HHH", MGMT_OP_SET_POWERED, index, 1)
                  + bytes([1 if powered else 0]))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            event = sock.recv(1024)
            if len(event) < 9:
                continue
            code, event_index, length = struct.unpack_from("<HHH", event)
            body = event[6:6 + length]
            if event_index != index or code not in (MGMT_EV_CMD_COMPLETE, MGMT_EV_CMD_STATUS):
                continue
            command, status = struct.unpack_from("<HB", body)
            if command != MGMT_OP_SET_POWERED:
                continue
            return "ok" if status == 0 else f"status 0x{status:02x}"
        return "timed out"
    except OSError as err:
        return str(err)
    finally:
        sock.close()


class UserChannel:
    """Exclusive raw HCI access to one controller."""

    def __init__(self, index: int) -> None:
        self.index = index
        af_bluetooth = getattr(socket, "AF_BLUETOOTH", 31)
        btproto_hci = getattr(socket, "BTPROTO_HCI", 1)
        sock_type = socket.SOCK_RAW | getattr(socket, "SOCK_CLOEXEC", 0)
        libc = ctypes.CDLL(None, use_errno=True)
        fd = libc.socket(af_bluetooth, sock_type, btproto_hci)
        if fd < 0:
            raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
        address = struct.pack("=HHH", af_bluetooth, index, HCI_CHANNEL_USER)
        if libc.bind(fd, address, len(address)) < 0:
            error = ctypes.get_errno()
            os.close(fd)
            raise OSError(error, os.strerror(error))
        self.sock = socket.socket(af_bluetooth, sock_type, btproto_hci, fileno=fd)
        # Non-event packets seen while waiting for a command reply. They are kept rather than
        # dropped so a caller reading ACL data never loses a frame to a concurrent command.
        self.spare: list[tuple[int, bytes]] = []

    def close(self) -> None:
        self.sock.close()

    def command(self, opcode: int, payload: bytes = b"", timeout: float = 3.0) -> bytes:
        """Send one command and return the parameters of its completion event."""
        self.sock.send(
            bytes([HCI_COMMAND_PKT]) + struct.pack("<HB", opcode, len(payload)) + payload)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for event in self.events(deadline - time.monotonic()):
                code, params = event
                if code == EV_CMD_COMPLETE:
                    _count, returned = struct.unpack_from("<BH", params)
                    if returned == opcode:
                        status = params[3]
                        if status:
                            raise OSError(
                                f"command 0x{opcode:04x} failed with status 0x{status:02x}")
                        return params[4:]
                elif code == EV_CMD_STATUS:
                    status, _count, returned = struct.unpack_from("<BBH", params)
                    if returned == opcode:
                        if status:
                            raise OSError(
                                f"command 0x{opcode:04x} failed with status 0x{status:02x}")
                        return b""
        raise TimeoutError(f"command 0x{opcode:04x} got no answer")

    def read(self, timeout: float):
        """Return the next (packet_type, body) from the controller, or None."""
        if self.spare:
            return self.spare.pop(0)
        if timeout <= 0:
            return None
        ready, _, _ = select.select([self.sock], [], [], timeout)
        if not ready:
            return None
        packet = self.sock.recv(2048)
        if len(packet) < 2:
            return None
        return packet[0], packet[1:]

    def events(self, timeout: float):
        """Yield (event_code, parameters) for whatever has arrived.

        Anything that is not an event is set aside for `read` instead of being discarded.
        """
        packet = self.read(timeout)
        if packet is None:
            return
        kind, body = packet
        if kind != HCI_EVENT_PKT:
            self.spare.append(packet)
            return
        if len(body) < 2:
            return
        yield body[0], body[2:2 + body[1]]


def configure_set(
    channel: UserChannel, handle: int, address: str, *, public: bool = False
) -> None:
    """One connectable legacy-PDU advertising set.

    A set normally carries its own random address, which is the point of this exercise. The
    controller's own public address is the exception: it cannot be assigned to a set, so that
    set advertises as public instead. Reusing it keeps the native tiles that are already bound
    to it working, and only the new tiles need new addresses.
    """
    # Connectable + scannable + legacy PDUs, which is what a WoStrip looks like.
    properties = 0x0013
    interval = 0x000080  # 80 * 0.625 ms = 100 ms, the add-on's fast interval
    channel.command(OP_LE_SET_EXT_ADV_PARAMS, struct.pack(
        "<BH3s3sBBB6sBbBBBBB",
        handle, properties,
        interval.to_bytes(3, "little"), interval.to_bytes(3, "little"),
        0x07,        # all three primary channels
        0x00 if public else 0x01,  # own address type: public or random
        0x00, b"\x00" * 6,   # no directed peer
        0x00,        # no filter policy
        0x7F,        # no TX power preference
        0x01,        # primary PHY 1M
        0x00,        # no secondary skip
        0x01,        # secondary PHY 1M
        handle,      # advertising SID, distinct per set
        0x00,        # no scan request notifications
    ))
    if not public:
        # The random address belongs to the set and must be set after its parameters.
        channel.command(OP_LE_SET_ADV_SET_RANDOM_ADDR,
                        bytes([handle]) + address_bytes(address))
    data = advertisement_for(address)
    channel.command(OP_LE_SET_EXT_ADV_DATA,
                    bytes([handle, 0x03, 0x01, len(data)]) + data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("adapter", help="hci1, hci2, …")
    parser.add_argument("addresses", nargs="+", help="one static random address per tile")
    parser.add_argument("--seconds", type=float, default=120.0, help="how long to advertise")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation")
    args = parser.parse_args()

    index = int(args.adapter.removeprefix("hci"))
    if not args.yes:
        print(f"This takes {args.adapter} away from BlueZ and Home Assistant for "
              f"{args.seconds:.0f}s. Continue? [y/N] ", end="", flush=True)
        if input().strip().lower() not in ("y", "yes"):
            return 1

    outcome = set_powered(index, False)
    if outcome != "ok":
        print(f"Could not power {args.adapter} down: {outcome}")
        print("The user channel needs the controller down and unused. Run this as root in a")
        print("container with NET_ADMIN — the bridge add-on's own container qualifies.")
        return 1
    channel = None
    try:
        channel = UserChannel(index)
        channel.command(OP_RESET)
        channel.command(OP_SET_EVENT_MASK, bytes.fromhex("ffffffffffffff3f"))
        # Subevents 1..32. The old mask stopped at 15 and so hid LE Advertising Set
        # Terminated (0x12), which is the only event that names the set a connection used.
        channel.command(OP_LE_SET_EVENT_MASK, bytes.fromhex("ffffffff00000000"))

        own_public = ":".join(
            f"{byte:02X}" for byte in reversed(channel.command(OP_READ_BD_ADDR)[:6]))
        print(f"{args.adapter}: the controller's own public address is {own_public}")

        def normalised(value: str) -> str:
            return value.replace(":", "").replace("-", "").upper()

        for address in args.addresses:
            if normalised(address) == normalised(own_public):
                continue
            first = bytes.fromhex(normalised(address)[:2])[0]
            if first & 0xC0 != 0xC0:
                print()
                print(f"{address} cannot be used. A set can only carry the controller's own")
                print(f"public address ({own_public}) or a static random address, whose top two")
                print("bits must be 11 — the first octet must be C0 or higher, such as DA.")
                return 2

        available = channel.command(OP_LE_READ_ADV_SETS)[0]
        print(f"{args.adapter}: the controller offers {available} advertising sets")
        if len(args.addresses) > available:
            print(f"…but {len(args.addresses)} addresses were asked for. Stopping.")
            return 2

        for handle, address in enumerate(args.addresses):
            public = normalised(address) == normalised(own_public)
            configure_set(channel, handle, address, public=public)
            print(f"  set {handle}: advertising as {address}"
                  f"{' (the controller\'s own public address)' if public else ''}")

        enable = bytes([0x01, len(args.addresses)])
        for handle in range(len(args.addresses)):
            enable += struct.pack("<BHB", handle, 0, 0)
        channel.command(OP_LE_SET_EXT_ADV_ENABLE, enable)
        print()
        print("All sets are live. Press the native tiles on the remote now.")
        print("Every connection below names the set it arrived on — different sets mean this")
        print("works and one adapter can carry several tiles.")
        print()

        by_handle = dict(enumerate(args.addresses))
        reached: set[int] = set()
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            for code, params in channel.events(min(1.0, deadline - time.monotonic())):
                if code == EV_LE_META and params:
                    subevent = params[0]
                    if subevent in (LE_CONNECTION_COMPLETE, LE_ENHANCED_CONNECTION_COMPLETE):
                        status = params[1]
                        handle_id = struct.unpack_from("<H", params, 2)[0]
                        peer = ":".join(f"{b:02X}" for b in reversed(params[6:12]))
                        print(f"CONNECTED  handle={handle_id} peer={peer} "
                              f"status=0x{status:02x}")
                    elif subevent == LE_ADV_SET_TERMINATED:
                        status, adv_handle, connection = struct.unpack_from("<BBH", params, 1)
                        reached.add(adv_handle)
                        print(f"  …on advertising set {adv_handle} = "
                              f"{by_handle.get(adv_handle, 'unknown')} "
                              f"(connection {connection}, status 0x{status:02x})")
                elif code == EV_DISCONN_COMPLETE:
                    handle_id = struct.unpack_from("<H", params, 1)[0]
                    # 0x13 is the peer hanging up, which is what WoRWS does when nothing
                    # answers its ATT discovery. Expected here; this spike serves no ATT.
                    print(f"DISCONNECTED handle={handle_id} reason=0x{params[3]:02x}")
                    # A connectable set stops advertising once it is used, so arm them again
                    # to make the test repeatable without a restart.
                    try:
                        channel.command(OP_LE_SET_EXT_ADV_ENABLE, enable)
                        print("  …all sets advertising again; press another tile")
                    except (OSError, TimeoutError) as err:
                        print(f"  …could not re-arm the sets: {err}")
        print()
        print(f"Time is up. Sets that received a connection: "
              f"{', '.join(f'{h} ({by_handle.get(h)})' for h in sorted(reached)) or 'none'}")
        if len(reached) > 1:
            print("Two different sets answered on one adapter: several native tiles on one")
            print("controller are possible, and the remaining work is ATT over raw ACL.")
        elif reached:
            print("Only one set was used. Bind a second tile to the other address first —")
            print("a tile still pointing at the old address will always land on set 0.")
        return 0
    except (OSError, TimeoutError) as error:
        print(f"Failed: {error}")
        if isinstance(error, OSError) and error.errno in (1, 13):
            print("Run as root, in a container with NET_ADMIN and NET_RAW.")
        if isinstance(error, OSError) and error.errno == 16:
            print(f"{args.adapter} is still busy. Make sure Home Assistant's Bluetooth")
            print("integration is not using it and the add-on is stopped.")
        return 1
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        if channel is not None:
            try:
                channel.command(OP_LE_SET_EXT_ADV_ENABLE, bytes([0x00, 0x00]), timeout=1.0)
            except (OSError, TimeoutError):
                pass
            channel.close()
        # Hand the controller back, whatever happened above.
        print(f"{args.adapter} returned to BlueZ: {set_powered(index, True)}")


if __name__ == "__main__":
    raise SystemExit(main())
