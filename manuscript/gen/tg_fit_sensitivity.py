#!/usr/bin/env python3
"""Tg fit-procedure sensitivity: re-extract Tg from every accepted staircase log under a
predeclared set of analysis-only alternatives, using extract_thermal.py's own main().

Procedures (fixed before any result was read):
  live           the campaign's settings: --fit_method auto, --equilibration_fraction 0.5,
                 no initial guess, no fit_t_max_K. Must reproduce the stored Tg_K and verdict.
  bilinear       --fit_method bilinear (segmented fit only)
  hyperbola      --fit_method hyperbola (smoothed bilinear only; physics swap still applies)
  eqf_0.25       --equilibration_fraction 0.25 (last 25% of each temperature step averaged)
  eqf_0.75       --equilibration_fraction 0.75
  trim_top2      the two highest temperature steps removed from the log before fitting
  trim_bottom2   the two lowest temperature steps removed

Rule (predeclared, reviewer comment 1): an axis is sensitive iff its effect exceeds the pooled
within-system replicate s.d. of the live Tg over reportable fits. Effect per system = mean dTg
over that system's runs that are reportable under the live procedure.

Usage: mcp-servers/.venv/bin/python manuscript/gen/tg_fit_sensitivity.py
Writes: manuscript/gen/out/tg_fit_sensitivity.{json,md}; scratch fits under SCRATCH.
"""
from __future__ import annotations

import contextlib
import glob
import io
import json
import math
import os
import sys
from multiprocessing import Pool
from pathlib import Path
from statistics import mean, stdev

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out"
ANALYSIS = REPO / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"
SCRATCH = Path(os.environ.get("TG_FIT_SCRATCH", "/tmp/claude-1002/-home-arz2-PolyJarvis-v2/"
                              "8a7dad1a-b1d9-4fe6-b7e2-a2e77f6ffcc3/scratchpad/tg_fit"))
SYSTEMS = ["PE", "PEG", "PLLA", "aPS", "sPVC", "PEEK", "PSU"]
PROCEDURES = ["live", "bilinear", "hyperbola", "eqf_0.25", "eqf_0.75", "trim_top2", "trim_bottom2"]


def local(p: str) -> Path:
    return REPO / ("data/" + p.split("/data/", 1)[1]) if "/data/" in p else Path(p)


def targets() -> list[dict]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from replicates import reported_runs
    runs = [name for _, _, name in reported_runs()]
    runs += ["tg_sensitivity/" + os.path.basename(d) for d in sorted(glob.glob(str(REPO / "data/tg_sensitivity/TGS_*")))]
    out = []
    for r in runs:
        ws = json.loads((REPO / "data" / r / "workflow_state.json").read_text())
        th = ws["stages"]["thermal"]
        att = th.get("accepted_attempt") or th["attempts"][-1]["attempt_id"]
        adir = REPO / "data" / r / "attempts" / "thermal" / att
        t = json.loads((adir / "raw" / "thermal.json").read_text())
        p = json.loads((adir / "executor_state.json").read_text()).get("parameters", {})
        out.append({"run": r, "system": r.split("/")[-1].split("_")[0] if not r.startswith("tg_") else None,
                    "attempt": att, "log": str(local(t["log_file"])), "step_K": float(p.get("tg_t_step_K") or 20),
                    "plateau_csv": str(adir / "raw" / "tg_density_bins_plateau.csv"),
                    "stored": {k: t.get(k) for k in ("Tg_K", "tg_gate_verdict", "tg_gate_cause", "fit_method",
                                                     "fit_quality", "r_squared", "tg_uncertainty_K",
                                                     "equilibration_fraction", "fit_t_max_K")}})
    return out


