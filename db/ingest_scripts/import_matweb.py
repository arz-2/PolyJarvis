#!/usr/bin/env python3
"""
import_matweb.py — Load MatWeb property data into polymer_db.sqlite and
patch missing fields in guides/polymer_rules.json.

Input: data/matweb_refs.json  (produced by fetch_matweb_refs.py)

Changes to polymer_db.sqlite:
  1. Adds "MatWeb" to sources table (skips if already present).
  2. Updates poly_class on the canonical polymer row for each class.
  3. Inserts density_measurements (RT amorphous, phase='amorphous') if not
     already present from MatWeb.
  4. Inserts mechanical_measurements (youngs_modulus, bulk_modulus,
     shear_modulus, poisson_ratio) if not already present from MatWeb.

Changes to guides/polymer_rules.json (missing fields only — never overwrites):
  - experimental_density_gcm3  for PEST, PVNL, PSFO, PDIE, PKTN
  - exp_K_GPa                  for PVNL
  - exp_E_GPa                  for PHYC (PE), PDIE (NR/PI)
  - Adds "sources" top-level key with MatWeb citation entry per polymer.
  - Appends MatWeb source ID to each class's citations array.

Usage:
  python3 db/ingest_scripts/import_matweb.py [--dry-run] [--refs PATH]

Run from the project root:
  python -m db.ingest_scripts.import_matweb
"""

import argparse
import json
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
DEFAULT_REFS = REPO_ROOT / "data" / "matweb_refs.json"
DB_PATH      = REPO_ROOT / "db" / "polymer_db.sqlite"
RULES_PATH   = REPO_ROOT / "guides" / "polymer_rules.json"

# Canonical polymer_id in polymer_db.sqlite for each PolyJarvis class.
# These are the primary single-chain, amorphous, unfilled grades.
CANONICAL_DB_IDS: dict[str, int] = {
    "PHYC": 1951,   # "Polyethylene" (generic amorphous)
    "PACR": 211,    # "Poly(methyl methacrylate)"
    "PEST": 826,    # "Poly(lactic acid)"
    "PVNL": 634,    # "Poly(vinyl chloride)"
    "PSFO": 1997,   # "Bisphenol-A polysulfone"
    "PDIE": 2069,   # "cis-1,4-Polyisoprene"
    "PKTN": 963,    # "Poly(ether ether ketone)"
}

# polymer_rules.json fields that come from MatWeb and are MISSING for these classes.
# Format: {class: [field, ...]}
MISSING_FIELDS: dict[str, list[str]] = {
    "PEST": ["experimental_density_gcm3"],
    "PVNL": ["experimental_density_gcm3", "exp_K_GPa", "exp_E_GPa"],
    "PSFO": ["experimental_density_gcm3"],
    "PDIE": ["experimental_density_gcm3", "exp_E_GPa"],
    "PKTN": ["experimental_density_gcm3"],
    "PHYC": ["exp_E_GPa"],
    "PACR": [],  # already complete
}

# Representative polymer name per class (for notes field in DB)
CLASS_POLYMER: dict[str, str] = {
    "PHYC": "PE", "PACR": "PMMA", "PEST": "PLA",
    "PVNL": "PVC", "PSFO": "PSU", "PDIE": "PI", "PKTN": "PEEK",
}

# polymer_rules.json key for each PolyJarvis class
CLASS_TO_RULES_KEY: dict[str, str] = {rec[0]: rec[1]  # polymer_id → poly_class
    for rec in [("PE", "PHYC"), ("PMMA", "PACR"), ("PLA", "PEST"),
                ("PVC", "PVNL"), ("PSU", "PSFO"), ("NR", "PDIE"), ("PEEK", "PKTN")]}
