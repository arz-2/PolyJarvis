#!/usr/bin/env python3
"""Run every new pressure point of the bm_diagnostics_r2 legs on one claimed GPU, sequentially.

Production path only: each point is one run_bulk_modulus_series call (one pressure, one chain),
the same call do_mechanical makes, loaded through run_campaign's own server-module loader.

Resumable: a point whose log already contains "STAGE COMPLETE" is skipped; a partial point
directory is moved aside to <dir>.partial_<timestamp>, never deleted. One GPU claim is held for
the launcher's whole life (run name bm_diagnostics_r2) and released on exit, so it never races the
campaign runs' per-stage claims. Trajectory dumps are gzipped (pigz, tested) after each point; the
Murnaghan analysis reads logs only.

Usage (background):
  setsid nohup mcp-servers/.venv/bin/python benchmarks/bm_diagnostics_r2/run_legs.py \
      > benchmarks/bm_diagnostics_r2/launcher.log 2>&1 &
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import legs as L  # noqa: E402

REPO = L.REPO
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))
import run_campaign as rc  # noqa: E402

RUN = "bm_diagnostics_r2"
STATUS = HERE / "status.json"
PIDFILE = HERE / "launcher.pid"
MIN_FREE_GB = 20.0
HW = [sys.executable, str(REPO / "orchestration" / "scripts" / "hardware_runtime.py")]


def log(msg: str) -> None:
    print(f"{datetime.now().isoformat(timespec='seconds')} {msg}", flush=True)


def load_status() -> dict:
    try:
        return json.loads(STATUS.read_text())
    except (OSError, json.JSONDecodeError):
        return {"points": {}}


def save_status(st: dict) -> None:
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2) + "\n")
    tmp.replace(STATUS)


def complete(logp: Path) -> bool:
    try:
        with logp.open(errors="replace") as f:
            return any("STAGE COMPLETE" in line for line in f)
    except OSError:
        return False


def release() -> None:
    subprocess.run(HW + ["release", "--run", RUN], capture_output=True, text=True)
    log("GPU claim released")


def claim() -> str:
    out = subprocess.run(HW + ["claim", "--run", RUN, "--need", "1", "--wait-s", "21600"],
                         capture_output=True, text=True)
    for line in reversed(out.stdout.strip().splitlines()):
        line = line.strip()
        if out.returncode == 0 and line and all(part.isdigit() for part in line.split(",")):
            return line                      # plain-mode output: bare comma-separated GPU ids
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(d, dict):
            continue
        if d.get("claimed"):
            return ",".join(str(g) for g in d["claimed"])
        raise SystemExit(f"GPU claim failed: {d}")
    raise SystemExit(f"GPU claim failed: {out.stdout} {out.stderr}")


def gzip_dumps(point_dir: Path) -> None:
    for dump in sorted(point_dir.rglob("*.dump")):
        gz = Path(str(dump) + ".gz")
        if gz.exists():
            continue
        subprocess.run(["pigz", "-k", "-p", "4", str(dump)], check=True)
        subprocess.run(["pigz", "-t", str(gz)], check=True)
        dump.unlink()


def main() -> int:
    PIDFILE.write_text(str(os.getpid()) + "\n")
    digest = hashlib.sha256(L.INPUT_CELL.read_bytes()).hexdigest()
    if digest != L.INPUT_CELL_SHA256:
        raise SystemExit(f"input cell sha256 mismatch: {digest}")

    todo = [pt for pt in L.points_to_simulate() if not complete(L.simulated_log(L.key(*pt), pt[0]))]
    log(f"{len(todo)} points to simulate (est {L.est_gpu_hours(todo):.1f} GPU-h)")
    st = load_status()
    if not todo:
        log("nothing to do")
        return 0

    atexit.register(release)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    gpu_ids = claim()
    log(f"claimed GPU {gpu_ids}")

    lam = rc._load_server_module("lammps_engine_server", rc.LAMMPS_ENGINE_DIR / "server.py",
                                 rc.LAMMPS_ENGINE_DIR, rc._mcp_env("mcp-lammps-engine"))

    for p, damp, steps in todo:
        k = L.key(p, damp, steps)
        point_dir = L.RUN_AREA / "points" / k
        logp = L.simulated_log(k, p)
        if complete(logp):
            continue
        free_gb = shutil.disk_usage(L.RUN_AREA).free / 1e9
        if free_gb < MIN_FREE_GB:
            log(f"STOP: only {free_gb:.1f} GB free (< {MIN_FREE_GB})")
            return 3
        if point_dir.exists():
            aside = point_dir.with_name(f"{point_dir.name}.partial_{datetime.now():%Y%m%d_%H%M%S}")
            point_dir.rename(aside)
            log(f"moved partial {point_dir.name} -> {aside.name}")
        t0 = time.time()
        log(f"submit {k} on GPU {gpu_ids}")
        series = lam.run_bulk_modulus_series(
            data_file=str(L.INPUT_CELL), work_dir=str(point_dir), pressures_atm=[p],
            temp_K=L.TEMP_K, run_name=RUN, gpu_ids=gpu_ids, mpi=L.MPI,
            velocity_seed=L.VELOCITY_SEED, npt_steps=int(steps), dt_fs=L.DT_FS,
            thermo_freq=L.THERMO_FREQ, thermostat_damp_fs=L.T_DAMP_FS, barostat_damp_fs=float(damp),
            use_long_range=True, use_trappe=False, use_pcff=True, use_opls=False, engine=L.ENGINE)
        if series.get("status") == "error":
            log(f"ERROR submitting {k}: {series.get('error')}")
            st["points"][k] = {"status": "submit_error", "error": series.get("error")}
            save_status(st)
            continue
        result = rc.wait_for_run(lam, series["chain_id"], k)
        ok = complete(logp)
        if ok:
            gzip_dumps(point_dir)
        st["points"][k] = {"pressure_atm": p, "barostat_damp_fs": damp, "npt_steps": steps,
                           "chain_id": series["chain_id"], "gpu_ids": gpu_ids,
                           "status": "complete" if ok else f"incomplete:{result.get('status')}",
                           "log": str(logp.relative_to(REPO)),
                           "wall_h": round((time.time() - t0) / 3600, 3),
                           "finished_at": datetime.now(timezone.utc).isoformat()}
        save_status(st)
        log(f"{k}: {st['points'][k]['status']} ({st['points'][k]['wall_h']} h)")
    log("all points processed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
