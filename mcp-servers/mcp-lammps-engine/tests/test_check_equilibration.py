"""Unit tests for the equilibration drift gate (_analyse_property).

This is the function behind the PASS / EXTEND / ESCALATE verdict. A false PASS
would let an unequilibrated system flow into Tg and modulus extraction.
"""
import numpy as np
import pandas as pd

from check_equilibration_comprehensive import _analyse_property, _analyse_energy_components

# representative thresholds (mirror the script defaults)
DRIFT_PCT = 1.0
DRIFT_PVALUE = 0.05
BLOCKS = 5


def test_flat_series_is_equilibrated():
    rng = np.random.default_rng(0)
    values = 0.95 + rng.normal(0, 1e-4, size=200)
    res = _analyse_property(values, "density", DRIFT_PCT, DRIFT_PVALUE, BLOCKS)
    assert res["drift"]["pass"] is True
    assert res["block_sem"]["pass"] is True
    assert res["equilibrated"] is True


def test_strong_drift_is_not_equilibrated():
    values = np.linspace(0.90, 1.10, 200)  # steady, significant upward trend
    res = _analyse_property(values, "density", DRIFT_PCT, DRIFT_PVALUE, BLOCKS)
    assert res["drift"]["pass"] is False
    assert res["equilibrated"] is False
    assert res["drift"]["drift_pct"] > DRIFT_PCT


def test_result_structure():
    values = 0.95 + np.zeros(100)
    res = _analyse_property(values, "density", DRIFT_PCT, DRIFT_PVALUE, BLOCKS)
    for key in ("mean", "n_points", "drift", "block_sem", "equilibrated"):
        assert key in res
    assert res["n_points"] == 100


# ─── gate B: per-energy-term drift ────────────────────────────────────────────
# Added after tracing RadonPy's own check_eq(), which gates bond/angle/dihedral/
# vdW/Kspace energies independently rather than only the aggregate total.


def test_flat_energy_components_all_pass():
    rng = np.random.default_rng(1)
    prod = pd.DataFrame({
        "E_bond": 500 + rng.normal(0, 0.05, size=200),
        "E_angle": 300 + rng.normal(0, 0.05, size=200),
        "E_vdwl": -800 + rng.normal(0, 0.05, size=200),
    })
    res = _analyse_energy_components(prod, DRIFT_PCT, DRIFT_PVALUE)
    assert res["pass"] is True
    assert set(res["components"]) == {"bond", "angle", "vdw"}
    assert all(c["pass"] for c in res["components"].values())


def test_one_drifting_component_fails_the_set():
    rng = np.random.default_rng(2)
    prod = pd.DataFrame({
        "E_bond": np.linspace(500, 550, 200),  # steady, significant upward trend
        "E_angle": 300 + rng.normal(0, 0.05, size=200),
    })
    res = _analyse_energy_components(prod, DRIFT_PCT, DRIFT_PVALUE)
    assert res["components"]["bond"]["pass"] is False
    assert res["components"]["angle"]["pass"] is True
    assert res["pass"] is False


def test_missing_columns_are_skipped_not_failed():
    prod = pd.DataFrame({"E_bond": 500 + np.zeros(50)})
    res = _analyse_energy_components(prod, DRIFT_PCT, DRIFT_PVALUE)
    assert set(res["components"]) == {"bond"}
    assert res["pass"] is True


def test_canceling_component_drift_fails_gate_b_even_when_total_is_flat():
    """The motivating case: bond energy relaxing down while vdW drifts up can net a
    flat TotEng. Gate B must catch this from the per-term check even though the
    aggregate-only _analyse_property call on TotEng would have passed."""
    n = 200
    rng = np.random.default_rng(3)
    bond = np.linspace(550, 500, n) + rng.normal(0, 0.05, n)   # drifting down
    vdwl = np.linspace(-850, -800, n) + rng.normal(0, 0.05, n)  # drifting up, canceling
    tot_eng = bond + vdwl  # ~flat by construction

    prod = pd.DataFrame({"E_bond": bond, "E_vdwl": vdwl, "TotEng": tot_eng})

    aggregate = _analyse_property(prod["TotEng"].values, "energy", DRIFT_PCT, DRIFT_PVALUE, BLOCKS)
    assert aggregate["equilibrated"] is True  # aggregate alone is fooled

    component = _analyse_energy_components(prod, DRIFT_PCT, DRIFT_PVALUE)
    assert component["pass"] is False  # gate B's per-term check is not fooled
    equilibrated = bool(aggregate["equilibrated"] and component["pass"])
    assert equilibrated is False


