"""chemistry_policy — comparing a molecule's real chemistry against its class's constants.

The premise, and the reason a disagreement is worth reporting at all: across all 43
`member_smiles` in guides/polymer_rules.json, the electrostatics implied by the molecule's
own functional groups agrees with its class's declared value 43/43. The proxy is exact on
curated chemistry, so it is not noisy -- when it breaks on a novel polymer, something real
has happened.

Everything here is advisory. These checks emit findings; they never rewrite a class
constant. The class table is curated against real validation runs, while this is a rule over
SMARTS, and the repo's standing discipline is that code owns decisions and advisories inform
them.

Pure logic over profile dicts -- no RDKit, no conda -- so it runs in the default suite.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import chemistry_policy as cp  # noqa: E402


def _profile(**over):
    base = {"functional_groups": [], "polarity_class": "apolar",
            "implied_electrostatics": "lj_cut", "hbond_donors": 0, "formal_charge": 0}
    base.update(over)
    return base


def _fg(gid, polarity, location="pendant"):
    return {"id": gid, "polarity": polarity, "location": location}


def _codes(profile, class_entry):
    return [f["code"] for f in cp.consistency(profile, class_entry)["findings"]]


# --- electrostatics ---------------------------------------------------------
def test_agreement_produces_no_electrostatics_finding():
    assert cp.check_electrostatics(_profile(), {"electrostatics": "lj_cut"}) is None


def test_polar_chemistry_under_lj_cut_is_a_warning():
    """The one that can be a physics error: truncating Coulomb on a polar polymer discards
    the interaction that dominates cohesive energy."""
    f = cp.check_electrostatics(
        _profile(implied_electrostatics="pppm",
                 functional_groups=[_fg("hydroxyl_alcohol", "polar_protic")]),
        {"electrostatics": "lj_cut"})
    assert f["code"] == "CHEM_ELECTROSTATICS_UNDERSPECIFIED"
    assert f["severity"] == cp.WARNING
    assert f["suggested_override"] == {"electrostatics": "pppm"}
    assert "hydroxyl_alcohol (pendant)" in f["detail"]


def test_pppm_on_an_apolar_molecule_is_only_an_advisory():
    """Wasteful, not wrong -- so it must not carry the same severity as the reverse."""
    f = cp.check_electrostatics(_profile(implied_electrostatics="lj_cut"),
                                {"electrostatics": "pppm"})
    assert f["code"] == "CHEM_ELECTROSTATICS_OVERSPECIFIED"
    assert f["severity"] == cp.ADVISORY
    assert f["suggested_override"] is None


def test_unknown_composition_produces_no_electrostatics_finding():
    """Fail closed: with no implied value there is nothing to compare, and inventing one
    would be worse than staying quiet."""
    assert cp.check_electrostatics(_profile(implied_electrostatics=None),
                                   {"electrostatics": "lj_cut"}) is None


def test_a_class_with_no_declared_electrostatics_is_not_second_guessed():
    assert cp.check_electrostatics(_profile(), {}) is None


# --- hydrogen bonding -------------------------------------------------------
def test_protic_groups_with_donors_raise_the_hbond_advisory():
    f = cp.check_hbond_network(
        _profile(hbond_donors=1, functional_groups=[_fg("amide_NH", "polar_protic", "backbone")]),
        {})
    assert f["code"] == "CHEM_HBOND_NETWORK"
    assert f["groups"] == ["amide_NH"]


def test_acceptors_alone_are_not_an_hbond_network():
    """An ester accepts but cannot donate; there is no inter-chain network without a donor."""
    assert cp.check_hbond_network(
        _profile(hbond_donors=0, functional_groups=[_fg("ester", "polar_aprotic")]), {}) is None


def test_donor_count_without_a_protic_group_does_not_fire():
    assert cp.check_hbond_network(_profile(hbond_donors=2), {}) is None


# --- pendant chemistry ------------------------------------------------------
def test_pendant_polar_groups_are_reported_as_context():
    f = cp.check_pendant_chemistry(
        _profile(functional_groups=[_fg("ester", "polar_aprotic", "pendant")]), {})
    assert f["code"] == "CHEM_PENDANT_POLAR_GROUPS"
    assert f["severity"] == cp.ADVISORY


def test_backbone_polar_groups_are_not_pendant_findings():
    """A backbone ester DID inform the class label -- that is what makes PLA a polyester."""
    assert cp.check_pendant_chemistry(
        _profile(functional_groups=[_fg("ester", "polar_aprotic", "backbone")]), {}) is None


def test_an_apolar_pendant_group_is_not_reported():
    """PS's pendant phenyl is not chemistry the class missed; PSTR is named for it."""
    assert cp.check_pendant_chemistry(
        _profile(functional_groups=[_fg("benzene_ring", "apolar", "pendant")]), {}) is None


