"""
import_tg.py — load Polymer Handbook 4th ed. Tg data into polymer_db.sqlite.

Source: literature/Polymer_Handbook/tg_all.csv
Format: semicolon-delimited, columns:
    no, material_category, polymer, form, cas_no, tg_C, remarks, refs

Run from the project root:
    python -m db.import_tg
"""

import csv
import os
import re
import sqlite3
import sys

_HERE = os.path.dirname(__file__)
_ROOT = os.path.dirname(_HERE)
_CSV = os.path.join(_ROOT, "literature", "Polymer_Handbook", "tg_all.csv")

SOURCE_KEY = "PolymerHandbook4ed"
SOURCE_TITLE = "Brandrup, Immergut & Grulke (eds.), Polymer Handbook, 4th ed."
SOURCE_YEAR = 1999


def _parse_tg(tg_raw: str, remarks: str) -> list[tuple[float, bool, bool]]:
    """
    Parse the tg_C field. Returns list of (tg_C_value, approximate, conflicting).

    Handles:
      "106"         → [(106.0, False, False)]
      "~110"        → [(110.0, True,  False)]
      "107, 43"     → [(107.0, False, True), (43.0, False, True)]
      ""            → []
    """
    tg_raw = tg_raw.strip()
    if not tg_raw:
        return []

    approximate = tg_raw.startswith("~")
    if approximate:
        tg_raw = tg_raw[1:].strip()

    conflicting = "conflict" in remarks.lower()

    parts = [p.strip() for p in tg_raw.split(",")]
    results = []
    for part in parts:
        # strip any trailing text (e.g. "below Tm")
        m = re.match(r"^-?\d+(\.\d+)?", part)
        if m:
            results.append((float(m.group()), approximate, conflicting))

    return results


def run(csv_path: str = _CSV, db_path: str | None = None) -> None:
    import db as polymer_db  # noqa: PLC0415
    if db_path:
        polymer_db.DB_PATH = db_path
    polymer_db.init_db()

    conn = polymer_db._get_conn()

    # Upsert source
    conn.execute(
        "INSERT OR IGNORE INTO sources(key, title, year) VALUES (?,?,?)",
        (SOURCE_KEY, SOURCE_TITLE, SOURCE_YEAR),
    )
    source_id = conn.execute(
        "SELECT id FROM sources WHERE key=?", (SOURCE_KEY,)
    ).fetchone()[0]

    tg_rows = 0
    polymer_cache: dict[tuple[str, str], int] = {}

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            polymer_name = row["polymer"].strip()
            cas_no = row["cas_no"].strip() or None
            category = row["material_category"].strip()
            form = row["form"].strip() or None
            remarks = row["remarks"].strip()
            handbook_ref = row["refs"].strip() or None
            tg_raw = row["tg_C"].strip()

            if not polymer_name:
                continue

            # Resolve or insert polymer
            cache_key = (polymer_name, cas_no or "")
            if cache_key not in polymer_cache:
                conn.execute(
                    "INSERT OR IGNORE INTO polymers(name, cas_no, category) VALUES (?,?,?)",
                    (polymer_name, cas_no, category),
                )
                pid = conn.execute(
                    "SELECT id FROM polymers WHERE name=? AND (cas_no=? OR (cas_no IS NULL AND ? IS NULL))",
                    (polymer_name, cas_no, cas_no),
                ).fetchone()[0]
                polymer_cache[cache_key] = pid
            polymer_id = polymer_cache[cache_key]

            # Parse and insert Tg values
            parsed = _parse_tg(tg_raw, remarks)
            for tg_C, approximate, conflicting in parsed:
                tg_K = tg_C + 273.15
                notes_parts = []
                if remarks and remarks.lower() not in ("conflicting data",):
                    notes_parts.append(remarks)
                if approximate:
                    notes_parts.append("approximate")
                if conflicting:
                    notes_parts.append("conflicting data")
                notes = "; ".join(notes_parts) or None

                # Extract measurement method from remarks
                method = None
                method_keywords = [
                    "DSC", "dilatometry", "dilatometric",
                    "mechanical method", "NMR", "DMA",
                    "extrapolated", "brittle temperature",
                ]
                for kw in method_keywords:
                    if kw.lower() in remarks.lower():
                        method = kw
                        break

                conn.execute(
                    """INSERT INTO tg_measurements
                       (polymer_id, tg_C, tg_K, form, method, source_id, notes, handbook_ref)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (polymer_id, tg_C, tg_K, form, method, source_id, notes, handbook_ref),
                )
                tg_rows += 1

    conn.commit()
    n_polymers = conn.execute("SELECT COUNT(*) FROM polymers").fetchone()[0]
    print(f"Inserted {tg_rows} Tg rows, {n_polymers} unique polymers")


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else _CSV
    run(csv_path)
