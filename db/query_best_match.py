#!/usr/bin/env python3
"""
Query polymer_db.sqlite for experimental values best matching a simulated system.

Matching priority:
  1. --polymer_name  → exact then LIKE (copolymers excluded)   → match_confidence=high
  2. --polymer_class → CLASS_CANONICAL_PATTERN fallback         → match_confidence=medium
  3. no match        → writes {match_method: "none"} and exits 0

Per-property ranking:
  tg           : prefer atactic/conventional form; within that prefer DSC; fall back to
                 all forms (excluding plasticized/blend notes) only when no form rows exist
  density      : filter phase='amorphous' (fall back to 'glass'); pick row closest to T_sim_K
  bulk_modulus : pick rows closest to 298.15 K; aggregate range

Usage:
  python3 db/query_best_match.py \\
    --polymer_name "Poly(methyl methacrylate)" \\
    --polymer_class PACR \\
    --T_sim_K 300.0 \\
    --is_glassy true \\
    --properties tg,density,bulk_modulus \\
    --output_path /abs/path/to/exp_lookup.json

Limitations (known gaps):
  - No SMILES in DB — matching is name-based only.
  - Cooling rate, strain rate, system size are not in the schema.
  - DB name inconsistencies (e.g. "Poly(methylmethacrylate)" vs
    "Poly(methyl methacrylate)") may cause some entries to be missed.
"""

import argparse
import json
import math
import os
import sqlite3
import statistics
import sys
import re

DB_PATH = os.path.join(os.path.dirname(__file__), "polymer_db.sqlite")

# Per-class canonical LIKE patterns for the class-level fallback.
# Maps poly_class → list of patterns to try in order; first that returns ≥1 row wins.
# These target the most widely-studied representative polymer of each class.
CLASS_CANONICAL_PATTERN: dict[str, list[str]] = {
    "PHYC": ["Poly(ethylene)", "Polyethylene", "Polyethylene, linear"],
    "PDIE": ["cis-1,4-Polybutadiene", "Poly(butadiene)", "Poly(1,2-butadiene)"],
    "PACR": ["Poly(methyl methacrylate)", "Poly(methylmethacrylate)"],
    "PSTR": ["Poly(styrene)", "Polystyrene"],
    "PVNL": ["Poly(vinyl chloride)", "Polystyrene"],  # PVC canonical
    "PEST": ["Poly(lactic acid)", "Poly(L-lactic acid)"],
    "PCBN": ["Polycarbonate of Bisphenol A", "Polycarbonate, (with Bisphenol A)", "Polycarbonate"],
    "PAMD": ["Nylon 6,6", "Nylon 6 ["],
    "PKTN": ["Poly(ether ether ketone)", "Polyetheretherketone"],
    "PSFO": ["Bisphenol-A polysulfone", "Poly(sulfone)", "Poly(ether sulfone)"],
    "PIMD": ["Poly(ether imide)"],
    "POXI": ["Poly(ethylene oxide)", "Poly(oxymethylene)"],
    "PSUL": ["Poly(phenylene sulfide)"],
    "PURT": ["polyurethane"],
    "PPHS": ["polyphosphazene"],
    "PANH": ["polyanhydride"],
    "PIMN": ["Poly(ethylenimine)", "Poly(ethyleneimine)"],
    "PPNL": ["Poly(p-phenylene vinylene)", "poly(phenylene vinylene)"],
    "PHAL": ["Poly(tetrafluoroethylene)", "Polytetrafluoroethylene", "Poly(vinylidene fluoride)"],
    "PSIL": ["Poly(dimethylsiloxane)", "Poly(dimethylsiloxane)"],
    "PURA": ["polyurea"],
}

# Tg scoring — lower is better
_TG_FORM_RANK = {"atactic": 0, "conventional": 1, "syndiotactic": 2, "isotactic": 3, "heterotactic": 4}
_TG_METHOD_RANK = {"DSC": 0, "Dilatometry": 1, "Mechanical method": 2, "DMA": 3, "NMR": 4}
_PREFERRED_FORMS = {"atactic", "conventional"}
# Notes keywords that indicate non-neat polymer (plasticizer, blend, additive)
_BAD_NOTES = re.compile(r"plasticiz|dibutyl|diethyl|bis\(2-ethyl|blend|additive|fiber", re.I)
# Form keywords that indicate chemical modification or unusual structure (not a simple tacticity)
_BAD_FORM = re.compile(r"sulfonat|sulphonat|cyanoethyl|nitro|quaternar|filled|blended|grafted|with ", re.I)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _is_copolymer_name(name: str) -> bool:
    return "-co-" in name.lower() or "copolymer" in name.lower()


