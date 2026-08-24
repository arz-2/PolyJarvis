#!/usr/bin/env python3
"""
select_system_size.py — mechanically select/check D-04_system_size from
decision_policy.json's require clauses and polymer_rules.json's own cited literature
values.

decision_policy.json's D-04_system_size requires DP above the Fox-Flory plateau for Tg
targets and DP/nchain above the entanglement-MW threshold for bulk_modulus targets.
Nothing checked either: dp_typical/nchain were read straight off static per-class
literals with no admissibility logic, unlike D-01/D-08 which each have a select_*.py
that measures rather than transcribes. This is that script for D-04 -- same contract as
select_forcefield.py: a checker against already-cited numbers, not a new formula.

Two literature values already sit in polymer_rules.json's _metadata.global_notes and are
made mechanically checkable here, not re-derived:

  FOX-FLORY PLATEAU (Patrone 2016): DP>=20 for chain-length-independent Tg on flexible
  backbones, DP>=50 for the three classes the notes name explicitly as stiff (PIMD,
  PKTN, PSFO). This is data (which three classes), not a rigidity classifier -- do not
  add group-contribution or backbone-flexibility inference here. Class-level, not
  per-member: it is a backbone-architecture threshold, and the source citation already
  names its exceptions at class granularity.

  ENTANGLEMENT MW (Me = rho*R*T/Ge, Mark 2007 Ch.25 Tables 25.1-25.5): documented with a
  real Me number for exactly six classes -- but for ONE MEMBER of each, not the class as
  a whole (e.g. PACR covers PMMA/PMA/PAA; only PMMA's Me=12,500 is documented). Me is
  resolved per-member via the run's own SMILES against the class's member_smiles table
  (hw_common.resolve_member), and refuses -- MW_FLOOR_UNKNOWN, never a class-level number
  -- when the SMILES matches no documented member. DP@Me = Me / repeat-unit molar mass is
  computed here with the SAME RDKit residue-mass convention select_hardware.py already
  uses (dummy '*' atoms carry zero mass) -- this reproduces the notes' own cited
  DP@Me=160 (PS) / 125 (PMMA) figures rather than storing a second, driftable copy.

A downward gap (class default already clears the floor by a wide margin) is reported as
a non-blocking size_over_provisioned advisory and NEVER sets decided_params_override --
shrinking DP for an already-protocol_validated SMILES is a protocol change, not a
tuning knob, and this script has no way to know a SMILES's validation status. An upward
gap (class default is BELOW its own documented floor) is what D-04's require clause is
actually about, and IS a decided_params_override candidate (or, if declined, an
uncertainty that must be acknowledged) -- same acknowledgeable-flag pattern as
select_forcefield.py's provenance flag.

nchain: no pre-build Rg predictor exists in this repo, and building one (e.g.
Rg ~ b*sqrt(C_inf*N)) would be exactly the invented-physics shortcut this script avoids
elsewhere. The L>=2*Rg chain-self-imaging criterion stays with the existing
post-build gate (check_equilibration_comprehensive) and its nchain_scale_for remedy;
validate_run_plan.py's _finite_size_findings already covers the pre-build L>=2*cutoff_A
half. This script adds only the one nchain fact global_notes documents and nothing
downstream currently surfaces: nchain=10 is a "throughput compromise" (Hayashi 2022)
while nchain=20 is the "literature-recommended production minimum for PCFF classes"
(Bejagam 2020).

Usage:
  python3 orchestration/scripts/select_system_size.py <CLASS> "<SMILES>" \\
      [--properties tg,bulk_modulus] [--dp_typical N] [--nchain N]
Prints JSON, always exits 0 (errors are {"error": ...} in the payload, matching
select_forcefield.py -- callers parse JSON, never a traceback).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hw_common import load_rules, get_class_entry, resolve_member  # noqa: E402
from select_hardware import _monomer_atoms_and_mw               # noqa: E402

# Fox-Flory plateau (Patrone 2016, polymer_rules.json:_metadata.global_notes). Data, not
# a classifier: these are the three classes the notes name as stiff backbones.
STIFF_BACKBONE_CLASSES = {"PIMD", "PKTN", "PSFO"}
FOX_FLORY_FLEXIBLE_FLOOR_DP = 20
FOX_FLORY_STIFF_FLOOR_DP = 50

PCFF_NCHAIN_PRODUCTION_MINIMUM = 20  # Bejagam 2020; nchain=10 is Hayashi2022 throughput compromise


def _fox_flory_floor(polymer_class: str) -> tuple:
    stiff = polymer_class.upper() in STIFF_BACKBONE_CLASSES
    floor = FOX_FLORY_STIFF_FLOOR_DP if stiff else FOX_FLORY_FLEXIBLE_FLOOR_DP
    note = (f"Fox-Flory plateau (Patrone 2016): DP>={floor} for "
            f"{'stiff' if stiff else 'flexible'}-backbone classes")
    return floor, note


def _resolve_me_member(cls: dict, smiles: str):
    """(member_name, Me_gmol) for the member this smiles resolves to, or (None, None)."""
    me_by_member = cls.get("entanglement_Me_gmol")
    if not me_by_member:
        return None, None
    member = resolve_member(cls, "member_smiles", smiles)
    if member is None:
        return None, None
    me = me_by_member.get(member)
    return (member, me) if isinstance(me, (int, float)) else (None, None)


def _entanglement_floor(polymer_class: str, smiles: str, cls: dict):
    """(dp_at_me, note) or (None, uncertainty_dict)."""
    member, me = _resolve_me_member(cls, smiles)
    if me is None:
        documented = cls.get("entanglement_Me_gmol")
        if not documented:
            detail = ("no documented entanglement Me for this class in "
                      "polymer_rules.json:_metadata.global_notes")
        else:
            documented_members = sorted(k for k, v in documented.items()
                                        if isinstance(v, (int, float)))
            detail = (f"class has documented Me for member(s) {documented_members} only; "
                      "this SMILES did not resolve to one -- refusing rather than "
                      "generalizing a sibling member's Me to this molecule")
        return None, {"name": "MW_FLOOR_UNKNOWN", "dominant": False, "class": polymer_class,
                      "detail": detail + " -- bulk_modulus chain-length adequacy is "
                                "UNASSESSED, not assumed adequate"}
    try:
        _, mw_per_monomer = _monomer_atoms_and_mw(smiles, is_ua=False)
    except Exception as e:  # noqa: BLE001 -- an RDKit failure must not decide the floor
        return None, {"name": "system_size_mw_estimate_failed", "dominant": False,
                      "detail": f"{type(e).__name__}: {e}"}
    dp_at_me = round(me / mw_per_monomer)
    note = (f"entanglement MW Me={me} g/mol for member {member!r} (Mark 2007 Ch.25) / "
            f"repeat-unit MW {mw_per_monomer:.1f} g/mol -> DP@Me={dp_at_me}")
    return dp_at_me, note


# Canonical order (not the arbitrary iteration order of a set) so evidence text/floors
# stay reproducible across calls with the same property set.
_KNOWN_PROPERTY_ORDER = ("tg", "bulk_modulus", "density")


def property_floors(polymer_class: str, smiles: str, properties, cls: dict = None) -> dict:
    """Per-property DP floor -- the piece select_system_size() collapses via max().

    One entry per element of `properties`, keyed by property name:
      {"floor_dp": int|None, "source": str|None, "note": str|None, "unmet": dict|None}
    `floor_dp` is None both when no floor mechanism applies at all (e.g. density) and
    when one applies but could not resolve (MW_FLOOR_UNKNOWN) -- `unmet` then carries
    the reason (the same uncertainty dict select_system_size() would report). Exposed
    standalone so a multi-arm planner can size each arm from its own property subset
    instead of the single run-wide max().
    """
    if cls is None:
        cls = get_class_entry(load_rules(), polymer_class, warn_on_miss=True)
    properties = set(properties or [])
    result = {}
    for prop in sorted(properties, key=lambda p: _KNOWN_PROPERTY_ORDER.index(p)
                       if p in _KNOWN_PROPERTY_ORDER else len(_KNOWN_PROPERTY_ORDER)):
        if prop == "tg":
            floor, note = _fox_flory_floor(polymer_class)
            result[prop] = {"floor_dp": floor, "source": "fox_flory_tg", "note": note,
                            "unmet": None}
        elif prop == "bulk_modulus":
            dp_at_me, note_or_unc = _entanglement_floor(polymer_class, smiles, cls)
            if dp_at_me is not None:
                result[prop] = {"floor_dp": dp_at_me, "source": "entanglement_bm",
                                "note": note_or_unc, "unmet": None}
            else:
                result[prop] = {"floor_dp": None, "source": None, "note": None,
                                "unmet": note_or_unc}
        else:
            result[prop] = {"floor_dp": None, "source": None, "note": None, "unmet": None}
    return result


def select_system_size(polymer_class: str, smiles: str, properties=None,
                       dp_typical: int = None, nchain: int = None) -> dict:
    rules = load_rules()
    cls = get_class_entry(rules, polymer_class, warn_on_miss=True)
    dp = dp_typical if dp_typical is not None else cls.get("dp_typical")
    nchain_v = nchain if nchain is not None else cls.get("nchain")
    if dp is None:
        return {"error": f"polymer_rules.json class {polymer_class!r} has no dp_typical"}
    properties = set(properties or [])

    uncertainties = []
    floors = []  # (source, floor_dp, note)

    for prop, info in property_floors(polymer_class, smiles, properties, cls=cls).items():
        if info["floor_dp"] is not None:
            floors.append((info["source"], info["floor_dp"], info["note"]))
        elif info["unmet"] is not None:
            uncertainties.append(info["unmet"])

    required_floor = max((f[1] for f in floors), default=None)
    floor_violated = required_floor is not None and dp < required_floor

    decided_params_override = {}
    if floor_violated:
        decided_params_override = {"dp_typical": required_floor}
        reason = (f"dp_typical={dp} is below the documented floor {required_floor} for the "
                  f"requested properties {sorted(properties)}: "
                  + "; ".join(n for _, _, n in floors))
        confidence = "medium"
    elif floors:
        reason = (f"dp_typical={dp} clears the documented floor(s): "
                  + "; ".join(n for _, _, n in floors))
        confidence = "high"
    else:
        reason = ("no DP floor applies to the requested properties "
                  f"{sorted(properties) or ['(none requested)']} (e.g. density-only)")
        confidence = "medium"

    # Downward gap: class default is well above the floor. Never an override -- shrinking
    # DP for an already-protocol_validated SMILES is a protocol change this script cannot
    # authorize; report it and let the Planner/user opt in.
    if required_floor is not None and not floor_violated and dp > 1.5 * required_floor:
        uncertainties.append({
            "name": "size_over_provisioned", "dominant": False,
            "detail": (f"dp_typical={dp} is {dp / required_floor:.1f}x the documented floor "
                      f"{required_floor} for {sorted(properties)} -- a smaller run would "
                      "still clear the cited literature floor, but lowering DP for an "
                      "already-validated protocol is a scientific decision, not this "
                      "script's to make. Reported, not overridden."),
            "current_dp_typical": dp, "documented_floor_dp": required_floor,
        })

    if nchain_v and nchain_v < PCFF_NCHAIN_PRODUCTION_MINIMUM:
        ff = (cls.get("preferred_ff") or "").lower()
        if "pcff" in ff:
            uncertainties.append({
                "name": "nchain_below_production_minimum", "dominant": False,
                "detail": (f"nchain={nchain_v} is below {PCFF_NCHAIN_PRODUCTION_MINIMUM}, the "
                          "literature-recommended production minimum for PCFF classes "
                          "(Bejagam 2020); nchain=10 is documented as a throughput compromise "
                          "(Hayashi 2022), not a production target. Advisory only -- the "
                          "L>=2*Rg finite-size gate (a separate, already-mechanized check) is "
                          "the binding constraint on nchain."),
                "current_nchain": nchain_v,
            })

    return {
        "decision": {
            "id": "D-04_system_size", "choice": f"DP={dp}, nchain={nchain_v}",
            "criteria_evaluated": ["property_target", "finite_size_effects", "gpu_budget"],
            "evidence": [{"claim": reason}],
            "confidence": confidence, "alternatives": [],
            # structured so validate_run_plan.py checks decided_params against what was
            # measured, rather than parsing the evidence prose (mirrors D-01's `admissible`)
            "required_dp_floor": required_floor,
            "floor_sources": [{"source": s, "floor_dp": f} for s, f, _ in floors],
        },
        "decided_params_override": decided_params_override,
        "uncertainties": uncertainties,
        "note": ("A documented floor is a hard require (D-04_system_size); a documented "
                 "over-provisioning gap is reported, never auto-shrunk. Entanglement Me is "
                 "resolved per-member via the run's SMILES and refuses (MW_FLOOR_UNKNOWN) "
                 "rather than generalizing a sibling member's value. Chain-self-imaging "
                 "(L>=2*Rg) is NOT assessed here -- see validate_run_plan.py's "
                 "_finite_size_findings (pre-build, minimum-image only) and "
                 "inspect_data_file's finite_size_forecast (post-build, the full check)."),
    }


# Literature grounding at any confidence level can resolve an otherwise-unresolvable
# MW_FLOOR_UNKNOWN (a cited, caveated estimate beats an outright refusal) -- but pushing a
# recommendation ABOVE an already-established mechanized floor requires the worker's own
# medium/high confidence bar, so a low-confidence guess never overrides real Fox-Flory/
# entanglement-Me evidence upward on a whim.
_GROUNDING_CONFIDENCE_TO_RAISE_AN_EXISTING_FLOOR = {"medium", "high"}


def _literature_dp_recommendation(literature_grounding: dict, cls: dict, smiles: str):
    """(dp, nchain, note, confidence) from a parsed literature_grounding_system_size.json,
    or (None, None, None, None) if it grounds nothing usable.

    Two distinct sources, both reduced to the same "a per-molecule DP was grounded" shape:
      - system_size.dp_typical/nchain: a direct convergence-DP citation (worker priority 2).
      - system_size.me_estimated_gmol: a packing-length-derived Me estimate (worker priority
        3, see .claude/agents/system-size-literature-worker.md) -- computed the SAME way a
        documented table Me is (DP@Me = Me / repeat-unit MW), just literature-sourced rather
        than curated, so it is never re-derived here from a raw C-infinity value this script
        would have to trust blindly.
    """
    if not literature_grounding:
        return None, None, None, None
    ss = literature_grounding.get("system_size") or {}
    confidence = ss.get("confidence")
    dp = ss.get("dp_typical")
    nchain = ss.get("nchain")
    if isinstance(dp, (int, float)) and dp:
        return (int(dp), int(nchain) if isinstance(nchain, (int, float)) else None,
                f"literature-grounded convergence DP ({ss.get('convergence_basis')}, "
                f"confidence={confidence})", confidence)
    me = ss.get("me_estimated_gmol")
    if isinstance(me, (int, float)) and me:
        try:
            _, mw_per_monomer = _monomer_atoms_and_mw(smiles, is_ua=False)
        except Exception as e:  # noqa: BLE001 -- a bad estimate must not crash the solve
            return None, None, None, None
        dp_at_me = round(me / mw_per_monomer)
        return (dp_at_me, None,
                f"literature-grounded packing-length Me estimate ({me} g/mol) / repeat-unit "
                f"MW {mw_per_monomer:.1f} g/mol -> DP@Me={dp_at_me} (confidence={confidence})",
                confidence)
    return None, None, None, None


def solve_system_size(polymer_class: str, smiles: str, properties=None,
                      dp_typical: int = None, nchain: int = None,
                      literature_grounding: dict = None) -> dict:
    """Cost-minimizing companion to select_system_size(): the DP/nchain a reasoned/novel
    plan should actually USE, not merely a check of whether the class default clears its
    floor.

    ADDITIVE, not a replacement -- select_system_size() itself is unchanged and stays the
    function validate_run_plan.py's _system_size_findings calls against EVERY plan,
    including frozen protocol_validated replays; shrinking DP there would risk silently
    changing an already-validated protocol. This function is only ever meant to be called
    from materialize_plan() (scientific_control.py), which by construction only ever
    produces plan_mode="reasoned" plans -- there is no replay-safety concern here.

    Fox-Flory's own premise is that accuracy is FLAT above the floor and falls off a cliff
    below it (that is what "plateau" means) -- so once a floor is known, there is no
    accuracy left to buy by exceeding it, and the cost-minimizing choice is exactly the
    floor, in both directions. This collapses to a closed-form set (not a search): DP is
    set to required_floor when one applies; nchain is set to the PCFF production minimum
    (Bejagam 2020) for PCFF-family classes, since no pre-build Rg predictor exists to give
    nchain a continuous cost/accuracy curve (select_system_size.py's own docstring rules
    that out as invented physics) -- this only moves the ALREADY-KNOWN floor from
    advisory to binding, it does not add new physics.

    literature_grounding (parsed literature_grounding_system_size.json, or None) makes the
    recommendation genuinely vary by molecule rather than only by class-bucket: a real,
    DOI-verified per-SMILES convergence DP (or packing-length-derived Me) can raise the
    recommendation above the mechanized floor at medium/high confidence, or resolve an
    otherwise-unresolvable MW_FLOOR_UNKNOWN at ANY confidence (a cited, caveated estimate
    beats outright refusal) -- but it never lowers a recommendation below a floor this
    script has already mechanically established; a single per-molecule study is not
    licensed to undercut Fox-Flory/entanglement-Me evidence.
    """
    base = select_system_size(polymer_class, smiles, properties=properties,
                              dp_typical=dp_typical, nchain=nchain)
    if "error" in base:
        return base

    rules = load_rules()
    cls = get_class_entry(rules, polymer_class, warn_on_miss=True)
    dp = dp_typical if dp_typical is not None else cls.get("dp_typical")
    nchain_v = nchain if nchain is not None else cls.get("nchain")
    required_floor = base["decision"].get("required_dp_floor")
    floor_was_unknown = required_floor is None and any(
        u.get("name") == "MW_FLOOR_UNKNOWN" for u in base.get("uncertainties", []))

    lit_dp, lit_nchain, lit_note, lit_confidence = _literature_dp_recommendation(
        literature_grounding, cls, smiles)

    recommended = {}
    reasons = []

    recommended_dp = required_floor
    if lit_dp is not None:
        if recommended_dp is None:
            # Resolves an MW_FLOOR_UNKNOWN -- any confidence beats refusal, but say so.
            recommended_dp = lit_dp
            reasons.append(f"{lit_note} -- resolves an otherwise-unassessed bulk_modulus "
                          "chain-length floor (no documented entanglement Me for this "
                          "class/member)")
        elif lit_confidence in _GROUNDING_CONFIDENCE_TO_RAISE_AN_EXISTING_FLOOR:
            if lit_dp > recommended_dp:
                recommended_dp = lit_dp
                reasons.append(f"{lit_note} -- raises the mechanized floor {required_floor} "
                              "for this specific molecule")
            else:
                reasons.append(f"{lit_note} -- does not exceed the mechanized floor "
                              f"{required_floor}; floor stands")
        else:
            reasons.append(f"{lit_note} -- confidence too low to raise an already-"
                          f"established floor {required_floor}; floor stands")

    if recommended_dp is not None and dp != recommended_dp:
        recommended["dp_typical"] = recommended_dp
        if not reasons:  # pure floor-clearing, no literature involved
            direction = "below" if dp < recommended_dp else "above"
            reasons.append(f"dp_typical={dp} is {direction} the documented floor "
                          f"{recommended_dp} for {sorted(set(properties or []))}; the "
                          "cost-minimizing choice is exactly the floor -- Fox-Flory's "
                          "plateau means there is no accuracy gain above it, and no "
                          "trajectory-length remedy exists below it")

    ff = (cls.get("preferred_ff") or "").lower()
    recommended_nchain = None
    if "pcff" in ff and nchain_v and nchain_v < PCFF_NCHAIN_PRODUCTION_MINIMUM:
        recommended_nchain = PCFF_NCHAIN_PRODUCTION_MINIMUM
    if (lit_nchain and lit_confidence in _GROUNDING_CONFIDENCE_TO_RAISE_AN_EXISTING_FLOOR
            and lit_nchain > (recommended_nchain or nchain_v or 0)):
        recommended_nchain = lit_nchain
        reasons.append(f"literature-grounded nchain={lit_nchain} raises the recommendation "
                      f"({lit_note})")
    if recommended_nchain is not None and recommended_nchain != nchain_v:
        recommended["nchain"] = recommended_nchain
        if "pcff" in ff and not any("nchain" in r for r in reasons):
            reasons.append(f"nchain={nchain_v} is below the PCFF production minimum "
                          f"{PCFF_NCHAIN_PRODUCTION_MINIMUM} (Bejagam 2020); binding this "
                          "for reasoned/novel plans rather than leaving it advisory-only "
                          "(no pre-build Rg predictor exists, so this stays a floor, not "
                          "a continuous cost/accuracy curve)")

    return {**base, "recommended_params": recommended, "recommendation_reasons": reasons,
            "floor_was_unknown": floor_was_unknown}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("polymer_class")
    p.add_argument("smiles")
    p.add_argument("--properties", help="comma-separated: tg,bulk_modulus,density")
    p.add_argument("--dp_typical", type=int, default=None)
    p.add_argument("--nchain", type=int, default=None)
    p.add_argument("--literature_grounding",
                   help="path to a literature_grounding_system_size.json to fold in via "
                        "solve_system_size() instead of the plain check")
    args = p.parse_args()

    try:
        if args.literature_grounding:
            lit = json.loads(Path(args.literature_grounding).read_text())
            result = solve_system_size(
                args.polymer_class, args.smiles,
                args.properties.split(",") if args.properties else None,
                args.dp_typical, args.nchain, literature_grounding=lit)
        else:
            result = select_system_size(
                args.polymer_class, args.smiles,
                args.properties.split(",") if args.properties else None,
                args.dp_typical, args.nchain)
    except Exception as e:  # noqa: BLE001 -- callers parse JSON, never a traceback
        result = {"error": f"{type(e).__name__}: {e}"}

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
