"""Unit tests for compute_tau_eff / integrated_act (autocorrelation time).

compute_tau_eff underpins the error bars on every extracted property, so a
silent regression here would quietly mis-state simulation uncertainty.

tau is the statistical inefficiency s = 1 + 2*sum_k c(k), so it has an absolute
scale worth pinning: s == 1 for independent frames, and s == (1+phi)/(1-phi) for
an AR(1) process. n_effective = n / s, with no further factor of 2.
"""
import numpy as np

from analysis_utils import compute_tau_eff, effective_sample_size, integrated_act


def ar1(n, phi, seed):
    """AR(1) series with known integrated autocorrelation time (1+phi)/(1-phi)."""
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n)
    x = np.empty(n)
    x[0] = noise[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + noise[i]
    return x


def test_constant_series_returns_zero():
    """A flat series has no variance, so tau is defined to be zero."""
    tau_frames, tau_frac = compute_tau_eff(np.full(1024, 0.95))
    assert tau_frames == 0.0
    assert tau_frac == 0.0


def test_white_noise_tau_is_one():
    """Uncorrelated samples carry no memory -> statistical inefficiency of 1."""
    rng = np.random.default_rng(0)
    x = rng.standard_normal(8192)
    tau_frames, tau_frac = compute_tau_eff(x)
    assert 1.0 <= tau_frames < 1.5
    assert tau_frac == tau_frames / len(x)


def test_ar1_recovers_known_tau():
    """AR(1) with phi=0.9 has integrated tau = (1+phi)/(1-phi) = 19."""
    tau_frames, _ = compute_tau_eff(ar1(200_000, 0.9, seed=1))
    assert abs(tau_frames - 19.0) / 19.0 < 0.20


def test_correlated_series_has_larger_tau_than_white_noise():
    """A series with strong memory must report a larger tau than white noise."""
    rng = np.random.default_rng(2)
    tau_white, _ = compute_tau_eff(rng.standard_normal(8192))
    tau_corr, _ = compute_tau_eff(ar1(8192, 0.9, seed=3))
    assert tau_corr > tau_white


def test_tail_averaging_regression():
    """The old batch-means tail average read the noisiest end of the blocking
    curve and underestimated tau by many-fold; tau must not collapse below 1."""
    tau_frames, _ = compute_tau_eff(ar1(4096, 0.95, seed=4))
    assert tau_frames > 10.0


def test_integrated_act_n_eff_has_no_factor_of_two():
    """n_effective is n/tau, not n/(2*tau)."""
    x = ar1(20_000, 0.9, seed=5)
    tau, n_eff = integrated_act(x)
    assert abs(n_eff - len(x) / tau) < 1e-6
    assert effective_sample_size(len(x), tau) == int(len(x) / tau)


def test_short_and_degenerate_inputs():
    """Guards must not divide by zero or return tau < 1."""
    assert integrated_act(np.array([])) == (1.0, 0.0)
    assert integrated_act(np.array([2.0])) == (1.0, 1.0)
    tau, n_eff = integrated_act(np.full(64, 3.0))
    assert tau == 1.0 and n_eff == 64.0