def run_one(job: tuple[dict, str]) -> dict:
    tgt, proc = job
    sys.path.insert(0, str(ANALYSIS))
    import extract_thermal as et  # noqa: E402

    outdir = SCRATCH / tgt["run"].replace("/", "__") / proc
    outdir.mkdir(parents=True, exist_ok=True)
    argv = ["extract_thermal.py", "--log_file", tgt["log"], "--output_dir", str(outdir),
            "--graphs_dir", str(outdir / "graphs"), "--equilibration_fraction", "0.5"]
    if proc == "bilinear":
        argv += ["--fit_method", "bilinear"]
    elif proc == "hyperbola":
        argv += ["--fit_method", "hyperbola"]
    elif proc.startswith("eqf_"):
        argv[argv.index("--equilibration_fraction") + 1] = proc.split("_")[1]

    original = et.parse_lammps_log
    if proc in ("trim_top2", "trim_bottom2"):
        # Set points come from the run's own stored plateau bins (what the live fit used), not
        # from the raw log, whose extreme rows need not be staircase steps.
        bins = sorted(float(line.split(",")[0]) for line in
                      Path(tgt["plateau_csv"]).read_text().splitlines()[1:] if line.strip())
        def trimmed(path, _orig=original, _proc=proc, _bins=bins, _step=tgt["step_K"]):
            df = _orig(path)
            # Cut at the midpoint between the 2nd and 3rd plateau bin from the end, so exactly the
            # two outermost bins go even where bins sit 5 K apart near the melt end.
            if _proc == "trim_top2":
                return df[df["Temp"] < 0.5 * (_bins[-2] + _bins[-3])].reset_index(drop=True)
            return df[df["Temp"] > 0.5 * (_bins[1] + _bins[2])].reset_index(drop=True)
        et.parse_lammps_log = trimmed
    old_argv = sys.argv
    sys.argv = argv
    res = {"run": tgt["run"], "procedure": proc}
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            et.main()
        t = json.loads((outdir / "thermal.json").read_text())
        res.update({k: t.get(k) for k in ("Tg_K", "tg_gate_verdict", "tg_gate_cause", "tg_reportable", "fit_method",
                                          "fit_quality", "r_squared", "tg_uncertainty_K", "tg_method_gap_K",
                                          "n_bins_total", "temp_range_K")})
    except SystemExit as e:
        res["error"] = f"exit {e.code}"
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {e}"
    finally:
        sys.argv = old_argv
        et.parse_lammps_log = original
    return res


