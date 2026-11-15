"""The Remote Studio glyph catalogue must match its exported firmware assets."""

import csv
import json
import re
import struct
from pathlib import Path


ROOT = Path(__file__).parents[1]
FRONTEND = ROOT / "custom_components/switchbot_urc/frontend"


def test_native_glyph_function_ids_match_index_and_png_assets():
    with (ROOT / "docs/native-glyph-resource-index.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        rows = list(csv.DictReader(stream))
    indexed = {
        int(row["keyFun"], 16): (int(row["primary_width"]), int(row["primary_height"]))
        for row in rows
        if row["primary_res_file_offset"]
    }

    source = (FRONTEND / "switchbot-urc-panel.js").read_text(encoding="utf-8")
    match = re.search(
        r"const NATIVE_GLYPH_LABELS = (\{.*?\});", source, re.S
    )
    assert match
    configured = {int(code): label for code, label in json.loads(match[1]).items()}
    assert configured == {
        int(row["keyFun"], 16): row["ui_label_en"] or None
        for row in rows
        if row["primary_res_file_offset"]
    }
    assets = {
        int(path.stem.removeprefix("keyfun-"), 16): path
        for path in (FRONTEND / "native-glyphs").glob("keyfun-*.png")
    }

    assert set(configured) == set(indexed) == set(assets)
    for function, path in assets.items():
        data = path.read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        assert struct.unpack(">II", data[16:24]) == indexed[function]
