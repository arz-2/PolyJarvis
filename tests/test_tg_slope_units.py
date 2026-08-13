"""Tg rate-dependence slope: per e-fold vs per decade.

`fit_multirate` regresses Tg against `np.log(rates)`, so its slope is K per e-fold.
Every physical comparison is per DECADE -- the 3-5 K/decade literature expectation, and
the "< 1 K/decade -> flat" threshold whose comment already said decade while the code
compared e-folds. A factor of ln(10) = 2.303 sat between the two.

The fit itself is left alone deliberately: `intercept` is paired with the natural-log
slope, and `tg_at_slow_rate_K` is computed as `intercept + slope*ln(ref)`. Rescaling
`slope` in place without the intercept would silently corrupt every extrapolated Tg.
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = (REPO_ROOT / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"
        / "extract_tg_multirate.py")
_spec = importlib.util.spec_from_file_location("_tg_mr", _SRC)
_tg = importlib.util.module_from_spec(_spec)
sys.modules["_tg"] = _tg
_spec.loader.exec_module(_tg)

LN10 = float(np.log(10.0))


def test_per_decade_is_the_efold_slope_times_ln10():
    r = _tg.fit_multirate([25.0, 50.0, 100.0], [400.0, 410.0, 420.0], regime="glassy")
    assert r["loglinear_slope_K_per_decade"] == pytest.approx(
        r["loglinear_slope_K"] * LN10)


def test_extrapolated_tg_still_pairs_with_the_natural_log_slope():
    """The regression check for the fix that was NOT made: tg_at_slow_rate_K must stay
    consistent with `slope`, not with the per-decade value."""
    ref = 5.0
    r = _tg.fit_multirate([25.0, 50.0, 100.0], [400.0, 415.0, 430.0],
                          slow_rate_ref=ref, regime="glassy")
    assert r["tg_method"] == "loglinear_extrapolation"
    assert r["tg_at_slow_rate_K"] == pytest.approx(
        r["loglinear_intercept_K"] + r["loglinear_slope_K"] * np.log(ref))


def test_flat_rate_threshold_is_applied_in_per_decade_units():
    """A slope of ~0.6 K/e-fold is ~1.4 K/decade: genuinely rate-dependent, and the
    old e-fold comparison wrongly called it flat."""
    rates = [10.0, 100.0, 1000.0]
    slope_per_decade = 1.4
    tgs = [400.0 + slope_per_decade * np.log10(x / 10.0) for x in rates]
    r = _tg.fit_multirate(rates, tgs, regime="glassy")
    assert r["loglinear_slope_K"] < 1.0                       # would have been "flat"
    assert r["loglinear_slope_K_per_decade"] == pytest.approx(1.4, abs=0.01)
    assert r["is_flat_rate_regime"] is False


def test_genuinely_flat_is_still_flat():
    rates = [10.0, 100.0, 1000.0]
    tgs = [400.0 + 0.3 * np.log10(x / 10.0) for x in rates]
    r = _tg.fit_multirate(rates, tgs, regime="glassy")
    assert r["is_flat_rate_regime"] is True
    assert r["tg_method"] == "flat_rate_mean"


def test_archived_ps4_slope_reproduces_in_both_units():
    """PS4's real rate ladder. 111.6 K/decade against a physical 3-5 is what the
    e-fold value of 48.5 concealed."""
    r = _tg.fit_multirate([25.0, 50.0, 100.0], [434.0, 415.8, 501.2],
                          slow_rate_ref=1.6667e-10, regime="glassy")
    assert r["loglinear_slope_K"] == pytest.approx(48.4746, abs=1e-3)
    assert r["loglinear_slope_K_per_decade"] == pytest.approx(111.62, abs=0.01)


def test_sign_gate_is_unit_independent():
    """slope_gate_pass tests the sign only, so it must be unaffected by the units fix --
    and it is exactly why it passes runs with r^2 = 0.002."""
    r = _tg.fit_multirate([25.0, 50.0, 100.0], [420.0, 410.0, 400.0], regime="glassy")
    assert r["slope_gate_pass"] is False
    assert r["loglinear_slope_K"] < 0 and r["loglinear_slope_K_per_decade"] < 0