def _name_variants(polymer_name: str) -> list[str]:
    """
    Generate alternative DB name forms to catch inconsistent naming conventions:
      "Poly(styrene)"           → also try "Polystyrene"
      "Poly(methyl acrylate)"   → also try "Polymethyl acrylate"
    This handles the common split where Tg data uses "Poly(X)" (Polymer Handbook format)
    but density/mechanical data uses "PolyX" (Mark2007/PolymerDataHandbook format).
    """
    variants = [polymer_name]
    m = re.match(r"^Poly\((.+)\)$", polymer_name, re.I)
    if m:
        inner = m.group(1)
        # "Poly(styrene)" → "Polystyrene"; "Poly(methyl acrylate)" → "Polymethyl acrylate"
        compact = "Poly" + inner[0].upper() + inner[1:]
        variants.append(compact)
    return variants


def find_polymer_ids(
    conn: sqlite3.Connection,
    polymer_name: str | None,
    polymer_class: str | None,
) -> tuple[list[int], str, str]:
    """
    Returns (polymer_ids, match_method, match_confidence).
    Searches by name first (with compact-name variants), then class-level canonical pattern.
    """
    if polymer_name:
        seen: set[int] = set()
        ids: list[int] = []
        for variant in _name_variants(polymer_name):
            # Exact case-insensitive match
            rows = conn.execute(
                "SELECT id, name FROM polymers WHERE name = ? COLLATE NOCASE",
                (variant,),
            ).fetchall()
            # LIKE with copolymer exclusion
            if not rows:
                rows = conn.execute(
                    """SELECT id, name FROM polymers
                       WHERE name LIKE ? COLLATE NOCASE
                         AND name NOT LIKE '%-co-%'
                         AND LOWER(name) NOT LIKE '%copolymer%'""",
                    (f"%{variant}%",),
                ).fetchall()
            for r in rows:
                if r["id"] not in seen and not _is_copolymer_name(r["name"]):
                    seen.add(r["id"])
                    ids.append(r["id"])
        if ids:
            return ids, "name_match", "high"

    # 2. Class-level canonical fallback — try each canonical name + its variants
    if polymer_class and polymer_class in CLASS_CANONICAL_PATTERN:
        for canonical in CLASS_CANONICAL_PATTERN[polymer_class]:
            seen2: set[int] = set()
            ids2: list[int] = []
            for variant in _name_variants(canonical):
                rows = conn.execute(
                    """SELECT id, name FROM polymers
                       WHERE name LIKE ? COLLATE NOCASE
                         AND name NOT LIKE '%-co-%'
                         AND LOWER(name) NOT LIKE '%copolymer%'""",
                    (f"%{variant}%",),
                ).fetchall()
                for r in rows:
                    if r["id"] not in seen2 and not _is_copolymer_name(r["name"]):
                        seen2.add(r["id"])
                        ids2.append(r["id"])
            if ids2:
                return ids2, "class_representative", "medium"

    return [], "none", "none"


def _placeholders(ids: list[int]) -> str:
    return ",".join("?" * len(ids))


