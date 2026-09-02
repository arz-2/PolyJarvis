#!/usr/bin/env python3
"""
canon_smiles.py — canonicalize a SMILES via RDKit.

The system-probe novelty gate (guides/system_characterization_cache.json) is keyed by
canonical SMILES so two atom-orderings of the same monomer collapse to one cache entry.
RDKit lives in the `radonpy`/`mol-builder` conda envs (not `base`); this reaches it via
mol_python.run_in_mol_env(), the one seam every RDKit/RadonPy caller in this repo shells
through, invoking rdkit_cli.py's `canon` subcommand. The SMILES travels as an argv element,
never interpolated into shell/python-c command text: run_in_mol_env shlex-quotes the conda
path and passes a real argv list on the direct-interpreter path, so stereo markers (forward
and back slashes) and other shell-meaningful characters in a SMILES cannot corrupt quoting.

Usage: python3 orchestration/canon_smiles.py "<smiles>" [--env radonpy]
Prints: {"smiles": "<input>", "canonical_smiles": "<output>"}  (exit 0)
     or {"error": "...", "smiles": "<input>"}                  (exit 1)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mol_python import run_in_mol_env, RDKIT_CLI  # noqa: E402


def canonicalize(smiles: str, env: str = "radonpy", timeout: int = 30, *,
                  isomeric: bool = True) -> str:
    args = ["canon", "--smiles", smiles] + ([] if isomeric else ["--no-isomeric"])
    r = run_in_mol_env(script_path=RDKIT_CLI, args=args, env=env, timeout=timeout)
    out = r.stdout.strip()
    if r.returncode != 0 or not out:
        raise RuntimeError(r.stderr.strip() or "empty output from RDKit canonicalization")
    return json.loads(out.splitlines()[-1])["canonical_smiles"]


def main():
    p = argparse.ArgumentParser(description="Canonicalize a SMILES via RDKit.")
    p.add_argument("smiles")
    p.add_argument("--env", default="radonpy",
                   help="conda env with RDKit installed (default: radonpy)")
    args = p.parse_args()
    try:
        canon = canonicalize(args.smiles, args.env)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        print(json.dumps({"error": str(e), "smiles": args.smiles}))
        sys.exit(1)
    print(json.dumps({"smiles": args.smiles, "canonical_smiles": canon}))


if __name__ == "__main__":
    main()
