"""select_hardware.py's cost model: GPU-hours estimation off guides/polymer_rules.json's
hardware_policy.directional_probe.size_points (3 real measured points per FF family,
2026-08-24) with a single-point near-linear-assumption fallback for a family with no
size_points at all (gaff, today).

The interpolation is log-log, not linear-in-atoms: measuring pcff/opls/trappe at three
real sizes (2026-08-24) showed the throughput-vs-size exponent is NOT constant across
families (trappe close to -1, i.e. linear cost-per-atom; pcff/opls clearly flatter, from
KOKKOS full-offload's fixed per-timestep overhead) -- these tests pin exact values against
a hand-computed log-log interpolation so a future edit can't silently drift back to a
single global exponent.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import select_hardware as cm  # noqa: E402

# A minimal, self-contained hardware_policy fixture -- independent of whatever
# guides/polymer_rules.json happens to contain right now, so these tests never drift if
# the real calibration data is re-measured.
HP = {
    "values_are_benchmarked": True,
    "host": {"gpus": 4, "gpu_model": "Quadro RTX 6000", "phys_cores": 18},
    "directional_probe": {
        "measured_on": "4x Quadro RTX 6000 / 18 phys cores",
        "recommended_by_ff": {
            "pcff": {"name": "gpu1_mpi1", "mpi": 1, "gpu": 1, "ns_per_day": 42.269,
                     "cell_atoms": 3020, "engine": "kokkos"},
        },
        "size_points": {
            "pcff": [
                {"atoms": 3020, "ns_per_day": 42.269, "engine": "kokkos", "mpi": 1, "gpu": 1},
                {"atoms": 5140, "ns_per_day": 30.63, "engine": "kokkos", "mpi": 1, "gpu": 1},
                {"atoms": 15040, "ns_per_day": 17.384, "engine": "kokkos", "mpi": 1, "gpu": 1},
            ],
        },
    },
}


def _rules(host_matches=True):
    hp = HP
    return {"hardware_policy": hp}, host_matches


def test_exact_match_reproduces_the_measured_point_exactly(monkeypatch):
    monkeypatch.setattr(cm, "host_matches", lambda rules: True)
    result = cm.estimate_ns_per_day(15040, "pcff", hp=HP, rules={})
    assert result["ns_per_day"] == 17.384
    assert result["confidence"] == "high"


def test_interpolation_within_range_is_high_confidence_and_hand_computed(monkeypatch):
    monkeypatch.setattr(cm, "host_matches", lambda rules: True)
    result = cm.estimate_ns_per_day(8000, "pcff", hp=HP, rules={})
    assert result["confidence"] == "high"
    # hand-computed log-log interpolation between (5140, 30.63) and (15040, 17.384)
    import math
    la, lb = math.log(5140), math.log(15040)
    na, nb = math.log(30.63), math.log(17.384)
    t = (math.log(8000) - la) / (lb - la)
    expected = math.exp(na + t * (nb - na))
    assert abs(result["ns_per_day"] - expected) < 1e-6


def test_interpolation_host_mismatch_downgrades_to_medium(monkeypatch):
    monkeypatch.setattr(cm, "host_matches", lambda rules: False)
    result = cm.estimate_ns_per_day(8000, "pcff", hp=HP, rules={})
    assert result["confidence"] == "medium"


def test_extrapolation_outside_measured_range_is_low_confidence(monkeypatch):
    monkeypatch.setattr(cm, "host_matches", lambda rules: True)
    below = cm.estimate_ns_per_day(1000, "pcff", hp=HP, rules={})
    above = cm.estimate_ns_per_day(30000, "pcff", hp=HP, rules={})
    assert below["confidence"] == "low"
    assert above["confidence"] == "low"
    # extrapolated, not clamped to an endpoint
    assert below["ns_per_day"] > 42.269
    assert above["ns_per_day"] < 17.384


def test_family_with_no_size_points_falls_back_to_single_point(monkeypatch):
    """opls has only recommended_by_ff, no size_points, in this fixture."""
    hp = {**HP, "directional_probe": {
        **HP["directional_probe"],
        "recommended_by_ff": {**HP["directional_probe"]["recommended_by_ff"],
                              "opls": {"name": "gpu1_mpi1", "mpi": 1, "gpu": 1,
                                       "ns_per_day": 55.191, "cell_atoms": 3220,
                                       "engine": "kokkos"}},
    }}
    monkeypatch.setattr(cm, "host_matches", lambda rules: True)
    result = cm.estimate_ns_per_day(3220, "opls", hp=hp, rules={})
    assert result["ns_per_day"] == 55.191
    assert result["confidence"] == "high"
    assert "measured_points" not in result  # single-point path, not the size_points path


def test_family_with_no_benchmark_data_at_all_is_none(monkeypatch):
    monkeypatch.setattr(cm, "host_matches", lambda rules: True)
    result = cm.estimate_ns_per_day(8000, "gaff", hp=HP, rules={})
    assert result["ns_per_day"] is None
    assert result["confidence"] == "none"


def test_gpu_hours_conversion_arithmetic(monkeypatch):
    monkeypatch.setattr(cm, "host_matches", lambda rules: True)
    # exact-match point: 15040 atoms, 17.384 ns/day, dt=1fs
    result = cm.gpu_hours(15040, steps=500_000, dt_fs=1.0, ff_family="pcff",
                         gpu_per_run=1, hp=HP, rules={})
    simulated_ns = 500_000 * 1.0 * 1e-6  # 0.5 ns
    expected_hours = (simulated_ns / 17.384) * 24.0 * 1
    assert abs(result["gpu_hours"] - expected_hours) < 1e-4  # gpu_hours() rounds to 4dp


def test_gpu_hours_scales_with_gpu_per_run(monkeypatch):
    monkeypatch.setattr(cm, "host_matches", lambda rules: True)
    one_gpu = cm.gpu_hours(15040, 500_000, 1.0, "pcff", gpu_per_run=1, hp=HP, rules={})
    two_gpu = cm.gpu_hours(15040, 500_000, 1.0, "pcff", gpu_per_run=2, hp=HP, rules={})
    assert abs(two_gpu["gpu_hours"] - 2 * one_gpu["gpu_hours"]) < 1e-6


def test_zero_atoms_or_steps_costs_nothing(monkeypatch):
    monkeypatch.setattr(cm, "host_matches", lambda rules: True)
    assert cm.gpu_hours(0, 500_000, 1.0, "pcff", hp=HP, rules={})["gpu_hours"] == 0.0
    assert cm.gpu_hours(15040, 0, 1.0, "pcff", hp=HP, rules={})["gpu_hours"] == 0.0


def test_no_benchmark_data_gpu_hours_is_none(monkeypatch):
    monkeypatch.setattr(cm, "host_matches", lambda rules: True)
    result = cm.gpu_hours(8000, 500_000, 1.0, "gaff", hp=HP, rules={})
    assert result["gpu_hours"] is None
    assert result["confidence"] == "none"


# --- plan_cost_estimate: per-stage step-count reuse -----------------------------------

EFFECTIVE_CLASS_TG = {
    "dt_fs": 1.0, "tg_t_step_K": 20, "tg_t_high_K": 600, "tg_t_low_K": 200,
    "tg_rates_K_per_ns": [25, 50], "tg_min_steps_per_T": 200000,
}


def test_tg_sweep_total_steps_sums_across_configured_rates():
    total, note = cm._tg_sweep_total_steps(EFFECTIVE_CLASS_TG)
    # n_bins mirrors script_generator.py's real temp-list construction: T_START down to
    # T_END by T_STEP, always force-appending T_END even when the range divides evenly --
    # for 600->200 step 20 that's 20 grid points (600,580,...,220) plus the forced 200 = 21,
    # not the naive (600-200)/20=20 a range-length/step formula would give.
    n_bins = 21
    # rate=25: n_steps_per_t = 20/(25*1*1e-6) = 800000 (above floor)
    # rate=50: n_steps_per_t = 20/(50*1*1e-6) = 400000 (above floor)
    expected = n_bins * 800000 + n_bins * 400000
    assert total == expected
    assert "2 rate(s)" in note


def test_tg_sweep_n_bins_matches_real_generator_on_a_non_exact_range():
    """Regression: PE1's real committed plan (sweep top 450 K, tg_t_low_K=100,
    tg_t_step_K=20 -- range 350 is not an exact multiple of 20) confirmed against its
    actual LAMMPS logs that script_generator.py's temp list has 19 points, not
    round(350/20)=18. cost_model must match the real generator exactly, not a
    closed-form approximation of it.

    The top is T_melt_hold_K now (the staircase starts at the gated melt cell), not the
    retired tg_t_high_K -- the arithmetic under test is unchanged."""
    cls = {"dt_fs": 2.0, "tg_t_step_K": 20, "T_melt_hold_K": 450, "tg_t_low_K": 100,
           "tg_rates_K_per_ns": [40], "tg_min_steps_per_T": 250000}
    total, note = cm._tg_sweep_total_steps(cls)
    assert "19 T-bin(s)" in note
    assert total == 19 * 250000


def test_tg_sweep_missing_config_is_unpriced():
    total, note = cm._tg_sweep_total_steps({"dt_fs": 1.0})
    assert total is None
    assert "no tg_rates_K_per_ns" in note


def test_murnaghan_total_steps_multiplies_pressures_by_sampling_factor():
    cls = {"bm_pressures_atm": [-1000, 0, 3000, 7000, 15000], "bm_npt_steps": 500000,
           "mechanical_sampling_factor": 2}
    total, note = cm._murnaghan_total_steps(cls)
    assert total == 5 * 500000 * 2
    assert "5 pressure point(s)" in note


def test_plan_cost_estimate_reports_equil_as_unpriced_but_prices_tg(monkeypatch):
    monkeypatch.setattr(cm, "host_matches", lambda rules: True)
    monkeypatch.setattr(cm, "load_rules", lambda: {"hardware_policy": HP,
                                                    "classes": {"PACR": {
                                                        "preferred_ff": "pcff", "dt_fs": 1.0,
                                                        "tg_t_step_K": 20, "tg_t_high_K": 600,
                                                        "tg_t_low_K": 200,
                                                        "tg_rates_K_per_ns": [25, 50],
                                                        "tg_min_steps_per_T": 200000,
                                                    }}})
    monkeypatch.setattr(cm, "hardware_policy", lambda rules=None: HP)
    monkeypatch.setattr("select_hardware._monomer_atoms_and_mw", lambda smiles, is_ua: (15, 100.12))

    plan = {
        "smiles": "*CC(C)(C(=O)OC)*", "polymer_class": "PACR",
        "decided_params": {"dp_typical": 50, "nchain": 20, "preferred_ff": "pcff"},
        "planned_stages": [{"stage": "build"}, {"stage": "equil"}, {"stage": "tg"}],
    }
    result = cm.plan_cost_estimate(plan)
    assert "error" not in result
    assert "equil" in {u["stage"] for u in result["unpriced_stages"]}
    assert "tg" in result["stages"]
    assert result["stages"]["tg"]["gpu_hours"] is not None
    assert result["total_gpu_hours"] == result["stages"]["tg"]["gpu_hours"]


def test_plan_cost_estimate_missing_smiles_is_an_error():
    assert "error" in cm.plan_cost_estimate({"polymer_class": "PACR"})
