"""Schema/integrity tests for guides/polymer_rules.json.

The orchestrator hard-depends on this file's structure to route builders and set
simulation parameters for all 21 PoLyInfo polymer classes. A malformed entry (a
missing key, a non-numeric temperature, an inverted Tg sweep range) would surface
as a confusing mid-run failure rather than an obvious data error, so we validate
the schema directly.
"""
import json
from pathlib import Path

import pytest

RULES_PATH = Path(__file__).resolve().parent.parent / "guides" / "polymer_rules.json"
RULES = json.loads(RULES_PATH.read_text())
CLASSES = RULES["classes"]

# Keys the orchestrator/workers read for every class (confirmed present across
# both EMC- and RadonPy-routed classes).
REQUIRED_KEYS = [
    "name",
    "preferred_builder",
    "preferred_ff",
    "forcefield",
    "charge_method",
    "dp_typical",
    "dp_min",
    "nchain",
    "density_initial_gcm3",
    "electrostatics",
    "cutoff_A",
    "dt_fs",
    "T_equil_K",
    "tg_t_high_K",
    "tg_t_low_K",
    "tg_t_step_K",
]


def test_has_expected_class_count():
    assert len(CLASSES) == 21


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_required_keys_present(cid):
    missing = [k for k in REQUIRED_KEYS if k not in CLASSES[cid]]
    assert not missing, f"{cid} missing required keys: {missing}"


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_numeric_fields_in_range(cid):
    e = CLASSES[cid]
    assert 0.1 <= e["density_initial_gcm3"] <= 2.5, "initial density out of plausible range"
    assert e["dp_min"] <= e["dp_typical"], "dp_min must not exceed dp_typical"
    assert e["nchain"] >= 1
    assert e["T_equil_K"] > 0
    assert e["dt_fs"] > 0
    assert e["cutoff_A"] > 0


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_tg_sweep_window_is_valid(cid):
    e = CLASSES[cid]
    assert e["tg_t_low_K"] < e["tg_t_high_K"], "Tg sweep low bound must be below high bound"
    assert e["tg_t_step_K"] > 0
    span = e["tg_t_high_K"] - e["tg_t_low_K"]
    assert e["tg_t_step_K"] <= span, "step size larger than the whole sweep window"


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_routing_fields_are_known(cid):
    e = CLASSES[cid]
    assert e["preferred_builder"] in {"emc", "radonpy"}
    assert e["electrostatics"] in {"pppm", "lj_cut"}


