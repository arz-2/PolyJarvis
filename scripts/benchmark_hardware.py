#!/usr/bin/env python3
"""
benchmark_hardware.py — mpi/gpu throughput benchmark for PolyJarvis LAMMPS cells.

Measures ns/day + the LAMMPS MPI-task timing breakdown (Pair / Kspace / Neigh /
Comm / ...) for a built .data cell across a config matrix, per template/pair-style
cost class. The breakdown is the discriminator: Kspace-dominated => more MPI ranks
help and GPU does not; Pair-dominated => GPU offload helps.

Two ways to define the run being benchmarked:
  (A) generate mode  — build a short NVT .in via the engine's ScriptGenerator from
      a .data file + FF flags (covers the lj/cut / class2+pppm / opls+pppm classes).
  (B) reuse mode     — point at an existing fully-formed .in (e.g. a real nvt_born.in,
      npt_deform.in, tg_sweep.in) and only override its run length; faithful for the
      special integrators/computes whose scaling differs from plain MD.

GPU is driven *entirely* from the mpirun command line (`-sf gpu -pk gpu N neigh no`),
never an in-file `package gpu` line — so the same .in serves every config and the
multi-GPU count N is honored (an in-file `package gpu 1` would silently override N).

POLITE SCHEDULING (default): never contends with in-flight screening runs. Each
config only runs on a GPU at ~0% utilization and only if its MPI ranks fit in the
spare physical cores (18 - live lmp ranks). Configs that don't fit are SKIPPED.
Pass --allow-busy for the definitive clean sweep when the box is drained.

Usage:
  # UA cell, plain NVT (lj/cut, no kspace)
  scripts/benchmark_hardware.py --data data/PE1/.../*.data --ff trappe

  # PCFF cell, class2 + pppm
  scripts/benchmark_hardware.py --data data/PMMA1/.../*.data --ff pcff --pppm

  # faithful born/deform/tg cost class via an existing input deck
  scripts/benchmark_hardware.py --data <equil.data> --reuse-in <real_nvt_born.in> \
      --label PSU1_born
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

# --- locate the engine's ScriptGenerator (generate mode) -------------------
REPO = Path(__file__).resolve().parents[1]
ENGINE = REPO / "mcp-servers" / "mcp-lammps-engine"
sys.path.insert(0, str(ENGINE))

LMP_DEFAULT = "/home/arz2/lammps-install/bin/lmp"
CONDA_ACTIVATE = "source ~/miniforge3/etc/profile.d/conda.sh; conda activate mol-builder"
PHYS_CORES = 18                       # i9-10980XE physical cores
GPU_IDLE_UTIL = 5                     # % util at-or-below = idle
GPU_IDLE_MEM_MB = 800                 # MB used at-or-below = idle (no run mid-setup)

# config matrix — gpu = number of *physical* GPUs; mpi = rank count (each rank = 1 core)
DEFAULT_CONFIGS = [
    {"name": "cpu_mpi4",   "mpi": 4,  "gpu": 0},
    {"name": "cpu_mpi8",   "mpi": 8,  "gpu": 0},
    {"name": "cpu_mpi16",  "mpi": 16, "gpu": 0},
    {"name": "gpu1_mpi1",  "mpi": 1,  "gpu": 1},
    {"name": "gpu1_mpi2",  "mpi": 2,  "gpu": 1},
    {"name": "gpu1_mpi4",  "mpi": 4,  "gpu": 1},
    {"name": "gpu1_mpi8",  "mpi": 8,  "gpu": 1},
    {"name": "gpu2_mpi2",  "mpi": 2,  "gpu": 2},
    {"name": "gpu4_mpi4",  "mpi": 4,  "gpu": 4},
]

SECTION_RE = re.compile(
    r"^(Pair|Bond|Angle|Dihedral|Improper|Kspace|Neigh|Comm|Output|Modify|Other)\s*\|"
)


# --------------------------------------------------------------------------
# Hardware probing (politeness)
# --------------------------------------------------------------------------
def gpu_status() -> list[dict]:
    """Return [{index, util, mem_used_mb}] from nvidia-smi, or [] if unavailable."""
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=index,utilization.gpu,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            gpus.append({"index": int(parts[0]),
                         "util": int(parts[1]),
                         "mem_used_mb": int(parts[2])})
    return gpus


def idle_gpu_ids() -> list[int]:
    return [g["index"] for g in gpu_status()
            if g["util"] <= GPU_IDLE_UTIL and g["mem_used_mb"] <= GPU_IDLE_MEM_MB]


def live_lmp_ranks(lmp_path: str = "lmp") -> int:
    """Count currently-running lmp processes (≈ MPI ranks in flight). Matches the
    exact process name `lmp` so the parent `mpirun` launchers are not counted."""
    try:
        out = subprocess.run(["pgrep", "-xc", "lmp"],
                             capture_output=True, text=True, timeout=10).stdout
        return int(out.strip() or 0)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return 0


# --------------------------------------------------------------------------
# Input-deck preparation
# --------------------------------------------------------------------------
def detect_params_file(data_file: str) -> str:
    """EMC/PCFF/TraPPE builds keep pair coeffs in a sibling *.params include."""
    d = Path(data_file).parent
    for cand in sorted(d.glob("*.params")):
        return str(cand)
    return ""


def make_input_generate(data_file: str, ff: str, pppm: bool, steps: int,
                        timestep: float, params_file: str, out_in: Path) -> None:
    """Build a short NVT .in via the engine ScriptGenerator (use_gpu always False —
    GPU is driven from the command line)."""
    from script_generator import ScriptGenerator  # type: ignore

    flags = {"use_pcff": ff == "pcff", "use_opls": ff == "opls",
             "use_trappe": ff == "trappe"}
    params = {
        **flags,
        "use_pppm": pppm,
        "use_gpu": False,             # never emit in-file `package gpu` (see module docstring)
        "use_shake": False,           # benchmark pair/kspace scaling, not SHAKE
        "write_restart": False,
        "params_file": params_file,   # include line for EMC pair coeffs
        "N_STEPS": steps,
        "TIMESTEP": timestep,
        "T_START": 400.0, "T_FINAL": 400.0, "T_DAMP": 100.0,
        "THERMO_FREQ": max(steps // 5, 100),
        "DUMP_FREQ": steps * 10,      # effectively no trajectory I/O during the run
        "init_velocity": 400.0,
        "LOG_FILE": str(out_in.with_suffix(".log").name),
    }
    gen = ScriptGenerator(data_file=data_file)
    gen.generate("nvt", str(out_in), params, data_file_override=data_file)


def make_input_reuse(reuse_in: str, data_file: str, steps: int, out_in: Path) -> None:
    """Copy an existing .in, strip any in-file `package gpu` line, point it at the
    given .data, and shorten the run to `steps`."""
    text = Path(reuse_in).read_text()
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("package gpu"):
            continue                                   # GPU set from command line
        if re.match(r"^\s*run\s+\d+", ln):
            ln = re.sub(r"^(\s*run\s+)\d+", rf"\g<1>{steps}", ln)
        if re.match(r"^\s*(read_data|read_restart)\s", ln):
            ln = re.sub(r"^(\s*(?:read_data|read_restart)\s+)\S+",
                        rf"\g<1>{data_file}", ln)
        lines.append(ln)
    out_in.write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------
# Run + parse one config
# --------------------------------------------------------------------------
def build_cmd(lmp: str, in_file: Path, mpi: int, gpu_ids: list[int]) -> tuple[str, dict]:
    """Return (shell command string, env-note). GPU purely via -sf/-pk flags."""
    env_prefix = ""
    gpu_flags = ""
    if gpu_ids:
        env_prefix = f"CUDA_VISIBLE_DEVICES={','.join(map(str, gpu_ids))} "
        gpu_flags = f" -sf gpu -pk gpu {len(gpu_ids)} neigh no"
    inner = (f"{env_prefix}mpirun -np {mpi} {shlex.quote(lmp)}{gpu_flags} "
             f"-in {shlex.quote(str(in_file))}")
    cmd = f"bash -c {shlex.quote(CONDA_ACTIVATE + '; ' + inner)}"
    return cmd, {"gpu_ids": gpu_ids, "gpu_flags": gpu_flags}


def parse_log(log_text: str) -> dict:
    res: dict = {"ns_per_day": None, "timesteps_per_s": None,
                 "loop_time_s": None, "procs": None, "atoms": None,
                 "sections_pct": {}}
    m = re.search(r"Performance:\s*([\d.]+)\s*ns/day.*?([\d.]+)\s*timesteps/s",
                  log_text)
    if m:
        res["ns_per_day"] = float(m.group(1))
        res["timesteps_per_s"] = float(m.group(2))
    m = re.search(r"Loop time of\s*([\d.]+)\s*on\s*(\d+)\s*procs.*?with\s*(\d+)\s*atoms",
                  log_text)
    if m:
        res["loop_time_s"] = float(m.group(1))
        res["procs"] = int(m.group(2))
        res["atoms"] = int(m.group(3))
    for ln in log_text.splitlines():
        if SECTION_RE.match(ln):
            cols = [c.strip() for c in ln.split("|")]
            try:
                res["sections_pct"][cols[0]] = float(cols[-1])
            except (ValueError, IndexError):
                pass
    return res


def run_config(cfg: dict, in_file: Path, lmp: str, work: Path,
               gpu_ids: list[int], timeout_s: int) -> dict:
    rundir = work / cfg["name"]
    rundir.mkdir(parents=True, exist_ok=True)
    # fresh log path per config
    cfg_in = rundir / "bench.in"
    text = in_file.read_text()
    text = re.sub(r"^log\s+\S+.*$", f"log {rundir/'bench.log'} ", text,
                  count=1, flags=re.M)
    cfg_in.write_text(text)

    cmd, note = build_cmd(lmp, cfg_in, cfg["mpi"], gpu_ids)
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              cwd=str(rundir), timeout=timeout_s)
        wall = time.time() - t0
    except subprocess.TimeoutExpired:
        return {**cfg, "status": "timeout", "gpu_ids": gpu_ids,
                "wall_s": time.time() - t0}

    log_path = rundir / "bench.log"
    log_text = log_path.read_text() if log_path.exists() else ""
    parsed = parse_log(log_text)
    status = "ok" if parsed["ns_per_day"] is not None else "failed"
    err_tail = ""
    if status == "failed":
        err_tail = (proc.stderr or log_text)[-600:]
    return {**cfg, "status": status, "wall_s": round(wall, 1),
            "gpu_ids": gpu_ids, **parsed,
            **({"error_tail": err_tail} if err_tail else {})}


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="built .data cell")
    ap.add_argument("--ff", choices=["pcff", "opls", "trappe", "gaff"],
                    help="force field family (generate mode)")
    ap.add_argument("--pppm", dest="pppm", action="store_true", default=None)
    ap.add_argument("--no-pppm", dest="pppm", action="store_false")
    ap.add_argument("--reuse-in", help="existing .in to benchmark (reuse mode)")
    ap.add_argument("--params-file", help="EMC pair-coeff include (default: auto-detect *.params next to --data)")
    ap.add_argument("--steps", type=int, default=4000, help="MD steps per config")
    ap.add_argument("--timestep", type=float, default=None, help="fs (default: 2 UA / 1 else)")
    ap.add_argument("--label", help="cell label for output (default: data dir name)")
    ap.add_argument("--out", help="output json path")
    ap.add_argument("--lmp", default=os.environ.get("LAMBDA_LAMMPS", LMP_DEFAULT))
    ap.add_argument("--max-cores", type=int, default=PHYS_CORES)
    ap.add_argument("--timeout", type=int, default=1800, help="per-config timeout (s)")
    ap.add_argument("--allow-busy", action="store_true",
                    help="skip politeness gating (clean-sweep mode, box drained)")
    ap.add_argument("--only", help="comma-separated config names to run (subset of the matrix)")
    ap.add_argument("--gpu-id", type=int, action="append",
                    help="force specific GPU id(s) for GPU configs (repeatable)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = str(Path(args.data).resolve())
    if not Path(data).exists():
        print(f"ERROR: data file not found: {data}", file=sys.stderr)
        return 2
    if not args.reuse_in and not args.ff:
        print("ERROR: need --ff (generate mode) or --reuse-in (reuse mode)",
              file=sys.stderr)
        return 2

    label = args.label or Path(data).parent.name or "cell"
    pppm = args.pppm
    if pppm is None:
        pppm = (args.ff in ("pcff", "opls", "gaff"))   # UA has no kspace
    timestep = args.timestep or (2.0 if args.ff == "trappe" else 1.0)

    work = Path("/tmp/polyjarvis/bench") / label
    work.mkdir(parents=True, exist_ok=True)
    master_in = work / "deck.in"
    if args.reuse_in:
        make_input_reuse(args.reuse_in, data, args.steps, master_in)
        mode = f"reuse:{Path(args.reuse_in).name}"
    else:
        params_file = args.params_file or detect_params_file(data)
        make_input_generate(data, args.ff, pppm, args.steps, timestep,
                            params_file, master_in)
        mode = (f"generate:nvt ff={args.ff} pppm={pppm} dt={timestep}fs"
                f" params={Path(params_file).name if params_file else 'none'}")

    print(f"== benchmark {label} ==")
    print(f"   data:   {data}")
    print(f"   deck:   {mode}")
    print(f"   steps:  {args.steps}   work: {work}\n")

    configs = DEFAULT_CONFIGS
    if args.only:
        want = {s.strip() for s in args.only.split(",")}
        configs = [c for c in configs if c["name"] in want]

    results = []
    for cfg in configs:
        # politeness gating
        idle = idle_gpu_ids()
        live = live_lmp_ranks(args.lmp)
        spare = args.max_cores - live
        gpu_ids: list[int] = []
        skip = None
        if not args.allow_busy:
            if cfg["mpi"] > spare:
                skip = f"needs {cfg['mpi']} cores, only {spare} spare (live ranks={live})"
            elif cfg["gpu"] > 0 and len(idle) < cfg["gpu"]:
                skip = f"needs {cfg['gpu']} idle GPU(s), idle={idle}"
        if cfg["gpu"] > 0:
            if args.gpu_id:
                gpu_ids = args.gpu_id[:cfg["gpu"]]
            else:
                gpu_ids = idle[:cfg["gpu"]]
                if args.allow_busy and len(gpu_ids) < cfg["gpu"]:
                    gpu_ids = list(range(cfg["gpu"]))   # clean sweep: trust caller

        if skip:
            print(f"  SKIP {cfg['name']:<11} — {skip}")
            results.append({**cfg, "status": "skipped", "reason": skip,
                            "concurrent_lmp_ranks": live})
            continue

        if args.dry_run:
            print(f"  PLAN {cfg['name']:<11} mpi={cfg['mpi']} gpu_ids={gpu_ids} "
                  f"(live ranks={live}, idle GPUs={idle})")
            continue

        print(f"  RUN  {cfg['name']:<11} mpi={cfg['mpi']} gpu_ids={gpu_ids} "
              f"(concurrent lmp ranks={live}) ... ", end="", flush=True)
        r = run_config(cfg, master_in, args.lmp, work, gpu_ids, args.timeout)
        r["concurrent_lmp_ranks"] = live
        results.append(r)
        if r["status"] == "ok":
            secs = r["sections_pct"]
            dom = max(secs, key=secs.get) if secs else "?"
            print(f"{r['ns_per_day']:.2f} ns/day  (dominant: {dom} {secs.get(dom,0):.0f}%)")
        else:
            print(r["status"])

    if args.dry_run:
        return 0

    ok = [r for r in results if r["status"] == "ok"]
    ok.sort(key=lambda r: r["ns_per_day"], reverse=True)
    summary = {
        "label": label, "data_file": data, "deck": mode, "steps": args.steps,
        "timestep_fs": timestep, "pppm": pppm,
        "host": {"phys_cores": args.max_cores, "lmp": args.lmp},
        "results": results,
        "recommended": ok[0] if ok else None,
    }
    out = Path(args.out) if args.out else Path(data).parent / "benchmark.json"
    out.write_text(json.dumps(summary, indent=2))

    print("\n== ranked (ns/day) ==")
    for r in ok:
        secs = r["sections_pct"]
        brk = "  ".join(f"{k}:{v:.0f}%" for k, v in sorted(
            secs.items(), key=lambda kv: kv[1], reverse=True)[:4])
        flag = " [contended]" if r.get("concurrent_lmp_ranks", 0) > 0 else ""
        print(f"  {r['name']:<11} {r['ns_per_day']:>7.2f}  | {brk}{flag}")
    if ok:
        print(f"\n  recommended: {ok[0]['name']} "
              f"({ok[0]['ns_per_day']:.2f} ns/day)")
    print(f"\n  written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
