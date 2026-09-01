"""Schema/integrity tests for guides/polymer_rules.json.

The orchestrator hard-depends on this file's structure to route builders and set
simulation parameters for all 21 PoLyInfo polymer classes. A malformed entry (a
missing key, a non-numeric temperature, an inverted Tg sweep range) would surface
as a confusing mid-run failure rather than an obvious data error, so we validate
the schema directly.
"""
import json
from pathlib import Path

import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "orchestration" / "scripts"))

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
    the thermal track sweeps by default instead of the highest-rate default.

    PKTN and PSFO carried "slowest_rate" until 2026-09-01. Their inversion was diagnosed as a
    cold-start artifact -- the staircase reheated the finished 300 K cell, so the top plateaus
    under-equilibrated, and a FASTER sweep spent less time contaminated there. The melt-start
    sweep removes that cause, so both returned to the highest rate. The key also gates
    method_gap_exempt, so dropping it re-arms the primary/alt Tg gap gate for those two
    classes: the next PEEK/PSU run tests the fix rather than assuming it."""
    expected = {"PEST": "highest_rate"}
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


# ─── temperature_schedule(): adapts to Tg and the requested assessment temperature ──

def _sched(cid, smiles=None, **overrides):
    import stage_params as sp
    entry = RULES["classes"][cid]
    args = SimpleNamespace(smiles=smiles, exp_tg_K=None, final_T_K=None,
                           T_equil_K=None, T_anneal_high_K=None)
    for k, v in overrides.items():
        setattr(args, k, v)
    return sp.temperature_schedule(args, entry)


@pytest.mark.parametrize("cid", sorted(RULES["classes"]))
def test_curated_members_keep_their_class_temperatures(cid):
    """The class T_equil_K was chosen to clear the melting points of the members the class
    curated -- the notes name those Tm values explicitly. A +/-80 K group-contribution estimate
    must never second-guess that. Under the Boyer rule 10 of 43 curated members would otherwise
    shift (PMMA +28 K, PSU/PES +40 K, PPNL +70 K); this pins that none of them do."""
    entry = RULES["classes"][cid]
    for _name, smis in (entry.get("member_smiles") or {}).items():
        if not smis:
            continue
        sched = _sched(cid, smiles=smis[0])
        assert sched["T_equil_K"] == entry["T_equil_K"], (
            f"{cid}/{_name}: curated member's T_equil moved "
            f"{entry['T_equil_K']} -> {sched['T_equil_K']}"
        )
        assert sched["schedule_source"] == "class_default"


def test_novel_stiff_smiles_can_raise_t_equil():
    """A SMILES the class never curated is an extrapolation: the class constant was sized for
    other members and a stiffer novel one can need a hotter melt. Only ever raises."""
    import stage_params as sp
    entry = dict(RULES["classes"]["POXI"])          # class T_equil = 500 K
    args = SimpleNamespace(smiles="*CC(c1ccccc1)(c1ccccc1)O*", exp_tg_K=600.0,
                           final_T_K=None, T_equil_K=None, T_anneal_high_K=None)
    sched = sp.temperature_schedule(args, entry)
    assert sched["tg_is_curated"] is False
    assert sched["schedule_source"] == "raised_for_novel_smiles"
    assert sched["T_equil_K"] == max(600.0 + 200.0, 1.5 * 600.0)   # Boyer wins above Tg=400
    assert sched["T_equil_K"] > entry["T_equil_K"]


def test_novel_floppy_smiles_never_lowers_t_equil():
    """Lowering risks under-melting on a low-confidence estimate; the class constant floors."""
    import stage_params as sp
    entry = dict(RULES["classes"]["PKTN"])          # class T_equil = 770 K
    args = SimpleNamespace(smiles="*CC*", exp_tg_K=150.0, final_T_K=None,
                           T_equil_K=None, T_anneal_high_K=None)
    sched = sp.temperature_schedule(args, entry)
    assert sched["T_equil_K"] == entry["T_equil_K"]
    assert sched["schedule_source"] == "class_default"


def test_anneal_ceiling_clears_the_requested_assessment_temperature():
    """A run assessed at or above its own melt temperature would otherwise leave cool_block a
    non-positive span to ramp through."""
    sched = _sched("POXI", smiles="*CCO*", final_T_K=900.0)
    assert sched["T_anneal_high_K"] >= 900.0 + 100.0


@pytest.mark.parametrize("cid", sorted(RULES["classes"]))
def test_anneal_ceiling_always_clears_the_margin(cid):
    """The invariant generate_equilibration_workflow enforces as a hard validation error."""
    sched = _sched(cid)
    assert sched["T_anneal_high_K"] >= sched["T_equil_K"] + 100.0
    assert sched["T_anneal_high_K"] >= sched["final_T_K"] + 100.0


def test_final_T_defaults_to_300_but_is_not_defined_by_it():
    assert _sched("POXI", smiles="*CCO*")["final_T_K"] == 300.0
    assert _sched("POXI", smiles="*CCO*", final_T_K=450.0)["final_T_K"] == 450.0


@pytest.mark.parametrize("cid", sorted(RULES["classes"]))
def test_curated_member_window_derives_from_its_own_measured_tg(cid):
    """The sweep window is ALWAYS derived from a Tg, never from the class constant -- and for
    a curated member from that member's own exact experimental value, which is better than
    both the class window and an estimate.

    A class window is sized for whichever member is most extreme, so every other member pays
    for chemistry it does not have, and any member outside the curated spread is not covered
    at all (POXI's 440 K top missed 24 of its 66 PI1070 entries). Across the 43 curated
    members this narrows the mean sweep from 24.2 to 20.6 T-bins with none failing to bracket.
    """
    import stage_params as sp
    entry = RULES["classes"][cid]
    for name, smis in (entry.get("member_smiles") or {}).items():
        if not smis:
            continue
        sched = _sched(cid, smiles=smis[0])
        tg = sched["tg_K"]
        if not isinstance(tg, (int, float)):
            continue
        assert sched["window_source"] == "curated_tg", (
            f"{cid}/{name}: curated member should size its window from its own Tg, "
            f"got {sched['window_source']}"
        )
        md_tg = tg + sp.MD_TG_OFFSET_K
        assert sched["tg_t_low_K"] < md_tg < sched["tg_t_high_K"], (
            f"{cid}/{name}: window {sched['tg_t_low_K']}-{sched['tg_t_high_K']} "
            f"misses the MD Tg {md_tg:.0f}"
        )
        assert sched["tg_t_low_K"] < tg, "no glassy branch below the transition to fit"


def test_an_explicit_window_override_is_never_second_guessed(cid="POXI"):
    """A plan that pins tg_t_high_K/tg_t_low_K means it; the derivation must stand down."""
    sched = _sched(cid, smiles="*CCO*", tg_t_high_K=777, tg_t_low_K=111)
    assert (sched["tg_t_low_K"], sched["tg_t_high_K"]) == (111, 777)
    assert sched["window_source"] == "class_default"


def test_novel_smiles_window_brackets_the_md_tg():
    """A novel SMILES gets a Tg-derived window, and it must still CONTAIN the transition --
    the sweep is sized around the MD Tg (estimate + ~120 K), not the experimental one.
    Unlike T_equil this may narrow: a missed window fails loudly (no breakpoint ->
    TG_NOT_REPORTABLE) rather than silently, as an under-melted cell would."""
    import stage_params as sp
    entry = dict(RULES["classes"]["POXI"])
    for tg in (150.0, 250.0, 350.0, 500.0):
        args = SimpleNamespace(smiles="*CC(c1ccccc1)(c1ccccc1)O*", exp_tg_K=tg,
                               final_T_K=None, T_equil_K=None, T_anneal_high_K=None,
                               tg_t_high_K=None, tg_t_low_K=None)
        sched = sp.temperature_schedule(args, entry)
        assert sched["window_source"] == "estimated_tg"
        md_tg = tg + sp.MD_TG_OFFSET_K
        assert sched["tg_t_low_K"] < md_tg < sched["tg_t_high_K"], (
            f"Tg={tg}: window {sched['tg_t_low_K']}-{sched['tg_t_high_K']} misses MD Tg {md_tg}"
        )
        assert sched["tg_t_low_K"] < tg, "no glassy branch below the transition to fit"


def test_a_low_confidence_estimate_never_sizes_the_protocol(monkeypatch):
    """The estimator flags confidence='very_low' with an explicit "leave global_defaults
    unchanged" warning once >30% of heavy atoms match no motif -- and 633 of the 1077 polymers
    in RadonPy's PI1070 set trip that, 59% of the real chemical space. Sizing a sweep window or
    a melt temperature from one of those would be worse than the class constant, which is at
    least a considered value for related chemistry."""
    import stage_params as sp
    entry = RULES["classes"]["PKTN"]
    monkeypatch.setattr(sp, "_estimate_tg_group_contribution",
                        lambda smi, timeout=30: {"tg_estimated_K": 250,
                                                 "confidence": "very_low",
                                                 "warning": "55% of heavy atoms unmatched"})
    sched = _sched("PKTN", smiles="*NOVEL*")
    assert sched["tg_trustworthy"] is False
    assert sched["schedule_source"] == "class_default"
    assert sched["window_source"] == "class_default"
    assert sched["T_equil_K"] == entry["T_equil_K"]
    assert (sched["tg_t_low_K"], sched["tg_t_high_K"]) == \
        (entry["tg_t_low_K"], entry["tg_t_high_K"])

    monkeypatch.setattr(sp, "_estimate_tg_group_contribution",
                        lambda smi, timeout=30: {"tg_estimated_K": 250,
                                                 "confidence": "low", "warning": None})
    ok = _sched("PKTN", smiles="*NOVEL*")
    assert ok["tg_trustworthy"] is True
    assert ok["window_source"] == "estimated_tg"


def test_regime_still_uses_a_low_confidence_estimate(monkeypatch):
    """Deliberate asymmetry: the regime only needs to know which side of Tg the assessment
    sits on, the estimate is already padded toward glassy by TG_ESTIMATE_UNCERTAINTY_K, and an
    unresolvable answer falls to the stricter gate set. The number is not the protocol there."""
    import stage_params as sp
    monkeypatch.setattr(sp, "_estimate_tg_group_contribution",
                        lambda smi, timeout=30: {"tg_estimated_K": 120,
                                                 "confidence": "very_low", "warning": "x"})
    args = SimpleNamespace(smiles="*NOVEL*", exp_tg_K=None, final_T_K=None)
    # Tg 120 + 80 K padding = 200 < 300 K assessment -> rubbery, from a very_low estimate
    assert sp._regime(args, RULES["classes"]["PKTN"]) == "rubbery"


# ─── The anneal ceiling must clear the Tg sweep's own top ──────────────────────────
#
# The thermal stage starts its staircase from a cell the equilibration cooldown already
# wrote: cool_block saves a .data file at every waypoint between the anneal ceiling and
# final_T_K, and one of those has to sit at or above tg_t_high_K or there is nothing to
# start from and the sweep falls back to reheating the finished final_T_K cell.
#
# The headroom is one cool block, not zero: anneal_hold runs NVT, so the cell AT the
# ceiling still carries the densified 300 K volume rather than a melt density. The first
# genuinely melt-density cell is cool_block_01's endpoint, one cool_block_dT_K down.


@pytest.mark.parametrize("cid", sorted(RULES["classes"]))
def test_class_ceiling_clears_its_own_class_sweep_top(cid):
    """The class-constant path -- what a SMILES with an untrustworthy Tg estimate takes, which
    is 59% of RadonPy's PI1070 set. Each class's tg_t_high_K and annealing_T_high_K were sized
    independently (window from the class's highest-Tg member + the MD offset; ceiling from
    T_equil), and were never compared: PCBN/PIMD/PIMN/POXI/PPHS were all short until 2026-09-01.
    """
    entry = RULES["classes"][cid]
    sched = _sched(cid)
    assert sched["window_source"] == "class_default", "no SMILES -> no Tg -> class window"
    dT = float(entry.get("cool_block_dT_K") or 25.0)
    assert sched["tg_t_high_K"] + dT <= sched["T_anneal_high_K"], (
        f"{cid}: sweep top {sched['tg_t_high_K']} K needs a ceiling of at least "
        f"{sched['tg_t_high_K'] + dT} K, have {sched['T_anneal_high_K']} K"
    )


@pytest.mark.parametrize("cid", sorted(RULES["classes"]))
def test_class_ceilings_are_self_consistent_without_being_auto_raised(cid):
    """Stronger than the test above, and the reason the five class ceilings were edited by hand
    rather than left to the sweep term. The term is a backstop for a class whose window is later
    widened without its ceiling following; if it BINDS today it means the shipped constants are
    still internally inconsistent and something is being silently patched at runtime."""
    sched = _sched(cid)
    assert sched["ceiling_source"] != "sweep_start_headroom", (
        f"{cid}: the class ceiling is being auto-raised to "
        f"{sched['T_anneal_high_K']} K at runtime -- fix annealing_T_high_K in the data file"
    )


@pytest.mark.parametrize("cid", sorted(RULES["classes"]))
def test_curated_member_ceiling_clears_its_derived_sweep_top(cid):
    """The per-SMILES path. A curated member's window is derived from its OWN measured Tg
    (Tg+270) while its ceiling comes from the class T_equil (+100), so the two coincide only
    when Tg < T_equil-195. Eight of the 43 members failed that -- PMMA, PAA, PS, P2VP, PVC,
    BPA-PC, PPO/PPE, PMHS -- each short by 3-25 K."""
    entry = RULES["classes"][cid]
    dT = float(entry.get("cool_block_dT_K") or 25.0)
    for name, smis in (entry.get("member_smiles") or {}).items():
        if not smis:
            continue
        sched = _sched(cid, smiles=smis[0])
        assert sched["tg_t_high_K"] + dT <= sched["T_anneal_high_K"], (
            f"{cid}/{name}: derived sweep top {sched['tg_t_high_K']} K exceeds ceiling "
            f"{sched['T_anneal_high_K']} K"
        )
        assert sched["tg_start_T_K"] == sched["tg_t_high_K"]


def test_an_explicit_window_override_never_moves_the_ceiling():
    """tg_t_high_K is hashed to the THERMAL stage (workflow_engine.PARAMETER_STAGE); the anneal
    ceiling shapes the EQUILIBRATION chain. Letting an explicit override feed the ceiling would
    rewrite the equilibration chain under an unchanged equilibration _input_hash -- the
    over-dedupe trap where a store serves one run's cell for another's. A DERIVED window is
    safe because it is a pure function of the SMILES, which is already build-hashed."""
    baseline = _sched("PIMN", smiles="*CCN*")
    override = _sched("PIMN", smiles="*CCN*", tg_t_high_K=900)
    assert override["tg_t_high_K"] == 900
    assert override["T_anneal_high_K"] == baseline["T_anneal_high_K"]
    assert override["ceiling_source"] != "sweep_start_headroom"
    # No guaranteed waypoint at 900 K, so no tag -- the thermal stage reheats instead of
    # starting from a cell that may not exist.
    assert override["tg_start_T_K"] is None


# ─── the cooldown runs at this class's own Tg-sweep rate ──────────────────────────
#
# cool_block and the Tg staircase are ONE continuous descent since the melt-start sweep
# (2026-09-01): cool_block ramps the annealed melt down to tg_t_high_K and writes the cell the
# staircase starts from, and the staircase continues to tg_t_low_K. Running the two halves at
# different rates puts a rate discontinuity in the middle of one trajectory, and glass density
# is rate-dependent -- ~1.1% per DECADE, measured over 21 archived multi-rate sweeps across 8
# chemistries. Matching them also makes a density-only run (which has no staircase) produce a
# glass with the same thermal history as a Tg run's.


@pytest.mark.parametrize("cid", sorted(RULES["classes"]))
def test_cooldown_rate_matches_the_classes_own_sweep_rate(cid):
    import stage_params as sp
    entry = RULES["classes"][cid]
    rates = entry.get("tg_rates_K_per_ns")
    if not rates:
        pytest.skip(f"{cid} configures no Tg rates")
    dt = entry.get("dt_fs", 1.0)
    dT = entry.get("cool_block_dT_K") or 25.0
    hold = sp.rate_matched_cool_block_hold_steps(entry, dt, dT)
    executed = dT / (hold * dt * 1e-06)
    expected = rates[sp.select_primary_tg_rate_index(entry)]
    assert abs(executed - expected) < 0.6, (
        f"{cid}: cool_block executes {executed:.1f} K/ns against a sweep at {expected} K/ns"
    )


@pytest.mark.parametrize("cid", sorted(RULES["classes"]))
def test_no_class_pins_cool_block_hold_steps(cid):
    """PACR (400,000) and PKTN (300,000) pinned it until 2026-09-01, both to slow cooling and
    clear UNDER_ANNEALED_COOLING, and both notes recorded themselves as unvalidated hypotheses.
    Neither could have worked -- halving the rate buys ~0.33% of density against 3-9% shortfalls
    -- and the gate they answered is now advisory. A pin here silently desynchronises the
    cooldown from the staircase, so it has to be a deliberate act with a note, not a leftover."""
    entry = RULES["classes"][cid]
    assert "cool_block_hold_steps" not in entry, (
        f"{cid} pins cool_block_hold_steps, overriding the sweep-rate match"
    )


def test_the_primary_rate_index_is_shared_with_do_thermal():
    """do_thermal picks the sweep rate and _resolve_equil_params picks the cooldown rate. They
    are the same descent, so they read the same function -- this is the guard against the two
    re-deriving it and drifting."""
    import stage_params as sp
    import run_campaign as rc
    assert rc.select_primary_tg_rate_index is sp.select_primary_tg_rate_index