# The build route (builder + force-field family + charge handling) must stay
# internally consistent — drift here (e.g. forcefield=GAFF2_mod / charge_method=RESP
# on a class that actually builds EMC/PCFF) surfaces as a wrong mid-run build rather
# than an obvious data error. This is a *structural* invariant only: it pins each
# class to one of the two routes and rejects a QM charge job on EMC. The exact
# per-class force field and embedded-charge token (pcff→bond-increment,
# opls→opls-library, trappe→embedded) are the authority of test_ff_routing.py, which
# is sourced from the same JSON; duplicating those exact values here only invites the
# two tests to contradict each other.
EMC_FF_FAMILIES = ("pcff", "opls", "trappe", "compass")   # substring families (both opls spellings)
# compass added 2026-08-26: it's a legal ENUM_OVERRIDES["preferred_ff"] value
# (scientific_control.py), stage_params.py already treats it as pcff-equivalent
# (class_ii = 'pcff' in ff or ff in ('compass', 'pcff_ore')), and it is mechanically
# EMC-admissible for at least one class (POXI) -- the tuple was simply incomplete,
# this closes a real test gap even though it doesn't itself unlock any currently
# non-admissible class (compass fails admissibility for PEST/PURT independently).
QM_CHARGE_JOBS = {"resp", "am1-bcc", "am1bcc", "gasteiger"}


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_build_route_consistency(cid):
    e = CLASSES[cid]
    builder, pref_ff = e["preferred_builder"], e["preferred_ff"]
    if builder == "emc":
        # EMC builds with one of its own all-atom/UA fields and embeds the
        # force field's charges directly — it never schedules a QM charge job.
        assert any(fam in pref_ff.lower() for fam in EMC_FF_FAMILIES), (
            f"{cid}: EMC build requires an EMC FF family {EMC_FF_FAMILIES}, "
            f"got preferred_ff={pref_ff!r}"
        )
        assert e["charge_method"].lower() not in QM_CHARGE_JOBS, (
            f"{cid}: EMC embeds force-field charges → must not run a QM charge job, "
            f"got charge_method={e['charge_method']!r}"
        )
    else:  # radonpy — runs a real charge-assignment job with a GAFF2 or Dreiding field
        # Dreiding added 2026-08-26: mcp-mol-builder-server's assign_forcefield/
        # submit_copolymerize_job now support it (radonpy.ff.dreiding.Dreiding, confirmed
        # installed and build-tested end-to-end after patching a dict-vs-list bug in that
        # module's assign_atypes/assign_dtypes/assign_itypes — see docs/ff_capability_gaps.json).
        assert pref_ff in {"GAFF2", "GAFF2_mod", "Dreiding"}, (
            f"{cid}: RadonPy route expects a GAFF2 or Dreiding field, got preferred_ff={pref_ff!r}"
        )
        assert e["forcefield"] in {"GAFF2", "GAFF2_mod", "Dreiding"}
        assert e["charge_method"] in {"RESP", "AM1-BCC"}, (
            f"{cid}: RadonPy runs a charge job → charge_method must be RESP/AM1-BCC, "
            f"got {e['charge_method']!r}"
        )


# D-03_electrostatics is mechanized by electrostatics_decision_guide's own class
# lists, not a separate script (unlike D-01/D-08) -- nothing previously checked that
# each class's electrostatics field actually agrees with the guide it is supposed to
# be implementing.
def test_electrostatics_matches_its_own_decision_guide():
    guide = RULES["electrostatics_decision_guide"]
    lj_classes = set(guide["use_lj_cut"]["classes"])
    pppm_classes = set(guide["use_pppm"]["classes"])
    assert lj_classes | pppm_classes == set(CLASSES), (
        "electrostatics_decision_guide's class lists have drifted from classes{}"
    )
    for cid, e in CLASSES.items():
        expected = "lj_cut" if cid in lj_classes else "pppm"
        assert e["electrostatics"] == expected, (
            f"{cid}: electrostatics_decision_guide says {expected!r}, "
            f"classes.{cid}.electrostatics is {e['electrostatics']!r}"
        )


# D-04_system_size's Fox-Flory require clause (mechanized by select_system_size.py):
# DP>=20 for flexible backbones, DP>=50 for the three classes global_notes names as
# stiff. dp_min is each class's own claimed floor -- this locks it to actually clear
# the plateau its class cites, the same self-consistency shape as
# test_electrostatics_matches_its_own_decision_guide above.
STIFF_BACKBONE_CLASSES = {"PIMD", "PKTN", "PSFO"}


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_dp_min_clears_its_own_fox_flory_floor(cid):
    floor = 50 if cid in STIFF_BACKBONE_CLASSES else 20
    assert CLASSES[cid]["dp_min"] >= floor, (
        f"{cid}: dp_min={CLASSES[cid]['dp_min']} is below the Fox-Flory floor {floor} "
        f"its own class ({'stiff' if cid in STIFF_BACKBONE_CLASSES else 'flexible'} "
        "backbone) claims to clear"
    )


def test_tg_slope_gate_fallback_valid():
    """tg_slope_gate_fallback marks classes whose highest configured Tg rate is
    documented as unreliable (degenerate/inverted fit); value names which rate
    the thermal track sweeps by default instead of the highest-rate default."""
    expected = {"PEST": "highest_rate", "PKTN": "slowest_rate", "PSFO": "slowest_rate"}
    found = {cid: c["tg_slope_gate_fallback"] for cid, c in CLASSES.items()
             if "tg_slope_gate_fallback" in c}
    assert found == expected
    for cid in found:
        assert isinstance(CLASSES[cid].get("_tg_slope_gate_note"), str), cid


