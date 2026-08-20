"""assess_cooling_contraction.assess() -- self-consistency-only cooling gate.

No test here passes an experimental/curated density or thermal-expansion value: the whole
point of the reframing is that the check never needs one. See
mcp-servers/mcp-lammps-engine/analysis_scripts/assess_cooling_contraction.py's module
docstring for the physics.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"))
from assess_cooling_contraction import assess  # noqa: E402


def test_shortfall_below_threshold_is_under_annealed_cooling():
    # rho_melt/rho_glass chosen so actual_contraction (1.10) is well short of the
    # alpha-predicted expected_contraction (1 + 2.5e-4*73 + 6e-4*177 = 1.1245).
    result = assess(rho_melt=1.00, rho_glass=1.05, tg_K=373.0, t_equil_K=550.0)
    assert result["verdict"] == "UNDER_ANNEALED_COOLING"
    assert result["under_annealed_cooling"] is True
    assert result["contraction_shortfall"] < 0.97


def test_shortfall_at_or_above_threshold_is_ok():
    # data/a-PS/attempts/equilibration/attempt-0001's real archived melt/glass densities --
    # regression lock for the reframed (all-generic-alpha) computation.
    result = assess(rho_melt=0.8956193048902196, rho_glass=0.9835512614285715,
                     tg_K=373.0, t_equil_K=550.0)
    assert result["verdict"] == "OK"
    assert result["under_annealed_cooling"] is False
    assert result["contraction_shortfall"] == 0.9766


def test_rubbery_regime_is_ok_noop():
    result = assess(rho_melt=0.85, rho_glass=0.86, tg_K=250.0, t_equil_K=300.0)
    assert result["verdict"] == "OK"
    assert result["regime"] == "rubbery_or_equilibrium"


def test_missing_tg_is_ok_noop():
    result = assess(rho_melt=0.85, rho_glass=0.86, tg_K=None, t_equil_K=300.0)
    assert result["verdict"] == "OK"
    assert result["regime"] == "rubbery_or_equilibrium"


def test_missing_glass_density_is_insufficient_data():
    result = assess(rho_melt=0.85, rho_glass=None, tg_K=373.0, t_equil_K=550.0)
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_missing_melt_density_is_ok_non_blocking():
    result = assess(rho_melt=None, rho_glass=0.98, tg_K=373.0, t_equil_K=550.0)
    assert result["verdict"] == "OK"
    assert "contraction_shortfall" not in result


def test_large_cooling_span_flags_extrapolation_unreliable():
    result = assess(rho_melt=0.80, rho_glass=0.95, tg_K=373.0, t_equil_K=700.0)
    assert result["extrapolation_reliable"] is False


def test_never_reads_an_experimental_or_curated_value():
    # assess() has no exp_density/band_pct parameter at all -- calling with one is a TypeError,
    # which is itself the guarantee: there is no code path back into an experiment comparison.
    import inspect
    params = set(inspect.signature(assess).parameters)
    assert "exp_density" not in params
    assert "exp_density_gcm3" not in params
    assert "band_pct" not in params
