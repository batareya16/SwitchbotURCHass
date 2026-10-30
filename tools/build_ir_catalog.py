"""Build `ir_catalog.db` from a SwitchBot app APK you already have.

The integration only needs IR *metadata* — type, brand, model and the `hxd_index` used to ask
`querymodel` for a code bank. The codes themselves are fetched from SwitchBot's cloud with the
user's own account and are never stored here.

The app ships that metadata as `assets/IRLibarayDb.pack` inside its asset split, which is a
gzip-compressed SQLite database. This script reads it and writes the compact catalog the
integration expects. Nothing is downloaded and nothing leaves the machine.

    python3 tools/build_ir_catalog.py --apk ~/switchbot_assets.apk \
        --output custom_components/switchbot_urc/ir_catalog.db

Point `--apk` at the split that actually contains the asset. In a split install it is usually
named `switchbot_assets.apk`; a single-file APK works too. The script says which entry it used.
"""
from __future__ import annotations

import argparse
import gzip
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

# remote_type -> library table prefix. The numbering is the integration's (see ir_catalog.py);
# `ARC` holds air conditioners and `AIR` air purifiers, which is easy to read the wrong way round.
TABLES = {
    1: "ARC",
    2: "TV",
    3: "Light",
    4: "IPTV",
    5: "TVBOX",
    6: "DVD",
    7: "FAN",
    8: "PJT",
    10: "SLR",
    11: "AIR",
    12: "ADO",
    13: "WATER",
    14: "Sweeper",
}
ASSET_NAME = "IRLibarayDb.pack"

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--apk", type=Path, required=True, help="APK containing the asset")
parser.add_argument("--output", type=Path, required=True, help="catalog file to write")
args = parser.parse_args()


def extract_library(apk: Path, into: Path) -> Path:
    with zipfile.ZipFile(apk) as archive:
        names = [name for name in archive.namelist() if name.endswith(ASSET_NAME)]
        if not names:
            raise SystemExit(
                f"{apk} does not contain {ASSET_NAME}. In a split install it normally lives in "
                "the asset split, often named switchbot_assets.apk."
            )
        name = names[0]
        print(f"reading {name}")
        packed = archive.read(name)
    library = into / "IRLibaray.db"
    library.write_bytes(gzip.decompress(packed))
    return library


with tempfile.TemporaryDirectory() as workdir:
    library_path = extract_library(args.apk, Path(workdir))
    library = sqlite3.connect(f"file:{library_path}?mode=ro", uri=True)
    version = dict(library.execute("SELECT TITLE, VERSION FROM DB_INFO_TABLE")).get("DB")
    print(f"library version {version}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    catalog = sqlite3.connect(args.output)
    catalog.execute(
        """CREATE TABLE profiles (
               remote_type INTEGER, brand TEXT, brand_cn TEXT, model TEXT, hxd_index TEXT,
               serial INTEGER, ac_type TEXT, code_type TEXT, priority TEXT)"""
    )

    written = 0
    for remote_type, prefix in TABLES.items():
        table = f"{prefix}_TABLE"
        try:
            rows = library.execute(
                f"""SELECT BRAND_EN, BRAND_CN, MODEL, HXD_INDEX, SERIAL, AC_TYPE, CODE_TYPE,
                           PRIORITY
                    FROM {table} GROUP BY HXD_INDEX"""
            ).fetchall()
        except sqlite3.Error as error:
            print(f"  {table}: skipped ({error})", file=sys.stderr)
            continue
        catalog.executemany(
            "INSERT INTO profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(remote_type, *row) for row in rows],
        )
        written += len(rows)
        print(f"  {table}: {len(rows)}")

    catalog.execute("CREATE INDEX profiles_type_brand ON profiles (remote_type, brand)")
    catalog.commit()
    catalog.close()

print(f"wrote {written} rows to {args.output}")
print(
    "This is the full library index, so it can contain more models than a catalog shipped with "
    "the integration. A model the cloud cannot resolve simply fails that one lookup."
)
