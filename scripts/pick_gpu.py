#!/usr/bin/env python3
"""
pick_gpu.py — GPU allocation helper for concurrent PolyJarvis runs.

The workstation has 4× Quadro RTX 6000 + one 18-physical-core CPU shared by many
concurrent screening runs. Pinning every run to GPU 0 (the documented default) and
oversubscribing the CPU is the main throughput killer. This helper hands out a
non-colliding GPU and reports the CPU-core budget, backed by a tiny file ledger.

Allocation policy (also in guides/HARDWARE.md):
  - Σ(mpi_ranks over all concurrent runs) ≤ 18 physical cores.
  - At most one GPU-heavy run per physical GPU.
  - A GPU is free if it is ~idle in nvidia-smi AND not claimed in the ledger.

Commands:
  pick_gpu.py status                       # GPUs, util, claims, spare cores
  pick_gpu.py claim --run NAME [--need 1]  # print free gpu id(s); record claim
  pick_gpu.py release --run NAME           # drop this run's claim(s)
  pick_gpu.py budget --mpi N               # exit 0 if N ranks fit in spare cores, else 1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

LEDGER = Path("/tmp/polyjarvis/gpu_locks")
PHYS_CORES = 18
IDLE_UTIL = 5          # %
IDLE_MEM_MB = 800
STALE_S = 60 * 60 * 36  # prune claims older than 36 h


def gpu_status() -> list[dict]:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 3:
            gpus.append({"index": int(p[0]), "util": int(p[1]),
                         "mem_used_mb": int(p[2])})
    return gpus


def live_ranks() -> int:
    try:
        return int(subprocess.run(["pgrep", "-xc", "lmp"],
                   capture_output=True, text=True, timeout=10).stdout.strip() or 0)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return 0


def _prune() -> None:
    if not LEDGER.exists():
        return
    now = time.time()
    for f in LEDGER.glob("gpu*.lock"):
        try:
            if now - f.stat().st_mtime > STALE_S:
                f.unlink()
        except OSError:
            pass


def claims() -> dict[int, dict]:
    _prune()
    out: dict[int, dict] = {}
    if not LEDGER.exists():
        return out
    for f in sorted(LEDGER.glob("gpu*.lock")):
        try:
            d = json.loads(f.read_text())
            out[int(f.stem.replace("gpu", ""))] = d
        except (ValueError, OSError):
            pass
    return out


def free_gpus() -> list[int]:
    claimed = claims()
    free = []
    for g in gpu_status():
        if g["index"] in claimed:
            continue
        if g["util"] <= IDLE_UTIL and g["mem_used_mb"] <= IDLE_MEM_MB:
            free.append(g["index"])
    return free


def cmd_status() -> int:
    gpus = gpu_status()
    cl = claims()
    print(f"{'GPU':<4}{'util%':<7}{'mem(MB)':<9}{'claim'}")
    for g in gpus:
        c = cl.get(g["index"], {})
        tag = f"{c.get('run','-')} ({c.get('ts','')})" if c else "-"
        print(f"{g['index']:<4}{g['util']:<7}{g['mem_used_mb']:<9}{tag}")
    lr = live_ranks()
    print(f"\nlive lmp ranks: {lr} / {PHYS_CORES} phys cores  "
          f"(spare: {PHYS_CORES - lr})")
    print(f"free GPUs (idle & unclaimed): {free_gpus()}")
    return 0


def cmd_claim(run: str, need: int) -> int:
    LEDGER.mkdir(parents=True, exist_ok=True)
    free = free_gpus()
    if len(free) < need:
        print(f"ERROR: need {need} free GPU(s), available: {free}", file=sys.stderr)
        return 1
    picked = free[:need]
    ts = time.strftime("%Y-%m-%dT%H:%M")
    for gid in picked:
        (LEDGER / f"gpu{gid}.lock").write_text(
            json.dumps({"run": run, "pid": os.getppid(), "ts": ts}))
    print(",".join(map(str, picked)))
    return 0


def cmd_release(run: str) -> int:
    for gid, c in claims().items():
        if c.get("run") == run:
            try:
                (LEDGER / f"gpu{gid}.lock").unlink()
            except OSError:
                pass
    return 0


def cmd_budget(mpi: int) -> int:
    spare = PHYS_CORES - live_ranks()
    fits = mpi <= spare
    print(f"mpi={mpi} spare_cores={spare} -> {'FITS' if fits else 'OVERSUBSCRIBED'}")
    return 0 if fits else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    c = sub.add_parser("claim"); c.add_argument("--run", required=True); c.add_argument("--need", type=int, default=1)
    r = sub.add_parser("release"); r.add_argument("--run", required=True)
    b = sub.add_parser("budget"); b.add_argument("--mpi", type=int, required=True)
    a = ap.parse_args()
    if a.cmd == "status":  return cmd_status()
    if a.cmd == "claim":   return cmd_claim(a.run, a.need)
    if a.cmd == "release": return cmd_release(a.run)
    if a.cmd == "budget":  return cmd_budget(a.mpi)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
