"""Fixed paths and settings for the PolyJarvis-vs-RadonPy benchmark harness.

Per the pilot's design (see docs/../plans, or the session that created this harness):
both arms run their own stock default workflow, unmodified, so this file intentionally
does not expose knobs for RadonPy_RetryEQ, RadonPy_GPU, RadonPy_MPI, etc. Those are left
unset so RadonPy's own env-var defaults (sample_script/eq.py) apply as-is.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BENCHMARK_ROOT = Path(__file__).resolve().parent
DATA_ROOT = BENCHMARK_ROOT / "data"

# The RadonPy checkout, its conda interpreter, and the LAMMPS build all live OUTSIDE this
# repo, so there is no repo-relative form for them. Resolve from the environment first, then
# fall back to the conventional per-user prefix under $HOME.
RADONPY_SOURCE_ROOT = Path(os.environ.get("RADONPY_PATH", Path.home() / "RadonPy"))
RADONPY_SAMPLE_SCRIPT_DIR = RADONPY_SOURCE_ROOT / "sample_script"
RADONPY_ENV_PYTHON = Path(os.environ.get(
    "RADONPY_ENV_PYTHON", Path.home() / "miniforge3" / "envs" / "radonpy" / "bin" / "python"))
LAMMPS_EXEC = Path(os.environ.get("LAMBDA_LAMMPS", Path.home() / "lammps-install" / "bin" / "lmp"))


def _load_physical_cores() -> int:
    """Same source of truth hardware_runtime.py uses, kept in sync by calibrate_hardware.py."""
    try:
        rules = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())
        return int(rules["hardware_policy"]["host"]["phys_cores"])
    except (KeyError, ValueError, OSError):
        return 18  # this host's known value; only reached if polymer_rules.json is unreadable


PHYSICAL_CORES = _load_physical_cores()
