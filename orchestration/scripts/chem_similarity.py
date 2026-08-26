#!/usr/bin/env python3
"""
chem_similarity.py — SMILES structural similarity via RDKit Morgan/Tanimoto.

RDKit lives in the `radonpy`/`mol-builder` conda envs, not `base` — same constraint
canon_smiles.py documents. This shells into `radonpy` by the same
source-conda.sh/activate pattern, passing the candidate list through a temp JSON file
(not argv/shell text) so a large batch (e.g. every class's member_smiles at once) never
hits shell-quoting or argv-length limits, and so SMILES stereo markers (`/`, `\\`) can't
corrupt anything.

This module's compute_similarities() is the one seam every caller (query_protocol_evidence.py)
goes through and the one seam tests monkeypatch — same convention already used for
canon_smiles.canonicalize (see tests/test_make_deterministic_plan_from_cache.py etc.).

Usage (CLI, for manual/real-env verification):
  python3 orchestration/scripts/chem_similarity.py --smoke '<smiles1>' '<smiles2>' [...]
Prints: {"<query>": {"<candidate>": <float 0..1>, ...}, "_errors": [...]}
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

_PY_SNIPPET = """\
import json
import os
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs

with open(os.environ['CHEM_SIMILARITY_INPUT']) as f:
    payload = json.load(f)

query = payload['query']
candidates = payload['candidates']
radius = payload.get('radius', 2)
n_bits = payload.get('n_bits', 2048)

def fp(smi):
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        return None
    return AllChem.GetMorganFingerprintAsBitVect(mol, radius, nBits=n_bits)

errors = []
query_fp = fp(query)
if query_fp is None:
    errors.append(f"query SMILES did not parse: {query}")

scores = {}
for cand in candidates:
    if query_fp is None:
        break
    cand_fp = fp(cand)
    if cand_fp is None:
        errors.append(f"candidate SMILES did not parse: {cand}")
        continue
    scores[cand] = DataStructs.TanimotoSimilarity(query_fp, cand_fp)

print(json.dumps({"scores": scores, "errors": errors}))
"""


def compute_similarities(query_smiles: str, candidate_smiles: list[str],
                          env: str = "radonpy", timeout: int = 30,
                          radius: int = 2, n_bits: int = 2048) -> dict:
    """Tanimoto similarity of query_smiles against every candidate, computed in one
    subprocess call. Returns {"scores": {candidate: score, ...}, "errors": [str, ...]}.
    A candidate (or the query) that fails to parse is dropped from `scores` and noted in
    `errors` rather than raising — one bad SMILES in a large batch must not sink the
    whole retrieval call."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f_snippet:
        f_snippet.write(_PY_SNIPPET)
        snippet_path = f_snippet.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f_input:
        json.dump({"query": query_smiles, "candidates": list(candidate_smiles),
                    "radius": radius, "n_bits": n_bits}, f_input)
        input_path = f_input.name
    try:
        script = (
            "source ~/miniforge3/etc/profile.d/conda.sh\n"
            f"conda activate {env}\n"
            f"python3 {snippet_path}\n"
        )
        run_env = dict(os.environ)
        run_env["CHEM_SIMILARITY_INPUT"] = input_path
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=timeout, env=run_env)
    finally:
        os.unlink(snippet_path)
        os.unlink(input_path)

    out = r.stdout.strip()
    if r.returncode != 0 or not out:
        raise RuntimeError(r.stderr.strip() or "empty output from RDKit similarity computation")
    return json.loads(out.splitlines()[-1])


def main():
    p = argparse.ArgumentParser(description="Compute Tanimoto similarity of a query SMILES "
                                             "against one or more candidates via RDKit.")
    p.add_argument("--smoke", nargs="+", metavar="SMILES", required=True,
                   help="first SMILES is the query, the rest are candidates")
    p.add_argument("--env", default="radonpy")
    args = p.parse_args()
    if len(args.smoke) < 2:
        print(json.dumps({"error": "need at least a query and one candidate SMILES"}))
        sys.exit(1)
    query, candidates = args.smoke[0], args.smoke[1:]
    try:
        result = compute_similarities(query, candidates, env=args.env)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    print(json.dumps({query: result}))


if __name__ == "__main__":
    main()
