#!/usr/bin/env python3
"""
pick_gpu.py — GPU allocation helper for concurrent PolyJarvis runs.

This box is shared by many concurrent screening runs. Pinning every run to GPU 0 (the
documented default) and oversubscribing the CPU is the main throughput killer. This helper
hands out a non-colliding GPU and reports the CPU-core budget, backed by a tiny file ledger.

The physical-core budget is read from guides/polymer_rules.json:hardware_policy.host.phys_cores
(the calibrated source of truth, kept in sync by calibrate_hardware.py), falling back to
os.cpu_count() — so this scales to whatever box the clone runs on rather than a hardcoded value.

Allocation policy (also in hardware/HARDWARE.md):
  - Σ(mpi_ranks over all concurrent runs) ≤ phys_cores.
  - At most one GPU-heavy run per physical GPU.
  - A GPU is free if it is ~idle in nvidia-smi AND not claimed in the ledger.

Commands (prepend --json to any for one structured JSON object on stdout):
  pick_gpu.py [--json] status                       # GPUs, util, claims, spare cores
  pick_gpu.py [--json] claim --run NAME [--need 1]  # print free gpu id(s); record claim
  pick_gpu.py [--json] release --run NAME           # drop this run's claim(s)
  pick_gpu.py [--json] budget --mpi N               # exit 0 if N ranks fit in spare cores, else 1

--json is opt-in: the default `claim` stdout stays bare comma-joined ids (the orchestrator
parses it) and `budget`'s 0/1 exit code is unchanged. pick_gpu is the only agent-facing
script that printed prose; the others already emit structured output (make_deterministic_plan
-> JSON, estimate_tg_group_contribution --output json, benchmark_hardware -> benchmark.json,
gen_prompt -> the worker prompt).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hw_common import detect_phys_cores, gpu_status   # shared host/GPU probes (single source of truth)

LEDGER = Path("/tmp/polyjarvis/gpu_locks")
PHYS_CORES = detect_phys_cores()
IDLE_UTIL = 5          # %
IDLE_MEM_MB = 800
STALE_S = 60 * 60 * 36  # prune claims older than 36 h


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


def cmd_status(js: bool = False) -> int:
    gpus = gpu_status()
    cl = claims()
    lr = live_ranks()
    if js:
        rows = [{**g, "claim": cl.get(g["index"], {}).get("run")} for g in gpus]
        print(json.dumps({"phys_cores": PHYS_CORES, "live_ranks": lr,
                          "spare_cores": PHYS_CORES - lr, "gpus": rows,
                          "free_gpus": free_gpus()}))
        return 0
    print(f"{'GPU':<4}{'util%':<7}{'mem(MB)':<9}{'claim'}")
    for g in gpus:
        c = cl.get(g["index"], {})
        tag = f"{c.get('run','-')} ({c.get('ts','')})" if c else "-"
        print(f"{g['index']:<4}{g['util']:<7}{g['mem_used_mb']:<9}{tag}")
    print(f"\nlive lmp ranks: {lr} / {PHYS_CORES} phys cores  "
          f"(spare: {PHYS_CORES - lr})")
    print(f"free GPUs (idle & unclaimed): {free_gpus()}")
    return 0


def cmd_claim(run: str, need: int, js: bool = False) -> int:
    LEDGER.mkdir(parents=True, exist_ok=True)
    free = free_gpus()
    if len(free) < need:
        if js:
            print(json.dumps({"error": "insufficient_free_gpus",
                              "need": need, "available": free}))
        else:
            print(f"ERROR: need {need} free GPU(s), available: {free}", file=sys.stderr)
        return 1
    picked = free[:need]
    ts = time.strftime("%Y-%m-%dT%H:%M")
    for gid in picked:
        (LEDGER / f"gpu{gid}.lock").write_text(
            json.dumps({"run": run, "pid": os.getppid(), "ts": ts}))
    if js:
        print(json.dumps({"run": run, "claimed": picked, "need": need}))
    else:
        print(",".join(map(str, picked)))           # bare ids — parsed by the orchestrator
    return 0


def cmd_release(run: str, js: bool = False) -> int:
    released = []
    for gid, c in claims().items():
        if c.get("run") == run:
            try:
                (LEDGER / f"gpu{gid}.lock").unlink()
                released.append(gid)
            except OSError:
                pass
    if js:
        print(json.dumps({"run": run, "released": sorted(released)}))
    return 0


def cmd_budget(mpi: int, js: bool = False) -> int:
    spare = PHYS_CORES - live_ranks()
    fits = mpi <= spare
    if js:
        print(json.dumps({"mpi": mpi, "spare_cores": spare, "fits": fits}))
    else:
        print(f"mpi={mpi} spare_cores={spare} -> {'FITS' if fits else 'OVERSUBSCRIBED'}")
    return 0 if fits else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true",
                    help="emit one JSON object on stdout instead of human text "
                         "(claim's bare ids and budget's exit code are unchanged)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    c = sub.add_parser("claim"); c.add_argument("--run", required=True); c.add_argument("--need", type=int, default=1)
    r = sub.add_parser("release"); r.add_argument("--run", required=True)
    b = sub.add_parser("budget"); b.add_argument("--mpi", type=int, required=True)
    a = ap.parse_args()
    if a.cmd == "status":  return cmd_status(a.json)
    if a.cmd == "claim":   return cmd_claim(a.run, a.need, a.json)
    if a.cmd == "release": return cmd_release(a.run, a.json)
    if a.cmd == "budget":  return cmd_budget(a.mpi, a.json)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
