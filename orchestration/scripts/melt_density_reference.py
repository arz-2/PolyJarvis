#!/usr/bin/env python3
"""Experimental melt density at T_equil, for the phase=melt equilibration gate.

The pre-cool gate ran with exp_density_gcm3=null because there was no experimental
comparison at melt temperature. There is: db/polymer_db.sqlite carries 53 melt rho(T)
equations from Mark 2007, each with its own fitted validity range, covering PS, PMMA, PC,
PSU, PEEK, PE, PP, Nylon, PEO, PVC, PDMS and PET. Reading one off at the run's own T_equil
catches a melt deficit BEFORE the cooling ramp is paid for.

The classification policy is transcribed from
manuscript_v2/test/ff_sensitivity/a1_experimental_melt_reference.py, which established it
and remains the frozen oracle this module is verified against. Do not "improve" it here
without re-checking a1's recorded results:

  * An equation is usable IN_RANGE, or NEAR_RANGE when T_equil falls no more than 10% of
    the fit's OWN WIDTH beyond its end. 7 C past a 150 C fit and 107 C past a 50 C fit are
    not the same act.
  * The deficit tolerance is the SPREAD ACROSS INDEPENDENT EQUATIONS for that polymer -- a
    measured quantity, not a chosen threshold. Below it, "deficit" is not separable from
    reference uncertainty.
  * A single equation cannot adjudicate a negative gap: melt_deficient is None there, never
    False. A positive gap still settles it.

Usage:
  python3 melt_density_reference.py --polymer_class PACR [--polymer_name "..."] \
      --t_equil_K 550 [--rho_melt 1.05]
Prints JSON. Called as a subprocess (the established contract with query_best_match.py),
never imported across the db/ and orchestration/ trees.
"""
import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "db" / "polymer_db.sqlite"
sys.path.insert(0, str(REPO_ROOT / "db"))

# A fit may be used this far beyond its own end, as a fraction of its width.
NEAR_RANGE_FRAC = 0.10
# Beyond this, the number is not evidence at all.
INDICATIVE_FRAC = 0.50


def _rho(py_expr: str, t_C: float) -> float:
    """Evaluate a Mark 2007 rho(T) equation. `t` is degrees Celsius."""
    return float(eval(py_expr, {"__builtins__": {}, "math": math}, {"t": t_C}))


def _melt_equation_rows(conn, ids):
    from query_best_match import get_density_equations_data
    data = get_density_equations_data(conn, ids) if ids else None
    return [r for r in (data or {}).get("rows", []) if r.get("phase") == "melt"]


def _resolve_ids(conn, polymer_class, polymer_name):
    """polymer_ids for this run, preferring a match that actually carries melt equations.

    find_polymer_ids' class fallback returns on the FIRST canonical pattern matching any
    polymers row, and the row that matches is often a Tg-table entry under a differently
    spaced name with no rho(T) data ("Poly(methyl methacrylate)" vs the equation-bearing
    "Poly(methylmethacrylate)"). Taking that answer loses PMMA, PC, PVC, PEO and PC -- most
    of the coverage this gate exists for. So: keep the primary result when it has melt
    equations, else walk the canonical patterns IN ORDER and take the first whose own rows
    carry them.

    Per-pattern, never a union across patterns: CLASS_CANONICAL_PATTERN["PVNL"] is
    ["Poly(vinyl chloride)", "Polystyrene"], so a union would grade PVC against
    polystyrene's rho(T). Tacticity-qualified rows are excluded unless the caller asked for
    one by name -- isotactic PMMA has its own density curve and a Tg ~90 K away, and the
    cells here are atactic (the same exclusion a1 makes).
    """
    from query_best_match import (CLASS_CANONICAL_PATTERN, _is_copolymer_name,
                                  _name_variants, _normalize_loose, find_polymer_ids)

    ids, method, confidence = find_polymer_ids(conn, polymer_name, polymer_class)
    if _melt_equation_rows(conn, ids):
        return ids, method, confidence

    def _tacticity_qualified(name):
        low = name.lower()
        return any(t in low for t in (", isotactic", ", syndiotactic", ", atactic"))

    want_tacticity = bool(polymer_name and _tacticity_qualified(polymer_name))
    all_rows = conn.execute("SELECT id, name FROM polymers").fetchall()

    def _accept(group, seen, row):
        if row["id"] in seen or _is_copolymer_name(row["name"]):
            return
        if _tacticity_qualified(row["name"]) and not want_tacticity:
            return
        seen.add(row["id"])
        group.append(row["id"])

    for canonical in CLASS_CANONICAL_PATTERN.get(polymer_class, []):
        group, seen = [], set()
        for variant in _name_variants(canonical):
            for row in conn.execute(
                """SELECT id, name FROM polymers
                   WHERE name LIKE ? COLLATE NOCASE
                     AND name NOT LIKE '%-co-%'
                     AND LOWER(name) NOT LIKE '%copolymer%'""",
                (f"%{variant}%",),
            ).fetchall():
                _accept(group, seen, row)
        # Loose-normalized pass, as find_polymer_ids does for names but not for classes:
        # "Poly(vinyl chloride)" never LIKE-matches the equation-bearing
        # "Poly(vinylchloride)", so without this PVNL falls through to its second canonical
        # pattern -- which is "Polystyrene" -- and grades PVC against polystyrene's rho(T).
        target = _normalize_loose(canonical)
        for row in all_rows:
            if _normalize_loose(row["name"]) == target:
                _accept(group, seen, row)
        if _melt_equation_rows(conn, group):
            return group, "class_representative_with_melt_equation", "medium"
    return ids, method, confidence


