#!/usr/bin/env python3
"""
select_system_size.py — mechanically select/check D-04_system_size from
decision_policy.json's require clauses and polymer_rules.json's own cited literature
values.

decision_policy.json's D-04_system_size requires DP above the Fox-Flory plateau for Tg
targets. Entanglement-MW (DP/nchain above the entanglement threshold) is reported for
bulk_modulus targets but is advisory only, never a require -- user-directed benchmark
acceptance criterion, 2026-08-25: entanglement Me gates the plateau shear modulus /
viscoelastic relaxation (reptation dynamics), not the isothermal bulk modulus K_T =
-V(dP/dV)_T, an EOS/local-packing quantity that need not track entanglement onset. The
right acceptance criterion for K is chain-length CONVERGENCE of density/K (a small DP
sweep confirming both plateau before DP reaches entanglement), not DP>=DP@Me.
Nothing checked either before this script existed: dp_typical/nchain were read straight
off static per-class literals with no admissibility logic, unlike D-01/D-08 which each
have a select_*.py that measures rather than transcribes. This is that script for D-04
-- same contract as forcefield.py: a checker against already-cited numbers, not a
new formula.

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
forcefield.py's provenance flag.

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
forcefield.py -- callers parse JSON, never a traceback).
"""
import argparse
import json
import functools
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules_common import load_rules, get_class_entry, resolve_member  # noqa: E402
from select_hardware import _monomer_atoms_and_mw               # noqa: E402
from mol_python import run_in_mol_env, RDKIT_CLI                 # noqa: E402

# ─── Cell size, derived per SMILES ────────────────────────────────────────────────
#
# RETIRED 2026-09-02: STIFF_BACKBONE_CLASSES / FOX_FLORY_FLEXIBLE_FLOOR_DP=20 /
# FOX_FLORY_STIFF_FLOOR_DP=50. They cited "Patrone et al. Macromolecules 2016", which is
# actually Polymer 87, 246-259 (DOI 10.1016/j.polymer.2016.01.074) -- a UQ-methodology paper on
# CROSSLINKED THERMOSET EPOXIES, which have no degree of polymerization. It prescribes no DP
# floor, no chain-length floor and no box rule.
#
# DP was also the wrong unit. Tg's chain-length dependence is a chain-END fraction effect, which
# scales with MOLECULAR WEIGHT; repeat mass spans 28 g/mol (PE) to 442 (PSU), so a DP floor is
# mass in the wrong currency -- and wrong by that 16x factor. Three independent criteria (Baker
# PRX 12 021047 Table IV; Fetters ch.25 DP@Me; Kuhn segments per chain) all say heavy aromatic
# monomers need FEWER repeat units than flexible ones. The retired rule required MORE.
#
# WHAT REPLACES THEM. Wang et al., Polym. J. 53, 455-462 (2021), DOI 10.1038/s41428-020-00443-1
# mapped Tg over molecular weight x chain number for PEO and found the governing variable is the
# TOTAL system molecular weight, not per-chain MW and not DP: run-to-run Tg scatter falls from
# +-50 K at 449 g/mol to +-5 K at 112,400 (~18.8 K per decade), and Tg is "molecular weight
# dependent and chain number independent" outside the finite-size region. Undersized cells did
# not merely get noisy -- their PEO transformed to a crystal-like phase instead of a rubbery one.
# They also require nchain >= 10.
SYSTEM_MW_FLOOR_GMOL = 50_000.0
"""Total system molecular weight floor. 50 kg/mol buys ~+-12 K of Tg scatter on Wang's curve.

NOT a convergence guarantee, and must never be described as one: the true Fox-Flory plateau is
20-40 kg/mol PER CHAIN (Baker PRX Table IV: PS 33.3, PMMA 41.2), i.e. ~250k atoms at 10 chains
for PS. No all-atom cell reaches it. This floor bounds the PRECISION of Tg; the chain-length BIAS
is reported as an uncertainty instead (see chain_length_bias_uncertainty)."""

MIN_NCHAIN = 10
"""Wang 2021. Also the RadonPy default, whose 1,077-polymer dataset validates it for density,
Cp, refractive index and expansion -- though notably NOT for Tg."""

TG_SIZE_SCATTER_K_PER_DECADE = 18.8
_SCATTER_ANCHOR_MW, _SCATTER_ANCHOR_K = 449.0, 50.0
"""Wang 2021 Fig. 4b anchors: +-50 K at Mw,s=449 g/mol, +-5 K at 112,400."""


