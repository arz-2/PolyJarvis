"""Unit tests for compute_tau_eff (autocorrelation time via batch means).

compute_tau_eff underpins the error bars on every extracted property, so a
silent regression here would quietly mis-state simulation uncertainty.

Note: this estimator's absolute normalisation is implementation-specific, so the
tests assert the *contract* that matters physically -- zero for a flat series,
non-negative and small for uncorrelated noise, and strictly larger for a
correlated series -- rather than pinning an exact magnitude.
"""
import numpy as np

from analysis_utils import compute_tau_eff


def test_constant_series_returns_zero():
    """A flat series has no variance, so tau is defined to be zero."""
    tau_frames, tau_frac = compute_tau_eff(np.full(1024, 0.95))
    assert tau_frames == 0.0
    assert tau_frac == 0.0


def test_white_noise_tau_is_small_and_nonnegative():
    """Uncorrelated samples carry little memory -> small, non-negative tau."""
    rng = np.random.default_rng(0)
    x = rng.standard_normal(8192)
    tau_frames, tau_frac = compute_tau_eff(x)
    assert tau_frames >= 0.0
    assert tau_frames < 1.0
    assert tau_frac == tau_frames / len(x)


def test_correlated_series_has_larger_tau_than_white_noise():
    """An AR(1) process with strong memory must report a larger tau."""
    rng = np.random.default_rng(1)
    n = 8192
    phi = 0.9
    noise = rng.standard_normal(n)
    x = np.empty(n)
    x[0] = noise[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + noise[i]

    tau_white, _ = compute_tau_eff(rng.standard_normal(n))
    tau_corr, _ = compute_tau_eff(x)
    assert tau_corr > tau_white
