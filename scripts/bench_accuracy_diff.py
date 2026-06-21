#!/usr/bin/env python3
"""
bench_accuracy_diff.py — physics-parity check for GPU-offload benchmark arms.

Given a baseline LAMMPS log (arm A0) and one or more variant logs (A1/A2/A3), compare
the equilibrated averages of density, total energy, and pressure. Speed gains from
moving work onto the GPU (pppm/gpu, KOKKOS, mixed precision) are only acceptable if the
physics is unchanged, so this is the gate that accompanies the ns/day numbers.

Reuses the engine's thermo parser (analysis_scripts/extract_equilibrated_density.py:
parse_lammps_log) so column handling matches the rest of the pipeline.

Gates (vs baseline):
  density:  |Δρ| / ρ   < 0.5 %
  energy:   |Δ⟨TotEng⟩| / |⟨TotEng⟩| < 0.1 %
  pressure: |Δ⟨P⟩| within combined block-SEM (atm pressures are noisy; advisory)

Usage:
  scripts/bench_accuracy_diff.py \
      --baseline A0=/tmp/.../A0/npt.log \
      --variant  A1=/tmp/.../A1/npt.log \
      --variant  A2=/tmp/.../A2/npt.log \
      --variant  A3=/tmp/.../A3/npt.log \
      --tail-frac 0.5 --out /tmp/.../accuracy.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"))
from extract_equilibrated_density import parse_lammps_log  # type: ignore

import numpy as np

RHO_GATE_PCT = 0.5      # density % tolerance
ENE_GATE_PCT = 0.1      # total-energy % tolerance


def _block_sem(x: np.ndarray, nblocks: int = 10) -> float:
    """Block-averaged SEM — robust to autocorrelation in an MD time series."""
    x = np.asarray(x, float)
    if x.size < nblocks:
        return float(x.std(ddof=1) / max(np.sqrt(x.size), 1)) if x.size > 1 else 0.0
    blocks = np.array_split(x, nblocks)
    means = np.array([b.mean() for b in blocks])
    return float(means.std(ddof=1) / np.sqrt(nblocks))


# columns compared, with the relative-% gate used for each (None = diagnostic only, not gated).
# E_long is the PPPM/kspace energy (checks pppm/gpu); E_bond..E_impro are the class2 bonded
# terms (check KOKKOS class2/kk). PotEng/TotEng are the headline correctness gates.
COLUMNS = [
    ("Density",  "density",   RHO_GATE_PCT),
    ("PotEng",   "pot_energy", ENE_GATE_PCT),
    ("TotEng",   "tot_energy", ENE_GATE_PCT),
    ("E_long",   "e_long",    0.2),          # PPPM kspace energy — pppm/gpu check
    ("E_bond",   "e_bond",    0.2),          # class2 bond — KOKKOS check
    ("E_angle",  "e_angle",   0.2),
    ("E_dihed",  "e_dihed",   0.2),
    ("E_impro",  "e_impro",   None),         # often ~0; diagnostic only
    ("Press",    "pressure",  None),         # noisy in atm; advisory
]


def summarize(log_path: str, tail_frac: float) -> dict:
    """Mean ± block-SEM of each compared column over the last tail_frac of the run."""
    df = parse_lammps_log(log_path)
    n = len(df)
    if n == 0:
        return {"error": f"no thermo rows parsed from {log_path}"}
    start = int(n * (1.0 - tail_frac))
    tail = df.iloc[start:]
    out: dict = {"n_rows": n, "tail_rows": len(tail)}
    for col, key, _gate in COLUMNS:
        if col in tail.columns:
            v = tail[col].to_numpy(dtype=float)
            out[key] = {"mean": float(v.mean()), "block_sem": _block_sem(v)}
        else:
            out[key] = None
    return out


def _pct_diff(var: float, base: float) -> float:
    return abs(var - base) / abs(base) * 100.0 if base else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", required=True, help="LABEL=/path/to/log (arm A0)")
    ap.add_argument("--variant", action="append", default=[],
                    help="LABEL=/path/to/log (repeatable)")
    ap.add_argument("--tail-frac", type=float, default=0.5,
                    help="fraction of the run (from the end) to average over")
    ap.add_argument("--out", help="write JSON report here")
    args = ap.parse_args()

    def split(spec: str) -> tuple[str, str]:
        label, _, path = spec.partition("=")
        return label, path

    b_label, b_path = split(args.baseline)
    base = summarize(b_path, args.tail_frac)
    if "error" in base:
        print(f"ERROR baseline: {base['error']}", file=sys.stderr)
        return 2

    rows = []
    for spec in args.variant:
        v_label, v_path = split(spec)
        s = summarize(v_path, args.tail_frac)
        if "error" in s:
            rows.append({"arm": v_label, "error": s["error"]})
            continue
        rec: dict = {"arm": v_label, "cols": {}}
        verdict_ok = True
        for col, key, gate in COLUMNS:
            if not (s.get(key) and base.get(key)):
                continue
            vm, bm = s[key]["mean"], base[key]["mean"]
            d = _pct_diff(vm, bm)
            entry = {"var": round(vm, 4), "base": round(bm, 4), "delta_pct": round(d, 5)}
            if gate is not None:
                entry["gate_pct"] = gate
                entry["pass"] = d < gate
                verdict_ok &= entry["pass"]
            rec["cols"][key] = entry
        rec["verdict"] = "PASS" if verdict_ok else "FAIL"
        rows.append(rec)

    report = {"baseline": {"arm": b_label, **base},
              "gates": {"density_pct": RHO_GATE_PCT, "energy_pct": ENE_GATE_PCT},
              "variants": rows}

    # human-readable table — headline gates + key diagnostics (E_long=kspace, E_bond=bonded)
    show = [("pot_energy", "ΔPotEng%"), ("tot_energy", "ΔTotEng%"),
            ("e_long", "ΔE_long%"), ("e_bond", "ΔE_bond%"), ("density", "Δrho%")]
    bm = base
    print(f"\nbaseline {b_label}: PotEng={bm.get('pot_energy',{}) and bm['pot_energy']['mean']:.2f}"
          f"  E_long={bm.get('e_long',{}) and bm['e_long']['mean']:.2f}\n")
    hdr = f"{'arm':<5}" + "".join(f"{h:>11}" for _, h in show) + f"{'verdict':>9}"
    print(hdr)
    for r in rows:
        if "error" in r:
            print(f"{r['arm']:<5}  ERROR: {r['error']}")
            continue
        line = f"{r['arm']:<5}"
        for key, _h in show:
            v = r["cols"].get(key, {}).get("delta_pct")
            line += f"{v:>11.5f}" if v is not None else f"{'-':>11}"
        print(line + f"{r['verdict']:>9}")

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
