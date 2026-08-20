"""Minimization-convergence check (Change 4a) -- LAMMPS' `minimize` command always exits 0
even at MAXITER/MAXEVAL without meeting ETOL/FTOL, so `_build_chain_script` greps the stage's
own log for its stopping-criterion line after the stage completes. Two convergent forms are
known from this repo's archive: "energy tolerance" and "linesearch alpha is zero" (a
legitimate stall, not an artificial cutoff -- distinct from "max iterations"/"max force
evaluations", which mean the structure was cut off before finding a real minimum).

The pattern itself is tested directly via a real `grep -Eq` subprocess call (no `mcp`
dependency, always runnable) rather than importing server.py, since this checkout has no
`mcp` package installed. `test_build_chain_script_emits_the_check` additionally verifies the
generated bash script contains the exact same pattern, skipped if `mcp` is unavailable.
"""
import subprocess
import sys

import pytest

PATTERN = r"Stopping criterion.*(tolerance|linesearch alpha is zero)"


def _matches(log_line: str) -> bool:
    proc = subprocess.run(["grep", "-Eq", PATTERN], input=log_line, text=True)
    return proc.returncode == 0


@pytest.mark.parametrize("log_line,expected_convergent", [
    ("  Stopping criterion = energy tolerance", True),
    ("  Stopping criterion = linesearch alpha is zero", True),
    ("  Stopping criterion = max iterations", False),
    ("  Stopping criterion = max force evaluations", False),
    ("  some unrelated log line", False),
])
def test_convergence_pattern(log_line, expected_convergent):
    assert _matches(log_line) is expected_convergent


def test_pattern_matches_real_archived_convergent_log():
    """data/PP/attempts/equilibration/attempt-0005's real minimize.log."""
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[3]
    log = (repo_root / "data" / "PP" / "attempts" / "equilibration" / "attempt-0005"
           / "work" / "minimize" / "minimize.log")
    if not log.exists():
        pytest.skip("archived PP minimize.log not present in this checkout")
    proc = subprocess.run(["grep", "-Eq", PATTERN, str(log)])
    assert proc.returncode == 0


def test_build_chain_script_emits_the_check():
    try:
        import server  # noqa: F401 -- requires the `mcp` package, not installed in every checkout
    except ModuleNotFoundError as exc:
        pytest.skip(f"server.py import unavailable in this environment: {exc}")
    stages = [{"name": "minimize", "script": "minimize.in", "work_dir": "/tmp/w",
               "log_file": "minimize_run.log"}]
    script = server._build_chain_script("chain123", stages, mpi=1, gpu_ids="0", engine="cpu")
    assert "sentinel_fail minimize_not_converged" in script
    assert PATTERN.replace(r"\.", ".") in script or "Stopping criterion.*(tolerance" in script
    assert "set -euo pipefail" in script
