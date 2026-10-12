"""select_stable_window must actually be able to trim the ladder size runs use.

sPVC_1, 2026-09-10. min_points defaulted to 5, so for a 5-point ladder --
bm_pressures_atm = [-1000, 0, 1500, 3000, 5000], which every run in the stereo_r2
benchmark uses -- max_trim = n - min_points = 0 and the untrimmed window was the ONLY
candidate ever fitted. sPVC_1's -1000 atm point had cavitated (relaxation 169 frames vs
2.9-4.9 for the other four, n_eff 29 vs 510-869), the reported B0 was biased 25.7% low,
and "no trim improved r_squared"/plateau_confirmed=True reported a search that never ran.

The ladder below is that run's own measured (V, P), not a synthetic one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis_scripts"))
from extract_bulk_modulus_murnaghan import select_stable_window  # noqa: E402

# data/sPVC_1/attempts/mechanical/attempt-0001/raw/mechanical.json
SPVC_VOLUMES_A3 = [67137.66, 63165.68, 60620.19, 58872.74, 57013.36]
SPVC_PRESSURES_ATM = [-1000.0, 0.0, 1500.0, 3000.0, 5000.0]
SPVC_PRESSURES_GPA = [-0.101325, 0.0, 0.151988, 0.303975, 0.506625]
SPVC_FLAGS = {0: ["possible cavitation/discontinuity in this interval."],
              1: ["possible cavitation/discontinuity in this interval."]}


def test_the_cavitated_tension_point_is_dropped_from_a_five_point_ladder():
    sel = select_stable_window(SPVC_VOLUMES_A3, SPVC_PRESSURES_GPA,
                               SPVC_PRESSURES_ATM, SPVC_FLAGS)
    assert sel["trim_total"] == 1, "the ladder was not trimmed at all"
    assert sel["n_points"] == 4
    assert 0 in sel["excluded_idx"], "the flagged tension point was not the one dropped"
    # 2.5446 GPa untrimmed -> 3.1975 trimmed; r_squared 0.998617 -> 0.999887.
    assert sel["r_squared"] > 0.9998
    assert 3.1 < sel["B0_GPa"] < 3.3


def test_min_points_still_allows_a_meaningful_murnaghan_fit():
    """Murnaghan has three free parameters, so 4 points is the floor that leaves any
    residual degree of freedom. The trim must never go below it."""
    sel = select_stable_window(SPVC_VOLUMES_A3, SPVC_PRESSURES_GPA,
                               SPVC_PRESSURES_ATM, SPVC_FLAGS)
    assert sel["n_points"] >= 4


def test_a_ladder_above_the_acceptance_bar_is_left_untrimmed():
    """The fix must not make the selector trim-happy. aPS_1 (untrimmed r_squared
    0.999665) and PLLA_1 (0.999613) both clear r2_acceptable, so their numbers were
    unchanged by this default moving -- that is what kept the three runs comparable."""
    clean = SPVC_VOLUMES_A3[1:]           # the same ladder minus the cavitated point
    sel = select_stable_window(clean, SPVC_PRESSURES_GPA[1:],
                               SPVC_PRESSURES_ATM[1:], {}, min_points=3)
    assert sel["trim_total"] == 0
    assert sel["n_points"] == 4


def test_no_searchable_trim_reports_unknown_not_confirmed():
    """A ladder too short to trim must not claim plateau_confirmed=True -- that asserts
    a stability nothing tested, the same vacuous-check shape this file exists to catch."""
    sel = select_stable_window(SPVC_VOLUMES_A3, SPVC_PRESSURES_GPA,
                               SPVC_PRESSURES_ATM, SPVC_FLAGS, min_points=5)
    assert sel["trim_total"] == 0
    assert sel["plateau_confirmed"] is None, "claimed a plateau it could not have tested"
    assert "not evidence" in sel["selection_note"].lower()


# --- the convergence verdict must not re-punish the point screening removed -----------------
from extract_bulk_modulus_murnaghan import assess_ladder_convergence  # noqa: E402


def test_the_excluded_point_does_not_make_the_trimmed_fit_look_unstable():
    """Half of the sPVC_1 defect: trimming fixed the FIT, the verdict still failed.

    Leave-one-out runs on the untrimmed ladder -- that is what lets it find a contaminated
    point at all. But the verdict describes the fit being reported, which has already had that
    point removed. Feeding it the excluded point's own dB0 reports the screening's success as
    the fit's instability: sPVC_1 came out BM_REPORTABLE at B0=3.1975 (r^2 0.999887, within
    2.9% of the independent fluctuation modulus) and was stamped BM_LADDER_NOT_CONVERGED /
    loo_unstable on the strength of the same 25.7% that justified the trim.
    """
    all_points = 25.66      # dropping the cavitated -1000 atm point
    retained = 2.34         # the largest shift among the four points actually fitted

    stale = assess_ladder_convergence(plateau_confirmed=True,
                                      loo_max_dB0_pct=all_points, b0_prime=8.0561)
    assert stale["bm_convergence_verdict"] == "BM_LADDER_NOT_CONVERGED"
    assert "loo_unstable" in stale["bm_convergence_reasons"]

    fixed = assess_ladder_convergence(plateau_confirmed=True,
                                      loo_max_dB0_pct=retained, b0_prime=8.0561)
    assert fixed["bm_convergence_verdict"] == "BM_LADDER_CONVERGED"
    assert fixed["bm_convergence_reasons"] == []
    assert fixed["bm_convergence_confidence"] == "high"


def test_a_genuinely_unstable_retained_ladder_still_fails():
    """The re-scoping must not become a way to pass everything: if a point the fit KEEPS
    dominates the answer, that is real instability and must still fail."""
    v = assess_ladder_convergence(plateau_confirmed=True,
                                  loo_max_dB0_pct=18.0, b0_prime=8.0)
    assert v["bm_convergence_verdict"] == "BM_LADDER_NOT_CONVERGED"
    assert v["bm_convergence_reasons"] == ["loo_unstable"]


def test_an_untrimmed_ladder_is_judged_on_all_of_its_points():
    """With nothing excluded, retained == all, so behaviour is unchanged from before."""
    for pct in (2.0, 25.66):
        expected = "BM_LADDER_CONVERGED" if pct <= 10.0 else "BM_LADDER_NOT_CONVERGED"
        assert assess_ladder_convergence(True, pct, 8.0)["bm_convergence_verdict"] == expected
