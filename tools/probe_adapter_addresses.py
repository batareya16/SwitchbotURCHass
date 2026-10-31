#!/usr/bin/env python3
"""Report whether one Bluetooth controller can serve several native bridge addresses.

Each native tile on the WoRWS is keyed on a six-byte BLE address (see PROTOCOL.md), so several
tiles need several addresses. This script answers, for the controller actually in the machine,
the two questions that decide whether that is possible without more dongles:

1. How many advertising sets does the controller support, and does it do extended advertising?
   A Bluetooth 5 controller can advertise from several sets, each with its own random address.
2. Can a raw ATT listener bind to an address the controller does not own as its identity?
   The bridge's GATT server is an L2CAP listener bound to a local address. A refusal here
   settles the question immediately; an acceptance does not, because the bind is permissive
   and no peer can reach an address the controller never advertises.

Run it on the Home Assistant host, as root, against the adapter the add-on uses:

    python3 probe_adapter_addresses.py hci1

It only reads, and binds a socket it closes again. It changes nothing.
"""
from __future__ import annotations

import ctypes
import os
import socket
import struct
import sys

MGMT_OP_READ_COMMANDS = 0x0002
MGMT_OP_READ_INFO = 0x0004
MGMT_OP_READ_ADV_FEATURES = 0x003D
MGMT_EV_CMD_COMPLETE = 0x0001
MGMT_EV_CMD_STATUS = 0x0002
HCI_DEV_NONE = 0xFFFF
HCI_CHANNEL_CONTROL = 3

# MGMT "supported settings" bits, from the kernel's mgmt.h. Extended advertising is not one
# of them: it is reported through Read Advertising Features instead.
SETTINGS = {
    0x0200: "LE",
    0x0400: "advertising",
    0x0800: "secure connections",
    0x2000: "privacy (resolvable addresses)",
    0x8000: "static address",
}

# Read Advertising Features supported_flags. The last three say whether the controller does
# extended advertising, which is what a Bluetooth 5 radio adds over a 4.x one.
# The advertising opcodes that would be needed to give an instance its own address. Reading
# the controller's command list turns "BlueZ cannot do this" from a claim into a fact about
# this kernel.
ADV_COMMANDS = {
    0x003D: "Read Advertising Features",
    0x003E: "Add Advertising",
    0x003F: "Remove Advertising",
    0x0054: "Add Extended Advertising Parameters",
    0x0055: "Add Extended Advertising Data",
}

ADV_FLAGS = {
    0x0001: "switch into connectable",
    0x0010: "TX power in the advertisement",
    0x0040: "local name in the advertisement",
    0x0080: "extended advertising, 1M secondary channel",
    0x0100: "extended advertising, 2M secondary channel",
    0x0200: "extended advertising, coded secondary channel",
}


def _open_mgmt_socket() -> socket.socket:
    """Open the HCI control channel the way the add-on does.

    Python's own ``bind`` for BTPROTO_HCI wants a tuple and rejects a packed sockaddr, and the
    tuple form carrying the channel only exists on newer CPython. Going through libc works on
    every version, and it is the call the bridge itself already relies on.
    """
    af_bluetooth = getattr(socket, "AF_BLUETOOTH", 31)
    btproto_hci = getattr(socket, "BTPROTO_HCI", 1)
    sock_type = socket.SOCK_RAW | getattr(socket, "SOCK_CLOEXEC", 0)
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.socket(af_bluetooth, sock_type, btproto_hci)
    if fd < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    address = struct.pack("=HHH", af_bluetooth, HCI_DEV_NONE, HCI_CHANNEL_CONTROL)
    try:
        if libc.bind(fd, address, len(address)) < 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        return socket.socket(af_bluetooth, sock_type, btproto_hci, fileno=fd)
    except Exception:
        os.close(fd)
        raise


def _mgmt_command(index: int, opcode: int, payload: bytes = b"") -> bytes:
    sock = _open_mgmt_socket()
    try:
        sock.settimeout(5.0)
        sock.send(struct.pack("<HHH", opcode, index, len(payload)) + payload)
        while True:
            event = sock.recv(4096)
            code, event_index, length = struct.unpack_from("<HHH", event)
            body = event[6:6 + length]
            if event_index != index or code not in (MGMT_EV_CMD_COMPLETE, MGMT_EV_CMD_STATUS):
                continue
            command, status = struct.unpack_from("<HB", body)
            if command != opcode:
                continue
            if status:
                raise OSError(f"MGMT 0x{opcode:04x} failed with status 0x{status:02x}")
            return body[3:]
    finally:
        sock.close()


