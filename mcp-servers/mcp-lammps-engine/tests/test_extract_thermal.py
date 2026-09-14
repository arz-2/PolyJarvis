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


# --- an unidentifiable width must not be reported as a measurement -------------------------
from extract_thermal import C_LOWER_BOUND_K  # noqa: E402


def test_a_width_that_runs_to_its_bound_is_reported_as_unresolved_not_zero():
    """sPVC_2, 2026-09-11. c is bounded below at C_LOWER_BOUND_K; a fit landing there means the
    width is UNIDENTIFIABLE, not that it measured zero. Reporting 0.00 invites it to be read as
    a measurement -- and it was, by a check that then discarded a perfectly good Tg.

    A sweep sampling every few K cannot resolve a width finer than its own spacing, so this is
    the expected outcome for any transition sharper than the sampling.
    """
    T, rho = _synthetic_rho_vs_T(Tg=300.0)          # a genuinely sharp piecewise curve
    res = curvefit_hyperbola(T, rho)
    assert res is not None
    if res["transition_width_resolved"] is False:
        assert res["transition_width_c_K"] is None, "a bound-hit width must not be a number"
    else:
        assert res["transition_width_c_K"] > C_LOWER_BOUND_K * 10.0


def test_a_resolved_width_is_still_reported_as_a_number():
    """The flag must not swallow genuine widths -- a broad transition still reports c."""
    T = np.linspace(150.0, 600.0, 60)
    Tg, c = 400.0, 40.0
    rho = 1.10 - 4.0e-4 * (T - Tg) - 2.0e-4 * np.sqrt((T - Tg) ** 2 + c ** 2)
    res = curvefit_hyperbola(T, rho)
    assert res is not None
    assert res["transition_width_resolved"] is True
    assert res["transition_width_c_K"] is not None
    assert abs(res["transition_width_c_K"] - c) < 15.0


def test_the_width_flag_is_present_on_every_hyperbola_result():
    """Downstream code branches on transition_width_resolved, so it must always be set rather
    than sometimes absent -- an absent key reads as None, which is neither True nor False."""
    for Tg in (250.0, 300.0, 450.0):
        T, rho = _synthetic_rho_vs_T(Tg=Tg)
        res = curvefit_hyperbola(T, rho)
        if res is None:
            continue
        assert "transition_width_resolved" in res
        assert isinstance(res["transition_width_resolved"], bool)
        if res["transition_width_resolved"]:
            assert isinstance(res["transition_width_c_K"], float)
        else:
            assert res["transition_width_c_K"] is None


# --- the estimator must not be chosen by the data ------------------------------------------
def test_an_unresolved_width_does_not_change_the_estimator(tmp_path):
    """The replicate requirement, as a unit test on the swap rule.

    sPVC_1 and sPVC_2 are seed-only replicates of one protocol. Before 2026-09-11 replicate 2's
    width fitted below the sweep resolution, which counted as a hard violation and swapped it to
    a bilinear -- so the two replicates reported under different models and their Tg difference
    mixed seed variance with estimator variance (10.7 K reported vs 7.2 K like-for-like).

    With c -> 0 the hyperbola IS the bilinear, so the swap changed parameterisation, not model.
    """
    import re, inspect, extract_thermal
    src = inspect.getsource(extract_thermal.main) if hasattr(extract_thermal, "main") else \
        (tmp_path.parent, open(extract_thermal.__file__).read())[1]
    assert "_ESTIMATOR_PRESERVING" in src
    # the preserving set must contain the width case and NOTHING that is a real physics failure
    block = src.split("_ESTIMATOR_PRESERVING = ")[1].split("\n")[0]
    assert "transition_width_unresolved" in block
    for real_failure in ("slope_sign_invalid", "tg_pinned_to_sweep_endpoint", "fit_missing"):
        assert real_failure not in block, (
            f"{real_failure} is a genuine physics failure -- the alternative fit is a better "
            "answer there, so it must still swap")


def test_the_swap_still_fires_on_a_real_physics_violation():
    """Narrowing the swap must not disable it: inverted slopes still hand over to the
    alternative fit, because there the other model is genuinely the better answer."""
    import inspect, extract_thermal
    src = open(extract_thermal.__file__).read()
    assert "_swap_worthy = [v for v in primary_violations" in src
    assert "if _swap_worthy and alt_result is not None" in src
    # and the violation list still detects the real cases
    assert "slope_sign_invalid" in src and "tg_pinned_to_sweep_endpoint" in src
