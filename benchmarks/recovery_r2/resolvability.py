#!/usr/bin/env python3
"""Which failures can ONLY an LLM resolve -- as a falsifiable test, not an assertion.

The ablation's headline number is meaningless without this partition. A benchmark built only
from faults the automatic ladder already handles measures the LLM at zero by construction; one
built only from faults nothing can fix measures it at zero for the opposite reason. Both are
rigged, in opposite directions, and neither is visible in a bare "A2 beat A1 by N%".

Three classes, and the first two are decided mechanically:

  CLASS 1  AUTOMATIC   -- default_remedies() routes the code to a non-agent_only remedy that
                          does not decline. Both arms resolve it. The LLM adds nothing, and
                          that is the correct answer, not a disappointing one.
  CLASS 2  UNRESOLVABLE -- no key in ALLOWED_OVERRIDES reaches the root cause. Neither arm
                          resolves it. The live campaign's three `stop` decisions are all
                          here: a host-level kill, an environment failure, and a code defect
                          in the EXTEND continuation path -- the agent diagnosed each
                          correctly and correctly declined to invent a plan-level fix.
  CLASS 3  LLM-ONLY    -- the code escalates (agent_only, or the automatic remedy declines or
                          exhausts its cap) AND a fix exists inside ALLOWED_OVERRIDES. A1 must
                          halt; A2 may resolve. This is the only class where the arms can
                          diverge on OUTCOME rather than just on how they fail.

Class 3 is falsifiable in both directions. If the named override is not in ALLOWED_OVERRIDES
the claim is void -- checked here. If an automatic remedy would in fact fix it, it is Class 1
-- also checked here. What is NOT checked mechanically is the third condition: that choosing
the override requires reading evidence the registry does not encode. That is the judgment, and
it is written down per entry so a reviewer can dispute it.

    python3 benchmarks/recovery_r2/resolvability.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from scientific_control import ALLOWED_OVERRIDES  # noqa: E402
from code_inventory import inventory  # noqa: E402

#: Codes whose registered automatic remedy DECLINES rather than acting, with the condition.
#: A declining remedy is registered but inert, so the code escalates exactly like agent_only.
DECLINES = {
    "TG_REVIEW": (
        "workflow_engine._tg_review raises ValueError (a remedy declines by raising) unless "
        "tg_gate_cause == 'breakpoint_ambiguity'. And per its own measured note, every one of "
        "the 21 classes sits at exactly 1.00x tg_min_steps_per_T, so halving tg_t_step_K always "
        "lands under the floor and _apply_remedy's validation declines the other sub-case too. "
        "As configured today TG_REVIEW escalates in BOTH sub-cases."),
}

#: The fix a reasoning agent could reach, per escalating code, with why the registry cannot.
#: Every `override` here is asserted against ALLOWED_OVERRIDES below -- an entry naming a key
#: outside the contract is a bug in this table, not a finding.
LLM_REACHABLE = {
    "TG_REVIEW": {
        "override": ["tg_rate_K_per_ns"],
        "why_not_automatic": (
            "The lever carries EXTRA_INVALIDATION to `cooling`: lowering the rate re-runs the "
            "whole cooldown as well as the sweep, which the ladder deliberately refuses to "
            "spend automatically."),
        "why_reasoning_is_needed": (
            "The two sub-causes want OPPOSITE levers -- breakpoint_ambiguity wants a finer "
            "grid, method_gap wants more time per temperature -- and telling them apart means "
            "reading whether hyperbola and bilinear fits landed >20 K apart on the same points. "
            "Choosing the new rate then trades wall-clock against fit quality with no encoded "
            "rule."),
        "evidence": "workflow_engine.py:486-516",
    },
    "EXTEND": {
        "override": ["npt_continuation_ns"],
        "why_not_automatic": (
            "continue_npt sizes an extension from a measured quantity and REFUSES rather than "
            "guess when none is available -- added 2026-09-09 after a tau fitted to a 2% C(t) "
            "decay produced a 9.3 us extension request."),
        "why_reasoning_is_needed": (
            "When the measurement is unidentifiable the agent must decide from the trace "
            "whether the melt is slow or stuck, and pick a defensible duration. The live "
            "campaign's one revise_plan is exactly this shape: C(t) had decayed 11.5% on a 5 ns "
            "melt, so the agent raised nvt_melt_min_steps to 15M."),
        "evidence": "the live PLLA_1 escalation, 2026-09-09T12:24",
        "class_3_condition": "when decay_fraction is too small to identify tau, so continue_npt "
                             "refuses to size the extension. Class 1 whenever it can.",
    },
    "FF_PROVENANCE_ZERO_SUBSTITUTED": {
        "override": ["preferred_ff"],
        "why_not_automatic": (
            "There is no rule for which field to fall back to; the registry has no candidate "
            "ordering and picking wrong measures a force field that does not describe the "
            "chemistry."),
        "why_reasoning_is_needed": (
            "Requires reading WHICH coefficients were zero-substituted and knowing which field "
            "covers that moiety -- chemistry knowledge, not a lookup."),
        "evidence": "run_campaign.py:477-495",
    },
    "BACKBONE_TYPES_UNRESOLVED": {
        "override": ["backbone_types"],
        "why_not_automatic": (
            "Auto-derivation from bond topology already ran and failed; there is no second "
            "deterministic route."),
        "why_reasoning_is_needed": (
            "Naming the backbone atom types means reading the topology and deciding what counts "
            "as mainchain for THIS chemistry."),
        "evidence": "backbone_topology.py; BACKBONE_TYPES_UNRESOLVED is a last resort",
    },
    "SIZE_MIN_IMAGE_VIOLATION": {
        "override": ["nchain"],
        "why_not_automatic": (
            "ONLY after the cap. finite_size_rebuild handles it automatically twice "
            "(local_cap=2); a third recurrence exhausts the rung and escalates."),
        "why_reasoning_is_needed": (
            "Two forecast-driven rebuilds having failed is evidence the forecast is wrong for "
            "this system, so a third pass needs a judgement about why rather than another "
            "application of the same formula."),
        "evidence": "default_remedies(): finite_size_rebuild, local_cap=2",
        "class_3_condition": "only after the 2-application cap is exhausted. Class 1 for the "
                             "first two recurrences.",
    },
}


def classify_codes() -> dict:
    inv = inventory()
    live = {**inv["live_automatic"], **inv["live_agent_only"]}
    out = {}
    for code, row in sorted(live.items()):
        escalates = code in inv["live_agent_only"] or code in DECLINES
        reachable = LLM_REACHABLE.get(code)
        # A code can be Class 1 in its normal path and Class 3 only under a stated
        # condition -- an exhausted cap, or a measurement the remedy needs and cannot get.
        # Those are the most valuable faults in the set precisely because the SAME code
        # exercises both arms identically until the condition bites.
        conditional = bool(reachable and reachable.get("class_3_condition"))
        if reachable and (escalates or conditional):
            klass = "3_llm_only_conditional" if (conditional and not escalates) else "3_llm_only"
        elif escalates:
            klass = "2_unresolvable"
        else:
            klass = "1_automatic"
        entry = {"class": klass, "remedy_id": row["remedy_id"],
                 "local_cap": row["local_cap"], "escalates": escalates}
        if code in DECLINES:
            entry["declines"] = DECLINES[code]
        if reachable:
            entry.update({k: v for k, v in reachable.items()})
        out[code] = entry
    return out


def validate(table: dict) -> list[str]:
    """A Class-3 claim naming a key outside the override contract is void."""
    failures = []
    for code, entry in table.items():
        for key in entry.get("override") or []:
            if key not in ALLOWED_OVERRIDES:
                failures.append(f"{code}: claims the fix is {key!r}, which is NOT in "
                                f"ALLOWED_OVERRIDES -- the claim is void")
    for code in LLM_REACHABLE:
        if code not in table:
            failures.append(f"{code}: named in LLM_REACHABLE but the registry does not route "
                            f"it (or no producer mints it)")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    table = classify_codes()
    failures = validate(table)
    if args.json:
        print(json.dumps({"codes": table, "failures": failures}, indent=2))
        return 1 if failures else 0
    buckets = {"1_automatic": [], "2_unresolvable": [], "3_llm_only": [],
               "3_llm_only_conditional": []}
    for code, entry in table.items():
        buckets[entry["class"]].append((code, entry))
    titles = {
        "1_automatic": "CLASS 1 -- AUTOMATIC (both arms resolve; the LLM adds nothing, correctly)",
        "2_unresolvable": "CLASS 2 -- UNRESOLVABLE (no override reaches the cause; neither arm)",
        "3_llm_only": "CLASS 3 -- LLM-ONLY (escalates AND a legal override exists) <-- the ablation",
        "3_llm_only_conditional": "CLASS 3c -- CONDITIONAL (Class 1 until a stated condition bites, then LLM-only)",
    }
    for key in ("3_llm_only", "3_llm_only_conditional", "1_automatic", "2_unresolvable"):
        print(f"\n{titles[key]}  [{len(buckets[key])}]")
        for code, entry in buckets[key]:
            print(f"  {code}")
            if key.startswith("3_"):
                print(f"      fix: {entry['override']}  ({entry['remedy_id']}, cap={entry['local_cap']})")
                print(f"      not automatic: {entry['why_not_automatic'][:150]}")
                if entry.get("class_3_condition"):
                    print(f"      only when: {entry['class_3_condition']}")
    print(f"\nvalidation: {'FAIL -- ' + '; '.join(failures) if failures else 'PASS -- every '
          'Class-3 fix is inside ALLOWED_OVERRIDES'}")
    print("\nHeadline metric: LLM contribution = Class-3 trials A2 resolves / Class-3 trials.")
    print("Report Classes 1 and 2 alongside it, or the denominator is unauditable.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
