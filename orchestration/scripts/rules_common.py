#!/usr/bin/env python3
"""
rules_common.py — guides/polymer_rules.json access and class/member resolution.

The single source of truth for reading the rules file and answering "what does this class
say", "which member of it is this SMILES", and -- since 2026-09-02 -- "what is this SMILES'
canonical form", the question the other two rest on. This is the most-imported module in the
orchestration layer, and until 2026-09-02 it lived inside hw_common.py -- a file named for
hardware, two thirds of whose call sites (load_rules, get_class_entry, resolve_member*,
resolve_ff_family) had nothing to do with hardware at all. Nobody looking for the rules
loader would have opened a file called hw_common.

hardware_runtime.py keeps what that name actually describes: live host/GPU probing and the
GPU claim ledger. It imports hardware_policy() from here, one way, no cycle.

canonicalize() arrived from canon_smiles.py, a 53-line module that existed only to wrap one
subprocess call. Four modules imported it, and this one already lazy-imported it from inside
_canon_for_match() -- member resolution cannot answer "is this the same molecule" without
it, so the canonical form and the tables it is matched against now live together.

stdlib only -- importable by any orchestration/scripts/<x>.py (orchestration/scripts/ is on
sys.path[0] when run as a CLI; benchmark_hardware.py / calibrate_hardware.py also insert
orchestration/scripts/ explicitly). mol_python is stdlib-only too, and does not import back.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mol_python import run_in_mol_env, RDKIT_CLI  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
RULES_PATH = REPO / "guides" / "polymer_rules.json"


def load_rules() -> dict:
    """Parse guides/polymer_rules.json."""
    with open(RULES_PATH) as f:
        return json.load(f)


def get_class_entry(rules: dict, polymer_class: str, warn_on_miss: bool = False) -> dict:
    """Class entry from polymer_rules, falling back to global_defaults on an unknown class."""
    entry = rules["classes"].get(polymer_class.upper())
    if entry is None:
        if warn_on_miss:
            print(f"WARNING: class '{polymer_class}' not found in polymer_rules.json; "
                  "using global_defaults", file=sys.stderr)
        entry = rules["global_defaults"]
    return entry


def primary_source(rules: dict, source_id: str) -> dict | None:
    """Resolve a class `citations[]` id to its full record in _metadata.primary_sources.

    The per-class citations arrays hold only opaque ids ("Afzal2021"); the real citation
    strings and DOIs live in _metadata.primary_sources and, until 2026-09-02, had no reader
    at all. Joining them is what lets the deterministic decision autofill emit evidence
    entries carrying a real source_doi/citation -- which is what validate_run_plan.py's
    evidence_required check actually asks for.

    Returns {'id','citation','doi','relevance', ...} or None for an unknown id.
    """
    if not source_id:
        return None
    for entry in rules.get("_metadata", {}).get("primary_sources", []) or []:
        if entry.get("id") == source_id:
            return entry
    return None


def source_evidence(rules: dict, source_id: str, claim: str, *,
                    criterion: str | None = None, resolver: str | None = None) -> dict:
    """One decision-row evidence entry backed by a primary_sources id.

    Emits `source_doi`/`citation` only when the id actually resolves -- never a fabricated
    or placeholder citation. `origin` is always "autofill": benchmarks/.../llm_contribution.py
    uses that tag to keep deterministic-baseline reasoning out of the LLM-contribution count.
    """
    entry = primary_source(rules, source_id) or {}
    out = {"claim": claim, "origin": "autofill"}
    if criterion:
        out["criterion"] = criterion
    if resolver:
        out["resolver"] = resolver
    if entry.get("doi"):
        out["source_doi"] = entry["doi"]
    if entry.get("citation"):
        out["citation"] = entry["citation"]
    return out


def hardware_policy(rules: dict | None = None) -> dict:
    """The hardware_policy block (loads rules if not supplied). {} if absent."""
    rules = rules if rules is not None else load_rules()
    return rules.get("hardware_policy", {})


def canonicalize(smiles: str, env: str = "radonpy", timeout: int = 30, *,
                  isomeric: bool = True) -> str:
    """Canonical SMILES via RDKit. Raises RuntimeError on any RDKit-side failure.

    Two callers need this for different reasons. The system-probe novelty gate
    (guides/system_characterization_cache.json) is keyed by ISOMERIC canonical SMILES so two
    atom-orderings of the same monomer collapse to one cache entry while a different stereo
    variant stays its own entry; _canon_for_match() below strips stereo instead, because
    tacticity must not change which class member a SMILES resolves to.

    RDKit lives in the `radonpy`/`mol-builder` conda envs, not in this interpreter, so this
    shells through mol_python.run_in_mol_env() -- the one seam every RDKit caller uses -- to
    rdkit_cli.py's `canon` subcommand. The SMILES travels as an argv element and is never
    interpolated into shell/python -c command text: run_in_mol_env passes a real argv list on
    the direct-interpreter path and shlex-quotes on the conda path, so stereo markers (forward
    and back slashes) and other shell-meaningful characters cannot corrupt quoting.
    """
    args = ["canon", "--smiles", smiles] + ([] if isomeric else ["--no-isomeric"])
    r = run_in_mol_env(script_path=RDKIT_CLI, args=args, env=env, timeout=timeout)
    out = r.stdout.strip()
    if r.returncode != 0 or not out:
        raise RuntimeError(r.stderr.strip() or "empty output from RDKit canonicalization")
    return json.loads(out.splitlines()[-1])["canonical_smiles"]


@lru_cache(maxsize=256)
def _canon_for_match(smiles: str) -> str | None:
    """Stereo-stripped canonical SMILES for member-identity matching. Distinct from
    guides/system_characterization_cache.json's canonical_smiles cache key, which stays
    isomeric -- a different stereo variant of the same molecule needs independent protocol
    validation there, but tacticity/stereo markers must not change which class member a
    SMILES resolves to.

    Memoized: canonicalize() shells into a conda env per call. None on any failure
    (unparseable SMILES, RDKit/conda unavailable, timeout) -- never raises."""
    if not smiles:
        return None
    try:
        return canonicalize(smiles, isomeric=False)
    except (RuntimeError, subprocess.TimeoutExpired):
        return None


def resolve_member(cls: dict, field: str, smiles: str) -> str | None:
    """Which member of cls[field] (a {member_name: [canonical_smiles, ...]} table) this
    smiles resolves to, or None."""
    member_smiles = cls.get(field) or {}
    canon = _canon_for_match(smiles)
    if canon is None:
        return None
    for member, variants in member_smiles.items():
        if not isinstance(variants, list):
            continue  # skip a sibling "note" string key
        if canon in variants:
            return member
    return None


def resolve_member_value(cls: dict, value_field: str, smiles: str):
    """cls[value_field] resolved for this smiles: the bare value if value_field is a
    scalar (applies to the whole class), the matched member's entry if value_field is a
    dict and cls['member_smiles'] resolves this smiles to one of its keys, else None."""
    val = cls.get(value_field)
    if isinstance(val, (int, float)):
        return val
    if not isinstance(val, dict):
        return None
    member = resolve_member(cls, "member_smiles", smiles)
    if member is None:
        return None
    v = val.get(member)
    return v if isinstance(v, (int, float)) else None


def resolve_ff_family(ff_raw: str, hp: dict) -> str:
    """Map a class's preferred_ff string to a by_forcefield family key
    (pcff | opls | trappe | gaff) via hardware_policy.ff_aliases, with a substring
    fallback. Used by stage_params.resolve_hardware and any consumer keying on FF family."""
    fam = hp.get("ff_aliases", {}).get(ff_raw) or hp.get("ff_aliases", {}).get(ff_raw.upper())
    if fam is None:
        fl = ff_raw.lower()
        # compass shares pcff's class2 functional form and its hardware profile, but
        # contains neither "pcff" nor any other family token, so the substring chain
        # below would silently drop it into "gaff" -- a different engine and rank count.
        fam = ("pcff" if ("pcff" in fl or fl == "compass") else "opls" if "opls" in fl
               else "trappe" if "trappe" in fl else "gaff")
    return fam


def main() -> int:
    """`canon` CLI, inherited from canon_smiles.py.

    The novel-run-plan skill canonicalizes a SMILES from a shell before writing decision.json,
    and does it from the base env -- so the entry point has to be a module that runs HERE and
    shells inward, not rdkit_cli.py, which only runs inside the RDKit env. Output contract is
    canon_smiles.py's, unchanged:
      {"smiles": ..., "canonical_smiles": ...}  exit 0
      {"error": ..., "smiles": ...}             exit 1
    """
    ap = argparse.ArgumentParser(description="polymer_rules access; canonicalize a SMILES.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("canon", help="canonicalize a SMILES via RDKit")
    c.add_argument("smiles")
    c.add_argument("--env", default="radonpy",
                   help="conda env with RDKit installed (default: radonpy)")
    c.add_argument("--no-isomeric", action="store_true",
                   help="strip stereo (the member-matching form, not the cache-key form)")
    a = ap.parse_args()

    try:
        canon = canonicalize(a.smiles, a.env, isomeric=not a.no_isomeric)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        print(json.dumps({"error": str(e), "smiles": a.smiles}))
        return 1
    print(json.dumps({"smiles": a.smiles, "canonical_smiles": canon}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