def tg_scatter_K(system_mw_gmol: float) -> float:
    """Implied Tg run-to-run scatter for a cell of this total molecular weight (Wang 2021).

    Reported on every run so the size-induced uncertainty is visible rather than assumed away.
    Floored at 3 K -- the curve is two anchor points in ONE polymer and must not be extrapolated
    into implying arbitrary precision.
    """
    if not system_mw_gmol or system_mw_gmol <= 0:
        return None
    import math as _m
    return round(max(3.0, _SCATTER_ANCHOR_K - TG_SIZE_SCATTER_K_PER_DECADE
                     * (_m.log10(system_mw_gmol) - _m.log10(_SCATTER_ANCHOR_MW))), 1)


@functools.lru_cache(maxsize=512)
def derive_cell(smiles: str, is_ua: bool = False, nchain: int = MIN_NCHAIN):
    """(dp, nchain, system_mw_gmol, note) sized from THIS SMILES, not from a class default.

    Class-level dp_typical/nchain were removed 2026-09-02: none of the 21 classes carried any
    note justifying either, and repeat mass varies up to 3x WITHIN a class (PEST: PLA 72 ->
    PBT 220 g/mol), so one number per class cannot be right for its own members -- two PSFO
    members differed 2.2x in atom count for no recorded reason.
    """
    _, m_repeat = _monomer_atoms_and_mw(smiles, is_ua)
    if not m_repeat:
        return None, nchain, None, "could not resolve a repeat-unit mass from the SMILES"
    dp = max(1, math.ceil(SYSTEM_MW_FLOOR_GMOL / (nchain * m_repeat)))
    mw_s = m_repeat * dp * nchain
    note = (f"DP={dp} x {nchain} chains = {mw_s:,.0f} g/mol total (repeat {m_repeat:.1f} g/mol), "
            f"clearing the {SYSTEM_MW_FLOOR_GMOL:,.0f} g/mol system-mass floor (Wang 2021); "
            f"implied Tg scatter +-{tg_scatter_K(mw_s)} K")
    return dp, nchain, mw_s, note

PCFF_NCHAIN_PRODUCTION_MINIMUM = 20
"""ADVISORY ONLY since 2026-09-02 -- reported as an uncertainty, never a binding recommendation.

It was binding until then, and silently doubled every PCFF cell: nchain went 10 -> 20 while DP
stayed put, so the cell landed at 2x SYSTEM_MW_FLOOR_GMOL (PMMA 100k g/mol where 50k is the
criterion). Its source, "Bejagam 2020", has no copy in this repo's literature/ and no verified
DOI anywhere in polymer_rules.json, so the claim could not be checked. What IS verified:
Wang 2021 requires nchain >= 10, and Hayashi 2022 (RadonPy, PDF in literature/) ran nchain=10
across 1,077 polymers. A confidence-gated literature nchain from literature-grounding-worker
still raises nchain bindingly -- that path carries a DOI-verified source, this constant does not.
"""

# Per-SMILES rigidity-based DP recommendation (solve_system_size() only -- see that function's
# docstring for why this must never reach select_system_size() itself).
#
# KUHN_SEGMENTS_PER_CHAIN_TARGET = 7 was REMOVED 2026-09-02 along with _dp_from_kuhn/_kuhn_floor.
# Its own comment called it "a placeholder constant pending empirical (deferred) tuning", i.e. a
# segments-per-chain target with no source, and it converted a real literature Kuhn mass into an
# arbitrary DP. A Kuhn-segments-per-chain criterion is also a chain-length-CONVERGENCE claim, and
# this module's position (Wang 2021) is that chain-length convergence is unreachable at all-atom
# scale and must be REPORTED as an uncertainty, never gated on. A DOI-verified literature DP still
# raises the recommendation via _literature_dp_recommendation(); nothing else may invent one.
DP_TYPICAL_HARD_CEILING = 1000      # mirrors scientific_control.py's OVERRIDE_RANGES["dp_typical"]
                                     # upper bound; duplicated here rather than imported to avoid
                                     # a circular import (scientific_control.py imports this module)


def _fox_flory_floor(polymer_class: str, smiles: str = None, cls: dict = None) -> tuple:
    """(floor_dp, note) from the system-mass floor, derived from this SMILES.

    Keeps the `fox_flory_tg` source name so downstream consumers (validate_run_plan,
    plan artifacts, decision rows) need no vocabulary change -- but the number now comes from
    Wang 2021's total-system-mass criterion, not from the retired DP constants.
    """
    if not smiles:
        return None, ("no SMILES supplied -- cell size is derived per-molecule and cannot be "
                      "resolved from the class alone")
    is_ua = (cls or {}).get("preferred_ff", "") == "trappe-ua"
    dp, _n, mw_s, note = derive_cell(smiles, is_ua)
    return dp, note


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


