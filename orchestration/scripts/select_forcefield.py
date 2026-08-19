#!/usr/bin/env python3
"""Mechanically select D-01_ff from policy + measured admissibility.

decision_policy.json's D-01_ff already requires that the chosen field have parameter
coverage for every atom type in the SMILES. Nothing enforced it: the class -> field map
in polymer_rules.json was applied unconditionally, and an inadequate field announced
itself only by crashing the build.

This implements the policy's require clauses the way select_hardware.py implements
D-08's -- the Planner calls it and transcribes the result rather than re-deriving it.

Order of operations, and what each step is allowed to decide:

  1 ADMISSIBILITY   ff_capability -- can this installation integrate the field, and can
                    the front end type this SMILES? Hard gate; removes candidates.
  2 PROVENANCE      ff_provenance on the cell step 1 already built -- were the emitted
                    parameters locally invented, silently zeroed, or taken from a
                    wildcard fallback? Demotes a candidate, never drops it.
  3 ARCHIVE PRIOR   ff_domain -- reported only. Its own leave-one-family-out backtest
                    finds extrapolation anti-correlated with error, so it must not rank.
  4 CHOICE          the class default when admissible, else a DOI-backed alternative,
                    else escalate.
  5 SPREAD          count independent lineages among survivors. Agreement inside one
                    lineage (pcff/pcff_ore/compass are all Class II) is not evidence.

Prints JSON, always exits 0.
"""
import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ff_capability      # noqa: E402
import ff_domain          # noqa: E402
import ff_provenance      # noqa: E402
from hw_common import load_rules, get_class_entry  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# a field family shares a functional form and a fitting lineage, so two members
# agreeing is one piece of evidence, not two
LINEAGE = {
    "pcff": "class2", "pcff_ore": "class2", "compass": "class2",
    "opls/2024/opls-aa": "opls", "opls/2012/opls-aa": "opls",
    # OPLS-UA is a distinct representation (no explicit H, no improper term) fit
    # separately from OPLS-AA -- not the same functional form, so it gets its own
    # lineage bucket rather than being folded into "opls".
    "opls/2024/opls-ua": "opls_ua", "opls/2012/opls-ua": "opls_ua",
    "trappe-ua": "ua", "trappe-eh": "ua",
    "gaff": "gaff", "gaff2": "gaff", "gaff2_mod": "gaff",
    "dreiding": "dreiding", "charmm/c36a": "charmm",
}


def _provenance(field, cell_dir, emc_root):
    if not cell_dir:
        return {"verdict": "FF_PROVENANCE_NOT_CHECKED",
                "reason": "no built cell — front end does not emit an EMC parameter file"}
    try:
        return ff_provenance.assess(cell_dir, field, emc_root)
    except Exception as e:  # noqa: BLE001 — a reader failure must not decide the field
        return {"verdict": "FF_PROVENANCE_NOT_CHECKED", "reason": f"{type(e).__name__}: {e}"}


def _archive_prior(field, cell_dir, archive_root):
    if not cell_dir:
        return {"verdict": "FF_UNAVAILABLE", "reason": "no built cell to fingerprint"}
    try:
        fp = ff_domain.cell_fingerprint(cell_dir)
        if fp is None:
            return {"verdict": "FF_UNAVAILABLE", "reason": "no readable emc_build.params"}
        out = ff_domain.assess(fp, ff_domain.build_vocabulary(archive_root), field)
    except Exception as e:  # noqa: BLE001
        return {"verdict": "FF_UNAVAILABLE", "reason": f"{type(e).__name__}: {e}"}
    return {k: out[k] for k in ("verdict", "extrapolated_types",
                                "extrapolated_atom_fraction", "is_accuracy_prediction")
            if k in out}