def get_tg_data(conn: sqlite3.Connection, polymer_ids: list[int]) -> dict | None:
    ph = _placeholders(polymer_ids)
    rows = conn.execute(
        f"""SELECT t.tg_K, t.form, t.method, t.notes, t.handbook_ref,
                   s.key AS source_key, p.name AS polymer_name
            FROM tg_measurements t
            JOIN polymers p ON p.id = t.polymer_id
            LEFT JOIN sources s ON s.id = t.source_id
            WHERE t.polymer_id IN ({ph}) AND t.tg_K IS NOT NULL
            ORDER BY t.tg_K""",
        polymer_ids,
    ).fetchall()
    if not rows:
        return None

    all_rows = [dict(r) for r in rows]

    # Exclude plasticized/blend rows and chemically-modified forms — these shift Tg by design
    clean_rows = [
        r for r in all_rows
        if not _BAD_NOTES.search(r.get("notes") or "")
        and not _BAD_FORM.search(r.get("form") or "")
    ]

    # Prefer atactic/conventional; fall back to all clean rows if none
    preferred = [r for r in clean_rows if (r["form"] or "").lower() in _PREFERRED_FORMS]
    agg_rows = preferred if preferred else clean_rows

    if not agg_rows:
        return None

    def _score(r: dict) -> tuple[int, int]:
        form_s = _TG_FORM_RANK.get((r["form"] or "").lower(), 99)
        method_s = _TG_METHOD_RANK.get(r["method"] or "", 99)
        return (form_s, method_s)

    agg_rows_sorted = sorted(agg_rows, key=_score)
    tg_values = sorted(r["tg_K"] for r in agg_rows)

    # IQR clipping for all_clean fallback (n ≥ 4) to remove outliers
    # (e.g. beta-transitions at low T, or chemical-modification artefacts)
    clipped = False
    if not preferred and len(tg_values) >= 4:
        q1 = statistics.quantiles(tg_values, n=4)[0]
        q3 = statistics.quantiles(tg_values, n=4)[2]
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        filtered = [v for v in tg_values if lo <= v <= hi]
        if filtered and len(filtered) < len(tg_values):
            tg_values = filtered
            agg_rows_sorted = [r for r in agg_rows_sorted if lo <= r["tg_K"] <= hi]
            clipped = True

    return {
        "agg_median_K": round(statistics.median(tg_values), 1),
        "agg_range_K": [round(min(tg_values), 1), round(max(tg_values), 1)],
        "n_rows": len(tg_values),
        "form_filter": "atactic/conventional" if preferred else "all_clean",
        "outliers_clipped": clipped,
        "preferred_method": agg_rows_sorted[0]["method"] if agg_rows_sorted else None,
        "rows": [
            {k: v for k, v in r.items() if k not in ("handbook_ref",)}
            for r in agg_rows_sorted[:6]
        ],
    }


def get_density_data(
    conn: sqlite3.Connection,
    polymer_ids: list[int],
    T_sim_K: float,
) -> dict | None:
    ph = _placeholders(polymer_ids)

    # Try amorphous first, then glass as fallback (both valid at 300 K)
    rows: list[dict] = []
    for phase in ("amorphous", "glass"):
        fetched = conn.execute(
            f"""SELECT d.density_gcm3, d.T_K, d.phase, d.notes,
                       s.key AS source_key, p.name AS polymer_name
                FROM density_measurements d
                JOIN polymers p ON p.id = d.polymer_id
                LEFT JOIN sources s ON s.id = d.source_id
                WHERE d.polymer_id IN ({ph}) AND d.phase = ?
                ORDER BY ABS(d.T_K - ?)""",
            [*polymer_ids, phase, T_sim_K],
        ).fetchall()
        if fetched:
            rows = [dict(r) for r in fetched]
            break

    result: dict = {}
    if rows:
        best = rows[0]
        all_vals = [r["density_gcm3"] for r in rows]
        result = {
            "value_gcm3": best["density_gcm3"],
            "T_K": best["T_K"],
            "phase": best["phase"],
            "source_key": best["source_key"],
            "n_rows": len(rows),
        }
        if len(rows) > 1:
            result["all_range_gcm3"] = [round(min(all_vals), 4), round(max(all_vals), 4)]

    # Also check density_equations — evaluate at T_sim_K
    eq_rows = conn.execute(
        f"""SELECT de.py_expr, de.t_min_C, de.t_max_C, de.phase, de.tg_C,
                   s.key AS source_key
            FROM density_equations de
            LEFT JOIN sources s ON s.id = de.source_id
            WHERE de.polymer_id IN ({ph})
            ORDER BY de.phase""",
        polymer_ids,
    ).fetchall()

    t_sim_C = T_sim_K - 273.15
    for eq_row in eq_rows:
        eq = dict(eq_row)
        if eq["t_min_C"] <= t_sim_C <= eq["t_max_C"]:
            try:
                val = eval(  # noqa: S307 — internal DB data only
                    eq["py_expr"],
                    {"__builtins__": {}, "math": math, "t": t_sim_C},
                )
                result["density_equation"] = {
                    "py_expr": eq["py_expr"],
                    "t_min_C": eq["t_min_C"],
                    "t_max_C": eq["t_max_C"],
                    "phase": eq["phase"],
                    "source_key": eq["source_key"],
                    "evaluated_gcm3": round(float(val), 4),
                }
                break
            except Exception:
                pass

    return result if result else None


