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
    validate_overrides,
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
        "warmup_steps": 100000, "densify_ramp_steps": 200000,
        "densify_check_every_steps": 300000, "densify_steps_cap": 900000,
        "ff_activate_npt_steps": 150000,
        "anneal_heat_steps": 400000, "anneal_check_every_steps": 500000,
        "anneal_cap_steps": 1500000,
        "cool_block_dT_K": 25.0, "cool_block_hold_steps": 250000,
        "cool_block_hold_cap_steps": 750000,
        "stage7_min_steps": 600000, "stage7_cap_steps": 2400000,
        "stage8_min_steps": 700000, "stage8_cap_steps": 3500000,
        "compression_max_pressure_atm": 75000.0,
        "thermostat_damp_fs": 150.0, "barostat_damp_fs": 1500.0,
    }

    resolved = resolve_stage_params("equil", _args(), cls)

    assert resolved["anneal_cap_steps"] == 1500000
    assert resolved["anneal_heat_steps"] == 400000
    assert resolved["anneal_check_every_steps"] == 500000
    assert resolved["densify_ramp_steps"] == 200000
    assert resolved["compression_max_pressure_atm"] == 75000.0
    assert resolved["use_long_range_electrostatics"] is False
    assert resolved["thermostat_damp_fs"] == 150.0
    assert resolved["barostat_damp_fs"] == 1500.0
    # The descent's knobs belong to the COOLING stage now and are deliberately absent here --
    # passing them to the core chain would be passing arguments its generator does not take.
    for descent_knob in ("cool_block_hold_steps", "stage7_min_steps", "stage8_min_steps"):
        assert descent_knob not in resolved

    cooled = resolve_stage_params("cool", _args(), cls)
    assert cooled["cool_block_hold_steps"] == 250000
    assert cooled["cool_block_hold_cap_steps"] == 750000
    assert cooled["stage7_min_steps"] == 600000
    assert cooled["stage8_min_steps"] == 700000
    assert cooled["thermostat_damp_fs"] == 150.0


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
        overrides={"anneal_cap_steps": 3000000, "anneal_heat_steps": 500000,
                   "P_equil_atm": 1.5},
        confidence="high",
    )

    plan = materialize_plan(intent, decision)

    assert plan["decided_params"]["anneal_cap_steps"] == 3000000
    assert plan["decided_params"]["anneal_heat_steps"] == 500000
    assert plan["decided_params"]["P_equil_atm"] == 1.5


def test_integer_protocol_controls_reject_fractional_values():
    with pytest.raises(ValueError, match="anneal_cap_steps must be an integer"):
        validate_overrides({"anneal_cap_steps": 2.5})


@pytest.mark.parametrize(("overrides", "message"), [
    ({"tg_t_low_K": 700, "T_melt_hold_K": 600}, "tg_t_low_K"),
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