def select_forcefield(polymer_class, smiles, fields=None, archive_root="manuscript/data",
                      emc_root=ff_provenance.EMC_ROOT, keep_dir=None):
    rules = load_rules()
    cls = get_class_entry(rules, polymer_class, warn_on_miss=True)
    default_raw = cls.get("preferred_ff") or cls.get("forcefield")
    if not default_raw:
        return {"error": f"polymer_rules.json class {polymer_class!r} has no preferred_ff"}

    tmp = keep_dir or tempfile.mkdtemp(prefix="ffsel_")
    cap = ff_capability.assess_all(smiles, fields, keep_dir=tmp)
    if "error" in cap:
        return cap

    # polymer_rules.json's preferred_ff casing does not always match
    # ff_capability.FIELDS' canonical (lowercase) keys -- e.g. PURA stores
    # "GAFF2_mod" against the registry key "gaff2_mod". Resolve to the registry's
    # casing so an admissible class default is never mistaken for inadmissible;
    # the raw JSON value is still shown verbatim in the evidence claim below.
    default = next((f for f in cap["fields"] if f.lower() == default_raw.lower()),
                   default_raw)

    assessed = {}
    for field, r in cap["fields"].items():
        entry = {"admissible": r["candidate"],
                 "integrates": r["integrates"],
                 "types_smiles": r["types_smiles"],
                 "typing_error": r["typing_error"] or None,
                 "lineage": LINEAGE.get(field, field)}
        if r["candidate"]:
            entry["provenance"] = _provenance(field, r.get("cell_dir"), emc_root)
            entry["archive_prior"] = _archive_prior(field, r.get("cell_dir"), archive_root)
            entry["demoted"] = (entry["provenance"].get("verdict")
                                == "FF_PROVENANCE_BLOCKING")
        assessed[field] = entry

    admissible = [f for f, e in assessed.items() if e["admissible"]]
    clean = [f for f in admissible if not assessed[f].get("demoted")]

    # 4 -- choice
    alternatives, uncertainties = [], []
    if default in clean:
        choice, confidence = default, "high"
        reason = (f"class default {default!r} is admissible for this SMILES and its "
                  "emitted parameters carry no blocking provenance flag")
    elif default in admissible:
        choice, confidence = default, "medium"
        reason = (f"class default {default!r} is admissible but its parameters carry a "
                  "blocking provenance flag — see provenance.findings; the flag must be "
                  "acknowledged in this plan's uncertainties, not silently inherited")
        uncertainties.append({"name": "ff_parameter_provenance", "dominant": False,
                              "field": default,
                              "flags": assessed[default]["provenance"].get("counts", {})})
    else:
        doi_backed = [f for f in clean if cls.get("ff_justification_doi")
                      and f != default]
        if doi_backed:
            choice, confidence = sorted(doi_backed)[0], "low"
            reason = (f"class default {default!r} is NOT admissible for this SMILES "
                      f"({assessed.get(default, {}).get('typing_error')}); fell back to "
                      f"{choice!r}, which is admissible and carries class-level DOI "
                      "evidence")
        else:
            choice, confidence = None, "none"
            reason = (f"class default {default!r} is not admissible for this SMILES and "
                      "no admissible alternative carries DOI-backed evidence — escalate "
                      "rather than guess")
        uncertainties.append({"name": "ff_transferability", "dominant": True,
                              "reduction_probe": "literature_anchor"})
    alternatives = [{"field": f, "lineage": assessed[f]["lineage"],
                     "archive_prior": assessed[f].get("archive_prior", {}).get("verdict")}
                    for f in sorted(clean) if f != choice]

    # 5 -- spread
    lineages = sorted({assessed[f]["lineage"] for f in clean})
    spread = sorted(clean) if len(lineages) >= 2 else []
    if spread:
        uncertainties.append({
            "name": "ff_cross_field_spread", "dominant": False,
            "n_lineages": len(lineages), "lineages": lineages, "candidates": spread,
            "note": "reported as an uncertainty band; it does not select a field",
        })

    return {
        "decision": {
            "id": "D-01_ff", "choice": choice,
            "criteria_evaluated": ["literature_support", "parameter_coverage",
                                   "validation_data", "computational_cost"],
            "evidence": [
                {"claim": reason},
                {"claim": f"admissible fields (integrate + type this SMILES): {admissible}"},
                {"claim": f"class default source: polymer_rules.json:classes."
                          f"{polymer_class}.preferred_ff = {default_raw!r}",
                 "ff_justification_doi": cls.get("ff_justification_doi"),
                 "ff_note": cls.get("ff_note")},
            ],
            "confidence": confidence,
            "alternatives": alternatives,
            # structured so validate_run_plan.py checks the choice against what was
            # measured, rather than parsing the evidence prose
            "admissible": admissible,
            "provenance_flags": (assessed.get(choice, {}).get("provenance", {})
                                 .get("counts", {}) if choice else {}),
        },
        "decided_params_override": ({} if choice == default or choice is None
                                    else {"preferred_ff": choice}),
        "uncertainties": uncertainties,
        "admissible": admissible,
        "admissible_clean": clean,
        "n_lineages": len(lineages),
        "ff_spread_candidates": spread,
        "fields": assessed,
        "note": ("Admissibility is a hard gate; provenance demotes; the archive prior is "
                 "reported and never ranks. This selects an admissible field — it does "
                 "not claim the chosen field is the most accurate one."),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("polymer_class")
    p.add_argument("smiles")
    p.add_argument("--fields", help="comma-separated subset to consider")
    p.add_argument("--archive-root", default=os.path.join(REPO, "manuscript", "data"))
    p.add_argument("--emc-root", default=ff_provenance.EMC_ROOT)
    p.add_argument("--keep-dir", help="retain trial cells here instead of a temp dir")
    p.add_argument("--summary", action="store_true", help="omit the per-field detail")
    args = p.parse_args()

    try:
        result = select_forcefield(args.polymer_class, args.smiles,
                                   args.fields.split(",") if args.fields else None,
                                   args.archive_root, args.emc_root, args.keep_dir)
        if args.summary:
            result.pop("fields", None)
    except Exception as e:  # noqa: BLE001 — callers parse JSON, never a traceback
        result = {"error": f"{type(e).__name__}: {e}"}

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
