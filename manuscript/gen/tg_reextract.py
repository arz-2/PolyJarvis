#!/usr/bin/env python3
"""Re-extract every accepted Tg with the CURRENT extract_thermal.py (analysis-only).

The stored thermal.json of five runs was produced by extract_thermal.py before commit d76babf.
For one consistent code version, this re-runs the live campaign invocation (--fit_method auto,
--equilibration_fraction 0.5, no initial guess, no fit_t_max_K) on each accepted thermal attempt's
own staircase log, writing to gen/out/tg_reextract/<run>/thermal.json. data/ is never modified
(accepted artifacts are sha256-pinned). Idempotent: re-running overwrites the outputs; runs whose
thermal stage is not yet accepted are skipped, so it can be run again when reruns land.

Usage: mcp-servers/.venv/bin/python manuscript/gen/tg_reextract.py
"""
from __future__ import annotations

import contextlib
import glob
import io
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out" / "tg_reextract"
ANALYSIS = REPO / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"
SYSTEMS = ["PE", "PEG", "PLLA", "aPS", "sPVC", "PEEK", "PSU"]
KEYS = ("Tg_K", "tg_uncertainty_K", "r_squared", "fit_quality", "transition_width_c_K",
        "tg_method_gap_K", "tg_gate_verdict", "tg_gate_cause", "tg_reportable", "fit_method")


def local(p: str) -> Path:
    return REPO / ("data/" + p.split("/data/", 1)[1]) if "/data/" in p else Path(p)


def targets() -> list[dict]:
    runs = [f"{s}_{i}" for s in SYSTEMS for i in (1, 2, 3)]
    runs += [r for r in ("aPS_1_rerun", "sPVC_1_rerun") if (REPO / "data" / r / "workflow_state.json").exists()]
    runs += ["tg_sensitivity/" + os.path.basename(d) for d in sorted(glob.glob(str(REPO / "data/tg_sensitivity/TGS_*")))]
    out = []
    for r in runs:
        th = json.loads((REPO / "data" / r / "workflow_state.json").read_text())["stages"].get("thermal", {})
        leg = r.startswith("tg_sensitivity/")
        att = th.get("accepted_attempt") or (th["attempts"][-1]["attempt_id"] if leg and th.get("attempts") else None)
        if not att:
            continue
        stored_path = REPO / "data" / r / "attempts" / "thermal" / att / "raw" / "thermal.json"
        if not stored_path.exists():
            continue
        stored = json.loads(stored_path.read_text())
        out.append({"run": r, "attempt": att, "log": str(local(stored["log_file"])),
                    "stored": {k: stored.get(k) for k in KEYS}})
    return out


def run_one(tgt: dict) -> dict:
    sys.path.insert(0, str(ANALYSIS))
    import extract_thermal as et  # noqa: E402

    outdir = OUT / tgt["run"]
    outdir.mkdir(parents=True, exist_ok=True)
    argv = ["extract_thermal.py", "--log_file", tgt["log"], "--output_dir", str(outdir),
            "--graphs_dir", str(outdir / "graphs"), "--equilibration_fraction", "0.5"]
    old = sys.argv
    sys.argv = argv
    res = {"run": tgt["run"], "attempt": tgt["attempt"], "stored": tgt["stored"]}
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            et.main()
        t = json.loads((outdir / "thermal.json").read_text())
        res["current"] = {k: t.get(k) for k in KEYS}
    except SystemExit as e:
        res["error"] = f"exit {e.code}"
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {e}"
    finally:
        sys.argv = old
    return res


def main() -> None:
    tg = targets()
    with Pool(8) as pool:
        results = pool.map(run_one, tg, chunksize=1)
    rows = []
    for r in results:
        s, c = r["stored"], r.get("current") or {}
        rows.append({"run": r["run"], "attempt": r["attempt"], "error": r.get("error"),
                     "stored_Tg_K": s["Tg_K"], "current_Tg_K": c.get("Tg_K"),
                     "stored_unc_K": s["tg_uncertainty_K"], "current_unc_K": c.get("tg_uncertainty_K"),
                     "stored_verdict": s["tg_gate_verdict"], "current_verdict": c.get("tg_gate_verdict"),
                     "stored_reportable": s["tg_reportable"], "current_reportable": c.get("tg_reportable"),
                     "changed": (c.get("Tg_K") != s["Tg_K"] or c.get("tg_uncertainty_K") != s["tg_uncertainty_K"]
                                 or c.get("tg_reportable") != s["tg_reportable"])})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    for row in rows:
        flag = "CHANGED" if row["changed"] else "same"
        print(f"{row['run']:32} {flag:7} Tg {row['stored_Tg_K']} -> {row['current_Tg_K']} | "
              f"unc {row['stored_unc_K']} -> {row['current_unc_K']} | "
              f"{row['stored_verdict']} -> {row['current_verdict']} {row['error'] or ''}")


if __name__ == "__main__":
    main()
