"""D-07: extract_bulk_modulus_murnaghan.py's per-pressure-point volume SEM must be
autocorrelation-corrected (compute_tau_eff/effective_sample_size), not naive std/sqrt(n).

Motivation: consecutive NPT dumps are correlated, so a naive SEM understates the true
uncertainty on the mean volume at each pressure point -- this is what a prospective
mechanical_sampling_factor pricing decision (remedy_economics.py, Class C) needs to be
honest about before deciding whether a second, longer rung is worth its wall time. This is
additive to and distinct from fit_murnaghan()'s covariance-based B0_sem_GPa, which reflects
residual misfit of the means around the Murnaghan form, not sampling noise on any one mean.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"))

from extract_bulk_modulus_murnaghan import extract_mean_volume  # noqa: E402


def _write_log(path, values):
    lines = ["Step Volume"]
    for i, v in enumerate(values):
        lines.append(f"{i} {v:.6f}")
    path.write_text("\n".join(lines) + "\n")


def test_autocorrelated_series_gets_a_larger_sem_than_naive_std_over_sqrt_n(tmp_path):
    """Repeat each of 50 independent draws k=4 times consecutively (a stand-in for a
    correlated NPT trajectory). The population std is unchanged by exact repetition, but the
    real independent-sample count drops to ~n/k, so the corrected SEM should come out
    ~sqrt(k) larger than the naive std/sqrt(n) an uncorrected calculation would report."""
    rng = np.random.default_rng(7)
    k = 4
    unique = rng.normal(1000.0, 5.0, 50)
    correlated = np.repeat(unique, k)

    log_path = tmp_path / "p_test.log"
    _write_log(log_path, correlated)

    v_mean, v_std, n_prod, tau_frames, n_eff, vol_sem = extract_mean_volume(
        str(log_path), eq_fraction=1.0)

    assert n_prod == len(correlated)
    naive_sem = v_std / math.sqrt(n_prod)
    assert tau_frames > 1.0, "exact repetition must be detected as autocorrelation"
    assert n_eff < n_prod
    # corrected SEM ~ sqrt(k) times the naive (uncorrected) SEM
    ratio = vol_sem / naive_sem
    assert ratio == pytest.approx(math.sqrt(k), rel=0.35)


def test_independent_series_leaves_sem_close_to_naive(tmp_path):
    """No autocorrelation to correct for -- tau_frames should sit near 1 and the corrected
    SEM should be close to the naive std/sqrt(n) (the historical, uncorrected behavior)."""
    rng = np.random.default_rng(11)
    values = rng.normal(1000.0, 5.0, 200)

    log_path = tmp_path / "p_indep.log"
    _write_log(log_path, values)

    v_mean, v_std, n_prod, tau_frames, n_eff, vol_sem = extract_mean_volume(
        str(log_path), eq_fraction=1.0)

    naive_sem = v_std / math.sqrt(n_prod)
    assert tau_frames == pytest.approx(1.0, abs=0.5)
    assert vol_sem == pytest.approx(naive_sem, rel=0.3)


def test_eq_fraction_discards_burn_in_rows(tmp_path):
    """Only the production window (last eq_fraction of rows) should feed the SEM calc --
    burn-in rows at a very different volume must not contaminate it."""
    rng = np.random.default_rng(3)
    burn_in = np.full(100, 500.0)  # far from the production mean; would skew v_mean if kept
    production = rng.normal(1000.0, 5.0, 100)
    all_values = np.concatenate([burn_in, production])

    log_path = tmp_path / "p_burnin.log"
    _write_log(log_path, all_values)

    v_mean, v_std, n_prod, tau_frames, n_eff, vol_sem = extract_mean_volume(
        str(log_path), eq_fraction=0.5)

    assert n_prod == 100
    assert v_mean == pytest.approx(float(production.mean()), rel=0.05)
