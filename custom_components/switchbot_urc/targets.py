"""The bridge targets a WoRWS can send native presses to.

A Native tile connects to one fixed BLE address. Each tile needs its own address, and a
Bridge controller can serve several addresses.

The integration originally stored exactly one bridge in `entry.data["native_target"]`. It now
keeps a list in `entry.data["native_targets"]` and leaves the old key in place as the first
entry, so a configuration written by an earlier version keeps working untouched.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .addressing import normalise


def _usable(target: Any) -> bool:
    return isinstance(target, dict) and bool(target.get("device_id"))


def remove_saved_press_keys(hass, entry) -> None:
    """Discard old button-command keys from saved Bridge targets."""
    data = dict(entry.data)
    for field in ("native_target", "native_targets"):
        stored = data.get(field)
        records = stored if isinstance(stored, list) else [stored]
        cleaned = [
            {key: value for key, value in record.items()
             if key not in ("target_key", "target_key_id")}
            if isinstance(record, dict) else record
            for record in records
        ]
        if records != cleaned:
            data[field] = cleaned if isinstance(stored, list) else cleaned[0]

    options = dict(entry.options)
    options.pop("native_key_id", None)
    if data != entry.data or options != entry.options:
        hass.config_entries.async_update_entry(entry, data=data, options=options)


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
    wanted = normalise(str(
        (remote or {}).get("physical_device_id") or (remote or {}).get("device_id") or ""
    ))
    for target in targets:
        if normalise(str(target.get("device_id", ""))) == wanted:
            return target
    return targets[0]


def is_bridge_remote(entry, remote: dict[str, Any]) -> bool:
    """Recognize Studio-created remotes and older remotes with a saved Bridge target."""
    if remote.get("physical_device_id"):
        return True
    wanted = normalise(str(remote.get("device_id") or ""))
    return bool(wanted) and any(
        normalise(str(target["device_id"])) == wanted for target in all_targets(entry)
    )


def remember_target(hass, entry, target: dict[str, Any]) -> None:
    """Record a bridge, replacing any earlier one at the same address."""
    if not _usable(target):
        raise ValueError("A bridge target needs at least a device_id")
    address = normalise(str(target["device_id"]))
    kept = [
        item for item in all_targets(entry)
        if normalise(str(item.get("device_id", ""))) != address
    ]
    kept.append(deepcopy(target))
    data = dict(entry.data)
    data["native_targets"] = kept
    # Older code paths, and anything written by a previous version, still read this one.
    data["native_target"] = deepcopy(kept[0])
    hass.config_entries.async_update_entry(entry, data=data)


def forget_target(hass, entry, device_id: str) -> bool:
    """Drop a bridge by address. Returns whether anything was removed."""
    address = normalise(str(device_id))
    kept = [
        item for item in all_targets(entry)
        if normalise(str(item.get("device_id", ""))) != address
    ]
    if len(kept) == len(all_targets(entry)):
        return False
    data = dict(entry.data)
    data["native_targets"] = kept
    data["native_target"] = deepcopy(kept[0]) if kept else {}
    hass.config_entries.async_update_entry(entry, data=data)
    return True
