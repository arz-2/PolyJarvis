#!/usr/bin/env python3
"""Drives RadonPy's own AutoMD workflow (0_qm -> 1_eq -> 4_tg) for one polymer, independent
of PolyJarvis's orchestration.

This is the "native RadonPy arm" of the PolyJarvis-vs-RadonPy benchmark. It shells into the
dedicated `radonpy` conda env and runs RadonPy's own AutoMD_scripts, unmodified, with only
the env vars needed to point them at this polymer and this host. Everything else is left at
RadonPy's stock default: GAFF2_mod, RESP charges, 1000 atoms x 10 chains, 300 K, EQ21step,
RadonPy_RetryEQ=0, and 4_tg.py's own rule of computing Tg only when check_eq passed.

History: RadonPy 1.0b2 moved sample_script/{qm,eq}.py to AutoMD_scripts/{0_qm,1_eq}.py and
added 4_tg.py; this runner used to call the removed paths and never ran Tg. The terminal
group is now built by 0_qm.py itself (RadonPy_Do_Ter=True), which replaces the hand-built
ter_CH3.pickle this runner used to write.

Deviations from stock, each for host fairness and each recorded in timestamps.json:
  * PYTHONPATH -> the RadonPy checkout, so the 1.0b2 scripts import the 1.0b2 library they
    were written against (the conda env's site-packages is 1.0b1).
  * RadonPy_MPI / RadonPy_Conf_MM_MPI pinned (stock default is os.cpu_count(), i.e. LOGICAL
    threads -- 36 ranks on 18 physical cores, which OpenMPI refuses without oversubscribing).
  * --gpus N sets RadonPy_GPU=N (stock 0 = CPU only). The GPUs are claimed through
    orchestration/scripts/hardware_runtime.py and exposed via CUDA_VISIBLE_DEVICES, so the arm
    never lands on a card a PolyJarvis campaign holds.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from config import (LAMMPS_EXEC, RADONPY_ENV_PYTHON, RADONPY_SOURCE_ROOT, DATA_ROOT,
                    PHYSICAL_CORES, REPO_ROOT)

AUTOMD_DIR = RADONPY_SOURCE_ROOT / "AutoMD_scripts"
PHASES = {"qm": "0_qm.py", "eq": "1_eq.py", "tg": "4_tg.py"}
HW = REPO_ROOT / "orchestration" / "scripts" / "hardware_runtime.py"
LEDGER = Path("/tmp/polyjarvis/gpu_locks")
HEARTBEAT_S = 3600   # hardware_runtime prunes claims whose lock file is older than 36 h


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_phase(phase: str, cmd: list[str], cwd: Path, env: dict, log_path: Path) -> dict:
    started_at = _now()
    with open(log_path, "w") as log_f:
        proc = subprocess.run(cmd, cwd=str(cwd), env=env, stdout=log_f, stderr=subprocess.STDOUT)
    return {"phase": phase, "started_at": started_at, "finished_at": _now(),
            "returncode": proc.returncode, "log": str(log_path)}


def _claim_gpus(run: str, need: int) -> list[int]:
    r = subprocess.run([sys.executable, str(HW), "claim", "--run", run, "--need", str(need)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"GPU claim failed: {(r.stderr or r.stdout).strip()}")
    return [int(x) for x in r.stdout.strip().split(",")]


def _release_gpus(run: str) -> None:
    subprocess.run([sys.executable, str(HW), "release", "--run", run], capture_output=True)


def _heartbeat(gpus: list[int], stop: threading.Event) -> None:
    while not stop.wait(HEARTBEAT_S):
        for gid in gpus:
            try:
                os.utime(LEDGER / f"gpu{gid}.lock")
            except OSError:
                pass


def run_radonpy_arm(polymer_name: str, smiles: str, harness_root: Path | None = None,
                    ter_smiles: str = "*C", gpus: int = 0, mpi: int = PHYSICAL_CORES,
                    phases: tuple[str, ...] = ("qm", "eq", "tg")) -> dict:
    harness_root = harness_root or (DATA_ROOT / polymer_name / "radonpy")
    harness_root.mkdir(parents=True, exist_ok=True)
    work_dir = harness_root / polymer_name  # RadonPy's own ./<DBID> convention

    for path, what in ((RADONPY_ENV_PYTHON, "RadonPy conda env python"),
                       (LAMMPS_EXEC, "LAMMPS binary"), (AUTOMD_DIR / "0_qm.py", "AutoMD scripts")):
        if not path.exists():
            raise RuntimeError(f"{what} not found: {path}")

    env = os.environ.copy()
    env.update({
        "LAMMPS_EXEC": str(LAMMPS_EXEC),
        "PYTHONPATH": str(RADONPY_SOURCE_ROOT),
        "RadonPy_DBID": polymer_name,
        "RadonPy_SMILES": smiles,
        "RadonPy_SMILES_TER": ter_smiles,
        "RadonPy_Do_Ter": "True",
        "RadonPy_MPI": str(mpi),
        "RadonPy_Conf_MM_MPI": str(mpi),
        "RadonPy_GPU": str(gpus),
    })
    env.setdefault("OPAL_PREFIX", "/usr")

    run_tag = f"RADONPY_{polymer_name}"
    claimed: list[int] = []
    stop = threading.Event()
    record = {"polymer": polymer_name, "smiles": smiles, "status": "running", "error": None,
              "work_dir": str(work_dir), "phases": [],
              "deviations_from_stock": {"PYTHONPATH": str(RADONPY_SOURCE_ROOT),
                                        "RadonPy_MPI": mpi, "RadonPy_GPU": gpus}}
    ts_path = harness_root / "timestamps.json"
    try:
        if gpus > 0 and set(phases) & {"eq", "tg"}:
            claimed = _claim_gpus(run_tag, gpus)
            env["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, claimed))
            record["gpus_claimed"] = claimed
            threading.Thread(target=_heartbeat, args=(claimed, stop), daemon=True).start()
        for phase in phases:
            record["phases"].append(_run_phase(
                phase, [str(RADONPY_ENV_PYTHON), str(AUTOMD_DIR / PHASES[phase])],
                cwd=harness_root, env=env, log_path=harness_root / f"{phase}.log"))
            ts_path.write_text(json.dumps(record, indent=2))
            if record["phases"][-1]["returncode"] != 0:
                raise RuntimeError(f"{PHASES[phase]} failed "
                                   f"(rc={record['phases'][-1]['returncode']}); see {phase}.log")
        record["status"] = "complete"
    except Exception as exc:  # noqa: BLE001 - this runner's job is to record the failure
        record["status"] = "failed"
        record["error"] = str(exc)
    finally:
        stop.set()
        if claimed:
            _release_gpus(run_tag)
    ts_path.write_text(json.dumps(record, indent=2))
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--polymer", required=True)
    parser.add_argument("--smiles", required=True)
    parser.add_argument("--ter-smiles", default="*C")
    parser.add_argument("--gpus", type=int, default=0, help="stock RadonPy is 0 (CPU only)")
    parser.add_argument("--mpi", type=int, default=PHYSICAL_CORES)
    parser.add_argument("--phases", default="qm,eq,tg")
    args = parser.parse_args()

    result = run_radonpy_arm(args.polymer, args.smiles, ter_smiles=args.ter_smiles,
                             gpus=args.gpus, mpi=args.mpi,
                             phases=tuple(p for p in args.phases.split(",") if p))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "complete" else 1)


if __name__ == "__main__":
    main()
