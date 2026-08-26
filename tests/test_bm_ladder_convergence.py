"""assess_ladder_convergence: promotes the plateau_confirmed/leave-one-out/B0'-band
diagnostics in extract_bulk_modulus_murnaghan.py from warning-only text into a real,
additive bm_convergence_verdict signal (never folded into bm_gate_verdict's own
BM_REPORTABLE/BM_FALLBACK_DEFORM/BM_INADMISSIBLE contract).

Confidence split is deliberately asymmetric: decision_policy.json's own
rationale_bm_admissibility says leave-one-out dB0 is "emitted without a threshold...
not yet shown to be pathological, and no archived or live run carries
leave_one_out_refits to calibrate against" -- so loo_unstable/b0_prime_out_of_band
must never auto-widen the ladder (confidence=low) on their own. plateau_confirmed=False
is a self-consistency property of the fit under trimming, not an archive-calibrated
accuracy claim, so it alone drives confidence=high.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"))

from extract_bulk_modulus_murnaghan import assess_ladder_convergence  # noqa: E402


def test_all_checks_pass_is_converged():
    r = assess_ladder_convergence(plateau_confirmed=True, loo_max_dB0_pct=2.0, b0_prime=8.0)
    assert r["bm_convergence_verdict"] == "BM_LADDER_CONVERGED"
    assert r["bm_convergence_reasons"] == []
    assert r["bm_convergence_confidence"] == "high"


def test_plateau_not_confirmed_is_high_confidence():
    r = assess_ladder_convergence(plateau_confirmed=False, loo_max_dB0_pct=2.0, b0_prime=8.0)
    assert r["bm_convergence_verdict"] == "BM_LADDER_NOT_CONVERGED"
    assert r["bm_convergence_reasons"] == ["plateau_not_confirmed"]
    assert r["bm_convergence_confidence"] == "high"


def test_loo_unstable_alone_is_low_confidence():
    r = assess_ladder_convergence(plateau_confirmed=True, loo_max_dB0_pct=15.0, b0_prime=8.0)
    assert r["bm_convergence_verdict"] == "BM_LADDER_NOT_CONVERGED"
    assert r["bm_convergence_reasons"] == ["loo_unstable"]
    assert r["bm_convergence_confidence"] == "low"


def test_b0_prime_out_of_band_alone_is_low_confidence():
    r = assess_ladder_convergence(plateau_confirmed=True, loo_max_dB0_pct=2.0, b0_prime=25.0)
    assert r["bm_convergence_verdict"] == "BM_LADDER_NOT_CONVERGED"
    assert r["bm_convergence_reasons"] == ["b0_prime_out_of_band"]
    assert r["bm_convergence_confidence"] == "low"


def test_loo_and_b0_prime_combined_without_plateau_still_low_confidence():
    """Neither diagnostic is calibrated on its own, and combining two uncalibrated
    signals doesn't manufacture calibration -- only plateau_confirmed=False does."""
    r = assess_ladder_convergence(plateau_confirmed=True, loo_max_dB0_pct=15.0, b0_prime=25.0)
    assert r["bm_convergence_verdict"] == "BM_LADDER_NOT_CONVERGED"
    assert set(r["bm_convergence_reasons"]) == {"loo_unstable", "b0_prime_out_of_band"}
    assert r["bm_convergence_confidence"] == "low"


def test_plateau_not_confirmed_plus_other_reasons_stays_high_confidence():
    r = assess_ladder_convergence(plateau_confirmed=False, loo_max_dB0_pct=15.0, b0_prime=25.0)
    assert r["bm_convergence_verdict"] == "BM_LADDER_NOT_CONVERGED"
    assert set(r["bm_convergence_reasons"]) == {
        "plateau_not_confirmed", "loo_unstable", "b0_prime_out_of_band"}
    assert r["bm_convergence_confidence"] == "high"


def test_none_plateau_confirmed_is_not_treated_as_false():
    """plateau_confirmed=None (no window trim was ever evaluated) must not silently
    read as a convergence failure."""
    r = assess_ladder_convergence(plateau_confirmed=None, loo_max_dB0_pct=2.0, b0_prime=8.0)
    assert r["bm_convergence_verdict"] == "BM_LADDER_CONVERGED"