def _bind_att(address: str) -> str:
    """Try to own the fixed ATT CID on `address`, exactly as the add-on's server does."""
    af_bluetooth = getattr(socket, "AF_BLUETOOTH", 31)
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.socket(af_bluetooth, socket.SOCK_SEQPACKET, getattr(socket, "BTPROTO_L2CAP", 0))
    if fd < 0:
        return f"socket() failed: {os.strerror(ctypes.get_errno())}"
    try:
        raw = bytes.fromhex(address.replace(":", ""))[::-1]
        sockaddr = struct.pack("=HH6sHBx", af_bluetooth, 0, raw, 0x0004, 0x01)
        if libc.bind(fd, sockaddr, len(sockaddr)) < 0:
            return f"refused: {os.strerror(ctypes.get_errno())}"
        return "accepted"
    finally:
        os.close(fd)


def main() -> int:
    adapter = sys.argv[1] if len(sys.argv) > 1 else "hci0"
    index = int(adapter.removeprefix("hci"))

    info = _mgmt_command(index, MGMT_OP_READ_INFO)
    own_address = ":".join(f"{byte:02X}" for byte in reversed(info[:6]))
    supported, current = struct.unpack_from("<II", info, 8)
    print(f"{adapter}: identity address {own_address}")
    print("  supports:", ", ".join(
        name for bit, name in SETTINGS.items() if supported & bit) or "nothing relevant")
    print("  enabled: ", ", ".join(
        name for bit, name in SETTINGS.items() if current & bit) or "nothing relevant")

    try:
        features = _mgmt_command(index, MGMT_OP_READ_ADV_FEATURES)
        supported_flags, max_adv_len, max_scan_rsp_len, max_instances = struct.unpack_from(
            "<IBBB", features)
        print(f"  advertising sets the kernel will manage: {max_instances}")
        print(f"  advertisement budget: {max_adv_len} B, scan response {max_scan_rsp_len} B")
        print("  advertising features:", ", ".join(
            name for bit, name in ADV_FLAGS.items() if supported_flags & bit) or "none reported")
        extended = any(supported_flags & bit for bit in (0x0080, 0x0100, 0x0200))
        print(f"  extended (Bluetooth 5) advertising: {'yes' if extended else 'no'}")
    except OSError as err:
        print(f"  advertising features: unavailable ({err})")

    try:
        # Index is ignored for Read Commands; it is a controller-independent query.
        commands = _mgmt_command(0xFFFF, MGMT_OP_READ_COMMANDS)
        count = struct.unpack_from("<H", commands)[0]
        opcodes = set(struct.unpack_from(f"<{count}H", commands, 4))
        print()
        print("  advertising commands this kernel offers:")
        for opcode, label in ADV_COMMANDS.items():
            print(f"    0x{opcode:04x} {label}: {'yes' if opcode in opcodes else 'no'}")
        print("    none of them carries an address field, so every instance advertises as the")
        print("    identity address above.")
    except OSError as err:
        print(f"  command list unavailable ({err})")

    print()
    print("Binding the raw ATT listener (CID 0x0004), as the bridge's GATT server does:")
    print(f"  on the identity address {own_address}: {_bind_att(own_address)}")
    # One bit flipped in the first octet: a valid, different address this controller does not own.
    other = f"{info[5] ^ 0x02:02X}:" + ":".join(f"{byte:02X}" for byte in reversed(info[:5]))
    second = _bind_att(other)
    print(f"  on a second address {other}: {second}")
    print()
    print("Read that last line carefully: an L2CAP bind does not check the source address")
    print("against the controller's own, so 'accepted' means the kernel took the socket, not")
    print("that anything will ever connect to that address. It is necessary, not sufficient.")
    print()
    print("What actually decides it is whether the controller can advertise a second, stable")
    print("address at the same time. BlueZ offers no way to give an advertising instance its")
    print("own address — the kernel's Add Advertising carries no address field — so every")
    print("instance goes out as the identity above. Reaching a second address means driving")
    print("LE Set Advertising Set Random Address over raw HCI and serving ATT yourself, which")
    print("is a different program, not a setting.")
    print()
    print("The supported, boring answer is one adapter per native tile.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PermissionError:
        print("Permission denied opening the Bluetooth control channel. Run this as root, in a\n"
              "container that has NET_ADMIN and NET_RAW — the bridge add-on's own container does.")
        raise SystemExit(1) from None
    except OSError as error:
        print(f"Could not talk to the controller: {error}")
        print("Check the adapter name against `hciconfig -a`; this script takes hci0, hci1, …")
        raise SystemExit(1) from None