def main() -> None:
    tg = targets()
    jobs = [(t, p) for t in tg for p in PROCEDURES]
    with Pool(8) as pool:
        results = pool.map(run_one, jobs, chunksize=1)
    by = {(r["run"], r["procedure"]): r for r in results}

    # Reproduction check.
    repro = []
    for t in tg:
        live = by[(t["run"], "live")]
        ok = (live.get("Tg_K") is not None and abs(live["Tg_K"] - t["stored"]["Tg_K"]) <= 0.05
              and live.get("tg_gate_verdict") == t["stored"]["tg_gate_verdict"])
        repro.append({"run": t["run"], "stored_Tg_K": t["stored"]["Tg_K"], "live_Tg_K": live.get("Tg_K"),
                      "stored_verdict": t["stored"]["tg_gate_verdict"], "live_verdict": live.get("tg_gate_verdict"),
                      "reproduced": bool(ok)})

    # Runs the current code does not reproduce: re-run them with extract_thermal.py as it was
    # before commit d76babf (the code that produced the stored results), same log and settings.
    import subprocess
    import tempfile
    old_dir = Path(tempfile.mkdtemp(prefix="extract_thermal_pre_d76babf_", dir=SCRATCH.parent))
    for name in ("extract_thermal.py", "analysis_utils.py", "plot_style.py", "backbone_topology.py"):
        src = subprocess.run(["git", "-C", str(REPO), "show",
                              f"d76babf^:mcp-servers/mcp-lammps-engine/analysis_scripts/{name}"],
                             capture_output=True).stdout
        (old_dir / name).write_bytes(src if src else (ANALYSIS / name).read_bytes())
    for rec, t in zip(repro, tg):
        if rec["reproduced"]:
            continue
        od = SCRATCH / t["run"].replace("/", "__") / "pre_d76babf"
        subprocess.run([sys.executable, str(old_dir / "extract_thermal.py"), "--log_file", t["log"],
                        "--output_dir", str(od), "--graphs_dir", str(od / "graphs"),
                        "--equilibration_fraction", "0.5"], cwd=old_dir, capture_output=True)
        try:
            o = json.loads((od / "thermal.json").read_text())
            rec["pre_d76babf_Tg_K"] = o.get("Tg_K")
            rec["pre_d76babf_verdict"] = o.get("tg_gate_verdict")
            rec["reproduced_by_pre_d76babf_code"] = (abs(o["Tg_K"] - t["stored"]["Tg_K"]) <= 0.05
                                                     and o.get("tg_gate_verdict") == t["stored"]["tg_gate_verdict"])
        except Exception as e:  # noqa: BLE001
            rec["pre_d76babf_error"] = str(e)

    campaign = [t for t in tg if t["system"]]
    # Pooled within-system s.d. over live reportable fits.
    num = den = 0.0
    for s in SYSTEMS:
        xs = [by[(t["run"], "live")]["Tg_K"] for t in campaign
              if t["system"] == s and by[(t["run"], "live")].get("tg_reportable")]
        if len(xs) > 1:
            num += (len(xs) - 1) * stdev(xs) ** 2
            den += len(xs) - 1
    pooled = math.sqrt(num / den) if den else None

    axes = {}
    for proc in PROCEDURES[1:]:
        per_system, per_run = {}, []
        both, lost = [], []
        for s in SYSTEMS:
            ds = []
            for t in campaign:
                if t["system"] != s:
                    continue
                live, alt = by[(t["run"], "live")], by[(t["run"], proc)]
                d = None if alt.get("Tg_K") is None or live.get("Tg_K") is None else alt["Tg_K"] - live["Tg_K"]
                per_run.append({"run": t["run"], "live_Tg_K": live.get("Tg_K"), "Tg_K": alt.get("Tg_K"),
                                "dTg_K": None if d is None else round(d, 1),
                                "live_n_bins": live.get("n_bins_total"), "n_bins": alt.get("n_bins_total"),
                                "live_reportable": live.get("tg_reportable"), "verdict": alt.get("tg_gate_verdict"),
                                "cause": alt.get("tg_gate_cause"), "fit_method": alt.get("fit_method"),
                                "error": alt.get("error")})
                if d is not None and live.get("tg_reportable"):
                    ds.append(d)
                    if alt.get("tg_reportable"):
                        both.append(d)
                    else:
                        lost.append(t["run"])
            per_system[s] = {"n": len(ds), "mean_dTg_K": round(mean(ds), 1) if ds else None,
                             "max_abs_dTg_K": round(max(abs(x) for x in ds), 1) if ds else None,
                             "n_both_reportable": len(both),
                             "mean_dTg_both_reportable_K": round(mean(both), 1) if both else None,
                             "max_abs_dTg_both_reportable_K": round(max(abs(x) for x in both), 1) if both else None,
                             "became_unreportable": lost}
            both, lost = [], []
        effects = [abs(v["mean_dTg_K"]) for v in per_system.values() if v["mean_dTg_K"] is not None]
        effects_both = [abs(v["mean_dTg_both_reportable_K"]) for v in per_system.values()
                        if v["mean_dTg_both_reportable_K"] is not None]
        axes[proc] = {"per_system": per_system, "per_run": per_run,
                      "max_abs_system_effect_both_reportable_K": max(effects_both) if effects_both else None,
                      "sensitive_both_reportable": bool(pooled is not None and effects_both and max(effects_both) > pooled),
                      "runs_became_unreportable": sum(len(v["became_unreportable"]) for v in per_system.values()),
                      "max_abs_system_effect_K": max(effects) if effects else None,
                      "sensitive": bool(pooled is not None and effects and max(effects) > pooled),
                      "systems_over_threshold": [s for s, v in per_system.items()
                                                 if v["mean_dTg_K"] is not None and pooled and abs(v["mean_dTg_K"]) > pooled],
                      "verdict_changes": sum(1 for x in per_run if x["live_reportable"] is not None
                                             and x["verdict"] is not None
                                             and (x["verdict"] == "TG_REPORTABLE") != bool(x["live_reportable"]))}
    # Code-version axis: the stored (reported) Tg was produced by extract_thermal.py before commit
    # d76babf; "live" is the current code. dTg = stored - current, same log, same settings.
    per_system, per_run = {}, []
    for s in SYSTEMS:
        ds = []
        for t in campaign:
            if t["system"] != s:
                continue
            live = by[(t["run"], "live")]
            d = None if live.get("Tg_K") is None else t["stored"]["Tg_K"] - live["Tg_K"]
            per_run.append({"run": t["run"], "live_Tg_K": live.get("Tg_K"), "Tg_K": t["stored"]["Tg_K"],
                            "dTg_K": None if d is None else round(d, 1), "live_reportable": live.get("tg_reportable"),
                            "verdict": t["stored"]["tg_gate_verdict"], "fit_method": t["stored"]["fit_method"]})
            if d is not None and live.get("tg_reportable"):
                ds.append(d)
        per_system[s] = {"n": len(ds), "mean_dTg_K": round(mean(ds), 1) if ds else None,
                         "max_abs_dTg_K": round(max(abs(x) for x in ds), 1) if ds else None}
    effects = [abs(v["mean_dTg_K"]) for v in per_system.values() if v["mean_dTg_K"] is not None]
    axes["reported_code_vs_current"] = {
        "per_system": per_system, "per_run": per_run,
        "max_abs_system_effect_K": max(effects) if effects else None,
        "sensitive": bool(pooled is not None and effects and max(effects) > pooled),
        "systems_over_threshold": [s for s, v in per_system.items()
                                   if v["mean_dTg_K"] is not None and pooled and abs(v["mean_dTg_K"]) > pooled],
        "verdict_changes": sum(1 for x in per_run if x["live_reportable"] is not None
                               and (x["verdict"] == "TG_REPORTABLE") != bool(x["live_reportable"]))}

    legs = []
    for t in tg:
        if t["system"] is None:
            legs.append({"leg": t["run"].split("/")[-1],
                         **{p: by[(t["run"], p)].get("Tg_K") for p in PROCEDURES},
                         "live_verdict": by[(t["run"], "live")].get("tg_gate_verdict")})

    report = {"procedures": PROCEDURES, "reproduction": repro, "pooled_sd_reportable_K": round(pooled, 1) if pooled else None,
              "axes": axes, "legs": legs,
              "equilibration_duration_axis": "not controlled: no leg varied the melt-hold or per-step equilibration time"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tg_fit_sensitivity.json").write_text(json.dumps(report, indent=2) + "\n")

    L = ["# Tg fit-procedure sensitivity (analysis-only)", "",
         f"Reproduction of stored Tg with live settings: {sum(r['reproduced'] for r in repro)}/{len(repro)} "
         f"with current extract_thermal.py; the rest by the pre-d76babf code: "
         f"{sum(1 for r in repro if r.get('reproduced_by_pre_d76babf_code'))}/"
         f"{sum(1 for r in repro if not r['reproduced'])} "
         f"({', '.join(r['run'] for r in repro if not r['reproduced'])})",
         f"Pooled within-system s.d. (live, reportable fits): {report['pooled_sd_reportable_K']} K", "",
         "| Procedure | max abs system-mean dTg, all live-reportable runs (K) | systems over threshold | "
         "max abs system-mean dTg, runs reportable under both (K) | live-reportable runs made unreportable | "
         "sensitive? (all / both-reportable) |",
         "|---|---|---|---|---|---|"]
    for p, a in axes.items():
        L.append(f"| {p} | {a['max_abs_system_effect_K']} | {', '.join(a['systems_over_threshold']) or '—'} | "
                 f"{a.get('max_abs_system_effect_both_reportable_K', a['max_abs_system_effect_K'])} | "
                 f"{a.get('runs_became_unreportable', 0)} | {'yes' if a['sensitive'] else 'no'} / "
                 f"{'yes' if a.get('sensitive_both_reportable', a['sensitive']) else 'no'} |")
    L += ["", "## Per-run Tg (K) by procedure", "",
          "| Run | " + " | ".join(PROCEDURES) + " | live verdict |", "|" + "---|" * (len(PROCEDURES) + 2)]
    for t in tg:
        cells = []
        for p in PROCEDURES:
            r = by[(t["run"], p)]
            v = "err" if r.get("error") else f"{r['Tg_K']:.1f}" + ("*" if r.get("tg_gate_verdict") != "TG_REPORTABLE" else "")
            cells.append(v)
        L.append(f"| {t['run'].split('/')[-1]} | " + " | ".join(cells) + f" | {by[(t['run'], 'live')].get('tg_gate_verdict')} |")
    L += ["", "\\* = not TG_REPORTABLE under that procedure.", "",
          "Equilibration-duration axis: not controlled (no leg varied the melt hold or per-step time)."]
    (OUT / "tg_fit_sensitivity.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:14]))


if __name__ == "__main__":
    main()
