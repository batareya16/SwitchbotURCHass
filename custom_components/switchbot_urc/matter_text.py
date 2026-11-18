"""WoRWS "Matter" text remote: four captioned softkeys A-D and their advertised presses.

The write format is the one the official app builds for a Matter tile (``getCmdMatter`` and
``getEditMatterNameCmdMatter`` in the URC bundle): a normal ``0F 62 06`` page for device type
39 / control type 3 with four key records of type 5. Each record's keyFun is its index plus one
and its 32-byte field is the caption. V48 firmware evidence is in
``firmware-worws/evidence/mixed-v48/matter-text-remotes.md``.

Presses are not sent to a target. The remote only bumps one of four counters in its
advertisement (category 3), which is what :class:`MatterPressTracker` watches.
"""
from __future__ import annotations

from dataclasses import dataclass

from .commands import build_create

DEVICE_TYPE = 0x27
CONTROL_TYPE = 3
KEY_TYPE = 5
KEY_COUNT = 4
LETTERS = "ABCD"
CAPTION_FIELD = 32
# The app terminates every edited caption by writing zero to the last byte of the field.
CAPTION_MAX_BYTES = CAPTION_FIELD - 1
DEFAULT_CAPTIONS = ("BUTTON 1", "BUTTON 2", "BUTTON 3", "BUTTON 4")
STUDIO_DEVICE_TYPE = "MATTER_TEXT"
COMPANY_ID = 0x0969
ADVERT_CATEGORY = 3
PAYLOAD_SIZE = 17
_COUNTER_OFFSET = 13  # A, B, C, D at payload[13:17]; category at [10]; sequence at [6]
_ID_PREFIX = "4d54"  # "MT": a synthetic, never-routable address that cannot clash with a bridge


def normalize_captions(captions) -> tuple[str, ...]:
    """Validate the four captions exactly as the firmware field can hold them."""
    if not isinstance(captions, (list, tuple)) or len(captions) != KEY_COUNT:
        raise ValueError("A text remote has four captions, A to D")
    result = []
    for letter, caption in zip(LETTERS, captions):
        text = str(caption).strip()
        raw = text.encode("utf-8")
        if not raw:
            raise ValueError(f"Give button {letter} a caption")
        if b"\0" in raw:
            raise ValueError(f"Button {letter} has an invalid character")
        if len(raw) > CAPTION_MAX_BYTES:
            raise ValueError(
                f"Button {letter}'s caption is {len(raw)} bytes; the limit is {CAPTION_MAX_BYTES} "
                "(Cyrillic letters use two bytes each)"
            )
        result.append(text)
    return tuple(result)


def caption_field(caption: str) -> bytes:
    raw = caption.encode("utf-8")
    if len(raw) > CAPTION_MAX_BYTES:
        raise ValueError("caption does not fit the 32-byte field")
    return raw.ljust(CAPTION_FIELD, b"\0")


def new_device_id(taken: set[bytes], id_to_bytes) -> str:
    """A 12-hex id for the table. The bind check rejects an id already used by another slot."""
    for serial in range(0x10000):
        candidate = f"{_ID_PREFIX}{serial:08x}"
        if id_to_bytes(candidate) not in taken:
            return candidate
    raise ValueError("Could not allocate an id for the text remote")


def build_matter_create(
    *, remote_index: int, device_id: str, name: str, captions
) -> bytes:
    """One complete create or caption-update packet (same bytes the app sends)."""
    captions = normalize_captions(captions)
    return build_create(
        remote_index=remote_index,
        device_type=DEVICE_TYPE,
        control_type=CONTROL_TYPE,
        control_mode=0,
        icon=0,
        device_id=device_id,
        name=name,
        ble_key_type=KEY_TYPE,
        keys=[
            {"keyIndex": index, "keyFun": index + 1, "key_type": KEY_TYPE,
             "field32": caption_field(caption)}
            for index, caption in enumerate(captions)
        ],
    )


def is_matter_row(row) -> bool:
    """A device-table row (slot, type, control, id) of a Matter text remote."""
    return row[1] == DEVICE_TYPE and row[2] == CONTROL_TYPE


@dataclass
class MatterPressTracker:
    """Turn the stream of advertisements into A-D presses.

    The remote increments a five-bit counter (1..31, wrapping to 1) for the pressed key and
    sets that key's state to 1, then bumps the global sequence and advertises category 3. The
    counters stay latched afterwards, so only an advance of exactly one counter, seen together
    with a new sequence and the Matter category, is a press. The first sighting is a baseline.
    """

    previous: bytes | None = None

    def feed(self, payload: bytes) -> int | None:
        if len(payload) != PAYLOAD_SIZE or not payload[6]:
            return None
        previous = self.previous
        self.previous = payload
        if previous is None or payload[10] != ADVERT_CATEGORY or payload[6] == previous[6]:
            return None
        advanced = [
            index
            for index in range(KEY_COUNT)
            if (current := payload[_COUNTER_OFFSET + index]) >> 5
            and (current & 31) == ((previous[_COUNTER_OFFSET + index] & 31) % 31) + 1
        ]
        return advanced[0] if len(advanced) == 1 else None
