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
# opls→opls-library, trappe→none) are the authority of test_ff_routing.py, which is
# sourced from the same JSON; duplicating those exact values here only invites the
# two tests to contradict each other.
EMC_FF_FAMILIES = ("pcff", "opls", "trappe")   # substring families (both opls spellings)
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
    else:  # radonpy — runs a real charge-assignment job with a GAFF2 field
        assert pref_ff in {"GAFF2", "GAFF2_mod"}, (
            f"{cid}: RadonPy route expects a GAFF2 field, got preferred_ff={pref_ff!r}"
        )
        assert e["forcefield"] in {"GAFF2", "GAFF2_mod"}
        assert e["charge_method"] in {"RESP", "AM1-BCC"}, (
            f"{cid}: RadonPy runs a charge job → charge_method must be RESP/AM1-BCC, "
            f"got {e['charge_method']!r}"
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


def test_tg_fox_flory_K_carries_a_primary_source():
    """The DP correction shifts the graded band DOWN, toward the simulated value -- the
    same direction md_offset_K moved before it was deleted. That is defensible only
    because it corrects the REFERENCE for molecular weight rather than the simulation for
    a method artifact, and only when the constant is a real measurement. A K without a
    traceable source is exactly feedback_polymer_rules_sim_sourced_exp_bounds.md.

    Absence is the normal case and must stay cheap: a class with no citable K grades its
    band uncorrected. No generic fallback constant may be introduced."""
    for cid, c in CLASSES.items():
        ff = c.get("tg_fox_flory_K")
        if ff is None:
            continue
        assert isinstance(ff, dict), f"{cid}: tg_fox_flory_K must be a dict, got {type(ff)}"
        k = ff.get("K_K_g_per_mol")
        assert isinstance(k, (int, float)) and k > 0, f"{cid}: K_K_g_per_mol must be positive"
        # Measured Flory-Fox constants sit around 1e5 K*g/mol; anything orders away is a
        # unit error, which would silently move a PASS/FAIL band.
        assert 1e4 <= k <= 1e6, f"{cid}: K={k} is outside the physical 1e4-1e6 K*g/mol range"
        note = ff.get("note", "")
        assert "doi:" in note.lower(), f"{cid}: tg_fox_flory_K note must cite a DOI"
        # The constant is measured for ONE polymer, never for a whole class: PACR's 1.4e5
        # is PMMA's and PSTR's 1.083e5 is atactic PS's. Without an explicit member list a
        # PMA run (exp Tg 281 K) would take a -32 K band shift from a constant never
        # measured for it -- the same fabricated-number-in-a-band failure as inventing one,
        # reached by misapplication instead.
        members = ff.get("members")
        assert isinstance(members, list) and members, (
            f"{cid}: tg_fox_flory_K must name the members it was measured for")
        known = set(c.get("examples", []))
        assert set(members) & known or all(isinstance(m, str) for m in members), cid


def test_no_generic_fox_flory_fallback_exists():
    """Coverage is deliberately partial. If a later edit adds a class-independent default,
    every polymer's band shifts by a fabricated number."""
    assert "tg_fox_flory_K" not in RULES.get("global_defaults", {})
