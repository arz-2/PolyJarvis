"""Unit tests for bulk-modulus extraction (extract_bulk_modulus).

Covers both estimators:
  * compute_B_def        -- B = -(dP / d ln V) from regression of P vs ln(V)
  * compute_bulk_modulus -- K_T = kB*T*<V>/Var(V) from volume fluctuations
"""
import numpy as np

import extract_bulk_modulus as ebm
from extract_bulk_modulus import compute_B_def, compute_bulk_modulus


def test_B_def_recovers_known_slope():
    """A clean linear P vs ln(V) must yield B = -slope converted to GPa."""
    volumes = np.linspace(1000.0, 1100.0, 60)
    slope_atm = -2000.0  # P = slope*ln(V) + c, so dP/dlnV = slope
    pressures = slope_atm * np.log(volumes) + 5000.0

    B_gpa, r2, meta = compute_B_def(volumes, pressures)

    expected = -slope_atm * 101325.0 * ebm.PA_TO_GPA
    assert abs(B_gpa - expected) < 1e-6
    assert r2 > 0.999
    assert meta["n_points"] == len(volumes)


def test_bulk_modulus_matches_fluctuation_formula():
    """K_GPa must equal the closed-form kB*T*<V>/Var(V) using module constants."""
    volumes = np.array([1000.0, 1010.0, 990.0, 1005.0, 995.0, 1002.0])
    T = 300.0

    K_gpa, K_atm, meta = compute_bulk_modulus(volumes, T)

    V_mean = np.mean(volumes)
    V_var = np.var(volumes, ddof=1)
    K_pa_expected = ebm.KB_SI * T * V_mean / V_var / ebm.A3_TO_M3
    assert K_gpa is not None
    assert abs(K_gpa - K_pa_expected * ebm.PA_TO_GPA) < 1e-9
    assert abs(K_atm - K_pa_expected * ebm.PA_TO_ATM) < 1e-6
    assert abs(meta["V_mean_A3"] - V_mean) < 1e-9


def test_smaller_variance_gives_larger_modulus():
    """Stiffer system (less volume fluctuation) -> larger bulk modulus."""
    tight = np.array([1000.0, 1001.0, 999.0, 1000.5, 999.5])
    loose = np.array([1000.0, 1020.0, 980.0, 1010.0, 990.0])
    K_tight, _, _ = compute_bulk_modulus(tight, 300.0)
    K_loose, _, _ = compute_bulk_modulus(loose, 300.0)
    assert K_tight > K_loose


def test_zero_variance_returns_none():
    """A perfectly rigid volume series cannot define a modulus."""
    K_gpa, K_atm, meta = compute_bulk_modulus(np.full(10, 1000.0), 300.0)
    assert K_gpa is None
    assert K_atm is None
    assert "error" in meta
