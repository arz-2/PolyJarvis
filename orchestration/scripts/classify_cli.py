#!/usr/bin/env python3
"""
classify_cli.py — polymer_class and the full chemical-group profile of a repeat unit.

`make_deterministic_plan.make_plan` requires a polymer_class and raises on an unknown one,
and that class is load-bearing far beyond the force field: get_class_entry supplies
charge_method, electrostatics, cutoff_A, dt_fs, T_equil_K, density_initial_gcm3, the
per-member experimental bands and the tacticity default. Until now nothing in
orchestration/ derived it -- a live session got it from the mol-builder MCP server's
classify_polymer tool or by reading guides/polymer_rules.json itself. This module is the
base-env wrapper that closes that gap, so a headless driver can plan without a human.

The label is RadonPy's. poly.polyinfo_classifier is CALLED, never reimplemented:
docs/ff_coverage_sweep/arm0.jsonl -- this repo's classification ground truth, 982 rows over
RadonPy's PI1070 -- IS that function's output, so a competing SMARTS table here would be
reimplementing the thing the sweep validates against. See rdkit_cli.py's `classify`
subcommand for the profile it adds on top (backbone-vs-pendant group locations, which
polyinfo_classifier structurally cannot report because it matches on the mainchain only).

CAUTION -- the label is authoritative, but not unconditionally binding. RadonPy ranks PHAL
above PVNL, so PVC (*CC(*)Cl) classifies PHAL -> OPLS-AA, while guides/polymer_rules.json
lists PVC under PVNL -> PCFF. That is a force-field-level disagreement, not a naming
quibble, and PVF appears under BOTH classes' examples, so the rules file already concedes
the overlap. guides/class_overrides.json records such departures explicitly; both labels
and `class_source` are always reported so a substitution is never silent.
tests/test_class_agreement.py enumerates the full disagreement set.

Usage:
    from classify_cli import classify_polymer
    result = classify_polymer("*CC(*)c1ccccc1")   # -> {"polymer_class": "PSTR", ...}

    python3 orchestration/scripts/classify_cli.py --smiles '*CC(*)c1ccccc1'
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from mol_python import RDKIT_CLI, run_in_mol_env  # noqa: E402

# The `classify` subcommand needs RadonPy as well as RDKit. RadonPy is a site-package in
# `mol-builder`, not in `radonpy` -- forcefield.py:397 already reaches its RadonPy probe the
# same way, and that is the difference from every other rdkit_cli wrapper, which defaults to
# env="radonpy".
DEFAULT_ENV = "mol-builder"

# make_cyclicpolymer builds a real 4-mer per SMILES; run_in_mol_env's own 30 s default is
# sized for single-molecule RDKit calls and is not enough for a batch.
DEFAULT_TIMEOUT = 120
BATCH_TIMEOUT = 900


class ClassificationError(RuntimeError):
    """The class could not be resolved. Never carries a guessed class -- see UNRESOLVED_CLASS
    in rdkit_cli.classify for why a fabricated label is worse than a refusal here."""


def _invoke(args: list[str], env: str, timeout: int) -> dict:
    r = run_in_mol_env(script_path=RDKIT_CLI, args=args, env=env, timeout=timeout)
    out = r.stdout.strip()
    if not out:
        raise ClassificationError(r.stderr.strip() or "empty output from rdkit_cli classify")
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise ClassificationError(f"non-JSON output from rdkit_cli classify: {out[:400]}") from exc


def classify_polymer(smiles: str, *, env: str = DEFAULT_ENV, timeout: int = DEFAULT_TIMEOUT,
                     rules_path=None, overrides_path=None) -> dict:
    """Classify one repeat unit. Raises ClassificationError rather than returning a guess.

    Returns the rdkit_cli `classify` payload: polymer_class, polyinfo_class, class_source,
    class_id, priority_rank, flags (all 21 families), co_occurring, runner_up, and groups
    (each tagged backbone or pendant).
    """
    args = ["classify", "--smiles", smiles]
    if rules_path:
        args += ["--rules", str(rules_path)]
    if overrides_path:
        args += ["--overrides", str(overrides_path)]
    try:
        result = _invoke(args, env, timeout)
    except subprocess.TimeoutExpired as exc:
        raise ClassificationError(f"classify timed out after {timeout}s for {smiles!r}") from exc
    if "error" in result:
        raise ClassificationError(f"{result['error']}: {result.get('detail', '')}".strip(": "))
    return result


def classify_batch(smiles_list, *, env: str = DEFAULT_ENV, timeout: int = BATCH_TIMEOUT,
                   rules_path=None, overrides_path=None) -> list[dict]:
    """Classify many repeat units in ONE crossing of the conda seam.

    Per-SMILES failures come back as {"smiles": ..., "error": ...} entries rather than
    raising, matching rdkit_cli's `similarity` convention: one unclassifiable molecule must
    not sink a 982-row sweep.
    """
    smiles_list = list(smiles_list)
    if not smiles_list:
        return []
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(smiles_list, f)
        input_path = f.name
    try:
        args = ["classify", "--input", input_path]
        if rules_path:
            args += ["--rules", str(rules_path)]
        if overrides_path:
            args += ["--overrides", str(overrides_path)]
        return _invoke(args, env, timeout).get("results", [])
    finally:
        Path(input_path).unlink(missing_ok=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--smiles", default=None)
    p.add_argument("--input", default=None, help="JSON file holding a list of SMILES")
    p.add_argument("--env", default=DEFAULT_ENV)
    p.add_argument("--rules", default=None)
    p.add_argument("--overrides", default=None)
    args = p.parse_args()
    if bool(args.smiles) == bool(args.input):
        print(json.dumps({"error": "give exactly one of --smiles or --input"}))
        return 1
    try:
        if args.smiles:
            result = classify_polymer(args.smiles, env=args.env, rules_path=args.rules,
                                      overrides_path=args.overrides)
        else:
            result = {"results": classify_batch(json.loads(Path(args.input).read_text()),
                                                env=args.env, rules_path=args.rules,
                                                overrides_path=args.overrides)}
    except ClassificationError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
