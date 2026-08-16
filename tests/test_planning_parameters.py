"""Every advertised scientific knob must survive planning and parameter resolution."""

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from run_campaign import _base_args  # noqa: E402
from scientific_control import (  # noqa: E402
    ALLOWED_OVERRIDES,
    PlanDecision,
    ScientificIntent,
    _validate_overrides,
    materialize_plan,
    planning_context,
    planning_parameter_contract,
)
from stage_params import resolve_stage_params  # noqa: E402


def _args():
    args = _base_args("TUNABLE_TEST", "PSTR", "/tmp/plan.json")
    args.smiles = "*CC(c1ccccc1)*"
    args.data_path = "/tmp/cell.data"
    args.gpu_ids = "0"
    args.mpi_ranks = 1
    args.engine = "kokkos"
    return args


def test_planning_context_exposes_bounded_contract_for_every_override():
    intent = ScientificIntent("TUNABLE_TEST", "test parameters", "*CC(c1ccccc1)*",
                              ("density",), "PSTR")
    contract = planning_parameter_contract()

    assert set(contract) == set(ALLOWED_OVERRIDES)
    assert planning_context(intent)["planning_parameters"] == contract
    assert all("type" in spec for spec in contract.values())


def test_equilibration_controls_resolve_to_executable_steps():
    cls = {
        "preferred_ff": "pcff", "electrostatics": "lj_cut", "dt_fs": 2.0,
        "T_equil_K": 650.0, "annealing_T_high_K": 800.0, "P_equil_atm": 2.0,
        "t_equil_ns": 7.0, "eq_annealing_cycles": 6, "anneal_cycle_ns": 1.5,
        "npt_prod_ns": 3.0, "npt_prod300_ns": 4.0,
        "compression_max_pressure_atm": 75000.0,
        "thermostat_damp_fs": 150.0, "barostat_damp_fs": 1500.0,
    }

    resolved = resolve_stage_params("equil", _args(), cls)

    assert resolved["eq_annealing_cycles"] == 6
    assert resolved["anneal_cycle_steps"] == 750000
    assert resolved["nvt_prod_steps"] == 3500000
    assert resolved["npt_prod_steps"] == 1500000
    assert resolved["npt_prod300_steps"] == 2000000
    assert resolved["compression_max_pressure_atm"] == 75000.0
    assert resolved["use_long_range_electrostatics"] is False
    assert resolved["thermostat_damp_fs"] == 150.0
    assert resolved["barostat_damp_fs"] == 1500.0


def test_thermal_and_mechanical_controls_resolve_without_hardcoded_replacement():
    cls = {
        "preferred_ff": "pcff", "electrostatics": "pppm", "dt_fs": 1.0,
        "P_equil_atm": 3.0, "thermostat_damp_fs": 125.0,
        "barostat_damp_fs": 1250.0, "tg_t_high_K": 700.0,
        "tg_t_low_K": 180.0, "tg_t_step_K": 10.0, "tg_steps_per_t": 900000,
        "K_deform_rate_inv_s": 2e8, "K_deform_rate_slow_inv_s": 2e7,
        "K_strain_max": 0.02, "deform_eq_steps": 350000,
        "deform_strain_start": 0.001, "deform_avg_window": 500,
        "bm_pressures_atm": [-500, 0, 500, 1000, 2000], "bm_npt_steps": 800000,
        "bm_temperature_K": 325.0, "bm_thermo_freq": 250,
    }
    args = _args()

    tg = resolve_stage_params("tg", args, cls)
    deform = resolve_stage_params("deform", args, cls)
    bm = resolve_stage_params("murnaghan", args, cls)
    analysis = resolve_stage_params("analyze-bm", args, cls)

    assert (tg["pressure_atm"], tg["thermostat_damp_fs"], tg["barostat_damp_fs"]) == (
        3.0, 125.0, 1250.0)
    assert deform["deform_eq_steps"] == 350000
    assert analysis["deform_strain_start"] == 0.001
    assert analysis["deform_avg_window"] == 500
    assert bm["npt_steps"] == 800000
    assert bm["temp_K"] == 325.0
    assert bm["thermo_freq"] == 250


def test_agent_can_materialize_new_protocol_controls():
    intent = ScientificIntent("TUNABLE_TEST", "adjust annealing", "*CC(c1ccccc1)*",
                              ("density",), "PSTR")
    decision = PlanDecision(
        polymer_class="PSTR", properties=("density",), rationale=("Long anneal needed.",),
        overrides={"eq_annealing_cycles": 12, "anneal_cycle_ns": 3.0,
                   "t_equil_ns": 20.0, "P_equil_atm": 1.5},
        confidence="high",
    )

    plan = materialize_plan(intent, decision)

    assert plan["decided_params"]["eq_annealing_cycles"] == 12
    assert plan["decided_params"]["anneal_cycle_ns"] == 3.0
    assert plan["decided_params"]["t_equil_ns"] == 20.0


def test_integer_protocol_controls_reject_fractional_values():
    with pytest.raises(ValueError, match="eq_annealing_cycles must be an integer"):
        _validate_overrides({"eq_annealing_cycles": 2.5})


@pytest.mark.parametrize(("overrides", "message"), [
    ({"tg_t_low_K": 700, "tg_t_high_K": 600}, "tg_t_low_K"),
    ({"deform_strain_start": 0.04, "K_strain_max": 0.03}, "deform_strain_start"),
    ({"tg_rates_K_per_ns": [10.0], "tg_primary_rate_index": 2},
     "tg_primary_rate_index"),
    ({"bm_pressures_atm": [0, 100, 200]}, "four unique points"),
])
def test_materialization_rejects_inconsistent_protocol_controls(overrides, message):
    intent = ScientificIntent("TUNABLE_TEST", "invalid bounds", "*CC(c1ccccc1)*",
                              ("density",), "PSTR")
    decision = PlanDecision(
        polymer_class="PSTR", properties=("density",), rationale=("test",),
        overrides=overrides, confidence="high",
    )

    with pytest.raises(ValueError, match=message):
        materialize_plan(intent, decision)


def test_every_planning_parameter_has_an_explicit_invalidation_owner():
    from workflow_engine import PARAMETER_STAGE

    assert set(ALLOWED_OVERRIDES) <= set(PARAMETER_STAGE)