def test_every_term_is_judged_against_its_own_fluctuation_not_its_mean():
    """An energy term's mean carries an arbitrary force-field reference, so drift-as-a-percent-
    of-the-mean is a different bar for every term. aPS_1 (2026-09-09) is the worked example: vdW
    read 1.73% of a 1094 kcal/mol mean while the same drift is 0.32 of that term's own sigma.

    The same fractional drift must therefore get the same verdict whatever the term is called:
    both terms below drift ~1.7% of their mean, and each is decided by drift against its OWN
    fluctuation -- the noisy one passes, the quiet one fails.
    """
    rng = np.random.default_rng(11)
    n = 400
    trend = np.linspace(0, 18.0, n)
    prod = pd.DataFrame({
        "E_vdwl": 1094.0 + trend + rng.normal(0, 40.0, size=n),
        "E_dihed": 1094.0 + trend + rng.normal(0, 0.5, size=n),
    })
    res = _analyse_energy_components(prod, DRIFT_PCT, DRIFT_PVALUE)
    vdw, dihed = res["components"]["vdw"], res["components"]["dihedral"]

    for term in (vdw, dihed):
        assert term["criterion"] == "drift_sigma"
        assert term["drift_pct"] > 1.0, "the fixture must be one the OLD relative test would fail"

    assert vdw["drift_sigma"] < 1.0
    assert vdw["pass"] is True, "failed on a drift smaller than the term's own thermal noise"
    assert dihed["drift_sigma"] > 1.0
    assert dihed["pass"] is False, "a drift larger than the term's own noise must still fail"


def test_a_large_fractional_drift_passes_when_it_sits_inside_the_fluctuation():
    """The case the old per-term drift_pct test got wrong for bonded terms: a signed dihedral
    residual whose mean sits near zero turns a tiny absolute drift into a large percentage."""
    rng = np.random.default_rng(14)
    n = 400
    prod = pd.DataFrame({
        "E_dihed": -20.0 + np.linspace(0, 2.0, n) + rng.normal(0, 30.0, size=n),
    })
    dihed = _analyse_energy_components(prod, DRIFT_PCT, DRIFT_PVALUE)["components"]["dihedral"]
    assert dihed["drift_pct"] > 1.0
    assert dihed["drift_sigma"] < 1.0
    assert dihed["pass"] is True


def test_a_vdw_drift_larger_than_its_fluctuation_still_fails():
    """The new criterion must remain capable of failing -- a gate that cannot fail is the
    fail-open shape removed from this pipeline on 2026-09-09. This is also why RadonPy's
    absolute 30.0 kcal/mol bound was NOT adopted: measured across five melt holds its
    statistic ran 2.08-11.09, so it could never have bound any of them.
    """
    rng = np.random.default_rng(12)
    n = 400
    prod = pd.DataFrame({
        "E_vdwl": 1094.0 + np.linspace(0, 300.0, n) + rng.normal(0, 20.0, size=n),
    })
    res = _analyse_energy_components(prod, DRIFT_PCT, DRIFT_PVALUE)
    vdw = res["components"]["vdw"]
    assert vdw["drift_sigma"] > 1.0
    assert vdw["pass"] is False
    assert res["pass"] is False