# The staircase has to bracket the MD Tg, which is NOT the experimental Tg: at the
# 10-100 K/ns rates MD can reach, the transition is frozen in 80-120 K high (see
# PROPERTIES.md's tg_offset_corrected_K, reported as an annotation and never folded
# into PASS/FAIL). A window that brackets only the experimental value can start below
# the transition, leaving the bilinear fit with no breakpoint to find.
MD_TG_OFFSET_K = 120.0


def _member_tgs(entry):
    """Numeric member Tg values, dropping the prose 'notes'/'note' siblings."""
    raw = entry.get("experimental_tg_K")
    if isinstance(raw, dict):
        return [v for v in raw.values() if isinstance(v, (int, float))]
    return [raw] if isinstance(raw, (int, float)) else []


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_tg_window_brackets_the_md_tg_not_just_the_experimental_one(cid):
    """Every class's sweep must clear the MD Tg of its own CURATED members.

    Scope limit, stated because it is easy to over-trust this test: it can only see
    the members in experimental_tg_K. It does NOT catch a window that is too narrow
    for the class's wider chemical space. POXI is the worked example -- its curated
    members (PEO/PPO/PVME, exp Tg 198-242 -> MD ~362 K) cleared even the old 440 K
    top, so this test passed, while 24 of the 66 POXI entries in RadonPy's PI1070 set
    had an estimated MD Tg above 440 K. Detecting that required scoring the class's
    actual chemical space with estimate_tg_group_contribution.py, and the real fix is
    to resolve the window per-SMILES from that estimator rather than per class.
    """
    entry = CLASSES[cid]
    tgs = _member_tgs(entry)
    if not tgs:
        pytest.skip(f"{cid} has no numeric member Tg to bracket")
    md_upper = max(tgs) + MD_TG_OFFSET_K
    assert entry["tg_t_high_K"] > md_upper, (
        f"{cid}: sweep top {entry['tg_t_high_K']} K does not clear the MD Tg upper "
        f"estimate {md_upper:.0f} K (max member exp Tg {max(tgs):.0f} + "
        f"{MD_TG_OFFSET_K:.0f} K rate offset) -- the staircase would start below the "
        "transition and the bilinear fit would find no breakpoint"
    )
    assert entry["tg_t_low_K"] < min(tgs), (
        f"{cid}: sweep bottom {entry['tg_t_low_K']} K is not below the lowest member "
        f"exp Tg {min(tgs):.0f} K -- no glassy branch to fit"
    )


# A force field's LJ cutoff is part of its parameterization, not a free knob.
# Truncating dispersion earlier than the field was fit with systematically
# under-counts attraction and biases density low (pair_modify tail yes bounds the
# error but does not remove it; PPPM makes electrostatics cutoff-independent, so
# this is dispersion-only). 9.5 A is the EMC/Materials-Studio Class II convention
# and is correct for PCFF -- it is wrong when inherited by an OPLS-AA class.
FF_CUTOFF_FLOOR_A = {
    "opls/2024/opls-aa": 11.0,   # Jorgensen 1996: 11-13 A + switching function
    "opls/2012/opls-aa": 11.0,
    "trappe-ua": 14.0,           # 14 A is part of the TraPPE definition itself
}


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_cutoff_respects_its_force_fields_parameterization(cid):
    entry = CLASSES[cid]
    floor = FF_CUTOFF_FLOOR_A.get(entry.get("preferred_ff"))
    if floor is None:
        pytest.skip(f"{cid}: no published cutoff floor pinned for "
                    f"{entry.get('preferred_ff')!r}")
    assert entry["cutoff_A"] >= floor, (
        f"{cid}: cutoff_A={entry['cutoff_A']} A is below the {floor} A its own "
        f"force field ({entry['preferred_ff']}) was parameterized with"
    )
