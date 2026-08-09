#!/usr/bin/env python3
"""
canon_smiles.py — canonicalize a SMILES via RDKit.

The system-probe novelty gate (guides/system_characterization_cache.json) is keyed by
canonical SMILES so two atom-orderings of the same monomer collapse to one cache entry.
RDKit lives in the `radonpy` and `mol-builder` conda envs (not `base`); this shells into
`radonpy` by the same source-conda.sh/activate pattern the MCP servers use internally
(mcp-servers/mcp-lammps-engine/server.py:_conda_run). The SMILES is passed via an env var,
never interpolated into the shell/python-c command text, so stereo markers (`/`, `\\`) and
other shell-meaningful characters in a SMILES string can't corrupt the quoting.

Usage: python3 orchestration/canon_smiles.py "<smiles>" [--env radonpy]
Prints: {"smiles": "<input>", "canonical_smiles": "<output>"}  (exit 0)
     or {"error": "...", "smiles": "<input>"}                  (exit 1)
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

_PY_SNIPPET = """\
import os
from rdkit import Chem
smi = os.environ['CANON_SMILES_INPUT']
mol = Chem.MolFromSmiles(smi)
if mol is None:
    raise SystemExit('RDKit could not parse SMILES: ' + smi)
print(Chem.MolToSmiles(mol, canonical=True))
"""


def canonicalize(smiles: str, env: str = "radonpy", timeout: int = 30) -> str:
    # Written to a temp file, not `python3 -c "..."`, so SMILES-unrelated newline/quoting
    # concerns in the snippet itself never interact with bash's double-quote parsing.
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(_PY_SNIPPET)
        snippet_path = f.name
    try:
        script = (
            "source ~/miniforge3/etc/profile.d/conda.sh\n"
            f"conda activate {env}\n"
            f"python3 {snippet_path}\n"
        )
        run_env = dict(os.environ)
        run_env["CANON_SMILES_INPUT"] = smiles
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=timeout, env=run_env)
    finally:
        os.unlink(snippet_path)
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