# --- ionic ------------------------------------------------------------------
def test_a_charged_repeat_unit_is_a_warning():
    f = cp.check_ionic(_profile(polarity_class="ionic", formal_charge=-1,
                                functional_groups=[_fg("sulfonate", "ionic")]), {})
    assert f["code"] == "CHEM_IONIC_SPECIES" and f["severity"] == cp.WARNING


def test_a_neutral_repeat_unit_is_not():
    assert cp.check_ionic(_profile(), {}) is None


# --- build risk -------------------------------------------------------------
def test_alkene_raises_the_measured_build_risk_advisory():
    """4.1x baseline on the 735 PI1070 units with no N-carbonyl group -- the strongest
    signal in the sweep, and absent from guides/ff_moiety_rules.json entirely."""
    f = cp.check_build_risk(_profile(functional_groups=[_fg("alkene", "apolar", "backbone")]), {})
    assert f["code"] == "CHEM_BUILD_RISK"
    assert f["worst_group"] == "alkene"
    assert "with-ff-probe" in f["recommend"]


def test_build_risk_is_advisory_not_a_blocking_rule():
    """It is correlation over one population, not the per-field tried/failed measurement
    guides/ff_moiety_rules.json demands of a probe trigger. Promoting it to a hard rule
    would let an unmeasured correlation refuse a build."""
    f = cp.check_build_risk(_profile(functional_groups=[_fg("alkene", "apolar")]), {})
    assert f["severity"] == cp.ADVISORY
    assert f["suggested_override"] is None


def test_a_group_with_no_measured_risk_does_not_fire():
    assert cp.check_build_risk(
        _profile(functional_groups=[_fg("ether_aliphatic", "polar_aprotic")]), {}) is None


def test_every_build_risk_group_carries_its_evidence():
    for gid, entry in cp.BUILD_RISK_GROUPS.items():
        assert entry["n"] >= 20, f"{gid}: too few observations to quote a rate"
        assert entry["fail_rate"] > cp.BUILD_RISK_BASELINE, gid
        assert entry["why"], gid


# --- the verdict ------------------------------------------------------------
def test_verdict_is_consistent_when_only_advisories_fire():
    """Advisory findings are context, not a problem -- PMMA has a pendant ester by design."""
    v = cp.consistency(_profile(functional_groups=[_fg("ester", "polar_aprotic", "pendant")]),
                       {"electrostatics": "lj_cut", "_": None})
    assert "CHEM_PENDANT_POLAR_GROUPS" in [f["code"] for f in v["findings"]]


def test_verdict_is_review_when_a_warning_fires():
    v = cp.consistency(
        _profile(implied_electrostatics="pppm",
                 functional_groups=[_fg("hydroxyl_alcohol", "polar_protic")]),
        {"electrostatics": "lj_cut"})
    assert v["verdict"] == "review" and v["n_warnings"] == 1


def test_a_missing_profile_is_unavailable_not_consistent():
    """Silence must not read as a clean bill of health."""
    assert cp.consistency({}, {})["verdict"] == "unavailable"
    assert cp.consistency({"error": "unparseable"}, {})["verdict"] == "unavailable"


def test_consistency_never_returns_an_override_for_a_class_constant():
    """The whole module is advisory. Only check_electrostatics may even SUGGEST one, and it
    is the adjudicator -- not this code -- that decides whether to apply it."""
    v = cp.consistency(
        _profile(implied_electrostatics="pppm", hbond_donors=1, polarity_class="ionic",
                 formal_charge=-1,
                 functional_groups=[_fg("sulfonate", "ionic"), _fg("alkene", "apolar")]),
        {"electrostatics": "lj_cut"})
    suggested = [f["suggested_override"] for f in v["findings"] if f["suggested_override"]]
    assert suggested == [{"electrostatics": "pppm"}]


# --- melt margin: deliberately NOT checked here ------------------------------
def test_there_is_no_melt_margin_check():
    """A melt-margin check was written and removed; this pins the decision.

    T_equil_K is already derived per SMILES by stage_params.temperature_schedule -- for a
    novel repeat unit with a trustworthy Tg it is max(Tg + 200, 1.5 * Tg), with the class
    constant acting only as a floor. A check here would duplicate that while reading the
    class floor rather than the resolved value. Measured over all 1077 PI1070 units it fired
    once, on a `very_low`-confidence Tg the scheduler explicitly refuses to size from.

    If a melt-margin check is ever wanted again, it must read the RESOLVED schedule, not the
    class constant, and it must not fire on an untrustworthy estimate.
    """
    assert not hasattr(cp, "check_melt_margin")
    assert not hasattr(cp, "MELT_MARGIN_MIN_K")
    assert all(c.__name__ != "check_melt_margin" for c in cp.CHECKS)
