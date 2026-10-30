"""Merge the physical WoRWS table, cloud metadata, and local managed records."""
from __future__ import annotations

from typing import Any

from . import commands


def stable_id_for_local(device_id: str) -> bytes:
    """Return the 11-byte id represented by a local record."""
    compact = device_id.replace(":", "").replace("-", "")
    if len(compact) == 22:
        return bytes.fromhex(compact)
    return commands.id_to_bytes(device_id)


def deletion_verified(
    before: list[tuple[int, int, int, bytes]],
    after: list[tuple[int, int, int, bytes]],
    *,
    device_type: int,
    control_type: int,
    device_id: bytes,
) -> bool:
    """Return true only when one row with the requested identity disappeared."""
    signature = (int(device_type), int(control_type), device_id)

    def matching(entries: list[tuple[int, int, int, bytes]]) -> int:
        return sum(
            1
            for _index, item_type, item_control, item_id in entries
            if (item_type, item_control, item_id) == signature
        )

    return len(after) == len(before) - 1 and matching(after) == matching(before) - 1


def cloud_item_id(item: dict[str, Any]) -> bytes | None:
    """Extract a physical-table id from any supported cloud list item."""
    try:
        if item.get("remoteID"):
            return commands.cloud_remote_id_to_bytes(str(item["remoteID"]))
        value = item.get("thirdPartyDeviceID") or item.get("deviceID")
        if value:
            return commands.id_to_bytes(str(value))
    except ValueError:
        return None
    return None


def cloud_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Normalize the cloud's bindable-device response."""
    if not payload:
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in ("bindDevices", "items", "deviceList"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                identity = str(
                    item.get("remoteID") or item.get("thirdPartyDeviceID")
                    or item.get("deviceID") or repr(item)
                )
                if identity not in seen:
                    result.append(item)
                    seen.add(identity)
    return result


def merge_inventory(
    physical: list[tuple[int, int, int, bytes]],
    managed: list[dict[str, Any]],
    cloud: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build UI records, preserving several logical remotes behind one native MAC.

    Native bridge pages intentionally share the adapter's 11-byte table identity.  Match those
    repeated physical rows to local records by cached slot order, while keeping ``remote_id`` as
    the stable UI identity.  The physical table still owns the current slot after compaction.
    """
    def cached_slot(item: dict[str, Any], default: int = 0x10000) -> int:
        value = item.get("index")
        try:
            return int(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    managed_by_id: dict[bytes, list[dict[str, Any]]] = {}
    managed_order: dict[int, int] = {}
    for order, item in enumerate(managed):
        try:
            item_id = stable_id_for_local(str(item["device_id"]))
        except (KeyError, ValueError):
            continue
        managed_by_id.setdefault(item_id, []).append(item)
        managed_order[id(item)] = order
    for candidates in managed_by_id.values():
        candidates.sort(
            key=lambda item: (cached_slot(item), managed_order[id(item)])
        )
    cloud_by_id = {
        item_id: item for item in cloud if (item_id := cloud_item_id(item)) is not None
    }

    result: list[dict[str, Any]] = []
    seen: set[bytes] = set()
    physical_id_counts: dict[bytes, int] = {}
    for _index, _device_type, _control_type, item_id in physical:
        physical_id_counts[item_id] = physical_id_counts.get(item_id, 0) + 1

    for index, device_type, control_type, item_id in sorted(physical):
        candidates = managed_by_id.get(item_id, [])
        compatible: list[dict[str, Any]] = []
        for candidate in candidates:
            try:
                expected_type = commands.devtype_byte(str(candidate["device_type"]))
                expected_control = commands.control_type_for(
                    str(candidate["device_type"])
                )
            except (KeyError, ValueError):
                compatible.append(candidate)
                continue
            if expected_type == device_type and expected_control == control_type:
                compatible.append(candidate)
        pool = compatible or candidates
        exact = next(
            (item for item in pool if cached_slot(item, -1) == index), None
        )
        local = exact or (pool[0] if pool else {})
        if local:
            candidates.remove(local)
        remote = cloud_by_id.get(item_id, {})
        name = (
            (local.get("name") if local.get("name_override") else None)
            or remote.get("remoteName")
            or remote.get("thirdPartyDeviceName")
            or remote.get("deviceName")
            or local.get("name")
            or f"Unknown remote {index}"
        )
        kind = {0: "Native", 1: "IR", 3: "Matter", 4: "HID"}.get(
            control_type, f"Control {control_type}"
        )
        remote_id = str(local.get("remote_id", ""))
        if remote_id:
            identity = f"managed:{remote_id}"
        elif physical_id_counts[item_id] > 1:
            identity = f"physical:{item_id.hex()}:{index}"
        else:
            identity = item_id.hex()
        result.append(
            {
                "key": identity,
                "device_key": item_id.hex(),
                "index": index,
                "device_type_byte": device_type,
                "control_type": control_type,
                "device_id_bytes": item_id,
                "name": str(name),
                "kind": kind,
                "physical": True,
                "cloud": bool(remote),
                "cloud_item": remote,
                "managed": bool(local),
                "managed_item": local,
            }
        )
        seen.add(item_id)

    for item_id, remote in cloud_by_id.items():
        if item_id in seen or remote.get("isDeleted") is True:
            continue
        name = remote.get("remoteName") or remote.get("thirdPartyDeviceName") or "Cloud remote"
        result.append(
            {
                "key": f"cloud:{item_id.hex()}",
                "device_key": item_id.hex(),
                "index": remote.get("remoteIndex"),
                "device_type_byte": remote.get("type"),
                "control_type": 1 if remote.get("remoteID") else 4,
                "device_id_bytes": item_id,
                "name": str(name),
                "kind": "IR" if remote.get("remoteID") else "HID",
                "physical": False,
                "cloud": True,
                "cloud_item": remote,
                "managed": False,
                "managed_item": {},
            }
        )
    return result


def format_inventory(items: list[dict[str, Any]], cloud_status: str) -> str:
    if not items:
        physical = "No remotes found on the Universal Remote."
    else:
        lines = []
        for item in items:
            where = "device" if item["physical"] else "cloud only"
            cloud = ", cloud" if item["cloud"] and item["physical"] else ""
            slot = f"slot {item['index']}" if item["index"] is not None else "no slot"
            lines.append(f"• {item['name']} — {item['kind']}, {slot}, {where}{cloud}")
        physical = "\n".join(lines)
    return f"{physical}\n\nCloud: {cloud_status}"
