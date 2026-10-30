"""Translate SwitchBot cloud IR records into WoRWS BLE installation packets."""
from __future__ import annotations

import base64
import json
import secrets
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import commands


def decode_code_blob(value: str | bytes) -> bytes:
    """Decode the app's base64 + zlib/gzip code field, falling back to raw bytes."""
    if isinstance(value, bytes):
        encoded = value
    else:
        encoded = base64.b64decode(value, validate=True)
    try:
        return zlib.decompress(encoded, wbits=47)
    except zlib.error:
        return encoded


def _as_object(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in "[{":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _as_int(value: Any) -> int:
    """Parse cloud integers without treating decimal values such as ``08`` as octal."""
    text = str(value).strip()
    return int(text, 16 if text.lower().startswith("0x") else 10)


def parse_key_map(value: Any) -> list[tuple[int, int, int]]:
    """Parse the cloud ``key:start:length`` map into numeric bank references."""
    value = _as_object(value)
    records: list[tuple[int, int, int]] = []
    if isinstance(value, str):
        chunks = value.replace(",", ";").split(";")
        for chunk in chunks:
            fields = chunk.strip().split(":")
            if len(fields) != 3:
                continue
            try:
                records.append(tuple(_as_int(part) for part in fields))
            except ValueError:
                continue
    elif isinstance(value, dict):
        for key, reference in value.items():
            if isinstance(reference, str):
                fields = reference.split(":")
            elif isinstance(reference, (list, tuple)):
                fields = reference
            elif isinstance(reference, dict):
                fields = [
                    reference.get("start", reference.get("offset")),
                    reference.get("length", reference.get("len")),
                ]
            else:
                continue
            try:
                records.append((_as_int(key), _as_int(fields[0]), _as_int(fields[1])))
            except (TypeError, ValueError, IndexError):
                continue
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            try:
                records.append(
                    (
                        _as_int(item.get("key", item.get("keyFun"))),
                        _as_int(item.get("start", item.get("offset"))),
                        _as_int(item.get("length", item.get("len"))),
                    )
                )
            except (TypeError, ValueError):
                continue
    # Preserve server order but remove duplicate key functions.
    result: list[tuple[int, int, int]] = []
    seen: set[int] = set()
    for record in records:
        if record[0] not in seen:
            seen.add(record[0])
            result.append(record)
    return result


def generate_remote_id(now: datetime | None = None) -> str:
    """Generate the official app's 11-byte decimal-pair cloud IR identifier."""
    stamp = (now or datetime.now()).strftime("%Y%m%d%H%M")
    return f"01-{stamp}-{secrets.randbelow(100_000_000):08d}"


def find_cloud_items(payload: Any) -> list[dict[str, Any]]:
    """Extract IR item dictionaries from the API's observed envelope variants."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "remoteList", "remotes", "list", "data"):
        nested = payload.get(key)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        if isinstance(nested, dict):
            found = find_cloud_items(nested)
            if found:
                return found
    if any(key in payload for key in ("code", "keyMap", "remoteID", "itemID")):
        return [payload]
    return []


def _hex_bytes(value: Any) -> bytes:
    if not value:
        return b""
    compact = str(value).replace(" ", "").replace(":", "")
    try:
        return bytes.fromhex(compact)
    except ValueError:
        return b""


@dataclass(frozen=True)
class CloudIrProfile:
    """Downloadable cloud profile ready for a complete WoRWS installation."""

    key: str
    title: str
    default_name: str
    remote_id: bytes
    remote_id_text: str
    device_type: int
    code_bank: bytes
    key_map: tuple[tuple[int, int, int], ...]
    original_code: str = ""
    icon: int = 0
    key_map_original: Any = ""
    key_map_fast_bin: bytes = b""
    fast_config_bin: bytes = b""
    custom_code_banks: tuple[tuple[str, bytes], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not self.code_bank:
            raise ValueError("cloud IR profile has no code bank")
        valid = tuple(
            record
            for record in self.key_map
            if record[1] >= 0 and record[2] > 0
            and record[1] + record[2] <= len(self.code_bank)
        )
        if not valid:
            raise ValueError("cloud IR key map has no valid code-bank references")
        object.__setattr__(self, "key_map", valid[:90])

    def build_install(
        self, *, remote_index: int, name: str, remote_count: int
    ) -> tuple[tuple[str, bytes, frozenset[int]], ...]:
        """Build the official header/sync/transfers/pages/sync transaction."""
        result: list[tuple[str, bytes, frozenset[int]]] = [
            (
                "ir_create_header",
                commands.build_ir_empty_remote(
                    remote_index=remote_index,
                    device_type=self.device_type,
                    remote_id=self.remote_id,
                    name=name,
                    icon=self.icon,
                ),
                frozenset({0x01}),
            ),
            ("ir_sync_start", commands.build_ir_sync(remote_count, 1), frozenset({0x01})),
        ]
        result.extend(commands.build_ir_transfer_sequence(self.remote_id, self.code_bank))
        if self.key_map_fast_bin:
            result.extend(
                commands.build_ir_transfer_sequence(
                    self.remote_id, self.key_map_fast_bin,
                    data_type=1, transfer_name="keyMapFastBin",
                )
            )
        if self.fast_config_bin:
            result.extend(
                commands.build_ir_transfer_sequence(
                    self.remote_id, self.fast_config_bin,
                    data_type=2, transfer_name="fastConfigBin",
                )
            )
        for transfer_name, bank in self.custom_code_banks:
            result.extend(
                commands.build_ir_transfer_sequence(
                    self.remote_id, bank, data_type=3, transfer_name=transfer_name,
                )
            )
        result.extend(
            (
                f"ir_page_{page_number}",
                page,
                frozenset({0x01}),
            )
            for page_number, page in enumerate(
                commands.build_ir_pages(
                    remote_index=remote_index,
                    device_type=self.device_type,
                    remote_id=self.remote_id,
                    name=name,
                    key_map=list(self.key_map),
                    icon=self.icon,
                )
            )
        )
        result.append(
            ("ir_sync_end", commands.build_ir_sync(remote_count, 3), frozenset({0x01}))
        )
        return tuple(result)

    def create_cloud_item(self, *, remote_index: int, name: str) -> dict[str, Any]:
        """Return the createIrRemote item used by the official application."""
        meta = self.metadata
        return {
            "acType": meta.get("ac_type", meta.get("acType", "")),
            "brandEn": meta.get("brand", meta.get("brandEn", "")),
            "code": self.original_code,
            "codeType": meta.get("code_type", meta.get("codeType", "")),
            "createTime": int(datetime.now().timestamp() * 1000),
            "dbVersion": 30,
            "hxdIndex": meta.get("hxd_index", meta.get("hxdIndex", "")),
            "keyDetail": meta.get("keyDetail", []),
            "keyMap": self.key_map_original,
            "parentHubMac": meta.get("parentHubMac", ""),
            "priority": meta.get("priority", ""),
            "remoteID": self.remote_id_text,
            "remoteIndex": remote_index,
            "remoteName": name,
            "serial": meta.get("serial", 0),
            "sn": meta.get("sn", ""),
            "type": self.device_type,
            "userName": meta.get("userName", ""),
            "waitModify": True,
        }


def profile_from_cloud(
    item: dict[str, Any],
    *,
    remote_id: str | None = None,
    name: str | None = None,
    remote_type: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> CloudIrProfile:
    """Create a validated installable profile from querymodel/queryIrRemote data."""
    merged = dict(metadata or {})
    merged.update(item)
    remote_id_text = str(remote_id or merged.get("remoteID") or generate_remote_id())
    code_value = merged.get("code")
    if not code_value:
        raise ValueError("cloud IR response did not contain code")
    code_bank = decode_code_blob(code_value)
    key_map_value = merged.get("keyMap", "")
    key_map = parse_key_map(key_map_value)
    custom: list[tuple[str, bytes]] = []
    details = _as_object(merged.get("keyDetail", []))
    if isinstance(details, list):
        for index, detail in enumerate(details):
            if not isinstance(detail, dict) or not detail.get("code"):
                continue
            try:
                custom.append(
                    (
                        str(detail.get("key", detail.get("name", index))),
                        decode_code_blob(detail["code"]),
                    )
                )
            except (ValueError, TypeError):
                continue
    type_value = remote_type if remote_type is not None else merged.get("type", 2)
    try:
        resolved_type = _as_int(type_value)
    except (TypeError, ValueError):
        type_names = {
            "tv": 1,
            "air_conditioner": 2,
            "ac": 2,
            "fan": 3,
            "light": 4,
            "iptv": 5,
            "set_top_box": 6,
            "dvd": 7,
            "speaker": 8,
            "projector": 10,
            "camera": 11,
            "air_purifier": 12,
            "water_heater": 13,
            "vacuum": 14,
        }
        resolved_type = type_names.get(str(type_value).strip().lower(), 2)
    resolved_name = str(name or merged.get("remoteName") or merged.get("model") or "IR remote")
    key = str(merged.get("itemID") or merged.get("hxdIndex") or remote_id_text)
    return CloudIrProfile(
        key=key,
        title=resolved_name,
        default_name=resolved_name,
        remote_id=commands.cloud_remote_id_to_bytes(remote_id_text),
        remote_id_text=remote_id_text,
        device_type=resolved_type,
        code_bank=code_bank,
        key_map=tuple(key_map),
        original_code=str(code_value),
        key_map_original=key_map_value,
        key_map_fast_bin=_hex_bytes(merged.get("keyMapFastBin")),
        fast_config_bin=_hex_bytes(merged.get("fastConfigBin")),
        custom_code_banks=tuple(custom),
        metadata=merged,
    )
