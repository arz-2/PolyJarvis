"""Unit tests for the equilibration drift gate (_analyse_property).

This is the function behind the PASS / EXTEND / ESCALATE verdict. A false PASS
would let an unequilibrated system flow into Tg and modulus extraction.
"""
import numpy as np

from check_equilibration_comprehensive import _analyse_property

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
