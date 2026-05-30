#!/usr/bin/env python3
"""
emc_pipeline.py — Batch CLI for non-agent EMC runs.
For LLM-agent workflows, use the MCP tools per guides/STAGE_1–3.
This script is useful for scripted batch runs or debugging outside Claude Code.

Full pipeline from SMILES to Tg for any EMC-built polymer cell.
Handles PCFF, OPLS-AA, and TraPPE-UA force fields automatically via
lammps_flags returned by the EMC server.

Usage:
    python emc_pipeline.py build  CLASS SMILES [options]   # build cell only
    python emc_pipeline.py equil  CLASS SMILES [options]   # build + equilibrate
    python emc_pipeline.py tg     CLASS SMILES [options]   # build + equil + Tg sweep
    python emc_pipeline.py all    CLASS SMILES [options]   # same as tg

Examples:
    python emc_pipeline.py tg PCBN "*OC(=O)Oc1ccc(C(C)(C)c2ccc(*)cc2)cc1" --run-name BPAPC2
    python emc_pipeline.py tg PAMD "*C(=O)NCCCCC*" --max-temp 650 --tg-start 650 --tg-end 150
    python emc_pipeline.py equil PHAL "*CC(F)(F)*" --run-name PVDF1

Force field is auto-selected from CLASS — no --ff flag needed.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────

REPO         = Path(__file__).parent
EMC_JOBS_DIR = Path.home() / "polyjarvis_emc_jobs"
SIM_BASE     = Path.home() / "simulations"
LAMMPS       = Path.home() / "lammps-install/bin/lmp"
VENV_PY      = REPO / "mcp-servers/.venv/bin/python"

sys.path.insert(0, str(REPO / "mcp-servers/mcp-lammps-engine"))
sys.path.insert(0, str(REPO / "mcp-servers/mcp-emc-server"))

from script_generator import ScriptGenerator
from smiles_to_emc import build_cell

# ── FF routing (mirrors mcp-emc-server/_select_field) ─────────────────────────

_FF_MAP = {
    "PCBN": ("pcff",              {"use_pcff": True,  "use_opls": False}),
    "PAMD": ("pcff",              {"use_pcff": True,  "use_opls": False}),
    "PKTN": ("pcff",              {"use_pcff": True,  "use_opls": False}),
    "PSFO": ("pcff",              {"use_pcff": True,  "use_opls": False}),
    "PIMD": ("pcff",              {"use_pcff": True,  "use_opls": False}),
    "PHAL": ("opls/2024/opls-aa", {"use_pcff": False, "use_opls": True}),
    "PHYC": ("trappe-ua",         {"use_pcff": False, "use_opls": False}),
    "PDIE": ("trappe-ua",         {"use_pcff": False, "use_opls": False}),
    "PSTR": ("trappe-ua",         {"use_pcff": False, "use_opls": False}),
}

_STYLE_PREFIXES = (
    "pair_style", "bond_style", "angle_style",
    "dihedral_style", "improper_style", "kspace_style",
)

def _strip_params_styles(params_file: Path):
    """Remove force-field style lines from EMC .params file (keep coeffs only)."""
    lines = params_file.read_text().splitlines(keepends=True)
    stripped = [l for l in lines if not any(l.startswith(p) for p in _STYLE_PREFIXES)]
    if len(stripped) != len(lines):
        params_file.write_text("".join(stripped))

# ── cell build ─────────────────────────────────────────────────────────────────

def stage_build(args) -> dict:
    """Build EMC amorphous cell. Returns paths to data and params files."""
    polymer_class = args.polymer_class.upper()
    if polymer_class not in _FF_MAP:
        raise ValueError(f"Unsupported class '{polymer_class}'. Supported: {sorted(_FF_MAP)}")

    field, lammps_flags = _FF_MAP[polymer_class]
    run_dir = SIM_BASE / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    cell_dir = EMC_JOBS_DIR / args.run_name
    cell_dir.mkdir(parents=True, exist_ok=True)

    print(f"[build] Class={polymer_class}  FF={field}  DP={args.dp}  ntotal={args.ntotal}")
    data_path = build_cell(
        smiles=args.smiles,
        output_dir=cell_dir,
        output_name=args.run_name,
        field=field,
        density=args.density_initial,
        ntotal=args.ntotal,
        dp=args.dp,
        temperature=args.temp,
        seed=args.seed,
    )

    # Strip style lines from params file (EMC writes them; we override via templates)
    params_path = data_path.with_suffix(".params")
    if params_path.exists():
        _strip_params_styles(params_path)

    natoms = None
    for line in data_path.read_text().splitlines():
        if "atoms" in line and not line.strip().startswith("#"):
            try:
                natoms = int(line.split()[0])
                break
            except ValueError:
                pass

    print(f"[build] Done — {natoms} atoms → {data_path}")
    return {
        "data_path":    data_path,
        "params_path":  params_path if params_path.exists() else None,
        "lammps_flags": lammps_flags,
        "natoms":       natoms,
        "run_dir":      run_dir,
    }

# ── equilibration ──────────────────────────────────────────────────────────────

def stage_equil(build_result: dict, args) -> dict:
    """Generate and run 6-stage GPU equilibration."""
    data_path    = build_result["data_path"]
    params_path  = build_result["params_path"]
    lammps_flags = build_result["lammps_flags"]
    run_dir      = build_result["run_dir"]

    gen = ScriptGenerator(data_file=str(data_path))
    ff_base = {
        "use_shake":  False if lammps_flags["use_pcff"] else True,
        "use_pcff":   lammps_flags["use_pcff"],
        "use_opls":   lammps_flags["use_opls"],
    }
    if params_path and params_path.exists():
        ff_base["params_file"] = str(params_path)

    # Step counts scaled by atom count
    natoms = build_result["natoms"] or 3000
    if natoms < 5000:
        n_comp, n_npt, n_nvt = 300_000, 1_000_000, 1_000_000
    elif natoms < 15000:
        n_comp, n_npt, n_nvt = 500_000, 2_000_000, 2_000_000
    else:
        n_comp, n_npt, n_nvt = 1_000_000, 3_000_000, 3_000_000

    max_temp = args.max_temp

    stages = [
        ("01_minimize",     "minimize",     {"use_pppm":True,"use_gpu":True,"MIN_STYLE":"cg","MAXITER":50000},
         str(data_path)),
        ("02_nvt_softheat", "nvt",          {"T_START":args.temp,"T_FINAL":max_temp,"T_DAMP":50.0,"TIMESTEP":0.5,"N_STEPS":n_comp,"use_pppm":True,"use_gpu":True,"init_velocity":args.temp},
         None),
        ("03_npt_compress", "npt_compress", {"T_START":max_temp,"T_FINAL":max_temp,"T_DAMP":100.0,"P_START":1.0,"P_FINAL":args.max_press,"P_DAMP":1000.0,"TIMESTEP":1.0,"N_STEPS":n_comp,"use_pppm":True,"use_gpu":True},
         None),
        ("04_npt_pppm",     "npt",          {"T_START":max_temp,"T_FINAL":max_temp,"T_DAMP":100.0,"P_START":args.max_press,"P_FINAL":1.0,"P_DAMP":1000.0,"TIMESTEP":1.0,"N_STEPS":n_comp,"use_pppm":True,"use_gpu":True,"write_restart":True},
         None),
        ("05_npt_cool",     "npt",          {"T_START":max_temp,"T_FINAL":args.temp,"T_DAMP":100.0,"P_START":1.0,"P_FINAL":1.0,"P_DAMP":1000.0,"TIMESTEP":1.0,"N_STEPS":n_npt,"use_pppm":True,"use_gpu":True,"write_restart":True},
         None),
        ("06_nvt_production","nvt",         {"T_START":args.temp,"T_FINAL":args.temp,"T_DAMP":100.0,"TIMESTEP":1.0,"N_STEPS":n_nvt,"use_pppm":True,"use_gpu":True,"write_restart":False},
         None),
    ]

    prev_out = str(data_path)
    stage_info = []
    for name, tmpl, p, override_data in stages:
        d = run_dir / name
        d.mkdir(parents=True, exist_ok=True)
        out_data = str(d / f"{name}_out.data")
        inp = override_data or prev_out
        params = {"LOG_FILE":f"{name}.log","DUMP_FILE":f"{name}.dump","LAST_DUMP_FILE":f"{name}_last.dump","WRITE_DATA_FILE":out_data}
        params.update(p)
        params.update(ff_base)
        script_path = str(d / f"{name}.in")
        gen.generate(template_name=tmpl, output_path=script_path, params=params, data_file_override=inp)
        stage_info.append((name, d, script_path, out_data))
        prev_out = out_data
        print(f"[equil] Generated {name}.in")

    print(f"[equil] Running 6-stage GPU chain (mpi={args.mpi}, gpus={args.gpu_ids})...")
    for name, d, script_path, out_data in stage_info:
        print(f"[equil] Starting {name}...", flush=True)
        cmd = ["mpirun", "-np", str(args.mpi), str(LAMMPS),
               "-pk", "gpu", str(len(args.gpu_ids.split(","))),
               "-sf", "gpu", "-in", Path(script_path).name]
        result = subprocess.run(cmd, cwd=d, capture_output=False,
                                stdout=open(d / f"{name}_stdout.log", "w"),
                                stderr=subprocess.STDOUT)
        if result.returncode != 0:
            raise RuntimeError(f"Stage {name} failed (exit {result.returncode}). "
                               f"Check {d}/{name}_stdout.log")
        print(f"[equil] {name} done")

    final_data = stage_info[-1][3]  # 06_nvt_production_out.data
    print(f"[equil] Equilibration complete → {final_data}")
    return {"equil_data": final_data, "run_dir": run_dir, "lammps_flags": lammps_flags}

# ── Tg sweep ───────────────────────────────────────────────────────────────────

def stage_tg(equil_result: dict, args) -> dict:
    """Generate and run stepwise-cooling Tg sweep."""
    equil_data   = equil_result["equil_data"]
    lammps_flags = equil_result["lammps_flags"]
    run_dir      = equil_result["run_dir"]

    tg_dir = run_dir / "tg_sweep"
    tg_dir.mkdir(parents=True, exist_ok=True)

    gen = ScriptGenerator(data_file=equil_data)
    params = {
        "LOG_FILE":       "tg_sweep.log",
        "DUMP_FILE":      "",
        "LAST_DUMP_FILE": "tg_last.dump",
        "T_START":        args.tg_start,
        "T_END":          args.tg_end,
        "T_STEP":         args.tg_step,
        "N_STEPS_PER_T":  args.steps_per_t,
        "P_START":        1.0,
        "P_FINAL":        1.0,
        "P_DAMP":         1000.0,
        "T_DAMP":         100.0,
        "TIMESTEP":       1.0,
        "use_pppm":       True,
        "use_gpu":        True,
        "use_pcff":       lammps_flags["use_pcff"],
        "use_opls":       lammps_flags["use_opls"],
        "use_shake":      False if lammps_flags["use_pcff"] else True,
        "write_restart":  False,
    }
    script_path = str(tg_dir / "tg_sweep.in")
    gen.generate(template_name="npt_tg_step", output_path=script_path,
                 params=params, data_file_override=equil_data)
    print(f"[tg] Generated tg_sweep.in  ({args.tg_start}→{args.tg_end} K, {args.tg_step} K steps, {args.steps_per_t} steps/T)")

    n_temps = int((args.tg_start - args.tg_end) / args.tg_step) + 1
    total_steps = n_temps * args.steps_per_t
    print(f"[tg] {n_temps} temperatures × {args.steps_per_t} steps = {total_steps:,} total steps")

    print(f"[tg] Running Tg sweep...", flush=True)
    cmd = ["mpirun", "-np", str(args.mpi), str(LAMMPS),
           "-pk", "gpu", str(len(args.gpu_ids.split(","))),
           "-sf", "gpu", "-in", "tg_sweep.in"]
    result = subprocess.run(cmd, cwd=tg_dir, capture_output=False,
                            stdout=open(tg_dir / "tg_stdout.log", "w"),
                            stderr=subprocess.STDOUT)
    if result.returncode != 0:
        raise RuntimeError(f"Tg sweep failed. Check {tg_dir}/tg_stdout.log")

    log_path = tg_dir / "tg_sweep.log"
    print(f"[tg] Sweep complete → {log_path}")
    return {"tg_log": str(log_path), "run_dir": run_dir}

# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="EMC → LAMMPS pipeline for any EMC-supported polymer class")
    p.add_argument("stage",         choices=["build","equil","tg","all"], help="Pipeline stage to run")
    p.add_argument("polymer_class", help="PolyInfo class (PCBN, PAMD, PKTN, PSFO, PIMD, PHAL, PHYC, PDIE, PSTR)")
    p.add_argument("smiles",        help="Repeat-unit SMILES with two * connection points")

    p.add_argument("--run-name",   default=None,  help="Run directory name under ~/simulations/ [auto: CLASS_1]")
    p.add_argument("--dp",         type=int,   default=20,      help="Degree of polymerization [20]")
    p.add_argument("--ntotal",     type=int,   default=3000,    help="Target atom count for EMC [3000]")
    p.add_argument("--density",    type=float, default=None,    help="Initial packing density [class default]")
    p.add_argument("--temp",       type=float, default=300.0,   help="Target simulation temperature K [300]")
    p.add_argument("--max-temp",   type=float, default=600.0,   help="Peak annealing temperature K [600]")
    p.add_argument("--max-press",  type=float, default=50000.0, help="Compression pressure atm [50000]")
    p.add_argument("--seed",       type=int,   default=-1,      help="EMC random seed [-1=random]")
    p.add_argument("--gpu-ids",    default="0,1,2,3",           help="GPU IDs to use [0,1,2,3]")
    p.add_argument("--mpi",        type=int,   default=4,       help="MPI processes [4]")
    p.add_argument("--tg-start",   type=float, default=600.0,   help="Tg sweep start temperature K [600]")
    p.add_argument("--tg-end",     type=float, default=200.0,   help="Tg sweep end temperature K [200]")
    p.add_argument("--tg-step",    type=float, default=20.0,    help="Tg sweep temperature step K [20]")
    p.add_argument("--steps-per-t",type=int,   default=500000,  help="LAMMPS steps per temperature point [500000]")

    args = p.parse_args()

    # Auto run name
    if args.run_name is None:
        cls = args.polymer_class.upper()
        i = 1
        while (SIM_BASE / f"{cls}_{i}").exists():
            i += 1
        args.run_name = f"{cls}_{i}"

    # Default density by class
    if args.density is None:
        _defaults = {"PCBN":0.60,"PAMD":0.57,"PKTN":0.65,"PSFO":0.65,"PIMD":0.70,
                     "PHAL":0.89,"PHYC":0.48,"PDIE":0.45,"PSTR":0.53}
        args.density_initial = _defaults.get(args.polymer_class.upper(), 0.60)
    else:
        args.density_initial = args.density

    return args


def main():
    args = parse_args()
    print(f"=== emc_pipeline.py | run={args.run_name} | class={args.polymer_class} | stage={args.stage} ===")

    build_result = stage_build(args)

    if args.stage == "build":
        return

    equil_result = stage_equil(build_result, args)

    if args.stage == "equil":
        return

    tg_result = stage_tg(equil_result, args)
    print(f"\n=== Done. Tg sweep log: {tg_result['tg_log']} ===")
    print("Next: run extract_tg on the log file for Tg extraction.")


if __name__ == "__main__":
    main()
