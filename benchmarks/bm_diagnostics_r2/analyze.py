#!/usr/bin/env python3
"""Fit every bm_diagnostics_r2 leg with the production Murnaghan extractor and compare to baseline.

Each leg is fitted by extract_bulk_modulus_murnaghan.py (CLI, default eq_fraction 0.5 and its own
window selection / point exclusion), exactly as the mechanical stage does. Legs whose logs are not
all complete are reported as pending. Also records per-point tension diagnostics (production-window
volume, autocorrelation time, effective samples, first- vs second-half volume shift) for the
tension series and the 1M-step -1000 atm repeat.

Usage: mcp-servers/.venv/bin/python benchmarks/bm_diagnostics_r2/analyze.py
Writes benchmarks/bm_diagnostics_r2/results/results.json and the results table in README.md.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import legs as L  # noqa: E402

REPO = L.REPO
AS = REPO / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"
sys.path.insert(0, str(AS))
from analysis_utils import parse_lammps_log  # noqa: E402
from extract_bulk_modulus_murnaghan import extract_mean_volume  # noqa: E402

RES = HERE / "results"
STORED_BASELINE_B0 = 3.7592   # sPVC_3 mechanical.json bulk_modulus_GPa


def complete(logp: Path) -> bool:
    try:
        return "STAGE COMPLETE" in logp.read_text(errors="replace")
    except OSError:
        return False


def truncated(logp: Path, max_step: int) -> Path:
    out = RES / "truncated" / f"{logp.stem}_first{max_step}.log"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines, in_thermo, header_n = [], False, 0
    for line in logp.read_text(errors="replace").splitlines():
        tok = line.split()
        if tok[:1] == ["Step"]:
            in_thermo, header_n = True, len(tok)
            lines.append(line)
            continue
        if in_thermo and len(tok) == header_n:
            try:
                if int(float(tok[0])) > max_step:
                    break
            except ValueError:
                pass
        lines.append(line)
    lines.append(f"Loop time of 0 on 1 procs for {max_step} steps (truncated copy for analysis)")
    out.write_text("\n".join(lines) + "\n")
    return out


def leg_logs(leg: str, spec: dict):
    pairs = []
    for p, d, s in spec["points"]:
        _, logp = L.point_source(p, d, s)
        if not complete(logp):
            return None
        if spec.get("analysis") == "truncate":
            logp = truncated(logp, 250_000)
        pairs.append((p, logp))
    return sorted(pairs)


def fit(leg: str, pairs) -> dict:
    out_dir = RES / leg
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(AS / "extract_bulk_modulus_murnaghan.py"),
           "--log_files", *[str(l) for _, l in pairs],
           "--pressures_atm", *[str(p) for p, _ in pairs],
           "--output_dir", str(out_dir), "--graphs_dir", str(out_dir / "figures")]
    run = subprocess.run(cmd, capture_output=True, text=True)
    mj = out_dir / "mechanical.json"
    if not mj.exists():
        return {"status": "fit_failed", "stderr": run.stderr[-1500:]}
    m = json.loads(mj.read_text())
    apf = m.get("all_points_fit") or {}
    return {"status": "ok", "pressures_atm": m.get("pressures_atm"),
            "B0_GPa": m.get("bulk_modulus_GPa"), "B0_sem_GPa": m.get("bulk_modulus_sem_GPa"),
            "B0_prime": m.get("B0_prime"), "r_squared": m.get("r_squared"), "n_points": m.get("n_points"),
            "excluded_points": m.get("excluded_points"), "all_points_B0_GPa": apf.get("B0_GPa"),
            "all_points_B0_prime": apf.get("B0_prime"), "bm_gate_verdict": m.get("bm_gate_verdict"),
            "bm_convergence_verdict": m.get("bm_convergence_verdict"),
            "n_eff_per_point": m.get("n_eff_per_point"), "tau_frames_per_point": m.get("tau_frames_per_point")}


def point_diag(p: float, d: float, s: int) -> dict | None:
    _, logp = L.point_source(p, d, s)
    if not complete(logp):
        return None
    v_mean, v_std, n_prod, tau, n_eff, sem = extract_mean_volume(str(logp), 0.5)
    df = parse_lammps_log(str(logp))
    vol = df["Volume"].to_numpy(dtype=float)[int(len(df) * 0.5):]
    half = len(vol) // 2
    return {"pressure_atm": p, "npt_steps": s, "V_mean_A3": round(v_mean, 1), "V_std_A3": round(v_std, 1),
            "tau_frames": round(float(tau), 2), "n_eff": int(n_eff), "V_sem_A3": round(float(sem), 1),
            "half_shift_A3": round(float(vol[half:].mean() - vol[:half].mean()), 1),
            "half_shift_over_std": round(float((vol[half:].mean() - vol[:half].mean()) / v_std), 2) if v_std else None,
            "V_range_over_std": round(float((vol.max() - vol.min()) / v_std), 2) if v_std else None}


def main() -> int:
    results = {"generated_at": datetime.now(timezone.utc).isoformat(), "legs": {}, "tension_points": []}
    for leg, spec in L.LEGS.items():
        pairs = leg_logs(leg, spec)
        rec = {"axis": spec["axis"], "planned_pressures_atm": [p for p, _, _ in spec["points"]]}
        rec.update({"status": "pending"} if pairs is None else fit(leg, pairs))
        results["legs"][leg] = rec
    base = results["legs"].get("baseline", {})
    b0 = base.get("B0_GPa")
    base_all = base.get("all_points_B0_GPa")
    results["baseline_reproduces_stored"] = (b0 is not None and abs(b0 - STORED_BASELINE_B0) < 1e-3)
    for leg, rec in results["legs"].items():
        if rec.get("B0_GPa") is not None and b0:
            rec["dB0_pct_vs_baseline"] = round(100 * (rec["B0_GPa"] - b0) / b0, 2)
        if rec.get("all_points_B0_GPa") is not None and base_all:
            rec["dB0_all_points_pct_vs_baseline_all_points"] = round(100 * (rec["all_points_B0_GPa"] - base_all) / base_all, 2)
    seen = set()
    for p, d, s in L.LEGS["tension_series"]["points"] + [(-1000, L.BASE_DAMP_FS, 1_000_000)]:
        if (p, d, s) in seen:
            continue
        seen.add((p, d, s))
        diag = point_diag(p, d, s)
        results["tension_points"].append(diag or {"pressure_atm": p, "npt_steps": s, "status": "pending"})
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "results.json").write_text(json.dumps(results, indent=2) + "\n")

    rows = ["| Leg | Axis | Pressures fitted (atm) | B0 (GPa) | ΔB0 vs baseline | B0′ | R² | Excluded | All-points B0 (GPa) | Gate |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for leg, r in results["legs"].items():
        if r.get("status") != "ok":
            rows.append(f"| {leg} | {r['axis']} | — | {r.get('status')} | | | | | | |")
            continue
        exc = ", ".join(str(int(x["pressure_atm"])) for x in (r.get("excluded_points") or [])) or "—"
        rows.append(f"| {leg} | {r['axis']} | {', '.join(str(int(x)) for x in r['pressures_atm'])} | {r['B0_GPa']:.3f} | "
                    f"{r.get('dB0_pct_vs_baseline', 0):+.1f}% | {r['B0_prime']:.2f} | {r['r_squared']:.5f} | {exc} | "
                    f"{r['all_points_B0_GPa']:.3f} | {r['bm_gate_verdict']} |")
    rows += ["", "Tension diagnostics (production window = last 50% of each log):", "",
             "| P (atm) | steps | ⟨V⟩ (Å³) | σV | τ (frames) | n_eff | second−first half ⟨V⟩ (σ) | range/σ |", "|---|---|---|---|---|---|---|---|"]
    for t in results["tension_points"]:
        if "V_mean_A3" not in t:
            rows.append(f"| {t['pressure_atm']} | {t['npt_steps']} | pending | | | | | |")
        else:
            rows.append(f"| {t['pressure_atm']} | {t['npt_steps']} | {t['V_mean_A3']} | {t['V_std_A3']} | {t['tau_frames']} | "
                        f"{t['n_eff']} | {t['half_shift_over_std']} | {t['V_range_over_std']} |")
    rows.append("")
    rows.append(f"Baseline reproduces stored sPVC_3 B0 ({STORED_BASELINE_B0} GPa): {results['baseline_reproduces_stored']}")
    readme = HERE / "README.md"
    text = readme.read_text()
    start, end = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
    body = f"{start}\n_Generated {results['generated_at']} by analyze.py._\n\n" + "\n".join(rows) + f"\n{end}"
    text = text[:text.index(start)] + body + text[text.index(end) + len(end):]
    readme.write_text(text)
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
