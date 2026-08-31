#!/usr/bin/env python3
"""
import_polydatabase.py — load the PolyDatabase MD-simulation-literature dataset into
db/polydatabase_md.sqlite.

PolyDatabase (https://polydatabase.com) is an LLM-mined index of polymer MD-simulation
records: 1,095 rows / 198 DOIs / 1995-2025, covering density, glass-transition temperature,
radius of gyration, Young's modulus, diffusion coefficient, and viscosity, each tied to a
force field and a source DOI, plus a JSON "Extra Information" blob (temperature, pressure,
chain length, chain count, ensemble, morphology).

Source paper: Paudel, Shakya, Nag, Karki & An, "A structured dataset of polymers in
molecular dynamics simulations extracted by LLM-assisted text mining", ChemRxiv,
https://doi.org/10.26434/chemrxiv.15000400/v1 (posted 2026-02-25).

Data (CC BY 4.0): Zenodo record 17401439 —
https://zenodo.org/api/records/17401439/files/polydatabase_dataset_augmented.xlsx/content
(the "augmented" file is used here for its extra name-matching columns: Abbreviation,
Source Monomer, Common Trade Name, Polymer Chain Structure, Polymer Architecture,
Polymer Thermal Type, Polymer Origin Type.)

This is a static, versioned snapshot, not an accumulating fact table like tg_measurements —
each run fully rebuilds the table (DROP + recreate + bulk insert) rather than upserting.

Requires `openpyxl` (pip install openpyxl) to read the .xlsx — an ad hoc dependency for
this one-off ingest tool, not part of requirements-test.txt, matching the precedent set by
import_mark2007.py's pdfplumber dependency.

Usage (run from the project root):
    python3 db/ingest_scripts/import_polydatabase.py
    python3 db/ingest_scripts/import_polydatabase.py --xlsx-path PATH --db-path PATH
"""

import argparse
import json
import math
import os
import sqlite3
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))  # .../db/ingest_scripts
_DB_DIR = os.path.dirname(_HERE)  # .../db
_ROOT = os.path.dirname(_DB_DIR)  # repo root
_DEFAULT_XLSX = os.path.join(_ROOT, "literature", "polydatabase", "polydatabase_dataset_augmented.xlsx")
_DEFAULT_DB = os.path.join(_DB_DIR, "polydatabase_md.sqlite")
_SCHEMA = os.path.join(_DB_DIR, "polydatabase_schema.sql")

# Standardized unit for each `Property` value, per the source paper ("units were
# standardized across all outputs"). Not derived from the per-row "reported_value_original_unit"
# in Extra Information, which records the *source paper's own* unit before standardization.
_PROPERTY_UNIT = {
    "density": "g/cm3",
    "glass_transition_temp": "K",
    "youngs_modulus": "GPa",
    "radius_gyration": "nm",
    "diffusion_coefficient": "m2/s",
    "viscosity": "Pa.s",
}

_COLUMN_MAP = {
    "polymer_name": "Polymer Name",
    "abbreviation": "Abbreviation",
    "force_field": "Force Field",
    "force_field_type": "Force Field Type",
    "property": "Property",
    "value": "Value",
    "extra_info": "Extra Information",
    "source_monomer": "Source Monomer",
    "common_trade_name": "Common Trade Name",
    "chain_structure": "Polymer Chain Structure",
    "architecture": "Polymer Architecture",
    "thermal_type": "Polymer Thermal Type",
    "origin_type": "Polymer Origin Type",
    "doi": "DOI",
}


def run(xlsx_path: str = _DEFAULT_XLSX, db_path: str = _DEFAULT_DB) -> None:
    import pandas as pd  # noqa: PLC0415

    if not os.path.exists(xlsx_path):
        print(f"error: dataset not found at {xlsx_path}", file=sys.stderr)
        print(
            "download it from the public Zenodo record first, e.g.:\n"
            "  curl -sL -o "
            f"{xlsx_path} \\\n"
            "    https://zenodo.org/api/records/17401439/files/polydatabase_dataset_augmented.xlsx/content",
            file=sys.stderr,
        )
        sys.exit(1)

    df = pd.read_excel(xlsx_path)

    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS md_records")
    with open(_SCHEMA, encoding="utf-8") as f:
        conn.executescript(f.read())

    rows_inserted = 0
    for _, row in df.iterrows():
        property_name = str(row[_COLUMN_MAP["property"]]).strip()
        extra_info = _clean(row[_COLUMN_MAP["extra_info"]])
        # Validate (but don't reshape) the JSON blob — store the raw string either way so a
        # caller can always json.loads() it themselves without this script's field list going stale.
        if extra_info is not None:
            try:
                json.loads(extra_info)
            except json.JSONDecodeError:
                pass

        raw_value = row[_COLUMN_MAP["value"]]
        value = float(raw_value) if isinstance(raw_value, (int, float)) and not math.isnan(raw_value) else None

        conn.execute(
            """INSERT INTO md_records
               (polymer_name, abbreviation, force_field, force_field_type, property, value,
                unit, doi, extra_info, source_monomer, common_trade_name, chain_structure,
                architecture, thermal_type, origin_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(row[_COLUMN_MAP["polymer_name"]]).strip(),
                _clean(row[_COLUMN_MAP["abbreviation"]]),
                _clean(row[_COLUMN_MAP["force_field"]]),
                _clean(row[_COLUMN_MAP["force_field_type"]]),
                property_name,
                value,
                _PROPERTY_UNIT.get(property_name),
                _clean(row[_COLUMN_MAP["doi"]]),
                extra_info,
                _clean(row[_COLUMN_MAP["source_monomer"]]),
                _clean(row[_COLUMN_MAP["common_trade_name"]]),
                _clean(row[_COLUMN_MAP["chain_structure"]]),
                _clean(row[_COLUMN_MAP["architecture"]]),
                _clean(row[_COLUMN_MAP["thermal_type"]]),
                _clean(row[_COLUMN_MAP["origin_type"]]),
            ),
        )
        rows_inserted += 1

    conn.commit()
    n_dois = conn.execute("SELECT COUNT(DISTINCT doi) FROM md_records").fetchone()[0]
    n_polymers = conn.execute("SELECT COUNT(DISTINCT polymer_name) FROM md_records").fetchone()[0]
    print(f"Inserted {rows_inserted} rows, {n_dois} unique DOIs, {n_polymers} unique polymer names")
    conn.close()


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest the PolyDatabase MD-literature dataset")
    parser.add_argument("--xlsx-path", default=_DEFAULT_XLSX)
    parser.add_argument("--db-path", default=_DEFAULT_DB)
    args = parser.parse_args()
    run(args.xlsx_path, args.db_path)