# Reverse: poly_class → polymer_id (e.g. "PHYC" → "PE")
CLASS_TO_PID = {v: k for k, v in CLASS_TO_RULES_KEY.items()}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _ensure_matweb_source(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM sources WHERE key='MatWeb'").fetchone()
    if row:
        return row[0]
    conn.execute(
        "INSERT INTO sources (key, title, doi, year) VALUES (?,?,?,?)",
        ("MatWeb", "MatWeb — online materials property database (matweb.com)",
         None, None),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _update_poly_class(conn: sqlite3.Connection, db_id: int,
                       poly_class: str, dry_run: bool) -> None:
    current = conn.execute("SELECT poly_class FROM polymers WHERE id=?",
                           (db_id,)).fetchone()
    if current and current[0] == poly_class:
        return
    if dry_run:
        print(f"  [DRY] UPDATE polymers SET poly_class={poly_class!r} WHERE id={db_id}")
        return
    conn.execute("UPDATE polymers SET poly_class=? WHERE id=?", (poly_class, db_id))


def _already_in_db(conn: sqlite3.Connection, table: str, polymer_id: int,
                   source_id: int, extra_where: str = "") -> bool:
    sql = (f"SELECT 1 FROM {table} WHERE polymer_id=? AND source_id=?"
           + (f" AND {extra_where}" if extra_where else ""))
    return conn.execute(sql, (polymer_id, source_id)).fetchone() is not None


def _insert_density(conn: sqlite3.Connection, db_id: int, source_id: int,
                    density: float, polymer_id: str, dry_run: bool) -> None:
    if _already_in_db(conn, "density_measurements", db_id, source_id):
        print(f"  skip density (already in DB)")
        return
    note = f"amorphous RT from MatWeb ({CLASS_POLYMER.get(CANONICAL_DB_IDS.get(polymer_id, 0), polymer_id)})"
    if dry_run:
        print(f"  [DRY] INSERT density_measurements: polymer_id={db_id} "
              f"density={density} T=298.15 phase=amorphous src={source_id}")
        return
    conn.execute(
        "INSERT INTO density_measurements "
        "(polymer_id, density_gcm3, T_K, phase, source_id, notes) VALUES (?,?,?,?,?,?)",
        (db_id, density, 298.15, "amorphous", source_id, note),
    )


def _insert_mechanical(conn: sqlite3.Connection, db_id: int, source_id: int,
                       prop: str, value_GPa: float, dry_run: bool) -> None:
    if _already_in_db(conn, "mechanical_measurements", db_id, source_id,
                      f"property='{prop}'"):
        print(f"  skip {prop} (already in DB)")
        return
    if dry_run:
        print(f"  [DRY] INSERT mechanical_measurements: polymer_id={db_id} "
              f"property={prop!r} value_GPa={value_GPa} T=298.15 src={source_id}")
        return
    conn.execute(
        "INSERT INTO mechanical_measurements "
        "(polymer_id, property, value_GPa, T_K, source_id) VALUES (?,?,?,?,?)",
        (db_id, prop, value_GPa, 298.15, source_id),
    )


# ---------------------------------------------------------------------------
# polymer_rules.json patching
# ---------------------------------------------------------------------------

def _patch_rules(rules: dict, rec: dict, poly_class: str,
                 source_id_key: str) -> list[str]:
    """Apply MatWeb record to polymer_rules.json class entry.

    Returns list of (field, description) strings for display.
    Only fills fields that are currently MISSING (key absent from the class dict).
    """
    entry   = rules["classes"][poly_class]
    pid     = CLASS_POLYMER.get(CLASS_TO_PID.get(poly_class, ""), "")
    changes = []

    # --- experimental_density_gcm3 ---
    if ("experimental_density_gcm3" in MISSING_FIELDS.get(poly_class, [])
            and "experimental_density_gcm3" not in entry
            and "density_gcm3" in rec):
        val = rec["density_gcm3"]
        entry["experimental_density_gcm3"] = {
            pid: val,
            "note": f"amorphous RT (MatWeb)",
            "source": source_id_key,
        }
        changes.append(f"experimental_density_gcm3 = {val} g/cm³")

    # --- exp_K_GPa ---
    k_val = rec.get("K_GPa") or rec.get("K_GPa_derived")
    if ("exp_K_GPa" in MISSING_FIELDS.get(poly_class, [])
            and "exp_K_GPa" not in entry
            and k_val is not None):
        lo = round(k_val * 0.85, 2)
        hi = round(k_val * 1.15, 2)
        entry["exp_K_GPa"] = {
            "min": lo, "max": hi,
            "source": source_id_key,
            "note": f"derived K={k_val} GPa ±15% (MatWeb)",
        }
        changes.append(f"exp_K_GPa = [{lo}, {hi}] GPa")

    # --- exp_E_GPa ---
    if ("exp_E_GPa" in MISSING_FIELDS.get(poly_class, [])
            and "exp_E_GPa" not in entry
            and "E_GPa" in rec):
        e_val = rec["E_GPa"]
        entry["exp_E_GPa"] = {
            pid: e_val,
            "source": source_id_key,
            "note": "amorphous RT (MatWeb)",
        }
        changes.append(f"exp_E_GPa = {e_val} GPa")

    # --- citations ---
    cits = entry.get("citations", [])
    if source_id_key not in cits:
        entry.setdefault("citations", []).append(source_id_key)
        changes.append(f"citations ← {source_id_key}")

    return changes


def _add_sources_entry(rules: dict, rec: dict, source_id_key: str) -> None:
    sources = rules.setdefault("sources", {})
    if source_id_key in sources:
        return
    sources[source_id_key] = {
        "id":         source_id_key,
        "type":       "database",
        "database":   "MatWeb",
        "material_name": rec.get("material_name", ""),
        "url":        rec.get("url", ""),
        "accessed":   rec.get("accessed", ""),
        "poly_class": rec.get("poly_class", ""),
        "properties_extracted": [
            k for k in ("density_gcm3", "E_GPa", "G_GPa", "K_GPa", "poisson", "Tg_K")
            if k in rec
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(refs_path: Path, dry_run: bool) -> None:
    refs: dict[str, dict] = json.loads(refs_path.read_text())
    rules: dict = json.loads(RULES_PATH.read_text())

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    if not dry_run:
        source_id = _ensure_matweb_source(conn)
    else:
        source_id = -1
        print("[DRY-RUN MODE — no writes]\n")

    for pid, rec in refs.items():
        if rec.get("status") != "ok":
            print(f"[{pid}] skipped (status={rec.get('status')})")
            continue

        poly_class = rec["poly_class"]
        db_id      = CANONICAL_DB_IDS.get(poly_class)
        if db_id is None:
            print(f"[{pid}] WARN: no canonical DB id for class {poly_class!r}")
            continue

        print(f"\n[{pid}] ({poly_class}, db_id={db_id})")

        # 1. Update poly_class in DB
        _update_poly_class(conn, db_id, poly_class, dry_run)

        # 2. Insert density
        if "density_gcm3" in rec:
            _insert_density(conn, db_id, source_id, rec["density_gcm3"], poly_class, dry_run)

        # 3. Insert mechanical measurements
        for prop_key, db_prop in [("E_GPa", "youngs_modulus"),
                                   ("G_GPa", "shear_modulus"),
                                   ("K_GPa", "bulk_modulus")]:
            if prop_key in rec:
                _insert_mechanical(conn, db_id, source_id, db_prop, rec[prop_key], dry_run)
        # Derived K
        if "K_GPa" not in rec and "K_GPa_derived" in rec:
            _insert_mechanical(conn, db_id, source_id, "bulk_modulus",
                               rec["K_GPa_derived"], dry_run)

        # 4. Patch polymer_rules.json
        source_id_key = f"MatWeb_{pid}"
        _add_sources_entry(rules, rec, source_id_key)
        changes = _patch_rules(rules, rec, poly_class, source_id_key)
        if changes:
            for ch in changes:
                print(f"  rules: {ch}")
        else:
            print(f"  rules: no missing fields for {poly_class}")

    if not dry_run:
        conn.commit()
        conn.close()
        # Write updated polymer_rules.json
        RULES_PATH.write_text(json.dumps(rules, indent=2, ensure_ascii=False))
        print(f"\nCommitted DB changes.")
        print(f"Updated {RULES_PATH}")
    else:
        conn.close()
        print("\n[DRY-RUN] No files written.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print planned changes without writing")
    ap.add_argument("--refs",    default=str(DEFAULT_REFS),
                    help=f"Path to matweb_refs.json (default: {DEFAULT_REFS})")
    args = ap.parse_args()

    refs_path = Path(args.refs)
    if not refs_path.exists():
        sys.exit(f"refs file not found: {refs_path}\nRun fetch_matweb_refs.py first.")

    run(refs_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
