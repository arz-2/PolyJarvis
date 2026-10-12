#!/usr/bin/env python3
"""Grade one cell against PolyJarvis's equilibration gate. Runs in mcp-servers/.venv.

Two modes, because the two arms left different evidence behind:

  trajectory  The PolyJarvis cells kept their dumps, so the real checker
              (check_equilibration_comprehensive.py) runs on them unchanged, as a subprocess.
  log-only    RadonPy's run kept only its logs and analysis CSVs. `check_thermo` -- the
              checker's own section A -- runs on the log; `rg` (chain-mean Rg CV, the same
              statistic the checker computes) and `finite_size` are recovered from RadonPy's
              stored Rg and the log's box. p2, density_homogeneity, torsion, msid and
              chain_displacement need a trajectory and stay unmeasured.

Both modes then go through enforce_gate.collect_gates and enforce_gate.classify, so the clause,
its binding set and its unmeasured list are the production gate's, not a copy.

Usage:
    python polyjarvis_grader.py trajectory --log L --dump D --data F --backbone-types 1 4 \
        --cutoff-a 9.5 --dp 100 --checker-dir DIR --out polyjarvis.json [--reuse]
    python polyjarvis_grader.py log-only --log L --cutoff-a 12.0 --dp 142 \
        --rg-mean-a 19.86 --rg-chain-mean-sd-a 3.31 --out polyjarvis.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ANALYSIS = REPO / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"
CHECKER = ANALYSIS / "check_equilibration_comprehensive.py"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ANALYSIS))
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

import check_equilibration_comprehensive as cec  # noqa: E402
import enforce_gate  # noqa: E402
from analysis_utils import parse_lammps_log  # noqa: E402
from criteria import polyjarvis_verdict  # noqa: E402
from finite_size import classify_finite_size  # noqa: E402

# PEG's Tg is ~206 K and every cell here is graded at 300 K: require_rubbery, the clause round 1
# and data/peg_comparison_gate.py already graded these runs under.
REGIME = "rubbery"
# The checker CLI's own defaults, so the log-only thermo section is computed exactly as the
# trajectory mode's is.
EQ_FRACTION, DRIFT_PCT, DRIFT_P, BLOCKS, N_EFF_MIN = 0.5, 1.0, 0.01, 10, 20
RG_SPREAD_CV_MAX = 0.30


def thermo_section(thermo: dict) -> dict:
    """check_thermo's result reshaped exactly as the checker's main() writes `thermo`."""
    return {
        "equilibrated": thermo.get("equilibrated"),
        "density_drift": thermo.get("density", {}).get("drift"),
        "energy_drift": thermo.get("energy", {}).get("drift"),
        "energy_component_drift": thermo.get("energy", {}).get("component_drift"),
        "density_sem": thermo.get("density", {}).get("block_sem"),
        "energy_sem": thermo.get("energy", {}).get("block_sem"),
        "tau_eff_density_fraction": thermo.get("tau_eff_density_fraction"),
        "n_eff_density": {
            "pass": thermo.get("n_eff_density") is None or thermo["n_eff_density"] >= N_EFF_MIN,
            "n_eff": thermo.get("n_eff_density"), "n_eff_min": N_EFF_MIN,
        },
        "residual_stress": thermo.get("residual_stress"),
        "meta": thermo.get("meta"),
    }


def run_checker(log, dump, data, backbone_types, cutoff_a, checker_dir: Path, reuse: bool) -> dict:
    out_json = checker_dir / "equilibration.json"
    if not (reuse and out_json.is_file()):
        checker_dir.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(CHECKER), "--log_file", str(log), "--dump_file", str(dump),
               "--data_file", str(data), "--backbone_types", *map(str, backbone_types),
               "--cutoff_A", str(cutoff_a), "--n_eff_min", str(N_EFF_MIN),
               "--output_dir", str(checker_dir), "--output_name", "equilibration.json"]
        with open(checker_dir / "checker_stdout.txt", "w") as fh:
            proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
        if proc.returncode != 0:
            # A crashed checker must stop the grade -- an equilibration.json without its chain
            # sections is exactly the input that once let the melt gate pass on nothing.
            raise SystemExit(f"checker exited {proc.returncode}; see {checker_dir / 'checker_stdout.txt'}")
    comp = json.loads(out_json.read_text())
    if comp.get("status") != "success":
        raise SystemExit(f"checker result status {comp.get('status')!r} in {out_json}")
    return comp


def log_only_comp(log, cutoff_a, rg_mean_a, rg_chain_mean_sd_a) -> dict:
    thermo = cec.check_thermo(log, EQ_FRACTION, DRIFT_PCT, DRIFT_P, BLOCKS,
                              "Temp", "Density", "TotEng", ["Pxx", "Pyy", "Pzz"])
    if "error" in thermo:
        raise SystemExit(f"check_thermo failed on {log}: {thermo['error']}")
    comp = {"thermo": thermo_section(thermo), "chain": {}, "spatial": {}}

    if rg_mean_a and rg_chain_mean_sd_a is not None:
        cv = rg_chain_mean_sd_a / rg_mean_a
        comp["chain"]["rg"] = {
            "pass": not cv > RG_SPREAD_CV_MAX, "cv": round(cv, 4), "mean_Rg_A": rg_mean_a,
            "source": ("RadonPy eq_conv_data.csv Rg_mean_sd / eq_prop_data.csv Rg: the sd across "
                       "chains of each chain's time-mean Rg over its mean -- the checker's rg_cv"),
        }

    df = parse_lammps_log(log)
    last = df.iloc[-1]
    box = [float(last[c]) for c in ("Lx", "Ly", "Lz") if c in df.columns]
    fs = classify_finite_size(min(box) if len(box) == 3 else None, cutoff_a, rg_mean_a, None)
    if fs.get("available"):
        fs["graded_box"] = "last thermo row of the graded log"
    comp["spatial"]["finite_size"] = fs
    return comp


def _naive_p_failures(comp: dict) -> list[str]:
    """Components that would fail if drift significance ignored autocorrelation -- the verdict
    this gate gave before the 2026-09-10 n_eff correction. Reported, not binding."""
    components = ((comp.get("thermo") or {}).get("energy_component_drift") or {}).get("components") or {}
    failing = []
    for label, c in components.items():
        size = c.get("drift_sigma") if c.get("criterion") == "drift_sigma" else c.get("drift_pct")
        p_naive = c.get("p_value_naive")
        # p_naive of exactly 0.0 is the common case on a long log -- test for None, not falsiness.
        if size is not None and p_naive is not None and size > c["threshold"] and p_naive < DRIFT_P:
            failing.append(label)
    return sorted(failing)


def evaluate(comp: dict, dp_typical) -> dict:
    gates = enforce_gate.collect_gates(comp)
    clause, binding, advisory, unmeasured = enforce_gate.classify(gates, REGIME, dp_typical, None)
    failing = sorted(k for k, v in binding.items() if v is False)
    components = ((comp.get("thermo") or {}).get("energy_component_drift") or {}).get("components")
    return {
        "clause": clause,
        "verdict": polyjarvis_verdict(failing, unmeasured),
        "binding": binding,
        "failing_binding": failing,
        "unmeasured_binding": unmeasured,
        "advisory": advisory,
        "failing_advisory": sorted(k for k, v in advisory.items() if v is False),
        "energy_component_drift": components,
        "component_drift_failing_under_naive_p": _naive_p_failures(comp),
        "rg": (comp.get("chain") or {}).get("rg"),
        "finite_size": (comp.get("spatial") or {}).get("finite_size"),
        "density_mean": ((comp.get("thermo") or {}).get("density_drift") or {}).get("mean"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    t = sub.add_parser("trajectory")
    t.add_argument("--log", required=True)
    t.add_argument("--dump", required=True)
    t.add_argument("--data", required=True)
    t.add_argument("--backbone-types", type=int, nargs="+", required=True)
    t.add_argument("--checker-dir", required=True)
    t.add_argument("--reuse", action="store_true")
    o = sub.add_parser("log-only")
    o.add_argument("--log", required=True)
    o.add_argument("--rg-mean-a", type=float, default=None)
    o.add_argument("--rg-chain-mean-sd-a", type=float, default=None)
    for p in (t, o):
        p.add_argument("--cutoff-a", type=float, required=True)
        p.add_argument("--dp", type=int, default=None)
        p.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.mode == "trajectory":
        comp = run_checker(args.log, args.dump, args.data, args.backbone_types, args.cutoff_a,
                           Path(args.checker_dir), args.reuse)
    else:
        comp = log_only_comp(args.log, args.cutoff_a, args.rg_mean_a, args.rg_chain_mean_sd_a)
    result = {"mode": args.mode, "log": args.log, **evaluate(comp, args.dp)}
    Path(args.out).write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps({k: result[k] for k in ("verdict", "failing_binding", "unmeasured_binding")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
