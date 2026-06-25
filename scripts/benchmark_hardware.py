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
  (B) reuse mode     — point at an existing fully-formed .in (e.g. a real nvt_production.in,
      npt_deform.in, tg_sweep.in) and only override its run length; faithful for the
      special integrators/computes whose scaling differs from plain MD.

GPU is driven *entirely* from the mpirun command line (`-sf gpu -pk gpu N neigh no`),
never an in-file `package gpu` line — so the same .in serves every config and the
multi-GPU count N is honored (an in-file `package gpu 1` would silently override N).

POLITE SCHEDULING (default): never contends with other users' work. Each config
only runs on a GPU that is ~idle AND free of any compute process (any user), and
only if its MPI ranks fit in the spare physical cores (detected_cores − max(live
lmp ranks, measured busy cores)). Configs that don't fit are SKIPPED. The core
count and config ladder auto-scale to the box (see detect_phys_cores). Pass
--allow-busy for the definitive clean sweep when the box is drained (dedicated only).

Usage:
  # UA cell, plain NVT (lj/cut, no kspace)
  scripts/benchmark_hardware.py --data data/PE1/.../*.data --ff trappe

  # PCFF cell, class2 + pppm
  scripts/benchmark_hardware.py --data data/PMMA1/.../*.data --ff pcff --pppm

  # faithful deform/tg cost class via an existing input deck
  scripts/benchmark_hardware.py --data <equil.data> --reuse-in <real_npt_deform.in> \
      --label PSU1_deform
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

# --- locate the engine's ScriptGenerator (generate mode) -------------------
REPO = Path(__file__).resolve().parents[1]
ENGINE = REPO / "mcp-servers" / "mcp-lammps-engine"
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
# shared host/GPU probes (re-exported here so calibrate_hardware.py keeps using bh.detect_phys_cores / bh.gpu_status)
from hw_common import detect_phys_cores, gpu_status

LMP_DEFAULT = "/home/arz2/lammps-install/bin/lmp"
LMP_KOKKOS_DEFAULT = "/home/arz2/lammps-install-kokkos/bin/lmp"
CONDA_ACTIVATE = "source ~/miniforge3/etc/profile.d/conda.sh; conda activate mol-builder"

# Execution arms — how LAMMPS offloads work to the GPU. A0 is the current production
# behavior (GPU package: pair on GPU; bonded/kspace/neigh on CPU). A1/A2 are the
# no-rebuild "free wins" (move neighbor build and/or PPPM onto the idle GPU). A3 is the
# KOKKOS full-offload (pair+bonded+kspace+neigh all on GPU) and needs the KOKKOS binary.
#   engine  : "gpu" (GPU package) | "kokkos"
#   neigh   : GPU-package neighbor-build location ("no"=CPU, "yes"=GPU); ignored for kokkos
#   kspace  : "pppm" (CPU) | "pppm/gpu" (GPU pkg) | "kk" (kokkos -sf rewrites the deck)
ARMS: dict[str, dict] = {
    "A0": {"engine": "gpu",    "neigh": "no",  "kspace": "pppm",
           "desc": "baseline: GPU pkg, pppm-CPU, neigh-no"},
    "A1": {"engine": "gpu",    "neigh": "yes", "kspace": "pppm",
           "desc": "GPU pkg + neigh-yes"},
    "A2": {"engine": "gpu",    "neigh": "yes", "kspace": "pppm/gpu",
           "desc": "GPU pkg + pppm/gpu + neigh-yes"},
    "A3": {"engine": "kokkos", "neigh": None,  "kspace": "kk",
           "desc": "KOKKOS full-offload (-sf kk -pk kokkos)"},
}
# Resolve mpirun to an absolute path so the launched subshell does not depend on its
# own PATH (user-space Open MPI is often only on an interactive-login PATH). Override
# with LAMBDA_MPIRUN if mpirun lives somewhere non-standard.
MPIRUN = os.environ.get("LAMBDA_MPIRUN") or shutil.which("mpirun") or "mpirun"
GPU_IDLE_UTIL = 5                     # % util at-or-below = idle
GPU_IDLE_MEM_MB = 800                 # MB used at-or-below = idle (no run mid-setup)


PHYS_CORES = detect_phys_cores()


def _build_configs(phys: int) -> list[dict]:
    """Config matrix scaled to the box: gpu = number of *physical* GPUs; mpi = rank
    count (each rank ≈ 1 core). cpu/gpu1 rank ladders are capped at the physical-core
    count so a 32-core box surfaces its mpi=32 optimum and an 18-core box does not."""
    cfgs: list[dict] = []
    for m in (4, 8, 16, 32, 64):
        if m <= phys:
            cfgs.append({"name": f"cpu_mpi{m}", "mpi": m, "gpu": 0})
    for m in (1, 2, 4, 8, 16):
        if m <= phys:
            cfgs.append({"name": f"gpu1_mpi{m}", "mpi": m, "gpu": 1})
    cfgs.append({"name": "gpu2_mpi2", "mpi": 2, "gpu": 2})
    cfgs.append({"name": "gpu4_mpi4", "mpi": 4, "gpu": 4})
    return cfgs


# config matrix — gpu = number of *physical* GPUs; mpi = rank count (each rank = 1 core)
DEFAULT_CONFIGS = _build_configs(PHYS_CORES)

SECTION_RE = re.compile(
    r"^(Pair|Bond|Angle|Dihedral|Improper|Kspace|Neigh|Comm|Output|Modify|Other)\s*\|"
)


# --------------------------------------------------------------------------
# Hardware probing (politeness)
# --------------------------------------------------------------------------
def gpus_with_compute_procs() -> set[int]:
    """GPU indices that currently host a compute process from ANY user. Shared-box
    politeness: even a low-util GPU is off-limits if someone else is running on it."""
    try:
        uuid_to_idx: dict[str, int] = {}
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15).stdout
        for ln in out.strip().splitlines():
            parts = [p.strip() for p in ln.split(",")]
            if len(parts) >= 2:
                uuid_to_idx[parts[1]] = int(parts[0])
        apps = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=gpu_uuid", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15).stdout
        return {uuid_to_idx[u.strip()] for u in apps.strip().splitlines()
                if u.strip() in uuid_to_idx}
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return set()


def idle_gpu_ids() -> list[int]:
    busy = gpus_with_compute_procs()
    return [g["index"] for g in gpu_status()
            if g["util"] <= GPU_IDLE_UTIL and g["mem_used_mb"] <= GPU_IDLE_MEM_MB
            and g["index"] not in busy]


def busy_cores(phys: int) -> int:
    """Estimate cores currently busy with ANY work (not just lmp), by sampling the
    aggregate /proc/stat CPU line over ~0.7 s. Used to gate politely against other
    users' non-lmp load, which the lmp-only rank count cannot see."""
    def snap() -> tuple[int, int]:
        with open("/proc/stat") as f:
            v = list(map(int, f.readline().split()[1:]))
        idle = v[3] + (v[4] if len(v) > 4 else 0)   # idle + iowait
        return idle, sum(v)
    try:
        i0, t0 = snap()
        time.sleep(0.7)
        i1, t1 = snap()
        dt = t1 - t0
        if dt <= 0:
            return 0
        return int(round((1.0 - (i1 - i0) / dt) * phys))
    except Exception:
        return 0


def kokkos_binary_ok(lmp_path: str) -> bool:
    """True iff `lmp_path` exists and is a KOKKOS-enabled LAMMPS build. A fresh clone
    often has only the base binary, so the kokkos engine (arm A3 / engine=kokkos) must
    degrade gracefully rather than crash. Smoke test: the binary's `-h` package list
    names KOKKOS (cheap, no GPU needed)."""
    if not lmp_path or not Path(lmp_path).exists():
        return False
    try:
        out = subprocess.run([lmp_path, "-h"], capture_output=True, text=True,
                             timeout=30).stdout
        return "KOKKOS" in out.upper()
    except (OSError, subprocess.SubprocessError):
        return False


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
        "DUMP_FREQ": max(steps * 10, 1),  # >> run length = effectively no traj I/O; >=1 so a
                                          # run-0 parity deck (steps=0) is valid (dump freq 0 errors)
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
def _mpi_lib_export() -> str:
    """Prepend the Open MPI prefix lib dir (derived from the absolute mpirun path) to
    LD_LIBRARY_PATH, so a user-space MPI resolves even when the caller's environment
    doesn't already export it (e.g. agent/slash-command runs)."""
    if not os.path.isabs(MPIRUN):
        return ""
    libdir = Path(MPIRUN).resolve().parents[1] / "lib"
    if libdir.is_dir():
        return f"export LD_LIBRARY_PATH={shlex.quote(str(libdir))}:$LD_LIBRARY_PATH; "
    return ""


def build_cmd(lmp: str, in_file: Path, mpi: int, gpu_ids: list[int],
              arm: dict | None = None) -> tuple[str, dict]:
    """Return (shell command string, env-note). GPU offload via -sf/-pk flags, selected
    by the execution arm (defaults to A0 = GPU package, neigh on CPU)."""
    arm = arm or ARMS["A0"]
    env_prefix = ""
    gpu_flags = ""
    if gpu_ids:
        env_prefix = f"CUDA_VISIBLE_DEVICES={','.join(map(str, gpu_ids))} "
        n = len(gpu_ids)
        if arm["engine"] == "kokkos":
            gpu_flags = f" -k on g {n} -sf kk -pk kokkos"
        else:                                          # GPU package
            gpu_flags = f" -sf gpu -pk gpu {n} neigh {arm['neigh']}"
    inner = (f"{env_prefix}{shlex.quote(MPIRUN)} -np {mpi} {shlex.quote(lmp)}{gpu_flags} "
             f"-in {shlex.quote(str(in_file))}")
    cmd = f"bash -c {shlex.quote(CONDA_ACTIVATE + '; ' + _mpi_lib_export() + inner)}"
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
               gpu_ids: list[int], timeout_s: int, arm: dict | None = None) -> dict:
    rundir = work / cfg["name"]
    rundir.mkdir(parents=True, exist_ok=True)
    # fresh log path per config
    cfg_in = rundir / "bench.in"
    text = in_file.read_text()
    text = re.sub(r"^log\s+\S+.*$", f"log {rundir/'bench.log'} ", text,
                  count=1, flags=re.M)
    cfg_in.write_text(text)

    cmd, note = build_cmd(lmp, cfg_in, cfg["mpi"], gpu_ids, arm)
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
    ap.add_argument("--lmp-kokkos", default=os.environ.get("LAMBDA_LAMMPS_KOKKOS", LMP_KOKKOS_DEFAULT),
                    help="KOKKOS-enabled lmp binary (used when --arm A3)")
    ap.add_argument("--arm", choices=list(ARMS), default="A0",
                    help="execution arm: A0=baseline (default), A1=neigh-yes, "
                         "A2=pppm/gpu+neigh-yes, A3=KOKKOS full-offload")
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

    arm = ARMS[args.arm]
    lmp = args.lmp_kokkos if arm["engine"] == "kokkos" else args.lmp
    if arm["engine"] == "kokkos" and not kokkos_binary_ok(lmp):
        print(f"ERROR: arm {args.arm} needs a KOKKOS-enabled lmp but none usable at {lmp}. "
              f"Set LAMBDA_LAMMPS_KOKKOS to a KOKKOS build, or pick a GPU-package arm "
              f"(A0/A1/A2).", file=sys.stderr)
        return 2
    base_label = args.label or Path(data).parent.name or "cell"
    label = f"{base_label}__{args.arm}"
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

    # Derive the per-arm deck: A2 moves PPPM onto the GPU (kspace_style pppm -> pppm/gpu);
    # A3 (KOKKOS) keeps plain pppm and lets `-sf kk` rewrite every style at runtime.
    arm_in = master_in
    if arm["kspace"] == "pppm/gpu":
        new_text, nsub = re.subn(r"(kspace_style\s+)pppm\b", r"\1pppm/gpu",
                                 master_in.read_text())
        arm_in = work / "deck_arm.in"
        arm_in.write_text(new_text)
        if nsub == 0:
            print("   note:   no kspace_style pppm line (no-kspace cell) — A2 == A1 here")

    print(f"== benchmark {label} ==")
    print(f"   data:   {data}")
    print(f"   deck:   {mode}")
    print(f"   arm:    {args.arm} — {arm['desc']}   lmp: {lmp}")
    print(f"   steps:  {args.steps}   work: {work}\n")

    configs = DEFAULT_CONFIGS
    if args.only:
        want = {s.strip() for s in args.only.split(",")}
        configs = [c for c in configs if c["name"] in want]

    results = []
    for cfg in configs:
        # politeness gating — account for ALL load, not just lmp ranks
        idle = idle_gpu_ids()
        live = live_lmp_ranks(args.lmp)
        load = 0 if args.allow_busy else busy_cores(args.max_cores)
        spare = args.max_cores - max(live, load)
        gpu_ids: list[int] = []
        skip = None
        if not args.allow_busy:
            if cfg["mpi"] > spare:
                skip = f"needs {cfg['mpi']} cores, only {spare} spare (live lmp={live}, busy~{load})"
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
        r = run_config(cfg, arm_in, lmp, work, gpu_ids, args.timeout, arm)
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
        "arm": args.arm, "arm_desc": arm["desc"],
        "host": {"phys_cores": args.max_cores, "lmp": lmp},
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
