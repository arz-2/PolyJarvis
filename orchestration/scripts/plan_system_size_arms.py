#!/usr/bin/env python3
"""
plan_system_size_arms.py — decide whether a run's requested properties should split
into two independently-sized arms instead of one run paying the union's DP floor.

select_system_size.py's `required_dp_floor` is `max()` over every requested property's
own floor (select_system_size.py:collapsing property_floors() output). For a class with
a documented entanglement Me (PSTR/PACR/PAMD/PCBN/PEST/PSFO, one member each), that
union can be large: PACR/PMMA requesting tg (Fox-Flory floor 20) alongside bulk_modulus
(DP@Me=125) pays 125 for the whole pipeline just to satisfy the K target, even though Tg
only needed 20 -- a ~6x atom-count difference across build, equilibration, and every
downstream stage.

This script does not change that default. Splitting into two arms means two builds, two
equilibration chains, and a merge step (merge_arm_summaries.py) -- real overhead that
only pays for itself when the floors diverge a lot. It is explicitly opt-in: nothing in
make_deterministic_plan.py, scientific_control.py, or the single-run_name-per-plan
contract changes. A human or the orchestrating agent runs this first when a run wants
both a cheap and an expensive property; each returned arm is then planned and executed
through the existing, unmodified pipeline (two ordinary make_plan()/materialize_plan()
calls, two ordinary run_campaign_workflow invocations) under its own run_name.

Split rule (literature-grounded, no invented physics -- reuses select_system_size.py's
own property_floors(), never a second copy of the floor arithmetic):
  - both "tg" and "bulk_modulus" must be requested ("density" is optional and rides
    along with the tg arm when requested -- it has no DP floor of its own, per
    polymer_rules.json:_metadata.global_notes, so there is nothing principled to size a
    third arm around).
  - bulk_modulus's floor must be a genuine measured DP@Me, not MW_FLOOR_UNKNOWN -- an
    unresolved floor gives nothing to size a second arm against.
  - DP@Me must be at least `divergence_threshold` (default 2.0x) times the tg floor.
    Below that, one run at the higher floor is cheaper than the fixed cost of a second
    build+equilibration+merge. Most classes never clear this bar: any class without a
    documented Me has bulk_modulus inherit the same Fox-Flory floor as tg (divergence
    1.0x), so no split occurs for them by construction.

When the rule doesn't fire, this returns the same single-arm decision
select_system_size.py already makes for the full property set -- callers can invoke this
script unconditionally without special-casing the common case.

Usage:
  python3 orchestration/scripts/plan_system_size_arms.py <CLASS> "<SMILES>" \\
      --run_name NAME --properties tg,bulk_modulus [--nchain N] [--divergence_threshold 2.0]
Prints JSON, always exits 0 (errors are {"error": ...} in the payload).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hw_common import load_rules, get_class_entry              # noqa: E402
from select_system_size import select_system_size, property_floors  # noqa: E402

DEFAULT_DIVERGENCE_THRESHOLD = 2.0


def plan_arms(polymer_class: str, smiles: str, run_name: str, properties,
             dp_typical: int = None, nchain: int = None,
             divergence_threshold: float = DEFAULT_DIVERGENCE_THRESHOLD) -> dict:
    properties = set(properties or [])
    if not properties:
        return {"error": "no properties requested"}

    cls = get_class_entry(load_rules(), polymer_class, warn_on_miss=True)
    dp = dp_typical if dp_typical is not None else cls.get("dp_typical")
    nchain_v = nchain if nchain is not None else cls.get("nchain")
    if dp is None:
        return {"error": f"polymer_rules.json class {polymer_class!r} has no dp_typical"}

    pf = property_floors(polymer_class, smiles, properties, cls=cls)
    tg_floor = pf.get("tg", {}).get("floor_dp")
    bm_floor = pf.get("bulk_modulus", {}).get("floor_dp")

    divergence = None
    can_split = ("tg" in properties and "bulk_modulus" in properties
                and tg_floor is not None and bm_floor is not None)
    if can_split:
        divergence = bm_floor / tg_floor
        can_split = divergence >= divergence_threshold

    if can_split:
        tg_props = sorted(properties & {"tg", "density"})
        arms = [
            {"run_name": f"{run_name}_tg", "properties": tg_props, "dp_typical": tg_floor,
             "nchain": nchain_v, "floor_source": pf["tg"]["source"]},
            {"run_name": f"{run_name}_bm", "properties": ["bulk_modulus"],
             "dp_typical": bm_floor, "nchain": nchain_v,
             "floor_source": pf["bulk_modulus"]["source"]},
        ]
        reason = (f"bulk_modulus floor {bm_floor} is {divergence:.2f}x the tg floor "
                  f"{tg_floor} (>= {divergence_threshold}x threshold) -- splitting saves "
                  f"~{100 * (1 - tg_floor / bm_floor):.0f}% of atom count on the tg/density "
                  "arm vs. running everything at the bulk_modulus floor")
        return {"split": True, "arms": arms, "reason": reason,
                "divergence": divergence, "divergence_threshold": divergence_threshold}

    # No split: identical to select_system_size.py's own single-arm decision for the
    # full property set -- never a second, driftable copy of the floor arithmetic.
    whole = select_system_size(polymer_class, smiles, properties=properties,
                               dp_typical=dp, nchain=nchain_v)
    if "error" in whole:
        return whole
    # dp_typical raised to the floor only on a real violation, exactly
    # select_system_size.py's own decided_params_override rule -- never shrunk below the
    # class/pinned default for an over-provisioned gap.
    arm_dp = whole["decided_params_override"].get("dp_typical", dp)
    reason = ("no split: " + (
        "bulk_modulus not requested alongside tg" if "bulk_modulus" not in properties
        or "tg" not in properties else
        "bulk_modulus floor is MW_FLOOR_UNKNOWN for this class/member" if bm_floor is None
        else f"divergence {divergence:.2f}x is below the {divergence_threshold}x threshold"
        if divergence is not None else "no floor applies to the requested properties"))
    return {"split": False, "arms": [
        {"run_name": run_name, "properties": sorted(properties), "dp_typical": arm_dp,
         "nchain": nchain_v, "floor_source": None}],
        "reason": reason, "divergence": divergence,
        "divergence_threshold": divergence_threshold}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("polymer_class")
    p.add_argument("smiles")
    p.add_argument("--run_name", required=True,
                   help="base name; arm run_names are <run_name>_tg / <run_name>_bm when split")
    p.add_argument("--properties", required=True, help="comma-separated: tg,bulk_modulus,density")
    p.add_argument("--dp_typical", type=int, default=None)
    p.add_argument("--nchain", type=int, default=None)
    p.add_argument("--divergence_threshold", type=float, default=DEFAULT_DIVERGENCE_THRESHOLD)
    args = p.parse_args()

    try:
        result = plan_arms(args.polymer_class, args.smiles, args.run_name,
                           args.properties.split(","), args.dp_typical, args.nchain,
                           args.divergence_threshold)
    except Exception as e:  # noqa: BLE001 -- callers parse JSON, never a traceback
        result = {"error": f"{type(e).__name__}: {e}"}

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