def melt_reference(polymer_class, polymer_name, t_equil_K, rho_melt=None, db_path=DB_PATH):
    out = {
        "t_equil_K": t_equil_K,
        "t_equil_C": round(t_equil_K - 273.15, 2),
        "rho_melt_sim_gcm3": rho_melt,
        "status": None,
        "evidence": None,
        "verdict": None,
        "exp_density_gcm3": None,
        "melt_gap_pct": None,
        "tolerance_pp": None,
        "melt_deficient": None,
        "equations": [],
    }
    if not db_path.exists():
        out.update(status="NO_DB", evidence="insufficient", verdict="MELT_RHO_NO_REFERENCE",
                   reason=f"missing {db_path}")
        return out

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ids, match_method, match_confidence = _resolve_ids(conn, polymer_class, polymer_name)
        out["match_method"] = match_method
        out["match_confidence"] = match_confidence
        if not ids:
            out.update(status="NO_POLYMER_MATCH", evidence="insufficient",
                       verdict="MELT_RHO_NO_REFERENCE",
                       reason=f"no polymers row for class={polymer_class} name={polymer_name}")
            return out
        # Every equation, not the first in-range one: get_density_data breaks at the first
        # hit, which would destroy the cross-equation spread the tolerance rests on.
        rows = _melt_equation_rows(conn, ids)
    finally:
        conn.close()

    if not rows:
        out.update(status="NO_EXPERIMENTAL_EQUATION", evidence="insufficient",
                   verdict="MELT_RHO_NO_REFERENCE",
                   reason="no melt-phase rho(T) equation on file for this polymer")
        return out

    t_C = out["t_equil_C"]
    evaluated = []
    for r in rows:
        width = r["t_max_C"] - r["t_min_C"]
        beyond = max(0.0, t_C - r["t_max_C"], r["t_min_C"] - t_C)
        try:
            rho_exp = _rho(r["py_expr"], t_C)
        except Exception as exc:                                 # unparseable expression
            evaluated.append({"py_expr": r["py_expr"], "error": str(exc)})
            continue
        evaluated.append({
            "py_expr": r["py_expr"],
            "t_min_C": r["t_min_C"], "t_max_C": r["t_max_C"],
            "fit_width_C": round(width, 1),
            "in_range": bool(r["t_min_C"] <= t_C <= r["t_max_C"]),
            "beyond_range_C": round(beyond, 1),
            "beyond_frac_of_width": round(beyond / width, 3) if width else None,
            "rho_exp_gcm3": round(rho_exp, 4),
            "gap_pct": (round(100.0 * (rho_melt - rho_exp) / rho_exp, 2)
                        if rho_melt is not None else None),
            "source": r.get("source_key"),
        })
    out["equations"] = evaluated
    ok = [e for e in evaluated if "error" not in e]
    if not ok:
        out.update(status="NO_EXPERIMENTAL_EQUATION", evidence="insufficient",
                   verdict="MELT_RHO_NO_REFERENCE", reason="every equation failed to evaluate")
        return out

    in_range = [e for e in ok if e["in_range"]]
    near = [e for e in ok
            if not e["in_range"] and (e["beyond_frac_of_width"] or 9.0) <= NEAR_RANGE_FRAC]
    usable = in_range or near

    if usable:
        out["status"] = "IN_RANGE" if in_range else "NEAR_RANGE"
        out["evidence"] = "decisive"
        out["exp_density_gcm3"] = round(sum(e["rho_exp_gcm3"] for e in usable) / len(usable), 4)
    else:
        nearest = min(ok, key=lambda e: e["beyond_frac_of_width"] or 9.0)
        out["status"] = "T_EQUIL_OUTSIDE_EQUATION_RANGE"
        out["nearest_range_C"] = [nearest["t_min_C"], nearest["t_max_C"]]
        out["degrees_beyond_range_C"] = nearest["beyond_range_C"]
        out["beyond_frac_of_width"] = nearest["beyond_frac_of_width"]
        out["evidence"] = ("indicative"
                           if (nearest["beyond_frac_of_width"] or 9.0) <= INDICATIVE_FRAC
                           else "insufficient")
        # Reported so the extrapolation is visible, NOT promoted to exp_density_gcm3 --
        # that field is what the gate binds on, and an extrapolated value must not reach it.
        out["exp_density_extrapolated_gcm3"] = nearest["rho_exp_gcm3"]

    # Tolerance is the disagreement among the independent equations for this polymer: how
    # precisely experiment itself pins rho here. Measured, not chosen.
    all_gaps = [e["gap_pct"] for e in ok if e["gap_pct"] is not None]
    if len(all_gaps) > 1:
        out["tolerance_pp"] = round(max(all_gaps) - min(all_gaps), 2)
    out["n_equations"] = len(ok)
    out["n_in_range"] = len(in_range)

    if rho_melt is not None:
        ref = (out["exp_density_gcm3"] if out["exp_density_gcm3"] is not None
               else out.get("exp_density_extrapolated_gcm3"))
        if ref:
            out["melt_gap_pct"] = round(100.0 * (rho_melt - ref) / ref, 2)

    gap = out["melt_gap_pct"]
    if out["evidence"] == "decisive" and gap is not None:
        tol = out["tolerance_pp"]
        if tol is not None:
            out["melt_deficient"] = bool(gap < -tol)
        else:
            # One equation, no measured reference tolerance. A positive gap still settles
            # it; a negative one cannot be adjudicated and must not default to "fine".
            out["melt_deficient"] = False if gap >= 0 else None
        if out["melt_deficient"] is True:
            out["verdict"] = "MELT_RHO_DEFICIT"
        elif out["melt_deficient"] is False:
            out["verdict"] = "MELT_RHO_PASS"
        else:
            out["verdict"] = "MELT_RHO_NO_REFERENCE"
            out["reason"] = ("single equation, negative gap — reference uncertainty is "
                             "unmeasurable, so the deficit cannot be adjudicated")
    else:
        # indicative -> the gap is reported but does not bind; insufficient -> nothing to say.
        out["verdict"] = "MELT_RHO_NO_REFERENCE"
        out.setdefault("reason", f"evidence={out['evidence']}, status={out['status']}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--polymer_class")
    ap.add_argument("--polymer_name")
    ap.add_argument("--t_equil_K", type=float, required=True)
    ap.add_argument("--rho_melt", type=lambda v: None if v in ("", "null", "None") else float(v),
                    default=None)
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()
    print(json.dumps(melt_reference(args.polymer_class, args.polymer_name,
                                    args.t_equil_K, args.rho_melt, Path(args.db)), indent=2))


if __name__ == "__main__":
    main()
