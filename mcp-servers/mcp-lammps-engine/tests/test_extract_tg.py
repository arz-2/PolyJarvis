"""Unit tests for the Tg bilinear fit (extract_tg).

curvefit_bilinear *is* the reported glass-transition temperature. We feed it a
synthetic density-vs-temperature curve with a known kink and confirm it recovers
that temperature with a near-perfect fit.
"""
import numpy as np

from extract_tg import bilinear_indep, curvefit_bilinear


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
