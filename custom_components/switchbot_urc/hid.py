"""Best-effort decoding of HID / notify button reports from the remote.

When the remote is HID-configured it may notify key presses as standard HID keyboard reports
(8 bytes: [modifiers, reserved, k1..k6]) or consumer-control reports. We don't know the exact
report map until tested on a real host, so this decoder is intentionally permissive: it extracts
any non-zero usage codes and labels the common ones, and always passes the raw report through so
automations can match on bytes even before the map is finalized.
"""
from __future__ import annotations

# Common HID keyboard usage codes (page 0x07) the remote is likely to emit.
_KEYBOARD_USAGE = {
    0x28: "ENTER", 0x29: "ESC", 0x2A: "BACKSPACE", 0x4F: "RIGHT", 0x50: "LEFT",
    0x51: "DOWN", 0x52: "UP", 0x4A: "HOME", 0x76: "MENU",
}
# Common consumer-control usages (page 0x0C), low byte.
_CONSUMER_USAGE = {
    0xB0: "PLAY", 0xB1: "PAUSE", 0xCD: "PLAYPAUSE", 0xE2: "MUTE", 0xE9: "VOL+",
    0xEA: "VOL-", 0x30: "POWER",
}


def decode_report(report: bytes) -> dict:
    """Return {"raw": hex, "keys": [labels], "codes": [ints]} for a HID/notify report."""
    keys: list[str] = []
    codes: list[int] = []
    # Standard 8-byte keyboard report: modifiers, reserved, up to 6 key usages.
    if len(report) >= 3:
        for b in report[2:8]:
            if b:
                codes.append(b)
                keys.append(_KEYBOARD_USAGE.get(b, f"0x{b:02X}"))
    # Fallback: any lone consumer usage in a short report.
    for b in report:
        if b in _CONSUMER_USAGE and _CONSUMER_USAGE[b] not in keys:
            keys.append(_CONSUMER_USAGE[b])
            codes.append(b)
    return {"raw": report.hex(), "keys": keys, "codes": codes}


def is_press(report: bytes) -> bool:
    """True if the report carries at least one active key (not an all-zero key-up)."""
    return any(report[2:8]) if len(report) >= 3 else any(report)