def get_bulk_modulus_data(
    conn: sqlite3.Connection,
    polymer_ids: list[int],
    is_glassy: bool,
) -> dict | None:
    ph = _placeholders(polymer_ids)
    ref_T = 298.15
    rows = conn.execute(
        f"""SELECT m.value_GPa, m.T_K, m.notes,
                   s.key AS source_key, p.name AS polymer_name
            FROM mechanical_measurements m
            JOIN polymers p ON p.id = m.polymer_id
            LEFT JOIN sources s ON s.id = m.source_id
            WHERE m.polymer_id IN ({ph}) AND m.property = 'bulk_modulus'
            ORDER BY ABS(m.T_K - ?)""",
        [*polymer_ids, ref_T],
    ).fetchall()
    if not rows:
        return None

    rows = [dict(r) for r in rows]
    values = [r["value_GPa"] for r in rows]
    order_of_magnitude = "GPa" if is_glassy else "GPa (note: rubbery regime — verify scale)"

    return {
        "agg_median_GPa": round(statistics.median(values), 3),
        "agg_range_GPa": [round(min(values), 3), round(max(values), 3)],
        "n_rows": len(rows),
        "T_K_ref": ref_T,
        "value_unit": order_of_magnitude,
        # The schema has no measurement-method column, so rows can mix adiabatic K_S
        # (ultrasonic) with isothermal K_T (static compression / Tait). MD Murnaghan K is
        # K_T; grading against a K_S-inflated max is a false PASS. Consumers must check
        # per-row `notes` and prefer the polymer_rules exp_K_GPa (K_T-prioritized) range
        # for the headline grade when one exists.
        "method_caveat": (
            "rows may mix adiabatic K_S and isothermal K_T (no method column); MD reports "
            "K_T — cross-check row notes and prefer polymer_rules exp_K_GPa when set"
        ),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Query polymer_db for best experimental match")
    parser.add_argument("--polymer_name", default=None, help="Canonical polymer name for DB lookup")
    parser.add_argument("--polymer_class", default=None, help="PolyJarvis class code (fallback)")
    parser.add_argument("--T_sim_K", type=float, default=300.0, help="Simulation temperature in K")
    parser.add_argument(
        "--is_glassy",
        default="true",
        help="true/false — used to flag K scale; does not filter",
    )
    parser.add_argument(
        "--properties",
        default="tg,density,bulk_modulus",
        help="Comma-separated list of properties to look up",
    )
    parser.add_argument("--output_path", required=True, help="Absolute path for exp_lookup.json")
    args = parser.parse_args()

    props = {p.strip().lower() for p in args.properties.split(",")}
    is_glassy = args.is_glassy.lower() not in ("false", "0", "no")

    conn = _connect()
    polymer_ids, match_method, match_confidence = find_polymer_ids(
        conn, args.polymer_name, args.polymer_class
    )

    out_dir = os.path.dirname(os.path.abspath(args.output_path))
    os.makedirs(out_dir, exist_ok=True)

    if match_method == "none":
        result: dict = {
            "match_method": "none",
            "match_confidence": "none",
            "polymer_id": None,
            "polymer_name": None,
        }
        with open(args.output_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"No DB match. Wrote {args.output_path}")
        return

    p_name = conn.execute(
        "SELECT name FROM polymers WHERE id = ?", (polymer_ids[0],)
    ).fetchone()["name"]

    result = {
        "match_method": match_method,
        "match_confidence": match_confidence,
        "polymer_id": polymer_ids[0],
        "polymer_name": p_name,
        "n_polymer_ids": len(polymer_ids),
    }

    if "tg" in props:
        tg = get_tg_data(conn, polymer_ids)
        if tg:
            result["tg"] = tg

    if "density" in props:
        density = get_density_data(conn, polymer_ids, args.T_sim_K)
        if density:
            result["density"] = density

    if "bulk_modulus" in props:
        bm = get_bulk_modulus_data(conn, polymer_ids, is_glassy)
        if bm:
            result["bulk_modulus"] = bm

    with open(args.output_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"Wrote {args.output_path}")
    print(f"  match={match_method} ({match_confidence}), polymer='{p_name}' "
          f"(ids={polymer_ids})")
    if "tg" in result:
        tg = result["tg"]
        print(f"  Tg: {tg['agg_range_K']} K  median={tg['agg_median_K']} K  "
              f"n={tg['n_rows']}  filter={tg['form_filter']}")
    if "density" in result:
        d = result["density"]
        print(f"  density: {d.get('value_gcm3')} g/cm³  at T={d.get('T_K')} K  "
              f"phase={d.get('phase')}")
    if "bulk_modulus" in result:
        bm = result["bulk_modulus"]
        print(f"  K: {bm['agg_range_GPa']} GPa  median={bm['agg_median_GPa']} GPa  "
              f"n={bm['n_rows']}")


if __name__ == "__main__":
    main()