def test_every_term_reports_the_criterion_it_was_judged_on():
    """Every component says which test decided it, so a reader never infers it from the
    numbers -- drift_pct stays reported for continuity with runs graded before 2026-09-13."""
    rng = np.random.default_rng(13)
    n = 300
    prod = pd.DataFrame({
        "E_vdwl": 1000 + rng.normal(0, 10, size=n),
        "E_coul": -500 + rng.normal(0, 10, size=n),
        "E_angle": 300 + rng.normal(0, 1, size=n),
    })
    res = _analyse_energy_components(prod, DRIFT_PCT, DRIFT_PVALUE)
    for label in ("vdw", "coul", "angle"):
        assert res["components"][label]["criterion"] == "drift_sigma"
    for label in ("vdw", "coul", "angle"):
        assert "drift_pct" in res["components"][label]
        assert "threshold" in res["components"][label]


# --- drift significance must account for the series' own autocorrelation --------------------
from check_equilibration_comprehensive import _drift_significance  # noqa: E402
from scipy import stats as _sp  # noqa: E402


def _ar1(n, phi, sigma, seed):
    """An AR(1) series: correlated noise with NO trend at all."""
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + rng.normal(0, sigma)
    return x


def test_correlated_noise_is_not_certified_as_a_trend():
    """iPMMA_1, 2026-09-10. A slow excursion filled the graded window, the regression read it
    as a trend, and the naive p-value certified it at 1.85e-42 off ~22 independent samples.
    Strongly autocorrelated noise carries no trend; the corrected p must not claim one.
    """
    n = 1500
    values = 100.0 + _ar1(n, phi=0.99, sigma=0.05, seed=7)
    x = np.arange(n, dtype=float)
    slope, _, _, p_naive, stderr = _sp.linregress(x, values)
    p_eff, tau, n_eff = _drift_significance(values, slope, stderr, n, p_naive)

    assert n_eff < n / 10, f"autocorrelation not detected (n_eff={n_eff} of {n})"
    assert p_eff > p_naive, "the correction must never make a p-value smaller"
    assert p_eff > 0.01, f"correlated noise still certified as a trend (p_eff={p_eff})"


def test_a_real_trend_well_above_the_noise_still_registers():
    """The correction must not silence everything -- a trend large against the fluctuation,
    with enough independent samples behind it, has to stay significant."""
    n = 1500
    values = 100.0 + np.linspace(0, 20.0, n) + _ar1(n, phi=0.5, sigma=0.05, seed=8)
    x = np.arange(n, dtype=float)
    slope, _, _, p_naive, stderr = _sp.linregress(x, values)
    p_eff, tau, n_eff = _drift_significance(values, slope, stderr, n, p_naive)
    assert p_eff < 0.01, f"a genuine strong trend was silenced (p_eff={p_eff}, n_eff={n_eff})"


def test_the_correction_only_ever_loosens():
    """The property that makes this safe to ship onto already-graded runs: it can turn a FAIL
    into a PASS and never the reverse, so no previously passing run can newly fail."""
    for phi, seed in ((0.0, 1), (0.5, 2), (0.9, 3), (0.99, 4)):
        n = 800
        values = 50.0 + np.linspace(0, 1.0, n) + _ar1(n, phi=phi, sigma=0.02, seed=seed)
        x = np.arange(n, dtype=float)
        slope, _, _, p_naive, stderr = _sp.linregress(x, values)
        p_eff, _, _ = _drift_significance(values, slope, stderr, n, p_naive)
        assert p_eff >= p_naive - 1e-12, f"phi={phi}: correction tightened the test"


def test_the_gated_fields_record_both_p_values():
    """p_value stays the naive one for comparability with runs graded before 2026-09-10;
    p_value_eff is what the verdict is made on."""
    rng = np.random.default_rng(21)
    values = 100.0 + rng.normal(0, 0.1, size=400)
    res = _analyse_property(values, "density", DRIFT_PCT, DRIFT_PVALUE, 10)
    for key in ("p_value", "p_value_eff", "tau_frames", "n_eff"):
        assert key in res["drift"], f"{key} missing from the drift record"
