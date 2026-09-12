#!/usr/bin/env python3
"""
hardware_runtime.py — what this box has, and who currently has it.

Two halves that were always one question and could not stop importing each other:

  PROBES      what box is this, how many physical cores and GPUs does it have, and does it
              match the hardware_policy.host fingerprint the per-FF benchmark defaults were
              measured on. Single source of truth for probes several scripts each used to do
              their own way and drift on (this file's own ledger once hardcoded 18 cores after
              the box moved to 32).
  LEDGER      the atomic GPU claim/release ledger, and the CLI over it. This box is shared by
              many concurrent screening runs; pinning every run to GPU 0 (the documented
              default) and oversubscribing the CPU is the main throughput killer.

Merged 2026-09-02 (hw_common.py + pick_gpu.py). pick_gpu imported hw_common for the two probes
it is built on, and every "is a GPU free" answer needs both halves anyway: nvidia-smi says idle,
the ledger says unclaimed.

NOT to be confused with select_hardware.py, which is the other side of the clock: that one is
PLANNING-time policy (D-08 selection and the GPU-hours cost model that prices it, from
decision_policy.json), this one is RUN-time fact (what nvidia-smi and lscpu say right now, and
which runs hold claims). select_hardware imports host_matches() from here; nothing flows back.

Named hardware_runtime.py rather than hardware.py deliberately: the repo has a top-level
hardware/ directory, and a module of the same name next to it resolves by sys.path order --
the exact namespace-package shadowing removed when emc_fields.py met emc_fields/.

Allocation policy (also in hardware/HARDWARE.md):
  - S(mpi_ranks over all concurrent runs) <= phys_cores.
  - At most one GPU-heavy run per physical GPU.
  - A GPU is free if it is ~idle in nvidia-smi AND not claimed in the ledger.

Commands (prepend --json to any for one structured JSON object on stdout):
  hardware_runtime.py [--json] status                       # GPUs, util, claims, spare cores
  hardware_runtime.py [--json] claim --run NAME [--need 1]  # print free gpu id(s); record claim
  hardware_runtime.py [--json] release --run NAME           # drop this run's claim(s)
  hardware_runtime.py [--json] budget --mpi N               # exit 0 if N ranks fit, else 1

--json is opt-in: the default `claim` stdout stays bare comma-joined ids (the orchestrator
parses it) and `budget`'s 0/1 exit code is unchanged.

The physical-core budget is read from guides/polymer_rules.json:hardware_policy.host.phys_cores
(the calibrated source of truth, kept in sync by calibrate_hardware.py), falling back to a
direct lscpu/os.cpu_count() probe -- so this scales to whatever box the clone runs on.

stdlib only -- importable by any orchestration/scripts/<x>.py (orchestration/scripts/ is on
sys.path[0] when run as a CLI; benchmark_hardware.py / calibrate_hardware.py also insert
orchestration/scripts/ explicitly).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Optional
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules_common import hardware_policy  # noqa: E402


# ==============================================================================
# PROBES — live host and GPU facts (was hw_common.py)
# ==============================================================================

def _phys_cores_probe() -> int:
    """Probe the box's physical-core count directly (lscpu, then os.cpu_count()),
    WITHOUT consulting hardware_policy. Used by host_matches(), which must compare the
    live machine against the saved fingerprint — trusting the policy value there would
    make phys_cores always "match" itself."""
    try:
        out = subprocess.run(["lscpu"], capture_output=True, text=True, timeout=10).stdout
        cps = sockets = None
        for ln in out.splitlines():
            if ln.startswith("Core(s) per socket:"):
                cps = int(ln.split(":")[1])
            elif ln.startswith("Socket(s):"):
                sockets = int(ln.split(":")[1])
        if cps and sockets:
            return cps * sockets
    except Exception:
        pass
    return os.cpu_count() or 8


def detect_phys_cores() -> int:
    """Physical-core count for this box. Prefer the calibrated hardware_policy host
    value, fall back to a direct probe. Replaces the old hardcoded 18 so callers scale
    to whatever box this clone runs on."""
    try:
        n = int(hardware_policy()["host"]["phys_cores"])
        if n > 0:
            return n
    except Exception:
        pass
    return _phys_cores_probe()


def gpu_status() -> list[dict]:
    """Return [{index, util, mem_used_mb, mem_total_mb, mem_free_mb}] from nvidia-smi, or []."""
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=index,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4:
            used, total = int(parts[2]), int(parts[3])
            gpus.append({"index": int(parts[0]), "util": int(parts[1]),
                         "mem_used_mb": used, "mem_total_mb": total,
                         "mem_free_mb": max(0, total - used)})
    return gpus


def gpu_model() -> str:
    """The first GPU's marketing name from nvidia-smi (e.g. 'NVIDIA A800 40GB Active'),
    or 'unknown'. The model + count fingerprints the box for host-match gating."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=15).stdout
        names = [l.strip() for l in out.strip().splitlines() if l.strip()]
        if names:
            return names[0]
    except Exception:
        pass
    return "unknown"


