"""Work out which BLE addresses native tiles can use, and how many are left.

A native tile connects to one fixed address, and the WoRWS keeps its target key per six-byte
address, so every tile needs an address of its own. A Bluetooth 5 controller can carry one per
advertising set, so the number of tiles a setup can hold is the sum over its bridges of how many
sets each controller has — four on one dongle plus four on another is eight, not two.

Nothing here talks to a device. It decides what to ask for, so it can be tested on its own, and
so Remote Studio can tell someone what is possible before anything is written to the remote.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def normalise(address: str) -> str:
    """Compare addresses without caring about separators or case."""
    return address.replace(":", "").replace("-", "").upper()


def is_valid(address: str) -> bool:
    return len(normalise(address)) == 12 and all(
        char in "0123456789ABCDEF" for char in normalise(address)
    )


def format_address(compact: str) -> str:
    compact = normalise(compact)
    return ":".join(compact[index:index + 2] for index in range(0, 12, 2))


def is_static_random(address: str) -> bool:
    """Whether a random address is well formed: its top two bits must be 11.

    The other combinations are private addresses that rotate, or reserved. A tile stores a plain
    address and cannot resolve anything, so only the static form is usable.
    """
    return is_valid(address) and int(normalise(address)[:2], 16) & 0xC0 == 0xC0


@dataclass
class Bridge:
    """One controller an add-on instance is serving addresses from."""

    adapter: str
    address: str
    advertising_sets: int = 1
    serving: list[str] = field(default_factory=list)
    extended_advertising: bool = True

    @property
    def capacity(self) -> int:
        """How many tiles this controller can carry.

        Without extended advertising there is exactly one address — the controller's own — no
        matter how many advertising instances the kernel is willing to manage.
        """
        return max(1, self.advertising_sets) if self.extended_advertising else 1

    def candidates(self) -> list[str]:
        """Addresses this controller could serve, its own first.

        The derived ones keep the controller's lower five octets and vary the first, so they are
        stable across restarts, unique per controller in any realistic setup, and valid static
        random addresses. The controller's own address comes first because tiles already bound
        to it must keep working.
        """
        own = normalise(self.address)
        result = [format_address(own)]
        if not self.extended_advertising:
            return result
        for index in range(0x40):
            derived = f"{0xC0 | index:02X}{own[2:]}"
            if derived != own:
                result.append(format_address(derived))
        return result


@dataclass
class Allocation:
    """One address handed to one new tile."""

    address: str
    bridge: Bridge
    is_new_to_bridge: bool


def _belongs_to(bridge: Bridge, address: str) -> bool:
    """Whether this controller is the one carrying that address.

    `serving` is what the add-on reports it actually advertises, and it is authoritative: an
    address may have been configured by hand and need not be one this code would derive.
    `candidates` covers the addresses it would hand out next.
    """
    compact = normalise(address)
    return compact in {normalise(item) for item in bridge.serving} or compact in {
        normalise(item) for item in bridge.candidates()
    }


def capacity(bridges: list[Bridge]) -> int:
    return sum(bridge.capacity for bridge in bridges)


def free_slots(bridges: list[Bridge], used: list[str]) -> int:
    """How many more tiles can be added, counting per controller rather than in total.

    A controller that is full does not lend its spare capacity to another, so this is the sum of
    each bridge's own remainder.
    """
    total = 0
    for bridge in bridges:
        on_this = sum(1 for address in used if _belongs_to(bridge, address))
        total += max(0, bridge.capacity - on_this)
    return total


def without(used: list[str], address: str) -> list[str]:
    """`used` with one address released.

    Moving a tile from one address to another frees the one it is leaving, so planning the move
    against the unchanged list would refuse it on a full controller — and refuse exactly the
    swap that is meant to fix a controller whose address changed.
    """
    compact = normalise(address)
    return [item for item in used if normalise(item) != compact]


def allocate(bridges: list[Bridge], used: list[str], count: int = 1) -> list[Allocation]:
    """Pick `count` addresses for new tiles, or explain why it cannot.

    Bridges are filled in order: a controller already serving addresses is used up before the
    next one is touched, so a two-dongle setup does not end up with one tile on each.
    """
    if count < 1:
        raise ValueError("Ask for at least one address")
    taken = {normalise(address) for address in used}
    result: list[Allocation] = []
    for bridge in bridges:
        on_this = sum(1 for address in used if _belongs_to(bridge, address))
        room = bridge.capacity - on_this
        serving = {normalise(item) for item in bridge.serving}
        for candidate in bridge.candidates():
            if len(result) == count or room <= 0:
                break
            if normalise(candidate) in taken:
                continue
            taken.add(normalise(candidate))
            room -= 1
            result.append(Allocation(
                address=candidate,
                bridge=bridge,
                is_new_to_bridge=normalise(candidate) not in serving,
            ))
        if len(result) == count:
            return result
    available = free_slots(bridges, used)
    raise ValueError(
        f"Only {available} more native remote(s) fit on the bridges this integration knows "
        f"about ({len(bridges)} controller(s), {capacity(bridges)} address(es) in total). "
        "Add another Bluetooth adapter with its own add-on instance to go further."
    )


def describe(bridges: list[Bridge], used: list[str]) -> str:
    """One sentence for the panel, in the terms someone setting this up thinks in."""
    if not bridges:
        return "No native bridge is set up yet."
    spare = free_slots(bridges, used)
    parts = []
    for bridge in bridges:
        on_this = sum(1 for address in used if _belongs_to(bridge, address))
        detail = f"{bridge.adapter} holds {on_this} of {bridge.capacity}"
        if not bridge.extended_advertising:
            detail += " (no Bluetooth 5, so one address only)"
        parts.append(detail)
    return f"{spare} more native remote(s) fit. " + "; ".join(parts) + "."
