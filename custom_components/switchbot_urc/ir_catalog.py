"""Read-only access to the compact IR metadata catalog from the SwitchBot app."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


CATALOG_PATH = Path(__file__).with_name("ir_catalog.db")
REMOTE_TYPES = {
    1: "Air conditioner",
    2: "TV",
    3: "Light",
    4: "IPTV",
    5: "Set-top box",
    6: "DVD / Blu-ray",
    7: "Fan",
    8: "Projector",
    10: "Camera",
    11: "Air purifier",
    12: "Audio",
    13: "Water heater",
    14: "Robot vacuum",
}
# The catalog numbers its types like the SwitchBot hub does. The Universal Remote and the app use
# their own ids (REMOTE_*_TYPE in the app: IPTV 3, set-top box 4, DVD 5, fan 6, projector 7,
# camera 8, air purifier 10, audio 11, water heater 12, robot vacuum 13, light 14); that is the
# type byte written into the remote's pages and sent to the account.
APP_REMOTE_TYPES = {1: 1, 2: 2, 3: 14, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7, 10: 8, 11: 10, 12: 11,
                    13: 12, 14: 13}


def app_remote_type(catalog_type: int) -> int:
    """The remote type the app and the Universal Remote use for a catalog type."""
    return APP_REMOTE_TYPES.get(int(catalog_type), int(catalog_type))


@dataclass(frozen=True)
class CatalogProfile:
    """Metadata required to request one code bank from querymodel."""

    remote_type: int
    brand: str
    brand_cn: str
    model: str
    hxd_index: str
    serial: int
    ac_type: str
    code_type: str
    priority: str


def available() -> bool:
    """Whether the catalog file is present.

    The catalog is optional: it only carries the metadata needed to ask the cloud for a code
    bank, and it can be rebuilt from a SwitchBot app APK with `tools/build_ir_catalog.py`.
    When it is missing, the catalog install path is hidden and the other IR paths still work.
    """
    return CATALOG_PATH.is_file()


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{CATALOG_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def brands(remote_type: int) -> list[str]:
    """Return distinct catalog brands for a device type, or nothing without a catalog."""
    if not available():
        return []
    with _connect() as db:
        return [
            str(row[0])
            for row in db.execute(
                """SELECT DISTINCT brand FROM profiles WHERE remote_type = ?
                   ORDER BY brand COLLATE NOCASE""",
                (remote_type,),
            )
        ]


def profile_by_index(hxd_index: str) -> CatalogProfile | None:
    """Return the one catalog row behind an hxd_index, for callers that kept only that."""
    if not available():
        return None
    with _connect() as db:
        row = db.execute(
            """SELECT remote_type, brand, brand_cn, model, hxd_index, serial,
                      ac_type, code_type, priority
               FROM profiles WHERE hxd_index = ? LIMIT 1""",
            (str(hxd_index),),
        ).fetchone()
    return CatalogProfile(**dict(row)) if row else None


def profiles(remote_type: int, brand: str) -> list[CatalogProfile]:
    """Return all catalog models for a type and exact brand, or nothing without a catalog."""
    if not available():
        return []
    with _connect() as db:
        rows = db.execute(
            """SELECT remote_type, brand, brand_cn, model, hxd_index, serial,
                      ac_type, code_type, priority
               FROM profiles WHERE remote_type = ? AND brand = ? COLLATE NOCASE
               ORDER BY CASE WHEN model = 'no_model' THEN 1 ELSE 0 END,
                        model COLLATE NOCASE, serial""",
            (remote_type, brand),
        )
        return [CatalogProfile(**dict(row)) for row in rows]
