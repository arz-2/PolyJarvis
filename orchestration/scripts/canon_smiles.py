#!/usr/bin/env python3
"""
canon_smiles.py — canonicalize a SMILES via RDKit.

The system-probe novelty gate (guides/system_characterization_cache.json) is keyed by
canonical SMILES so two atom-orderings of the same monomer collapse to one cache entry.
RDKit lives in the `radonpy`/`mol-builder` conda envs (not `base`); this reaches it via
mol_python.run_in_mol_env(), the one seam every RDKit/RadonPy caller in this repo shells
through. The SMILES is passed via an env var, never interpolated into the shell/python-c
command text, so stereo markers (`/`, `\\`) and other shell-meaningful characters in a
SMILES string can't corrupt the quoting.

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
from mol_python import run_in_mol_env  # noqa: E402

_PY_SNIPPET = """\
import os
from rdkit import Chem
smi = os.environ['CANON_SMILES_INPUT']
isomeric = os.environ.get('CANON_SMILES_ISOMERIC', '1') != '0'
mol = Chem.MolFromSmiles(smi)
if mol is None:
    raise SystemExit('RDKit could not parse SMILES: ' + smi)
print(Chem.MolToSmiles(mol, canonical=True, isomericSmiles=isomeric))
"""


def canonicalize(smiles: str, env: str = "radonpy", timeout: int = 30, *,
                  isomeric: bool = True) -> str:
    r = run_in_mol_env(script=_PY_SNIPPET, env=env, timeout=timeout, extra_env={
        "CANON_SMILES_INPUT": smiles,
        "CANON_SMILES_ISOMERIC": "1" if isomeric else "0",
    })
    out = r.stdout.strip()
    if r.returncode != 0 or not out:
        raise RuntimeError(r.stderr.strip() or "empty output from RDKit canonicalization")
    return out.splitlines()[-1]


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
