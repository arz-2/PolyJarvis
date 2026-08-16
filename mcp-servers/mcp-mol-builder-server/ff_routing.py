"""Single source of truth for force-field / builder routing.

Routing (preferred force field + builder + justification) is read from
``guides/polymer_rules.json`` — the authoritative per-class table the orchestrator
already uses. Previously this logic was a second, hardcoded copy inside
``server.py:_get_preferred_ff`` that re-derived the force field from SMILES chemistry
and diverged from the JSON (e.g. advising ``opls-aa/2024`` for classes the JSON routes
to ``pcff``/``trappe-ua``). Centralising it here removes that drift.

This module is intentionally dependency-light (standard library only) so it can be
unit-tested without the RadonPy/RDKit environment that ``server.py`` otherwise requires.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path


def _find_rules_path() -> Path:
    """Locate guides/polymer_rules.json via POLYJARVIS_ROOT or by walking up from here."""
    env = os.environ.get("POLYJARVIS_ROOT")
    if env:
        cand = Path(env) / "guides" / "polymer_rules.json"
        if cand.exists():
            return cand
    for parent in Path(__file__).resolve().parents:
        cand = parent / "guides" / "polymer_rules.json"
        if cand.exists():
            return cand
    raise FileNotFoundError("guides/polymer_rules.json not found (set POLYJARVIS_ROOT)")


@lru_cache(maxsize=1)
def load_polymer_rules() -> dict:
    return json.loads(_find_rules_path().read_text())


def _fallback(reason: str) -> dict:
    """Safe routing result when the class is unknown or the rules file is unavailable.

    Never raises — classify_polymer must still return its classification.
    """
    return {
        "preferred_ff": None,
        "preferred_builder": None,
        "ff_confidence": "uncited",
        "ff_justification": f"routing unavailable ({reason}); consult polymer_rules.json",
        "ff_justification_doi": None,
    }


def get_preferred_ff(class_name: str) -> dict:
    """Authoritative FF/builder routing for a PoLyInfo class code (e.g. "PHYC").

    Returns the same keys the previous hardcoded helper did, but sourced from
    polymer_rules.json so they agree with the rest of the pipeline.
    """
    try:
        rules = load_polymer_rules()
    except Exception as exc:  # IO / parse error — degrade, don't break classification
        return _fallback(f"polymer_rules.json unavailable: {exc}")

    entry = rules.get("classes", {}).get(class_name)
    if entry is None:  # UNKNOWN / unmapped class
        return _fallback(f"class {class_name!r} not in polymer_rules.json")

    return {
        "preferred_ff": entry.get("preferred_ff"),
        "preferred_builder": entry.get("preferred_builder"),
        # Derived from citation presence, the same rule stage_params.py applies when it resolves
        # ff_confidence into the build prompt. The old classes.<CLASS>.confidence field this
        # read was retired in 49877fe; entry.get on a field no longer in the file silently
        # graded every class "low" and contradicted the prompt the builder was handed.
        "ff_confidence": "cited" if entry.get("ff_justification_doi") else "uncited",
        "ff_justification": entry.get("ff_note", ""),
        "ff_justification_doi": entry.get("ff_justification_doi"),
    }
