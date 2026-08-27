"""Unit tests for the equilibration drift gate (_analyse_property).

This is the function behind the PASS / EXTEND / ESCALATE verdict. A false PASS
would let an unequilibrated system flow into Tg and modulus extraction.
"""
import numpy as np
import pandas as pd

from check_equilibration_comprehensive import _analyse_property, _analyse_energy_components

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


# ─── gate B: per-energy-term drift ────────────────────────────────────────────
# Added after tracing RadonPy's own check_eq(), which gates bond/angle/dihedral/
# vdW/Kspace energies independently rather than only the aggregate total.


def test_flat_energy_components_all_pass():
    rng = np.random.default_rng(1)
    prod = pd.DataFrame({
        "E_bond": 500 + rng.normal(0, 0.05, size=200),
        "E_angle": 300 + rng.normal(0, 0.05, size=200),
        "E_vdwl": -800 + rng.normal(0, 0.05, size=200),
    })
    res = _analyse_energy_components(prod, DRIFT_PCT, DRIFT_PVALUE)
    assert res["pass"] is True
    assert set(res["components"]) == {"bond", "angle", "vdw"}
    assert all(c["pass"] for c in res["components"].values())


def test_one_drifting_component_fails_the_set():
    rng = np.random.default_rng(2)
    prod = pd.DataFrame({
        "E_bond": np.linspace(500, 550, 200),  # steady, significant upward trend
        "E_angle": 300 + rng.normal(0, 0.05, size=200),
    })
    res = _analyse_energy_components(prod, DRIFT_PCT, DRIFT_PVALUE)
    assert res["components"]["bond"]["pass"] is False
    assert res["components"]["angle"]["pass"] is True
    assert res["pass"] is False


def test_missing_columns_are_skipped_not_failed():
    prod = pd.DataFrame({"E_bond": 500 + np.zeros(50)})
    res = _analyse_energy_components(prod, DRIFT_PCT, DRIFT_PVALUE)
    assert set(res["components"]) == {"bond"}
    assert res["pass"] is True


def test_canceling_component_drift_fails_gate_b_even_when_total_is_flat():
    """The motivating case: bond energy relaxing down while vdW drifts up can net a
    flat TotEng. Gate B must catch this from the per-term check even though the
    aggregate-only _analyse_property call on TotEng would have passed."""
    n = 200
    rng = np.random.default_rng(3)
    bond = np.linspace(550, 500, n) + rng.normal(0, 0.05, n)   # drifting down
    vdwl = np.linspace(-850, -800, n) + rng.normal(0, 0.05, n)  # drifting up, canceling
    tot_eng = bond + vdwl  # ~flat by construction

    prod = pd.DataFrame({"E_bond": bond, "E_vdwl": vdwl, "TotEng": tot_eng})

    aggregate = _analyse_property(prod["TotEng"].values, "energy", DRIFT_PCT, DRIFT_PVALUE, BLOCKS)
    assert aggregate["equilibrated"] is True  # aggregate alone is fooled

    component = _analyse_energy_components(prod, DRIFT_PCT, DRIFT_PVALUE)
    assert component["pass"] is False  # gate B's per-term check is not fooled
    equilibrated = bool(aggregate["equilibrated"] and component["pass"])
    assert equilibrated is False
