#!/usr/bin/env python3
"""
apply_cached_characterization.py — reuse a prior system-probe measurement for this SMILES.

system-characterization-analyzer.md's cache write (guides/system_characterization_cache.json) is already
gated: an entry only exists when at least one of that run's reliability checks
(probe_tau_relax_reliable / probe_K0_reliable) came back true, so a fully-failed probe never
poisons the cache. What is still missing is the OTHER half of the loop: nothing reads a usable
cached entry's derived_* values back into a NEW run's decided_params, so a "known" SMILES would
otherwise silently fall back to guessed class defaults exactly as if it had never been measured.

This script closes that gap: given a run's run_plan.json and its canonical SMILES, if a usable
cache entry exists, patch decided_params with every non-null derived_* field (same field-name
mapping system-characterization-analyzer.md step 5 uses when it patches decided_params from a FRESH probe),
and append a D-09_characterization decision citing the cache entry's provenance. If there is no
entry, or the entry (defensively) carries no usable derived fields, this is a no-op -- exit 0,
decided_params untouched.

Called once per run from CLAUDE.md's GATE & PLAN step, right after plan generation, whenever
IS_NOVEL=false -- applies REGARDLESS of plan_mode/VALIDATED, since "characterized" (this script's
trigger -- Phase-A timing knobs measured, guides/system_characterization_cache.json[canonical_
smiles].derived_*) and "validated" (the plan_mode gate -- protocol_validated, stamped only after
Phase-C all-PASS) are two independent flags on the same cache entry. A SMILES can be
characterized-but-not-yet-validated (still lands in a reasoned plan) or validated for a different
property set than requested (still reasoned for the new property, but still reuses its old timing
knobs) -- see decision_policy.json:confidence_gate.

Usage:
  python3 orchestration/apply_cached_characterization.py \
      --run_plan data/<RUN>/raw/run_plan.json \
      --canonical_smiles "<canonical smiles>" \
      [--cache guides/system_characterization_cache.json]
Prints a JSON result summary to stdout (exit 0 whether or not anything was applied --
"nothing to reuse" is an expected, common outcome, not an error).
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_PATH = REPO_ROOT / "guides" / "system_characterization_cache.json"

# Same field-name mapping system-characterization-analyzer.md step 5 uses when patching decided_params
# from a fresh probe -- kept in sync by hand since both sides read the same cache schema
# (system-characterization-analyzer.md step 6's derived_* fields).
DERIVED_FIELD_MAP = {
    "derived_t_equil_ns": "t_equil_ns",
    "derived_eq_annealing_cycles": "eq_annealing_cycles",
    "derived_ct_min_decay_melt": "ct_min_decay_melt",
    "derived_K_deform_rate_inv_s": "K_deform_rate_inv_s",
    "derived_K_deform_rate_slow_inv_s": "K_deform_rate_slow_inv_s",
}


def apply_cached_characterization(run_plan_path: Path, canonical_smiles: str,
                                   cache_path: Path) -> dict:
    if not cache_path.exists():
        return {"applied": False, "reason": "no_cache_file", "cache_path": str(cache_path)}

    cache = json.loads(cache_path.read_text())
    entry = cache.get(canonical_smiles)
    if entry is None:
        return {"applied": False, "reason": "not_in_cache",
                "canonical_smiles": canonical_smiles}

    applied_fields = {
        decided_key: entry[derived_key]
        for derived_key, decided_key in DERIVED_FIELD_MAP.items()
        if entry.get(derived_key) is not None
    }
    if not applied_fields:
        # Defensive only -- the write-side gate (system-characterization-analyzer.md step 6) means an
        # entry should never exist with every derived_* field null, but a reuse consumer
        # should never assume its producer's invariant instead of checking it.
        return {"applied": False, "reason": "no_usable_fields_in_cache_entry",
                "canonical_smiles": canonical_smiles}

    plan = json.loads(run_plan_path.read_text())
    decided_params = plan.setdefault("decided_params", {})
    decided_params.update(applied_fields)

    both_reliable = bool(entry.get("probe_tau_relax_reliable")) and bool(entry.get("probe_K0_reliable"))
    decisions = plan.setdefault("decisions", [])
    decisions.append({
        "id": "D-09_characterization",
        "choice": applied_fields,
        "criteria_evaluated": ["measured_relaxation_reuse"],
        "evidence": [{
            "claim": "reused from guides/system_characterization_cache.json -- measured via "
                     "system-probe on an earlier run of this exact canonical SMILES",
            "source_run_name": entry.get("source_run_name"),
            "generated_at": entry.get("generated_at"),
            "tau_relax_ps": entry.get("probe_tau_relax_ps"),
            "K0_GPa": entry.get("probe_K0_GPa"),
        }],
        "confidence": "high" if both_reliable else "low",
        "alternatives": [],
    })

    run_plan_path.write_text(json.dumps(plan, indent=2) + "\n")

    return {
        "applied": True,
        "canonical_smiles": canonical_smiles,
        "run_plan": str(run_plan_path),
        "fields_applied": sorted(applied_fields.keys()),
        "source_run_name": entry.get("source_run_name"),
        "generated_at": entry.get("generated_at"),
        "reprobe_recommended": bool(entry.get("reprobe_recommended", False)),
    }


def main():
    p = argparse.ArgumentParser(
        description="Reuse a cached system-probe measurement's derived_* fields in a run_plan.json.")
    p.add_argument("--run_plan", required=True, metavar="RUN_PLAN_JSON",
                   help="Path to the run's run_plan.json (patched in place).")
    p.add_argument("--canonical_smiles", required=True,
                   help="Canonical SMILES to look up (orchestration/canon_smiles.py's output).")
    p.add_argument("--cache", default=str(CACHE_PATH),
                   help="Cache file to read (default: guides/system_characterization_cache.json).")
    args = p.parse_args()

    result = apply_cached_characterization(
        Path(args.run_plan), args.canonical_smiles, Path(args.cache))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
