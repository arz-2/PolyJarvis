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


# ─── the assessment temperature is final_T_K, not a hardcoded 300 ─────────────────
#
# rho_glass comes from npt_final, which runs at final_T_K. 300 K is only that parameter's
# default. Using 300 unconditionally gets both the cold endpoint of the expected contraction
# and the rubbery short-circuit wrong for any run assessed elsewhere -- the same trap
# stage_params._regime documents for the regime oracle.


def test_the_cold_endpoint_is_the_assessment_temperature():
    """Same cell, same densities, assessed at 350 K instead of 300: the glassy segment is 50 K
    shorter, so less contraction is expected and the shortfall rises."""
    at_300 = assess(rho_melt=1.00, rho_glass=1.05, tg_K=450.0, t_equil_K=650.0)
    at_350 = assess(rho_melt=1.00, rho_glass=1.05, tg_K=450.0, t_equil_K=650.0,
                    final_T_K=350.0)
    assert at_350["expected_contraction"] < at_300["expected_contraction"]
    assert at_350["contraction_shortfall"] > at_300["contraction_shortfall"]
    assert at_350["final_T_K"] == 350.0


def test_a_cell_assessed_above_its_tg_is_rubbery_even_when_tg_exceeds_300():
    """Tg=320 with final_T_K=350: the cell is never a glass at the temperature it is graded at,
    so there is no cooling stage to under-anneal. Hardcoding 300 would call this glassy and
    assess a contraction that never happened."""
    result = assess(rho_melt=1.00, rho_glass=1.02, tg_K=320.0, t_equil_K=600.0,
                    final_T_K=350.0)
    assert result["regime"] == "rubbery_or_equilibrium"
    assert result["verdict"] == "OK"
    assert result["under_annealed_cooling"] is False


def test_the_reliability_span_is_measured_from_the_assessment_temperature():
    """span = T_equil - final_T_K. Assessed at 400 K, a 650 K melt is a 250 K span (reliable),
    not the 350 K a hardcoded 300 would compute."""
    assert assess(rho_melt=1.0, rho_glass=1.1, tg_K=450.0,
                  t_equil_K=650.0)["extrapolation_reliable"] is False
    assert assess(rho_melt=1.0, rho_glass=1.1, tg_K=450.0, t_equil_K=650.0,
                  final_T_K=400.0)["extrapolation_reliable"] is True


def test_default_stays_300_so_legacy_calls_are_unchanged():
    a = assess(rho_melt=1.00, rho_glass=1.05, tg_K=373.0, t_equil_K=550.0)
    b = assess(rho_melt=1.00, rho_glass=1.05, tg_K=373.0, t_equil_K=550.0, final_T_K=300.0)
    assert a == b


# ─── calibration against real archived runs ───────────────────────────────────────
#
# (rho_melt, rho_glass, tg_K, t_equil_K) transcribed from the archived
# raw/cooling_contraction.json of runs in the sibling PolyJarvis checkout. Inlined rather than
# read from that path: the repo's tests must not depend on a sibling working tree.
#
# GROUND TRUTH, established independently of this gate: an investigation of these same runs
# (2026-08-12) found melt density correct and the glass 4.5-6.2% low, concluding the deficit
# was a cooling artifact rather than a force-field one (the sigma-shrink hypothesis was
# falsified). So these are known-under-annealed cells, and a gate that does NOT flag them is
# the broken one.

ARCHIVED = [
    #  run       rho_melt  rho_glass   tg_K   t_equil_K
    ("PEEK1",     1.0384,    1.1949,   418.0,   770.0),
    ("PEEK2",     1.0541,    1.1915,   418.0,   770.0),
    ("PMMA1",     1.0483,    1.1158,   378.0,   550.0),
    ("PMMA4",     1.0573,    1.1072,   378.0,   550.0),
    ("PSU2",      1.0503,    1.1851,   463.0,   700.0),
    ("PS2",       0.9077,    0.9832,   373.0,   550.0),
]


def test_the_default_alphas_flag_every_independently_diagnosed_under_annealed_run():
    for run, rho_melt, rho_glass, tg_K, t_equil_K in ARCHIVED:
        result = assess(rho_melt, rho_glass, tg_K, t_equil_K)
        assert result["verdict"] == "UNDER_ANNEALED_COOLING", (run, result)


def test_substituting_the_runs_own_measured_alphas_would_silence_the_gate():
    """Guards against an appealing but circular 'improvement'.

    Each run measures its own expansivities in the thermal stage (extract_thermal's
    cte_glassy_per_K / cte_rubbery_per_K), which looks like the obvious upgrade over generic
    constants. It is not usable yet: those numbers come from the pre-2026-09-01 cold-start Tg
    sweep, whose top plateaus read too dense and therefore FLATTEN the rubbery branch --
    archived cte_rubbery lands at 2.8-4.7e-4 against a literature range of ~5-7e-4, biased low
    in exactly that direction. Feeding them back in excuses the contamination with a
    measurement the contamination produced, and un-flags runs independently diagnosed as
    under-annealed.

    PEEK1's own measured values are used here. When a melt-start sweep raises cte_rubbery
    toward 5-6e-4, this test should be revisited -- that rise is the evidence that unlocks
    per-run alphas as the real design."""
    _, rho_melt, rho_glass, tg_K, t_equil_K = ARCHIVED[0]
    assert assess(rho_melt, rho_glass, tg_K, t_equil_K)["verdict"] == "UNDER_ANNEALED_COOLING"
    measured = assess(rho_melt, rho_glass, tg_K, t_equil_K,
                      alpha_glass=2.130e-4, alpha_melt=3.866e-4)
    assert measured["verdict"] == "OK"


def test_the_threshold_cannot_be_tightened_without_better_alphas():
    """The gate's own resolution limit, pinned so nobody narrows the 0.97 threshold without
    first fixing the alphas. +/-1e-4 on alpha_melt -- well inside the literature spread for
    polymer melts -- moves the shortfall by about the width of the threshold itself."""
    kw = dict(rho_melt=1.0384, rho_glass=1.1949, tg_K=418.0, t_equil_K=770.0)
    lo = assess(**kw, alpha_melt=5e-4)["contraction_shortfall"]
    hi = assess(**kw, alpha_melt=7e-4)["contraction_shortfall"]
    swing = lo - hi
    assert 0.05 < swing < 0.09, swing          # ~7%, against a 3% threshold band
