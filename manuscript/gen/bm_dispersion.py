#!/usr/bin/env python3
"""Analysis-only dispersion of the round-2 Murnaghan bulk modulus (reviewer comment 5).

For every accepted mechanical attempt of the 21 campaign runs:
  1. recompute each pressure point's mean volume from its own LAMMPS log with the repo's
     extractor (extract_mean_volume, same eq_fraction) and reproduce the stored B0 with
     fit_murnaghan on the stored point set (must agree within 1%);
  2. ladder-span dispersion: Murnaghan refits on every contiguous sub-ladder with >= 4 points
     and on every leave-one-out set, both on the fit script's selected points and on all
     simulated points (i.e. with and without its exclusions);
  3. fit-form dispersion: Murnaghan vs Birch-Murnaghan 3rd order vs Vinet on the same points;
  4. the stored volume-fluctuation K for comparison.
Per system, only gate-passing cells are summarised (gen/out/regrade_continuous.json).

Usage: mcp-servers/.venv/bin/python manuscript/gen/bm_dispersion.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from statistics import mean, stdev

import numpy as np
from scipy.optimize import curve_fit

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out"
sys.path.insert(0, str(REPO / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"))
from extract_bulk_modulus_murnaghan import extract_mean_volume, fit_murnaghan  # noqa: E402

SYSTEMS = ["PE", "PEG", "PLLA", "aPS", "sPVC", "PEEK", "PSU"]
ATM_TO_GPA = 1.01325e-4


def bm3(V, B0, Bp, V0):
    x = (V0 / V) ** (2.0 / 3.0)
    return 1.5 * B0 * (x ** 3.5 - x ** 2.5) * (1.0 + 0.75 * (Bp - 4.0) * (x - 1.0))


def vinet(V, B0, Bp, V0):
    x = (V / V0) ** (1.0 / 3.0)
    return 3.0 * B0 * (1.0 - x) / x ** 2 * np.exp(1.5 * (Bp - 1.0) * (1.0 - x))


def fit_form(fn, V, P):
    V = np.asarray(V, float)
    P = np.asarray(P, float)
    seed = float(V.mean())
    try:
        popt, _ = curve_fit(fn, V, P, p0=[1.0, 7.0, seed],
                            bounds=([0.01, 1.0, 0.5 * seed], [500.0, 30.0, 2.0 * seed]), maxfev=20000)
        res = P - fn(V, *popt)
        r2 = 1 - np.sum(res ** 2) / np.sum((P - P.mean()) ** 2)
        return {"B0_GPa": round(float(popt[0]), 4), "B0_prime": round(float(popt[1]), 3), "r2": round(float(r2), 6)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:80]}


def murn(V, P):
    popt, _, r2, ok = fit_murnaghan(list(V), list(P))
    if not ok:
        return None
    return {"B0_GPa": round(float(popt[0]), 4), "B0_prime": round(float(popt[1]), 3), "r2": round(float(r2), 6)}


def local(p: str) -> Path:
    return REPO / "data" / p.split("/data/", 1)[1]


def pressure_of(log: str) -> float:
    return float(re.search(r"bm_P(-?\d+(?:\.\d+)?)\.log$", log).group(1))


def spread(vals):
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return None
    return {"n": len(vals), "min": round(min(vals), 4), "max": round(max(vals), 4),
            "range_pct": round(100 * (max(vals) - min(vals)) / mean(vals), 1),
            "sd": round(stdev(vals), 4), "sd_pct": round(100 * stdev(vals) / mean(vals), 1)}


def ladder_family(P_atm, V):
    """Contiguous sub-ladders (>= 4 points) and leave-one-out sets on sorted points."""
    order = np.argsort(P_atm)
    P_atm = [P_atm[i] for i in order]
    V = [V[i] for i in order]
    n = len(P_atm)
    sub, loo = [], []
    for lo in range(n):
        for hi in range(lo + 4, n + 1):
            f = murn(V[lo:hi], [p * ATM_TO_GPA for p in P_atm[lo:hi]])
            sub.append({"points_atm": P_atm[lo:hi], **(f or {"error": "no convergence"})})
    if n >= 5:
        for k in range(n):
            idx = [i for i in range(n) if i != k]
            f = murn([V[i] for i in idx], [P_atm[i] * ATM_TO_GPA for i in idx])
            loo.append({"dropped_atm": P_atm[k], **(f or {"error": "no convergence"})})
    return sub, loo


def analyse_run(run: str) -> dict:
    ws = json.loads((REPO / "data" / run / "workflow_state.json").read_text())
    att = ws["stages"]["mechanical"]["accepted_attempt"]
    mj = json.loads((REPO / "data" / run / "attempts" / "mechanical" / att / "raw" / "mechanical.json").read_text())
    eqf = mj.get("eq_fraction", 0.5)
    pts = {}
    for lf in mj["log_files"]:
        v = extract_mean_volume(str(local(lf)), eqf)[0]
        pts[pressure_of(lf)] = v
    all_P = sorted(pts)
    sel_P = sorted(float(p) for p in mj["pressures_atm"])
    excluded = [p for p in all_P if p not in sel_P]

    rep_sel = murn([pts[p] for p in sel_P], [p * ATM_TO_GPA for p in sel_P])
    rep_all = murn([pts[p] for p in all_P], [p * ATM_TO_GPA for p in all_P])
    stored = mj["B0_GPa"]
    stored_all = (mj.get("all_points_fit") or {}).get("B0_GPa", stored)
    rec = {
        "run": run, "stored_B0_GPa": stored, "stored_all_points_B0_GPa": stored_all,
        "stored_B0_sem_GPa": mj.get("B0_sem_GPa"), "stored_B0_prime": mj.get("B0_prime"),
        "fluctuation_K_GPa": mj.get("fluctuation_bulk_modulus_GPa"),
        "pressures_all_atm": all_P, "pressures_selected_atm": sel_P, "excluded_atm": excluded,
        "reproduced_selected": rep_sel, "reproduced_all": rep_all,
        "reproduction_err_pct": round(100 * (rep_sel["B0_GPa"] - stored) / stored, 3) if rep_sel else None,
        "reproduction_all_err_pct": round(100 * (rep_all["B0_GPa"] - stored_all) / stored_all, 3) if rep_all else None,
    }
    for label, P in (("selected", sel_P), ("all", all_P)):
        sub, loo = ladder_family(P, [pts[p] for p in P])
        forms = {"murnaghan": murn([pts[p] for p in P], [p * ATM_TO_GPA for p in P]),
                 "birch_murnaghan3": fit_form(bm3, [pts[p] for p in P], [p * ATM_TO_GPA for p in P]),
                 "vinet": fit_form(vinet, [pts[p] for p in P], [p * ATM_TO_GPA for p in P])}
        rec[label] = {
            "subladders": sub, "loo": loo, "forms": forms,
            "span_spread": spread([s.get("B0_GPa") for s in sub] + [s.get("B0_GPa") for s in loo]),
            "form_spread": spread([f.get("B0_GPa") for f in forms.values() if f]),
        }
    return rec


def main() -> None:
    cont = json.loads((OUT / "regrade_continuous.json").read_text())["runs"]
    passing = lambda r: all((cont[r][st].get("verdict") or {}).get("verdict") == "PASS"
                            for st in ("equilibration", "cooling"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from replicates import k_basis, reported_runs
    runs = [name for _, _, name in reported_runs()]
    recs = {r: analyse_run(r) for r in runs}

    systems = {}
    for s in SYSTEMS:
        allp = k_basis(s) == "all_points"
        rs = [recs[name] for sys_, _, name in reported_runs() if sys_ == s and passing(name)]
        K = [r["stored_all_points_B0_GPa"] if allp else r["stored_B0_GPa"] for r in rs]
        rep_sd = stdev(K) if len(K) > 1 else None

        def pooled_sd(key, basis):
            sds = [r[basis][key]["sd"] for r in rs if r[basis][key]]
            return mean(sds) if sds else None

        span_sel, span_all = pooled_sd("span_spread", "selected"), pooled_sd("span_spread", "all")
        form_sel = pooled_sd("form_spread", "all" if allp else "selected")
        span_used = span_all if allp else (span_sel if span_sel is not None else span_all)
        parts = [x for x in (rep_sd, span_used, form_sel) if x is not None]
        combined = float(np.sqrt(sum(x * x for x in parts))) if parts else None
        excl_shift = [100 * (r["stored_all_points_B0_GPa"] - r["stored_B0_GPa"]) / r["stored_B0_GPa"]
                      for r in rs if r["excluded_atm"]]
        fluct_div = [100 * (r["fluctuation_K_GPa"] - r["stored_B0_GPa"]) / r["stored_B0_GPa"]
                     for r in rs if r["fluctuation_K_GPa"]]
        systems[s] = {
            "runs": [r["run"] for r in rs], "K_mean_GPa": round(mean(K), 3),
            "replicate_sd_GPa": None if rep_sd is None else round(rep_sd, 3),
            "span_sd_GPa_selected": None if span_sel is None else round(span_sel, 3),
            "span_sd_GPa_all_points": None if span_all is None else round(span_all, 3),
            "form_sd_GPa": None if form_sel is None else round(form_sel, 3),
            "combined_sd_GPa": None if combined is None else round(combined, 3),
            "combined_sd_pct": None if combined is None else round(100 * combined / mean(K), 1),
            "exclusion_shift_pct": [round(x, 1) for x in excl_shift],
            "fluctuation_vs_murnaghan_pct": [round(x, 1) for x in fluct_div],
            "max_reproduction_err_pct": max(abs(r["reproduction_err_pct"]) for r in rs),
        }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "bm_dispersion.json").write_text(json.dumps({"runs": recs, "systems": systems}, indent=2) + "\n")

    L = ["# Round-2 bulk-modulus dispersion (analysis only)\n",
         "Reproduction of stored B0 from the logs (fit script's selected points):\n",
         "| Run | stored B0 | reproduced | err % | all-points B0 (stored / reproduced) | excluded (atm) |", "|---|---|---|---|---|---|"]
    for r in recs.values():
        L.append(f"| {r['run']} | {r['stored_B0_GPa']} | {r['reproduced_selected']['B0_GPa']} | {r['reproduction_err_pct']} | "
                 f"{r['stored_all_points_B0_GPa']} / {r['reproduced_all']['B0_GPa']} | {r['excluded_atm'] or '—'} |")
    L += ["\nPer run: span (contiguous sub-ladders >= 4 points + leave-one-out) and fit-form spread of B0:\n",
          "| Run | span sd % (selected) | span range % (selected) | span sd % (all pts) | span range % (all pts) | Murnaghan / BM3 / Vinet (GPa) | form range % | K_fluct |",
          "|---|---|---|---|---|---|---|---|"]
    for r in recs.values():
        ss, sa, fs = r["selected"]["span_spread"], r["all"]["span_spread"], r["selected"]["form_spread"]
        f = r["selected"]["forms"]
        L.append(f"| {r['run']} | {ss['sd_pct'] if ss else '—'} | {ss['range_pct'] if ss else '—'} | "
                 f"{sa['sd_pct'] if sa else '—'} | {sa['range_pct'] if sa else '—'} | "
                 f"{f['murnaghan']['B0_GPa']} / {f['birch_murnaghan3'].get('B0_GPa')} / {f['vinet'].get('B0_GPa')} | "
                 f"{fs['range_pct'] if fs else '—'} | {r['fluctuation_K_GPa']} |")
    L += ["\nPer system (gate-passing cells):\n",
          "| System | n | K mean | replicate sd | span sd (selected / all pts) | form sd | combined sd (GPa, %) | exclusion shift % | fluct − Murn % |",
          "|---|---|---|---|---|---|---|---|---|"]
    for s, v in systems.items():
        L.append(f"| {s} | {len(v['runs'])} | {v['K_mean_GPa']} | {v['replicate_sd_GPa']} | {v['span_sd_GPa_selected']} / {v['span_sd_GPa_all_points']} | "
                 f"{v['form_sd_GPa']} | {v['combined_sd_GPa']} ({v['combined_sd_pct']}%) | {v['exclusion_shift_pct'] or '—'} | {v['fluctuation_vs_murnaghan_pct']} |")
    (OUT / "bm_dispersion.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
