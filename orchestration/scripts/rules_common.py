#!/usr/bin/env python3
"""
rules_common.py — guides/polymer_rules.json access and class/member resolution.

The single source of truth for reading the rules file and answering "what does this class
say" and "which member of it is this SMILES". This is the most-imported module in the
orchestration layer, and until 2026-09-02 it lived inside hw_common.py -- a file named for
hardware, two thirds of whose call sites (load_rules, get_class_entry, resolve_member*,
resolve_ff_family) had nothing to do with hardware at all. Nobody looking for the rules
loader would have opened a file called hw_common.

hw_common.py keeps what its name actually describes: live host and GPU probing. It imports
hardware_policy() from here, one way, no cycle.

stdlib only -- importable by any orchestration/scripts/<x>.py (orchestration/scripts/ is on
sys.path[0] when run as a CLI; benchmark_hardware.py / calibrate_hardware.py also insert
orchestration/scripts/ explicitly).
"""
from __future__ import annotations

import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

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


def hardware_policy(rules: dict | None = None) -> dict:
    """The hardware_policy block (loads rules if not supplied). {} if absent."""
    rules = rules if rules is not None else load_rules()
    return rules.get("hardware_policy", {})


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
    from canon_smiles import canonicalize
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