def _backbone_rigidity(smiles: str, timeout: int = 30):
    """Wrapper for rdkit_cli.py's `rigidity` -- RDKit lives in the radonpy conda env, not
    base, reached via mol_python.run_in_mol_env() (same seam
    stage_params.py's _estimate_tg_group_contribution uses). Returns the parsed result
    dict, or None on any failure (missing rdkit/conda, timeout, unparseable SMILES) --
    advisory only, never worth crashing plan resolution over."""
    try:
        r = run_in_mol_env(script_path=RDKIT_CLI, args=["rigidity", "--smiles", smiles],
                            timeout=timeout)
        result = json.loads(r.stdout.strip())
    except Exception:
        return None
    return result if isinstance(result, dict) and "error" not in result else None


def _dp_from_mw(m_repeat_gmol: float) -> int:
    """DP that clears the system-mass floor at MIN_NCHAIN chains.

    Identical by construction to derive_cell()'s DP -- both are
    ceil(SYSTEM_MW_FLOOR_GMOL / (MIN_NCHAIN * M_repeat)). Kept as a separate helper only
    because this path has an m_repeat in hand and derive_cell() takes a SMILES; it must never
    grow a second, differently-derived number. The retired DP_MW_BASELINE_GMOL = 5000 g/mol
    ("confirmed with user") expressed the same quantity as an unsourced per-chain target;
    SYSTEM_MW_FLOOR_GMOL / MIN_NCHAIN is the same value carrying Wang 2021's actual criterion.
    """
    return math.ceil(SYSTEM_MW_FLOOR_GMOL / (MIN_NCHAIN * m_repeat_gmol))


