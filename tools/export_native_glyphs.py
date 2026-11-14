#!/usr/bin/env python3
"""Export the indexed V48 keyFun glyphs as transparent PNGs for Remote Studio."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image


def decode(payload: bytes) -> list[tuple[int, int, int]]:
    pixels = []
    offset = 0
    while offset < len(payload):
        control = payload[offset]
        offset += 1
        count = control & 0x7F
        size = 3 if control & 0x80 else count * 3
        if offset + size > len(payload):
            raise ValueError(f"truncated pixel run at byte {offset - 1}")
        if control & 0x80:
            pixels.extend([tuple(payload[offset:offset + 3])] * count)
        else:
            pixels.extend(tuple(payload[pos:pos + 3]) for pos in range(offset, offset + size, 3))
        offset += size
    return pixels


def rgb565a8(triples: list[tuple[int, int, int]]) -> list[tuple[int, int, int, int]]:
    result = []
    for high, low, alpha in triples:
        value = (high << 8) | low
        result.append((
            ((value >> 11) & 0x1F) * 255 // 31,
            ((value >> 5) & 0x3F) * 255 // 63,
            (value & 0x1F) * 255 // 31,
            alpha,
        ))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--res", type=Path, required=True, help="V48 RES.bin")
    parser.add_argument("--index", type=Path, required=True, help="native-glyph-resource-index.csv")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    data = args.res.read_bytes()
    with args.index.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    resources: dict[int, tuple[int, int, int, int]] = {}
    for row in rows:
        if not row["primary_res_file_offset"]:
            continue
        function = int(row["keyFun"], 16)
        resource = int(row["primary_res_file_offset"], 16)
        width = int(row["primary_width"])
        height = int(row["primary_height"])
        payload_size = int(row["primary_payload_size_bytes"])
        entry = (resource, width, height, payload_size)
        previous = resources.setdefault(function, entry)
        if previous != entry:
            raise ValueError(f"duplicate keyFun {function:#06x} maps to different glyphs")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for function, (resource, width, height, payload_size) in resources.items():
        if resource + 12 + payload_size > len(data):
            raise ValueError(f"glyph {function:#06x} exceeds RES.bin")
        pixels = decode(data[resource + 12:resource + 12 + payload_size])
        if len(pixels) < width * height or len(pixels) - width * height > 4:
            raise ValueError(f"glyph {function:#06x} has an unexpected pixel count")
        image = Image.new("RGBA", (width, height))
        image.putdata(rgb565a8(pixels[:width * height]))
        image.save(args.output_dir / f"keyfun-{function:04x}.png")
    print(f"Exported {len(resources)} firmware glyphs to {args.output_dir}")


if __name__ == "__main__":
    main()