def live_host() -> dict:
    """Best-effort fingerprint of the box this is running on: GPU count + model + a
    DIRECT physical-core probe (not the policy echo). Shape matches hardware_policy.host
    so host_matches() and calibrate_hardware can compare/write the same dict."""
    return {"gpus": len(gpu_status()), "gpu_model": gpu_model(),
            "phys_cores": _phys_cores_probe()}


def _gpu_model_matches(live_model: str, saved_model: str) -> bool:
    """Loose GPU-model comparison: nvidia-smi's bare name (e.g. 'Quadro RTX 6000') and
    hardware_policy.host's saved name (e.g. 'Quadro RTX 6000 24GB') format the same card
    differently -- same principle as select_hardware.py's _host_matches_measured_on() token
    match. Match if either string is a substring of the other."""
    live_model = (live_model or "").strip()
    saved_model = (saved_model or "").strip()
    if not live_model or not saved_model:
        return False
    return live_model in saved_model or saved_model in live_model


def host_matches(rules: dict | None = None) -> bool:
    """True iff the live box matches hardware_policy.host (GPU model + count + phys cores).
    Used to decide whether the benchmarked per-FF defaults apply here or the user should
    re-run /calibrate-hardware. Missing/empty saved host → False (never benchmarked here)."""
    saved = hardware_policy(rules).get("host") or {}
    if not saved:
        return False
    live = live_host()
    return (_gpu_model_matches(live["gpu_model"], saved.get("gpu_model", ""))
            and live["gpus"] == saved.get("gpus")
            and live["phys_cores"] == saved.get("phys_cores"))


# ==============================================================================
# LEDGER — GPU claims and the CPU-rank budget (was pick_gpu.py)
# ==============================================================================

LEDGER = Path("/tmp/polyjarvis/gpu_locks")
PHYS_CORES = detect_phys_cores()
IDLE_UTIL = 5          # %
IDLE_MEM_MB = 800
MIN_FREE_MEM_MB = 8000
"""How much GPU memory a run needs to be able to claim a card.

This replaced an absolute `mem_used_mb <= IDLE_MEM_MB` test, which asked the wrong question.
800 MB was calibrated on a box where a neighbour's idle CUDA context was ~750 MB, so it read
as "nobody else is here." On 2026-09-11 a neighbour's 4-GPU training job grew its per-card
allocation from 754 MB to 5.8 GB and every card crossed the line at once -- on 40 GB A800s
with 34 GB still free. free_gpus() went empty, and because gpu_claim is scoped to each
SUBMISSION rather than to a run, PE_1 released its card at the equilibration->cooling boundary
and then could not reclaim it: "GPU claim failed (insufficient_free_gpus, available: [])" on a
box that was 85% idle by memory. Every concurrent run was one stage boundary from the same
failure.

Whether someone else is COMPUTING here is what IDLE_UTIL measures, and it measures it well.
Whether we can FIT is a question about free memory on this card, not about a constant that
predates the card. IDLE_MEM_MB is kept for callers that still want the strict "pristine card"
test (hardware/benchmark_hardware.py's politeness probe is deliberately stricter than this)."""
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
        # Free = nobody is computing here (util) AND our run fits (free memory). See
        # MIN_FREE_MEM_MB: an absolute cap on USED memory fails on a big card the moment a
        # neighbour parks a context on it, however much room is actually left.
        fits = g.get("mem_free_mb")
        if fits is None:                       # pre-mem_total probe result; fall back
            fits = max(0, g.get("mem_total_mb", 0) - g["mem_used_mb"])
        if g["util"] <= IDLE_UTIL and fits >= MIN_FREE_MEM_MB:
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


CLAIM_POLL_S = 15.0
"""How often a waiting claim re-checks. See _claim_free."""

DEFAULT_CLAIM_WAIT_S = 1800.0
"""Patience belongs to the CLAIM, not to whoever calls it.

run_campaign passes --wait-s explicitly, but a campaign already running has run_campaign.py
loaded in memory and would keep calling the old argument-free command -- while
hardware_runtime.py, which _pick_gpu invokes as a FRESH SUBPROCESS every time, is picked up
immediately. On 2026-09-11 that difference was three live runs, hours of GPU each, still one
stage boundary from PE_1's fate. Defaulting here fixes them mid-flight. Pass --wait-s 0 to
check availability by hand without blocking."""


