"""Unit tests for compute_tau_eff (autocorrelation time via batch means).

compute_tau_eff underpins the error bars on every extracted property, so a
silent regression here would quietly mis-state simulation uncertainty.
"""
import numpy as np

from analysis_utils import compute_tau_eff


def test_constant_series_returns_zero():
    """A flat series has no variance, so tau is defined to be zero."""
    tau_frames, tau_frac = compute_tau_eff(np.full(1024, 0.95))
    assert tau_frames == 0.0
    assert tau_frac == 0.0


def test_white_noise_tau_is_order_one():
    """Uncorrelated samples have a statistical inefficiency near 1."""
    rng = np.random.default_rng(0)
    x = rng.standard_normal(8192)
    tau_frames, tau_frac = compute_tau_eff(x)
    # iid data -> tau ~ 1; allow a generous band for finite-sample scatter.
    assert 0.3 < tau_frames < 3.0
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
    # Theoretical AR(1) inefficiency ~ (1+phi)/(1-phi) = 19 for phi=0.9.
    assert tau_corr > 3.0
    assert tau_corr > tau_white
