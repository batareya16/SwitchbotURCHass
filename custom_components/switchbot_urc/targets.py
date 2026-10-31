"""The bridge targets a WoRWS can send native presses to.

A native tile connects to one fixed BLE address, and the firmware keeps the target key per
six-byte address rather than per tile, so two tiles on one address are not independently usable
— binding the second is refused outright with `native_target_mac_in_use`. Several native tiles
therefore mean several addresses, which today means several Bluetooth controllers, one add-on
instance each.

The integration originally stored exactly one bridge in `entry.data["native_target"]`. It now
keeps a list in `entry.data["native_targets"]` and leaves the old key in place as the first
entry, so a configuration written by an earlier version keeps working untouched.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def _usable(target: Any) -> bool:
    return isinstance(target, dict) and bool(target.get("device_id"))


def all_targets(entry) -> list[dict[str, Any]]:
    """Every bridge this integration knows about, in the order they were added."""
    stored = entry.data.get("native_targets")
    if isinstance(stored, list):
        usable = [target for target in stored if _usable(target)]
        if usable:
            return usable
    single = entry.data.get("native_target")
    return [single] if _usable(single) else []


def target_for(entry, remote: dict[str, Any] | None) -> dict[str, Any]:
    """The bridge a given native remote talks to.

    A remote records the address it was bound to in `physical_device_id`. Fall back to the first
    known bridge, which is what a single-bridge installation has always used.
    """
    targets = all_targets(entry)
    if not targets:
        return {}
    wanted = str(
        (remote or {}).get("physical_device_id") or (remote or {}).get("device_id") or ""
    ).replace(":", "").lower()
    for target in targets:
        if str(target.get("device_id", "")).replace(":", "").lower() == wanted:
            return target
    return targets[0]


def remember_target(hass, entry, target: dict[str, Any]) -> None:
    """Record a bridge, replacing any earlier one at the same address."""
    if not _usable(target):
        raise ValueError("A bridge target needs at least a device_id")
    address = str(target["device_id"]).replace(":", "").lower()
    kept = [
        item for item in all_targets(entry)
        if str(item.get("device_id", "")).replace(":", "").lower() != address
    ]
    kept.append(deepcopy(target))
    data = dict(entry.data)
    data["native_targets"] = kept
    # Older code paths, and anything written by a previous version, still read this one.
    data["native_target"] = deepcopy(kept[0])
    hass.config_entries.async_update_entry(entry, data=data)


def forget_target(hass, entry, device_id: str) -> bool:
    """Drop a bridge by address. Returns whether anything was removed."""
    address = str(device_id).replace(":", "").lower()
    kept = [
        item for item in all_targets(entry)
        if str(item.get("device_id", "")).replace(":", "").lower() != address
    ]
    if len(kept) == len(all_targets(entry)):
        return False
    data = dict(entry.data)
    data["native_targets"] = kept
    data["native_target"] = deepcopy(kept[0]) if kept else {}
    hass.config_entries.async_update_entry(entry, data=data)
    return True