def _rigid_backbone_uncertainty(rigidity: dict, dp: int, m_repeat_gmol: float) -> dict:
    """The chain-length-bias uncertainty a stiff/semi-rigid backbone must carry.

    Replaces the retired dp_min fallback. dp_min was the SAME retired Fox-Flory/Patrone floor
    under a different key -- five classes cited "Patrone 2016" by name for it (PHYC 60, PIMD 50,
    PKTN 50, PSFO 50, PSIL 40), twelve carried no justification at all, and two (PVNL, PPNL) had
    notes contradicting their own value. It bound hardest exactly where the mass floor is
    cheapest: PEEK max(DP_MW=18, dp_min=50) = 50 and PSU max(12, 50) = 50, which is what kept
    those two unaffordable at 34k/54k atoms.

    Per the system-size plan, the rigid-aromatic chain-length risk is REPORTED on these runs,
    "not ignored and not used to block them".
    """
    return {
        "name": "RIGID_BACKBONE_CHAIN_LENGTH_BIAS", "dominant": False,
        "class": rigidity.get("rigidity_class"),
        "detail": (f"backbone classified {rigidity.get('rigidity_class')} "
                  f"({rigidity.get('classification_note')}). The cell is sized by total system "
                  f"mass (Wang 2021), which for this heavy repeat unit ({m_repeat_gmol:.1f} "
                  f"g/mol) gives DP={dp} -- short chains. No chain-length-convergence study "
                  "exists for rigid aromatic backbones, and no Kuhn-length value was supplied "
                  "for this SMILES, so the residual chain-length bias on Tg is UNQUANTIFIED. "
                  "Reported, not gated: a DP floor here would be the retired Fox-Flory rule, "
                  "whose cited source (Patrone 2016) prescribes no floor and studies crosslinked "
                  "epoxies with no degree of polymerization at all."),
    }


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
            floor, note = _fox_flory_floor(polymer_class, smiles, cls)
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
    # Class-level dp_typical/nchain were removed 2026-09-02 (none of the 21 classes carried any
    # note justifying either, and repeat mass varies up to 3x WITHIN a class). An explicit
    # caller value still wins; otherwise the cell is DERIVED from this run's own SMILES.
    dp = dp_typical if dp_typical is not None else cls.get("dp_typical")
    nchain_v = nchain if nchain is not None else cls.get("nchain")
    if dp is None or nchain_v is None:
        _dp, _n, _mw, _note = derive_cell(smiles, cls.get("preferred_ff", "") == "trappe-ua")
        dp = dp if dp is not None else _dp
        nchain_v = nchain_v if nchain_v is not None else _n
        if dp is None:
            return {"error": f"could not derive a cell for {polymer_class!r}: {_note}"}
    properties = set(properties or [])

    uncertainties = []
    floors = []  # (source, floor_dp, note)

    for prop, info in property_floors(polymer_class, smiles, properties, cls=cls).items():
        if info["floor_dp"] is not None and info["source"] == "entanglement_bm":
            # User-directed benchmark acceptance criterion, 2026-08-25 (see decision_policy.json
            # D-04_system_size): entanglement Me gates the plateau shear modulus / viscoelastic
            # relaxation (G_N^0 = rho*R*T/Me, reptation-dynamics territory), not the isothermal
            # bulk modulus K_T = -V(dP/dV)_T -- an EOS/local-packing quantity that need not track
            # entanglement onset at all. DP@Me is still worth surfacing (a longer chain does
            # change chain-end fraction, hence density, hence K), but it is advisory context,
            # never a require -- unlike Fox-Flory's floor_dp below, it must not feed
            # required_dp_floor/decided_params_override. The right acceptance criterion for K is
            # chain-length CONVERGENCE of density/K (see property_floors' bulk_modulus branch and
            # this module's docstring) -- run a small DP sweep and confirm both plateau, never
            # just "DP exceeds DP@Me".
            uncertainties.append({
                "name": "entanglement_dp_advisory", "dominant": False,
                "detail": (f"{info['note']} -- reported for context only, not an acceptance "
                          "criterion for bulk_modulus: entanglement Me governs shear/"
                          "viscoelastic properties (plateau modulus, reptation), not the "
                          "isothermal bulk modulus, which is an EOS/local-packing quantity. "
                          "Establish chain-length convergence of density/K instead (a small DP "
                          "sweep confirming both plateau) rather than requiring DP>=DP@Me."),
                "dp_at_me": info["floor_dp"],
            })
        elif info["floor_dp"] is not None:
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

    # Downward gap: the dp_typical this run was HANDED is well above the derived floor.
    # Never an override -- shrinking DP for an already-protocol_validated SMILES is a protocol
    # change this script cannot authorize; report it and let the Planner/user opt in.
    #
    # The trigger changed 2026-09-02 and the old comment ("class default is well above the
    # floor") no longer describes it: class defaults are gone, so the auto-fill path can never
    # land here -- the derived DP IS the floor. What remains reachable, and was checked rather
    # than assumed before this comment was rewritten, is an EXPLICIT dp_typical: a Planner
    # override (materialize_plan applies overrides over the auto-fill) or a frozen
    # protocol_validated plan replaying a DP chosen under the retired rules. Both are exactly
    # the cases worth flagging, so the branch stays.
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
        "note": ("A documented Fox-Flory (tg) floor is a hard require (D-04_system_size); a "
                 "documented over-provisioning gap is reported, never auto-shrunk. Entanglement "
                 "Me for bulk_modulus is advisory only (user-directed benchmark criterion, "
                 "2026-08-25 -- see decision_policy.json), resolved per-member via the run's "
                 "SMILES and refuses (MW_FLOOR_UNKNOWN) rather than generalizing a sibling "
                 "member's value, but never feeds required_dp_floor/decided_params_override. "
                 "Chain-self-imaging (L>=2*Rg) is NOT assessed here -- see "
                 "validate_run_plan.py's _finite_size_findings (pre-build, minimum-image only) "
                 "and inspect_data_file's finite_size_forecast (post-build, the full check)."),
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
        3, see .claude/agents/literature-grounding-worker.md's Part B) -- computed the SAME way a
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
    recommendation above a mechanized floor at medium/high confidence, or provide the
    recommendation at ANY confidence when no mechanized floor stands (a cited, caveated
    estimate beats nothing) -- true whether that's because Me is genuinely undocumented
    (MW_FLOOR_UNKNOWN) or, for bulk_modulus specifically, because entanglement Me is
    documented but advisory-only (never itself a require -- see property_floors). It never
    lowers a recommendation below a floor this script has already mechanically established
    (Fox-Flory for tg); a single per-molecule study is not licensed to undercut that.
    """
    base = select_system_size(polymer_class, smiles, properties=properties,
                              dp_typical=dp_typical, nchain=nchain)
    if "error" in base:
        return base

    rules = load_rules()
    cls = get_class_entry(rules, polymer_class, warn_on_miss=True)
    # Same precedence as select_system_size: explicit > class > derived. The class values were
    # removed 2026-09-02, so in practice this is the derivation -- and it MUST resolve, because
    # materialize_plan writes these into decided_params and cost_model needs them there.
    dp = dp_typical if dp_typical is not None else cls.get("dp_typical")
    nchain_v = nchain if nchain is not None else cls.get("nchain")
    dp_was_derived = dp is None
    nchain_was_derived = nchain_v is None
    if dp is None or nchain_v is None:
        _dp, _n, _mw, _note = derive_cell(smiles, cls.get("preferred_ff", "") == "trappe-ua")
        dp = dp if dp is not None else _dp
        nchain_v = nchain_v if nchain_v is not None else _n
        if dp is None:
            return {"error": f"could not derive a cell for {polymer_class!r}: {_note}"}
    required_floor = base["decision"].get("required_dp_floor")
    floor_was_unknown = required_floor is None and any(
        u.get("name") == "MW_FLOOR_UNKNOWN" for u in base.get("uncertainties", []))

    lit_dp, lit_nchain, lit_note, lit_confidence = _literature_dp_recommendation(
        literature_grounding, cls, smiles)

    recommended = {}
    reasons = []
    uncertainties = list(base.get("uncertainties", []))

    recommended_dp = required_floor
    if lit_dp is not None:
        if recommended_dp is None:
            # No mechanized DP requirement stands for these properties -- either genuinely
            # MW_FLOOR_UNKNOWN (Me undocumented) or, for bulk_modulus, entanglement Me was
            # resolved but is advisory-only (never a require, see property_floors). Either
            # way a real per-molecule convergence citation beats nothing at any confidence --
            # but the two reasons are different facts, say the right one.
            recommended_dp = lit_dp
            if floor_was_unknown:
                reasons.append(f"{lit_note} -- resolves an otherwise-unassessed bulk_modulus "
                              "chain-length floor (no documented entanglement Me for this "
                              "class/member)")
            else:
                reasons.append(f"{lit_note} -- provides the bulk_modulus chain-length "
                              "recommendation (entanglement Me is documented but advisory-"
                              "only, never itself an acceptance criterion for K; this is "
                              "real per-molecule convergence evidence instead)")
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

    # Per-SMILES rigidity/Kuhn-based DP recommendation, tg only -- generalizes the
    # class-level Fox-Flory floor above into a real per-molecule computation. Additive:
    # only ever RAISES recommended_dp, same convention as the literature-DP branch above.
    if properties and "tg" in set(properties):
        try:
            _, m_repeat = _monomer_atoms_and_mw(smiles, is_ua=False)
        except Exception as e:  # noqa: BLE001 -- an RDKit failure must not crash the solve
            m_repeat = None
            uncertainties.append({"name": "backbone_rigidity_mw_estimate_failed",
                                  "dominant": False, "detail": f"{type(e).__name__}: {e}"})
        if m_repeat:
            rigidity = _backbone_rigidity(smiles)
            if rigidity is None:
                uncertainties.append({
                    "name": "backbone_rigidity_estimate_failed", "dominant": False,
                    "detail": "rdkit_cli.py rigidity subprocess failed or timed out -- "
                              "rigidity-based DP recommendation skipped for this SMILES",
                })
            else:
                dp_mw = _dp_from_mw(m_repeat)
                rclass = rigidity.get("rigidity_class")
                # Rigidity no longer RAISES the DP -- it only decides whether this run has to
                # carry the chain-length-bias uncertainty. The mass floor sizes every cell; a
                # stiff backbone changes what is REPORTED about that cell, not how big it is.
                dp_candidate = dp_mw
                rigidity_note = f"{rigidity.get('classification_note')}; DP_MW={dp_mw}"
                if rclass != "flexible":
                    uncertainties.append(
                        _rigid_backbone_uncertainty(rigidity, dp_mw, m_repeat))

                if dp_candidate > DP_TYPICAL_HARD_CEILING:
                    uncertainties.append({
                        "name": "rigidity_dp_clamped", "dominant": False,
                        "detail": (f"rigidity DP recommendation {dp_candidate} exceeds "
                                  f"the dp_typical override ceiling {DP_TYPICAL_HARD_CEILING} "
                                  "(scientific_control.py's OVERRIDE_RANGES) -- clamped."),
                        "unclamped_dp": dp_candidate,
                    })
                    dp_candidate = DP_TYPICAL_HARD_CEILING

                if recommended_dp is None or dp_candidate > recommended_dp:
                    recommended_dp = dp_candidate
                    reasons.append(f"rigidity DP recommendation: {rigidity_note}")
                else:
                    reasons.append(f"rigidity DP recommendation ({rigidity_note}) does "
                                  f"not exceed the existing recommendation {recommended_dp}")

    # A DERIVED value must always be emitted, not only when it differs from `dp`: with the class
    # defaults removed there is no other source, and materialize_plan writes recommended_params
    # straight into decided_params -- which cost_model and the builder both require.
    if recommended_dp is not None:
        # dp_was_derived: emit even when it equals `dp`, because with the class defaults removed
        # there is no other source and materialize_plan writes recommended_params straight into
        # decided_params -- which cost_model and the builder both require.
        if dp_was_derived or dp != recommended_dp:
            recommended["dp_typical"] = recommended_dp
        if dp_was_derived and not reasons:
            # The cell was derived rather than pinned, so nothing else explains it. Without this
            # the D-04 decision row carries no evidence for the size it chose.
            _, _, _mw, _note = derive_cell(smiles, cls.get("preferred_ff", "") == "trappe-ua")
            reasons.append(f"dp_typical={recommended_dp} derived from this SMILES' own repeat "
                          f"unit to clear the {SYSTEM_MW_FLOOR_GMOL:,.0f} g/mol system-mass "
                          f"floor (Wang 2021): {_note}")
        if not reasons and dp != recommended_dp:  # pure floor-clearing, no literature involved
            direction = "below" if dp < recommended_dp else "above"
            reasons.append(f"dp_typical={dp} is {direction} the documented floor "
                          f"{recommended_dp} for {sorted(set(properties or []))}; the "
                          "cost-minimizing choice is exactly the floor -- there is no accuracy "
                          "gain above it, and no trajectory-length remedy exists below it")
    elif dp_was_derived:
        # No property floor applies (density-only), but the cell still has to be sized: the
        # system-mass derivation is the answer and nothing else will supply it.
        recommended["dp_typical"] = dp
        reasons.append(f"dp_typical={dp} derived from this SMILES' own repeat unit to clear the "
                      f"{SYSTEM_MW_FLOOR_GMOL:,.0f} g/mol system-mass floor; no property-specific "
                      "chain-length floor applies to the requested properties")

    ff = (cls.get("preferred_ff") or "").lower()
    recommended_nchain = None
    # PCFF_NCHAIN_PRODUCTION_MINIMUM is ADVISORY (see its docstring). It used to be binding
    # here, which doubled every PCFF cell without re-deriving DP -- so the cell sat at 2x the
    # system-mass floor rather than at it.
    if "pcff" in ff and nchain_v and nchain_v < PCFF_NCHAIN_PRODUCTION_MINIMUM:
        uncertainties.append({
            "name": "nchain_below_pcff_advisory_minimum", "dominant": False,
            "detail": (f"nchain={nchain_v} is below the advisory PCFF production minimum "
                      f"{PCFF_NCHAIN_PRODUCTION_MINIMUM}. Its source (\"Bejagam 2020\") has no "
                      "copy in this repo and no verified DOI, so the claim is unchecked; "
                      "nchain>=10 (Wang 2021, verified) IS met, and Hayashi 2022 (RadonPy) ran "
                      f"nchain=10 across 1,077 polymers. Raising nchain to "
                      f"{PCFF_NCHAIN_PRODUCTION_MINIMUM} at a fixed system-mass floor would "
                      "halve per-chain MW (worse chain-length bias); raising it at fixed DP "
                      "doubles cost for no criterion this module can state. Reported, not "
                      "applied -- supply a DOI-verified literature nchain to raise it."),
        })
    if (lit_nchain and lit_confidence in _GROUNDING_CONFIDENCE_TO_RAISE_AN_EXISTING_FLOOR
            and lit_nchain > (recommended_nchain or nchain_v or 0)):
        # A DOI-verified literature nchain DOES bind. DP is deliberately NOT re-derived
        # downward to absorb it: shrinking chains to pay for more of them defeats the raise.
        recommended_nchain = lit_nchain
        reasons.append(f"literature-grounded nchain={lit_nchain} raises the recommendation "
                      f"({lit_note})")
    if recommended_nchain is not None and (nchain_was_derived
                                           or recommended_nchain != nchain_v):
        recommended["nchain"] = recommended_nchain
    elif nchain_was_derived:
        recommended["nchain"] = nchain_v

    return {**base, "uncertainties": uncertainties, "recommended_params": recommended,
            "recommendation_reasons": reasons, "floor_was_unknown": floor_was_unknown}


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
