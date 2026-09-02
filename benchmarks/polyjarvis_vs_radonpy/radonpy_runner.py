#!/usr/bin/env python3
"""Drives RadonPy's own native, stock workflow (QM charge/conformer step + EQ21step
equilibration) for one polymer, independent of PolyJarvis's orchestration.

This is the "native RadonPy arm" of the PolyJarvis-vs-RadonPy benchmark: it shells into
the dedicated `radonpy` conda env and runs RadonPy's own sample_script/{qm,eq}.py,
unmodified, with only the minimum env vars needed to point it at this polymer and at the
LAMMPS binary on this host. Every other RadonPy_* setting is left at its stock default
(RadonPy_RetryEQ=0, RadonPy_Temp=300.0, RadonPy_FF=GAFF2_mod, RadonPy_GPU=0, etc.) so the
run reflects RadonPy's own out-of-the-box behavior, not a tuned comparison.

RadonPy's sample scripts write to a CWD-relative `./<DBID>` directory and expect a
pre-built terminal-group object (`ter1.pickle`) to already exist there — neither qm.py
nor eq.py builds one (confirmed by reading both scripts and RadonPy's own tutorial, which
shows the terminal group built inline via `utils.mol_from_smiles('*C')`, a plain RDKit
call with no QM step). This runner creates that one file before launching qm.py.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import LAMMPS_EXEC, RADONPY_ENV_PYTHON, RADONPY_SAMPLE_SCRIPT_DIR, DATA_ROOT, PHYSICAL_CORES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_phase(phase: str, cmd: list[str], cwd: Path, env: dict, log_path: Path) -> dict:
    started_at = _now()
    with open(log_path, "w") as log_f:
        proc = subprocess.run(cmd, cwd=str(cwd), env=env, stdout=log_f, stderr=subprocess.STDOUT)
    finished_at = _now()
    return {
        "phase": phase,
        "started_at": started_at,
        "finished_at": finished_at,
        "returncode": proc.returncode,
        "log": str(log_path),
    }


def _write_terminal_group(work_dir: Path, python_bin: Path, ter_smiles: str, log_path: Path,
                           ter_id: str = "CH3") -> None:
    """Build ter_<ter_id>.pickle (+.json), named to match eq.py/qm.py's own default
    `RadonPy_TER_ID=CH3` env var (load_terminal_obj looks up `ter_%s.pickle % ter_ID_1`,
    not the ID-less `ter1.pickle` fallback, whenever RadonPy_TER_ID is set -- which it is
    by default).

    RadonPy's own tutorial builds the terminal group with a bare `utils.mol_from_smiles`
    call and nothing else -- but eq.py calls `ff.ff_assign(homopoly, charge=None)` (no
    charge kwarg), which per amber.py's own docstring ("If None, charge assignment is
    skipped") means eq.py relies on every atom already carrying an 'AtomicCharge'
    property before ff_assign ever runs. qm.py provides that for the monomer via
    `qm.assign_charges(...)`; nothing provides it for the terminal group, so a
    tutorial-style bare RDKit terminal crashes downstream at LAMMPS-data-file write time
    with `KeyError: 'AtomicCharge'` (confirmed empirically on this checkout). This
    mirrors qm.py's own RESP charge step onto the terminal group so the assembled chain
    is uniformly charged, with opt=False since a plain RDKit ETKDG conformer is a
    reasonable single-point-RESP input for a small, symmetric terminal group (matching
    the tutorial's own opt=False pattern for charge-only calls)."""
    snippet = (
        "from radonpy.core import utils\n"
        "from radonpy.sim import qm\n"
        f"mol = utils.mol_from_smiles({ter_smiles!r})\n"
        "qm.assign_charges(mol, charge='RESP', opt=False, work_dir='.', tmp_dir='.', "
        f"log_name='ter_{ter_id}')\n"
        f"utils.pickle_dump(mol, 'ter_{ter_id}.pickle')\n"
        f"utils.MolToJSON(mol, 'ter_{ter_id}.json')\n"
    )
    with open(log_path, "w") as log_f:
        proc = subprocess.run(
            [str(python_bin), "-c", snippet],
            cwd=str(work_dir),
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"terminal-group generation failed (rc={proc.returncode}); see {log_path}")


def run_radonpy_arm(polymer_name: str, smiles: str, harness_root: Path | None = None,
                     ter_smiles: str = "*C") -> dict:
    harness_root = harness_root or (DATA_ROOT / polymer_name / "radonpy")
    harness_root.mkdir(parents=True, exist_ok=True)
    work_dir = harness_root / polymer_name  # matches RadonPy's own `./%s % DBID` convention
    work_dir.mkdir(parents=True, exist_ok=True)

    if not RADONPY_ENV_PYTHON.is_file():
        raise RuntimeError(f"RadonPy conda env python not found: {RADONPY_ENV_PYTHON}")
    if not LAMMPS_EXEC.is_file():
        raise RuntimeError(f"LAMMPS binary not found: {LAMMPS_EXEC}")

    env = os.environ.copy()
    env["LAMMPS_EXEC"] = str(LAMMPS_EXEC)
    env["RadonPy_DBID"] = polymer_name
    env["RadonPy_SMILES"] = smiles
    # Everything else (RadonPy_Temp, RadonPy_FF, RadonPy_RetryEQ, RadonPy_GPU, RadonPy_NAtom,
    # RadonPy_NChain, ...) is deliberately left unset -> RadonPy's own defaults.
    #
    # RadonPy_MPI is the one deliberate, explicit deviation from "stock defaults everywhere,"
    # made for wall-time fairness rather than silently left alone: eq.py's own default is
    # `mpi = utils.cpu_count()`, i.e. os.cpu_count() -- LOGICAL thread count (36 on this
    # 18-physical-core/36-thread host), not physical cores. Confirmed empirically: with that
    # default, OpenMPI's own slot detection (physical cores) refuses to start at all
    # ("not enough slots") unless oversubscribed, and running 36 ranks on 18 physical cores
    # is 2x oversubscribed regardless -- a real wall-time penalty from context-switching
    # overhead, not a meaningful accuracy/throughput tradeoff RadonPy chose on purpose. Pinning
    # to the physical-core count here (see PHYSICAL_CORES in config.py) makes the wall-time
    # comparison apples-to-apples against PolyJarvis's own hardware policy, which already caps
    # Σmpi_ranks at physical cores (orchestration/scripts/hardware_runtime.py).
    env["RadonPy_MPI"] = str(PHYSICAL_CORES)

    phases = []
    status = "running"
    error = None
    try:
        _write_terminal_group(work_dir, RADONPY_ENV_PYTHON, ter_smiles, harness_root / "ter_setup.log")

        phases.append(_run_phase(
            "qm", [str(RADONPY_ENV_PYTHON), str(RADONPY_SAMPLE_SCRIPT_DIR / "qm.py")],
            cwd=harness_root, env=env, log_path=harness_root / "qm.log",
        ))
        if phases[-1]["returncode"] != 0:
            raise RuntimeError(f"qm.py failed (rc={phases[-1]['returncode']}); see {phases[-1]['log']}")

        phases.append(_run_phase(
            "eq", [str(RADONPY_ENV_PYTHON), str(RADONPY_SAMPLE_SCRIPT_DIR / "eq.py")],
            cwd=harness_root, env=env, log_path=harness_root / "eq.log",
        ))
        if phases[-1]["returncode"] != 0:
            raise RuntimeError(f"eq.py failed (rc={phases[-1]['returncode']}); see {phases[-1]['log']}")

        status = "complete"
    except Exception as exc:  # noqa: BLE001 - this runner's job is to record the failure, not hide it
        status = "failed"
        error = str(exc)

    result = {
        "polymer": polymer_name,
        "smiles": smiles,
        "status": status,
        "error": error,
        "work_dir": str(work_dir),
        "phases": phases,
    }
    (harness_root / "timestamps.json").write_text(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--polymer", required=True)
    parser.add_argument("--smiles", required=True)
    parser.add_argument("--ter-smiles", default="*C")
    args = parser.parse_args()

    result = run_radonpy_arm(args.polymer, args.smiles, ter_smiles=args.ter_smiles)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "complete" else 1)


if __name__ == "__main__":
    main()
