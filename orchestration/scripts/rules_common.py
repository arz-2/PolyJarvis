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


K_DEFORM_SLOW_RATE_DIVISOR = 10.0
"""Decade separation between the two deformation legs of the rate-sensitivity cross-check.

Every class that declares K_deform_rate_slow_inv_s uses exactly one tenth of its own
K_deform_rate_inv_s, so deriving the slow leg reproduces all of them (PSTR included, whose
primary is itself a decade below everyone else's) rather than hardcoding one number that
would contradict PSTR.
"""


def resolve_slow_deform_rate(cls: dict) -> float | None:
    """The slow deformation leg's strain rate, defaulting to one decade below the fast leg.

    PDIE, PHYC, PSIL and PURA carried no K_deform_rate_slow_inv_s until 2026-09-07, and a
    missing slow leg is not inert: _submit_deform returns None for mode="slow", so
    do_deformation never passes log_file_2/strain_rate_2, so extract_bulk_modulus_deform
    reports no rate_sensitivity, so workflow_engine.binding_gate_failure's
    `rate_sensitivity.verdict == "WARNING"` test can never be true. DEFORM_RATE_SENSITIVE
    was unreachable for exactly the four rubbery/soft classes where a 1e8 1/s strain rate is
    most likely to read stiff. It also silently degraded the _negative_modulus remedy, whose
    `slow or fast` fallback reassigned the fast rate to itself.

    Note this is NOT free: the slow leg runs a decade slower over the same K_strain_max, and
    N_STEPS = STRAIN_MAX / (STRAIN_RATE * TIMESTEP), so it costs roughly 10x the primary
    deform. That is the price the other 17 classes already pay for the cross-check.

    A class may still pin its own value; only absence is filled in. None only when the class
    declares no fast rate either.
    """
    slow = cls.get("K_deform_rate_slow_inv_s")
    if slow not in (None, "null"):
        return float(slow)
    fast = cls.get("K_deform_rate_inv_s")
    if fast in (None, "null"):
        return None
    return float(fast) / K_DEFORM_SLOW_RATE_DIVISOR


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


#: Integration timestep by force-field family. This is a FORCE-FIELD property, not a class
#: property: it is set by the fastest vibration the field has to integrate. United-atom fields
#: carry no explicit hydrogens, so their fastest mode is a heavy-atom stretch and 2 fs is
#: stable; every all-atom field here has explicit C-H and needs 1 fs.
#:
#: It lived on all 21 class entries in polymer_rules.json until 2026-09-07, where it was a
#: perfect function of ff_accuracy_prior -- 21 copies of 5 facts, with nothing keeping them
#: in step. Worse, the class carried the PRIOR while the run builds with the field D-01
#: actually resolved for this SMILES; when the probe cascades to another field, the class dt
#: no longer describes what runs. Deriving it from the resolved field fixes that too.
FF_TIMESTEP_FS = {"trappe": 2.0, "pcff": 1.0, "opls": 1.0, "gaff": 1.0, "dreiding": 1.0}

#: Fallback for a family with no entry: the conservative all-atom value. Never 2 fs -- an
#: over-long timestep is a silent integration error, not a slow run.
DEFAULT_TIMESTEP_FS = 1.0


def timestep_fs(ff_raw: str, hp: dict | None = None) -> float:
    """The integration timestep this force field requires, in fs.

    Pass the field the run actually BUILDS with (decided_params.preferred_ff), not the
    class's ff_accuracy_prior -- see FF_TIMESTEP_FS.
    """
    if not ff_raw:
        return DEFAULT_TIMESTEP_FS
    family = resolve_ff_family(ff_raw, hp if hp is not None else hardware_policy())
    return FF_TIMESTEP_FS.get(family, DEFAULT_TIMESTEP_FS)


# NOTE -- a tg_steps_per_bin() helper was written here and REMOVED.
#
# It derived the per-bin step count as (dT / rate) / dt, on the observation that
# tg_min_steps_per_T equalled exactly that for every class carrying it. The observation was
# true and the inference was wrong: tg_min_steps_per_T is an independent FLOOR, not a derived
# value. workflow_engine and scientific_control both check a proposed remedy or override
# against it precisely to catch a change that would halve tg_t_step_K, or raise the rate,
# straight through the sampling this class needs. Deriving the floor FROM the rate makes it
# move with whatever it was meant to constrain, so it can never be violated -- and
# test_auto_remedy_is_rejected_when_it_violates_a_protocol_floor duly went green while the
# guard it covers had stopped existing.
#
# Classes land exactly on their floor because the rate was chosen to sit there, not because
# the floor is a restatement of the rate. PSIL is the proof: rate 50 K/ns over a 20 K step is
# 0.4 ns per bin against a 0.2 ns floor -- comfortably above the minimum, not in conflict
# with it.
#
# One real wrinkle survives and is left for a human: the floor is stored in STEPS, so the
# physical time it guarantees is dt-dependent. With dt now resolved from the force field, a
# SMILES whose D-01 probe cascades to a field with a different timestep gets a different
# effective sampling floor from the same stored number. Storing it as ns per bin would fix
# that, but it is a data migration to guides/polymer_rules.json and a change to what the
# guard means, so it is not being made silently.


def resolve_ff_family(ff_raw: str, hp: dict) -> str:
    """Map a force-field name to a by_forcefield family key (pcff | opls | trappe | gaff).

    hardware_policy.ff_aliases names every field forcefield.RUNNABLE_FIELDS can select, pinned
    by test_every_runnable_field_has_an_explicit_hardware_family. The substring chain below is
    the last resort for a name from outside that set -- it is not the routing table, and it
    once masked an alias table whose display-cased keys had stopped matching entirely."""
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

    The novel-run-plan skill canonicalizes a SMILES from a shell before writing run_plan.json,
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
