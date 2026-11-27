"""WoRWS scene records and passive activation advertisements."""
from __future__ import annotations

from dataclasses import dataclass

from .commands import crc16_modbus

SCENE_LIST_QUERY = 0x04
SCENE_LIMIT = 10
RECORD_SIZE = 67


@dataclass(frozen=True)
class Scene:
    """One entry in the physical remote's separate scene list."""

    index: int
    name: str
    icon: int
    color: int

    def encode(self) -> bytes:
        name = self.name.encode("utf-8")
        if not 0 <= self.index < SCENE_LIMIT:
            raise ValueError("Scene index is out of range")
        if not name or b"\0" in name or len(name) > 63:
            raise ValueError("Use a scene name between 1 and 63 UTF-8 bytes")
        return bytes([self.index]) + name.ljust(64, b"\0") + bytes([self.icon, self.color])


def build_scene_list(scenes: list[Scene]) -> bytes:
    if len(scenes) > SCENE_LIMIT or len({scene.index for scene in scenes}) != len(scenes):
        raise ValueError("Scene slots must be unique and there can be at most ten")
    body = bytes([len(scenes)]) + b"".join(
        scene.encode() for scene in sorted(scenes, key=lambda scene: scene.index)
    )
    return (
        b"\x0f\x62\x09" + len(body).to_bytes(2, "big")
        + crc16_modbus(body).to_bytes(2, "big") + body
    )


def parse_scene_list(frame: bytes) -> dict[int, Scene]:
    """Read an enveloped 0F6304 response; V48 reads compute CRC over a different span."""
    if len(frame) < 9 or frame[:4] != b"\x01\x00\x00\x00":
        raise ValueError("The remote did not return its scene list")
    length = int.from_bytes(frame[4:6], "big")
    count = frame[8]
    if count > SCENE_LIMIT or length != 1 + count * RECORD_SIZE or len(frame) != 8 + length:
        raise ValueError("The remote returned an incomplete or invalid scene list")
    scenes = {}
    for offset in range(9, len(frame), RECORD_SIZE):
        index = frame[offset]
        if index >= SCENE_LIMIT or index in scenes:
            raise ValueError("The remote returned an invalid scene slot")
        name, terminator, _ = frame[offset + 1:offset + 65].partition(b"\0")
        if not terminator or not name:
            raise ValueError("The remote returned an invalid scene name")
        scenes[index] = Scene(index, name.decode("utf-8"), frame[offset + 65], frame[offset + 66])
    return scenes


@dataclass
class ScenePressTracker:
    """Ignore stale scene markers and repeats of a single BLE announcement."""

    previous: bytes | None = None

    def feed(self, payload: bytes) -> int | None:
        if len(payload) != 17 or not payload[6]:
            return None
        previous = self.previous
        self.previous = payload
        if previous is None or payload[10] != 2 or payload[8] >= SCENE_LIMIT:
            return None
        if payload[6] == previous[6]:
            return None
        # The global sequence also changes on unrelated events. V48 increments one
        # of these key counters on the scene IPC path before refreshing advertising.
        advances = sum(
            bool(current >> 5) and (current & 31) == ((old & 31) % 31) + 1
            for current, old in zip(payload[11:13], previous[11:13])
        )
        if advances == 1:
            return payload[8]
        return None