def _claim_free(run: str, need: int, wait_s: float) -> tuple[Optional[list[int]], float]:
    """Claim `need` GPUs atomically, waiting up to `wait_s` for them to come free.

    Two defects this closes, both of which cost a real campaign.

    WAITING. gpu_claim is scoped to each SUBMISSION, so a run releases its GPU at every stage
    boundary and re-races for one. On a box shared with an un-ledgered tenant that race is
    lost intermittently -- and a lost race was fatal, because workflow_engine's
    _transient_retry_blocked declines to retry when no GPU is free and declining ESCALATES to
    the recovery agent. PE_1 (2026-09-11) spent BOTH of its two agent calls on lost claim
    races at the cooling and thermal boundaries and terminated escalation_required with its
    build, equilibration and cooling all accepted. A neighbour's 30-second utilisation spike
    is a reason to wait, not to burn a scarce decision that a scientific failure will need.

    ATOMICITY. The old path read free_gpus() and then wrote the lock with write_text, so two
    processes that polled together both "claimed" the same card, last writer winning the
    ledger and both runs landing on one GPU -- the measured worst case on this hardware
    (~8x slower aggregate for two PPPM jobs sharing a card). O_EXCL makes the lock file
    itself the arbiter: whoever creates it owns the GPU, and a loser simply tries the next.
    """
    deadline = time.monotonic() + max(0.0, wait_s)
    started = time.monotonic()
    while True:
        got: list[int] = []
        for gid in free_gpus():
            try:
                fd = os.open(str(LEDGER / f"gpu{gid}.lock"),
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                continue                      # someone claimed it between poll and open
            with os.fdopen(fd, "w") as fh:
                json.dump({"run": run, "pid": os.getppid(),
                           "ts": time.strftime("%Y-%m-%dT%H:%M")}, fh)
            got.append(gid)
            if len(got) == need:
                return got, time.monotonic() - started
        for gid in got:                       # partial set is useless -- give it back
            (LEDGER / f"gpu{gid}.lock").unlink(missing_ok=True)
        if time.monotonic() >= deadline:
            return None, time.monotonic() - started
        time.sleep(min(CLAIM_POLL_S, max(0.0, deadline - time.monotonic())))


def cmd_claim(run: str, need: int, js: bool = False, adopt: str = None,
              wait_s: float = 0.0) -> int:
    LEDGER.mkdir(parents=True, exist_ok=True)
    if adopt:
        # ADOPTION, not allocation. The caller is reattaching to a detached chain that is ALREADY
        # running on these GPUs -- they are busy precisely because this run's own work is on them,
        # so free_gpus() correctly refuses to hand them out and would send the reattaching process
        # to a different GPU while the chain kept using this one. The ledger would then name a GPU
        # doing nothing and stay silent about the one under load. Recording where the work
        # actually is is the whole point of the ledger.
        picked = [int(g) for g in str(adopt).split(",") if str(g).strip() != ""]
        ts = time.strftime("%Y-%m-%dT%H:%M")
        for gid in picked:
            (LEDGER / f"gpu{gid}.lock").write_text(
                json.dumps({"run": run, "pid": os.getppid(), "ts": ts, "adopted": True}))
        if js:
            print(json.dumps({"run": run, "claimed": picked, "need": len(picked),
                              "adopted": True}))
        else:
            print(",".join(map(str, picked)))
        return 0
    picked, waited = _claim_free(run, need, wait_s)
    if picked is None:
        free = free_gpus()
        if js:
            print(json.dumps({"error": "insufficient_free_gpus", "need": need,
                              "available": free, "waited_s": waited}))
        else:
            print(f"ERROR: need {need} free GPU(s), available: {free} "
                  f"(waited {waited:.0f}s)", file=sys.stderr)
        return 1
    ts = time.strftime("%Y-%m-%dT%H:%M")
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
    c.add_argument("--wait-s", type=float, default=DEFAULT_CLAIM_WAIT_S,
                   help="Wait up to this many seconds for a GPU instead of failing at once "
                        f"(default {DEFAULT_CLAIM_WAIT_S:.0f}s). A lost claim race at a stage "
                        "boundary is transient; treating it as fatal escalates to the recovery "
                        "agent and spends one of only two calls (see _claim_free). Pass 0 for "
                        "the old fail-fast behaviour, e.g. when checking availability by hand.")
    c.add_argument("--adopt", default=None,
                   help="Comma-separated GPU ids a detached chain is already running on. Records "
                        "the claim on exactly those, bypassing the idle check -- for reattach.")
    r = sub.add_parser("release"); r.add_argument("--run", required=True)
    b = sub.add_parser("budget"); b.add_argument("--mpi", type=int, required=True)
    a = ap.parse_args()
    if a.cmd == "status":  return cmd_status(a.json)
    if a.cmd == "claim":   return cmd_claim(a.run, a.need, a.json, a.adopt, a.wait_s)
    if a.cmd == "release": return cmd_release(a.run, a.json)
    if a.cmd == "budget":  return cmd_budget(a.mpi, a.json)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
