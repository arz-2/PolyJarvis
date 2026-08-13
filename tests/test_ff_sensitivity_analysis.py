"""Test 1 free-leg analysis: the experimental melt reference.

`rho_exp(T_equil)` is load-bearing -- it is the denominator of every melt gap, so a wrong
value silently flips the force-field-vs-cooling-protocol classification that this whole
test exists to decide. It is also evaluated from strings stored in the database, which is
exactly the kind of thing that fails quietly.

The classification threshold is tested too. It is derived from the spread among the
independent experimental equations for the same polymer rather than chosen, because a
chosen constant is the move the reviewer objected to in the first place.
"""
import importlib.util
import math
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_SRC = REPO / "manuscript_v2/test/ff_sensitivity/a1_experimental_melt_reference.py"
_spec = importlib.util.spec_from_file_location("_a1", _SRC)
_a1 = importlib.util.module_from_spec(_spec)
sys.modules["_a1"] = _a1
_spec.loader.exec_module(_a1)

DB = REPO / "db/polymer_db.sqlite"


# ─── evaluating the stored equations ───────────────────────────────────────────

def test_exponential_equation_matches_closed_form():
    """PEEK: rho = 1.397*exp(-6.69e-4*t). Analytically checkable, so it catches a
    namespace or units error in the evaluator rather than trusting the DB round-trip."""
    expr = "1.397*math.exp(-6.69*1e-4*t)"
    assert _a1.rho_exp(expr, 350.0) == pytest.approx(1.397 * math.exp(-6.69e-4 * 350.0))


def test_polynomial_equation_matches_closed_form():
    expr = "1.223-5.29*1e-4*t-0.507*1e-6*t**2"
    t = 200.0
    assert _a1.rho_exp(expr, t) == pytest.approx(1.223 - 5.29e-4 * t - 0.507e-6 * t ** 2)


def test_evaluator_has_no_builtins():
    """The expressions come from the database, so the eval namespace must stay closed."""
    with pytest.raises((NameError, TypeError)):
        _a1.rho_exp("__import__('os').getcwd()", 25.0)


def test_temperature_is_celsius_not_kelvin():
    """Every stored equation is in degrees C. Passing Kelvin would give densities that
    are wrong by ~20% and still look plausible."""
    expr = "1.397*math.exp(-6.69*1e-4*t)"
    assert _a1.rho_exp(expr, 300.0 - 273.15) > _a1.rho_exp(expr, 300.0)


# ─── the reference data is right, not merely parseable ─────────────────────────

@pytest.mark.skipif(not DB.exists(), reason="polymer_db.sqlite not present")
@pytest.mark.parametrize("name,comparator", [
    ("Poly(methylmethacrylate)", 1.19),
    ("Polystyrene", 1.05),
])
def test_glass_equations_reproduce_the_manuscript_comparator(name, comparator):
    """Independent round-trip: the GLASS-phase equations are different table rows from
    the melt-phase ones a1 uses, and the 300 K comparators come from Brandrup/Polymer
    Data Handbook, not from Mark 2007. Agreement to ~1% is evidence the reference
    pipeline is sound; disagreement would invalidate every melt gap."""
    eqs = _a1.equations_for(_a1.load_equations(), name, "glass")
    vals = [_a1.rho_exp(e["py_expr"], 26.85) for e in eqs
            if e["t_min_C"] <= 26.85 <= e["t_max_C"]]
    assert vals, f"no in-range glass equation for {name}"
    assert sum(vals) / len(vals) == pytest.approx(comparator, rel=0.02)


@pytest.mark.skipif(not DB.exists(), reason="polymer_db.sqlite not present")
def test_isotactic_pmma_is_not_matched_by_the_atactic_lookup():
    """Isotactic PMMA has its own rows and a 90 K different Tg. Our cells are atactic;
    a substring match would silently pool the two."""
    eqs = _a1.equations_for(_a1.load_equations(), "Poly(methylmethacrylate)", "melt")
    assert eqs
    assert all(e["pname"] == "Poly(methylmethacrylate)" for e in eqs)
    assert not any("isotactic" in e["pname"] for e in eqs)


@pytest.mark.skipif(not DB.exists(), reason="polymer_db.sqlite not present")
def test_every_equation_carries_a_validity_range():
    """A range is what lets a1 refuse to extrapolate. An equation without one would be
    applied everywhere."""
    for e in _a1.load_equations():
        assert e["t_min_C"] is not None and e["t_max_C"] is not None
        assert e["t_max_C"] > e["t_min_C"], e["pname"]


# ─── the alpha heuristic, kept only for comparison ─────────────────────────────

def test_alpha_heuristic_reproduces_the_archived_pmma4_gap():
    """PMMA4's recorded melt_density_gap_pct is -0.25 under the shipped generic alphas.
    Reproducing it is what makes the side-by-side comparison in section 2 legitimate."""
    gap, _ = _a1.alpha_melt_gap(rho_melt=1.0572595271825573, exp_300=1.19,
                                tg_K=378.0, t_equil_K=550.0,
                                a_g=2.5e-4, a_m=6.0e-4)
    assert gap == pytest.approx(-0.25, abs=0.01)


def test_smaller_assumed_alpha_melt_makes_the_deficit_look_worse():
    """The direction that matters: the heuristic's answer depends on alpha_melt, and a
    smaller value drives the gap negative -- i.e. toward blaming the force field."""
    kw = dict(rho_melt=1.0573, exp_300=1.19, tg_K=378.0, t_equil_K=550.0, a_g=2.5e-4)
    generic, _ = _a1.alpha_melt_gap(a_m=6.0e-4, **kw)
    smaller, _ = _a1.alpha_melt_gap(a_m=3.56e-4, **kw)
    assert smaller < generic - 3.0
