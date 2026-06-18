"""Unit tests for the thermal property bilinear fits (extract_thermal).

curvefit_bilinear *is* the reported glass-transition temperature. We feed it a
synthetic density-vs-temperature curve with a known kink and confirm it recovers
that temperature with a near-perfect fit.
"""
import numpy as np

from extract_thermal import (
    bilinear_indep,
    curvefit_bilinear,
    curvefit_hyperbola,
    hyperbola_indep,
)


def test_bilinear_indep_switches_at_tg():
    """Below Tg the first line applies; at/above Tg the second line applies."""
    T = np.array([100.0, 200.0, 300.0, 400.0])
    out = bilinear_indep(T, a1=-1.0, b1=0.0, a2=-2.0, b2=300.0, Tg=300.0)
    # T < 300 -> a1*T + b1 ; T >= 300 -> a2*T + b2
    assert out[0] == -100.0          # 100 < Tg
    assert out[1] == -200.0          # 200 < Tg
    assert out[2] == -2.0 * 300 + 300  # 300 >= Tg -> -300
    assert out[3] == -2.0 * 400 + 300  # 400 >= Tg -> -500


def _synthetic_rho_vs_T(Tg=300.0, a_glassy=-2.0e-4, a_rubbery=-6.0e-4, b_glassy=1.25):
    """Continuous piecewise-linear density curve with a kink at Tg."""
    T = np.arange(100.0, 501.0, 10.0)
    # enforce continuity at Tg: b_rubbery = b_glassy + (a_glassy - a_rubbery)*Tg
    b_rubbery = b_glassy + (a_glassy - a_rubbery) * Tg
    rho = bilinear_indep(T, a_glassy, b_glassy, a_rubbery, b_rubbery, Tg)
    return T, rho


def test_curvefit_recovers_known_tg():
    T, rho = _synthetic_rho_vs_T(Tg=300.0)
    res = curvefit_bilinear(T, rho)
    assert res is not None
    assert abs(res["Tg_K"] - 300.0) < 15.0
    assert res["r_squared"] > 0.99
    # glassy segment is shallower than the rubbery segment (more expansion above Tg)
    assert abs(res["a_glassy"]) < abs(res["a_rubbery"])


def test_curvefit_returns_none_for_too_few_points():
    """Fewer than two points on a side of the midpoint cannot be fit."""
    T = np.array([100.0, 200.0, 300.0])
    rho = np.array([1.2, 1.1, 1.0])
    assert curvefit_bilinear(T, rho) is None


# ---------------------------------------------------------------------------
# Hyperbola (smoothed-bilinear) fit
# ---------------------------------------------------------------------------

def _synthetic_hyperbola_rho_vs_T(Tg=300.0, c=25.0,
                                  a_glassy=-2.0e-4, a_rubbery=-8.0e-4, rho0=1.0):
    """Smooth density curve with a finite-width transition of half-width c."""
    T = np.arange(100.0, 501.0, 10.0)
    m_bar = (a_glassy + a_rubbery) / 2
    delta = (a_rubbery - a_glassy) / 2
    rho = hyperbola_indep(T, rho0, m_bar, delta, Tg, c)
    return T, rho


def test_hyperbola_indep_reduces_to_asymptotic_slopes():
    """Far from Tg the model is linear with slopes m_bar -/+ delta."""
    T = np.array([0.0, 1.0])
    # delta>0: high-T slope = m_bar+delta, far below Tg slope = m_bar-delta
    far_low = hyperbola_indep(np.array([-1e6, -1e6 + 1.0]), 0.0, 1.0, 0.5, 0.0, 1.0)
    far_high = hyperbola_indep(np.array([1e6, 1e6 + 1.0]), 0.0, 1.0, 0.5, 0.0, 1.0)
    assert abs((far_low[1] - far_low[0]) - (1.0 - 0.5)) < 1e-3   # m_bar - delta
    assert abs((far_high[1] - far_high[0]) - (1.0 + 0.5)) < 1e-3  # m_bar + delta


def test_hyperbola_recovers_known_tg():
    rng = np.random.default_rng(0)
    T, rho = _synthetic_hyperbola_rho_vs_T(Tg=300.0, c=25.0)
    rho = rho + rng.normal(0, 2e-4, size=rho.shape)
    res = curvefit_hyperbola(T, rho)
    assert res is not None
    assert abs(res["Tg_K"] - 300.0) < 15.0
    assert res["r_squared"] > 0.95
    assert res["transition_width_c_K"] > 0.0
    assert res["tg_uncertainty_K"] is not None and res["tg_uncertainty_K"] >= 0.0
    # rubbery asymptote steeper (more negative) than glassy
    assert res["a_rubbery"] < res["a_glassy"] < 0


def test_hyperbola_handles_sharp_bilinear_data():
    """On a sharp piecewise curve the hyperbola still localises Tg (small c)."""
    T, rho = _synthetic_rho_vs_T(Tg=300.0)
    res = curvefit_hyperbola(T, rho)
    assert res is not None
    assert abs(res["Tg_K"] - 300.0) < 15.0
    assert abs(res["a_glassy"]) < abs(res["a_rubbery"])


def test_hyperbola_seed_from_bilinear():
    T, rho = _synthetic_hyperbola_rho_vs_T(Tg=320.0, c=15.0)
    seed = curvefit_bilinear(T, rho)
    res = curvefit_hyperbola(T, rho, seed=seed)
    assert res is not None
    assert abs(res["Tg_K"] - 320.0) < 15.0


def test_hyperbola_returns_none_for_too_few_points():
    T = np.array([100.0, 200.0, 300.0, 400.0])
    rho = np.array([1.2, 1.15, 1.1, 1.0])
    assert curvefit_hyperbola(T, rho) is None
