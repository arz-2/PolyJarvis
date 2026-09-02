#!/usr/bin/env python3
"""
mol_python.py — single seam for shelling out to the RDKit/RadonPy-capable Python
environment.

RDKit and RadonPy live outside PolyJarvis's own environment (in separate `radonpy`/
`mol-builder` conda envs). Six call sites (canon_smiles, chem_similarity,
select_hardware, select_system_size, stage_params, ff_capability) used to hand-roll
their own `source ~/miniforge3/etc/profile.d/conda.sh; conda activate <env>` string,
each with `~/miniforge3` hardcoded — reproducing this repo on any machine (including
CI) depended on that unversioned host convention. This module is the one place that
knows how to reach the environment, and the one seam callers/tests patch.

Two ways to reach it, chosen at call time by environment variables, never hardcoded:

  - POLYJARVIS_MOL_PYTHON, if set, names a Python interpreter to invoke directly --
    no conda activation at all. CI sets this: requirements-test.txt installs rdkit
    into the same venv pytest runs in, so POLYJARVIS_MOL_PYTHON is just that venv's
    own interpreter, and the RDKit-dependent tests stop needing a local conda/RadonPy
    install.
  - Otherwise, the historical conda-activate dance, rooted at POLYJARVIS_MINIFORGE_ROOT
    (default ~/miniforge3 -- still the right default for every workstation this ran on
    before; it just isn't hardcoded past this one module anymore).

Usage:
    from mol_python import run_in_mol_env

    r = run_in_mol_env(script=_SOME_PY_SOURCE, env="radonpy",
                        extra_env={"SOME_INPUT": value})
    # r is a subprocess.CompletedProcess (stdout/stderr/returncode) -- callers keep
    # their own output-parsing and error-handling unchanged.

    r = run_in_mol_env(script_path=SOME_EXISTING_SCRIPT, args=["--smiles", smiles],
                        env="radonpy")
"""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

MINIFORGE_ROOT = os.environ.get("POLYJARVIS_MINIFORGE_ROOT", os.path.expanduser("~/miniforge3"))

RDKIT_CLI = Path(__file__).resolve().parent / "rdkit_cli.py"
"""Every RDKit computation in this repo, as one in-env CLI (see rdkit_cli.py's docstring).

It lives next to this module because reaching it and reaching the environment are the same
problem: `run_in_mol_env(script_path=RDKIT_CLI, args=[subcommand, ...])` is the whole calling
convention, and no orchestration module should import rdkit_cli directly.
"""


def run_in_mol_env(*, script: str | None = None, script_path=None, args=None,
                    env: str = "radonpy", timeout: int = 30,
                    extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a Python file inside the RDKit/RadonPy-capable environment.

    Exactly one of `script` (source text -- written to a temp file first so its own
    quoting/newlines never interact with bash's -c parsing, the historical convention
    every caller already followed) or `script_path` (an existing .py file) must be
    given. `args` is an optional list of extra argv appended after the script,
    available as sys.argv[1:] inside it.
    """
    if (script is None) == (script_path is None):
        raise ValueError("run_in_mol_env: pass exactly one of script or script_path")

    run_env = dict(os.environ)
    if extra_env:
        run_env.update(extra_env)
    argv_tail = [str(a) for a in (args or [])]

    tmp_path = None
    if script is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(script)
            tmp_path = f.name
        target = tmp_path
    else:
        target = str(script_path)

    try:
        direct_python = os.environ.get("POLYJARVIS_MOL_PYTHON")
        if direct_python:
            cmd = [direct_python, target, *argv_tail]
            return subprocess.run(cmd, capture_output=True, text=True,
                                   stdin=subprocess.DEVNULL, timeout=timeout, env=run_env)

        quoted = " ".join(shlex.quote(a) for a in [target, *argv_tail])
        bash_script = (
            f"source {MINIFORGE_ROOT}/etc/profile.d/conda.sh\n"
            f"conda activate {env}\n"
            f"python3 {quoted}\n"
        )
        return subprocess.run(["bash", "-c", bash_script], capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, timeout=timeout, env=run_env)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
