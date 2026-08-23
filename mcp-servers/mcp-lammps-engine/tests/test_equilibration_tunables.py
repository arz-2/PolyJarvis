import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_DIR = REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"
SPEC = importlib.util.spec_from_file_location("lammps_engine_tunables_server",
                                              SERVER_DIR / "server.py")
server = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(SERVER_DIR))
try:
    SPEC.loader.exec_module(server)
finally:
    sys.path.remove(str(SERVER_DIR))


FULL_CHAIN_ORDER = [
    "minimize", "nvt_warmup", "npt_densify", "npt_ff_activate", "npt_densify_hold",
    "anneal_heat", "anneal_hold",
    "cool_block_01", "cool_block_02", "cool_block_03", "cool_block_04",
    "nvt_kinetic_stability", "npt_final",
]


def _base_kwargs(tmp_path, **overrides):
    kwargs = dict(
        data_file=str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data"),
        params_file=str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.params"),
        work_dir_base=str(tmp_path), velocity_seed=4242,
        densify_ramp_steps=1111, densify_check_every_steps=2222, densify_steps_cap=99999,
        ff_activate_npt_steps=3333,
        anneal_heat_steps=4444, anneal_check_every_steps=5555, anneal_cap_steps=99999,
        cool_block_dT_K=100.0, cool_block_hold_steps=6666, cool_block_hold_cap_steps=99999,
        stage7_min_steps=7777, stage7_cap_steps=99999,
        stage8_min_steps=8888, stage8_cap_steps=99999,
        warmup_steps=9999,
        use_long_range=False, temp=300.0, max_temp=700.0, press=2.0,
        max_press=60000.0, use_pcff=True, use_trappe=False, use_opls=False,
        engine="kokkos", thermostat_damp_fs=150.0, barostat_damp_fs=1500.0,
    )
    kwargs.update(overrides)
    return kwargs


def test_full_chain_order_and_step_counts_forward_correctly(tmp_path):
    """max_temp=700, temp=300, cool_block_dT_K=100 -> exactly 4 cool blocks (700->300)."""
    result = server.generate_equilibration_workflow(**_base_kwargs(tmp_path))

    assert result["status"] == "success", result
    assert result["run_order"] == FULL_CHAIN_ORDER
    by_name = {stage["name"]: stage for stage in result["stages"]}

    for name in result["run_order"]:
        params = by_name[name]["params"]
        if "T_DAMP" in params:
            assert params["T_DAMP"] == 150.0
        if "P_DAMP" in params:
            assert params["P_DAMP"] == 1500.0

    assert by_name["nvt_warmup"]["params"]["N_STEPS"] == 9999
    assert by_name["npt_densify"]["params"]["N_STEPS"] == 1111
    assert by_name["npt_densify"]["params"]["P_FINAL"] == 60000.0
    assert by_name["npt_ff_activate"]["params"]["N_STEPS"] == 3333
    assert by_name["npt_densify_hold"]["params"]["N_STEPS"] == 2222
    assert by_name["anneal_heat"]["params"]["N_STEPS"] == 4444
    assert by_name["anneal_heat"]["params"]["T_FINAL"] == 700.0
    assert by_name["anneal_hold"]["params"]["N_STEPS"] == 5555
    assert by_name["anneal_hold"]["params"]["T_START"] == 700.0
    for i in range(1, 5):
        assert by_name[f"cool_block_{i:02d}"]["params"]["N_STEPS"] == 6666
    assert by_name["cool_block_01"]["params"]["T_START"] == 700.0
    assert by_name["cool_block_04"]["params"]["T_FINAL"] == 300.0
    assert by_name["nvt_kinetic_stability"]["params"]["N_STEPS"] == 7777
    assert by_name["npt_final"]["params"]["N_STEPS"] == 8888
    assert all(not stage["params"].get("use_pppm", False) for stage in result["stages"])


def test_null_step_counts_select_atom_count_tier_defaults(tmp_path):
    null_steps = dict(
        densify_ramp_steps=None, densify_check_every_steps=None, densify_steps_cap=None,
        ff_activate_npt_steps=None, anneal_heat_steps=None, anneal_check_every_steps=None,
        anneal_cap_steps=None, cool_block_hold_steps=None, cool_block_hold_cap_steps=None,
        stage7_min_steps=None, stage7_cap_steps=None, stage8_min_steps=None,
        stage8_cap_steps=None, warmup_steps=None,
    )
    result = server.generate_equilibration_workflow(**_base_kwargs(tmp_path, **null_steps))
    assert result["status"] == "success", result
    by_name = {stage["name"]: stage for stage in result["stages"]}
    for name in ("nvt_warmup", "npt_densify", "npt_ff_activate", "npt_densify_hold",
                "anneal_heat", "anneal_hold", "cool_block_01", "nvt_kinetic_stability",
                "npt_final"):
        assert by_name[name]["params"]["N_STEPS"] > 0


# ── resume_from checkpoint walk ──────────────────────────────────────────────

def test_resume_from_rejects_unsupported_value(tmp_path):
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, resume_from="npt_compress")
    )
    assert result["status"] == "error"
    assert "resume_from" in result["error"]


def test_resume_from_rejects_extend_only_combination(tmp_path):
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, resume_from="anneal_hold", extend_only=True)
    )
    assert result["status"] == "error"


def test_resume_from_npt_final_is_rejected_as_nothing_left_to_generate(tmp_path):
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, resume_from="npt_final")
    )
    assert result["status"] == "error"
    assert "npt_final" in result["error"]


_CHECKPOINTS = ["nvt_warmup", "npt_densify", "npt_ff_activate", "npt_densify_hold",
               "anneal_hold", "cool_block", "nvt_kinetic_stability"]


def test_resume_from_each_checkpoint_yields_the_correct_tail(tmp_path):
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    for name in _CHECKPOINTS:
        result = server.generate_equilibration_workflow(
            **_base_kwargs(tmp_path, data_file=checkpoint, resume_from=name)
        )
        assert result["status"] == "success", (name, result)
        assert result["resumed_from"] == name
        expected_tail = FULL_CHAIN_ORDER[FULL_CHAIN_ORDER.index(_LAST_STAGE_OF[name]) + 1:]
        assert result["run_order"] == expected_tail, (name, result["run_order"])
        assert result["stages"][0]["input_data"] == checkpoint


# Maps each resume_from checkpoint name to the LAST concrete stage name it bundles (the point
# after which generation resumes) -- e.g. "anneal_hold" bundles anneal_heat+anneal_hold, so
# resuming from it starts after anneal_hold itself; "cool_block" bundles the whole ramp, so
# resuming from it starts after the LAST cool block in this test's 4-block full chain.
_LAST_STAGE_OF = {
    "nvt_warmup": "nvt_warmup",
    "npt_densify": "npt_densify",
    "npt_ff_activate": "npt_ff_activate",
    "npt_densify_hold": "npt_densify_hold",
    "anneal_hold": "anneal_hold",
    "cool_block": "cool_block_04",
    "nvt_kinetic_stability": "nvt_kinetic_stability",
}


# ── melt/production reference tagging ────────────────────────────────────────

def test_glassy_temp_tags_the_matching_cool_block_as_melt_reference(tmp_path):
    """temp between final_T_K and max_temp (the glassy case) -> the cool_block reaching
    exactly `temp` is tagged as melt_data_path, and the ramp continues past it to final_T_K."""
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, temp=500.0, max_temp=700.0, final_T_K=300.0,
                      cool_block_dT_K=100.0)
    )
    assert result["status"] == "success", result
    # 700 -> 500 -> 300 in 100 K steps: cool_block_02 ends at 500 (the tag), _04 ends at 300.
    by_name = {stage["name"]: stage for stage in result["stages"]}
    assert result["melt_data_path"] == by_name["cool_block_02"]["output_data"]
    assert by_name["cool_block_02"]["params"]["T_FINAL"] == 500.0
    assert by_name["cool_block_04"]["params"]["T_FINAL"] == 300.0


def test_rubbery_t_equil_k_tags_a_cool_block_and_gets_extra_hold(tmp_path):
    """Rubbery (temp == final_T_K): t_equil_K is the direct successor to the retired
    add_melt_npt flag -- an explicit melt-reference tag somewhere above final_T_K."""
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, temp=300.0, final_T_K=300.0, max_temp=700.0,
                      cool_block_dT_K=100.0, t_equil_K=500.0, melt_hold_extra_steps=999)
    )
    assert result["status"] == "success", result
    by_name = {stage["name"]: stage for stage in result["stages"]}
    assert result["melt_data_path"] == by_name["cool_block_02"]["output_data"]
    assert by_name["cool_block_02"]["params"]["N_STEPS"] == 6666 + 999
    assert by_name["cool_block_01"]["params"]["N_STEPS"] == 6666  # untagged block: no extra


def test_no_melt_tag_when_rubbery_and_no_t_equil_k(tmp_path):
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, temp=300.0, final_T_K=300.0)
    )
    assert result["status"] == "success", result
    assert result["melt_data_path"] is None


# ── anneal-margin validation ──────────────────────────────────────────────────

def test_max_temp_too_close_to_temp_is_rejected(tmp_path):
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, temp=300.0, max_temp=350.0, anneal_margin_K=100.0)
    )
    assert result["status"] == "error"
    assert "anneal_margin_K" in result["error"] or "max_temp" in result["error"]


def test_final_t_k_above_temp_is_rejected(tmp_path):
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, temp=300.0, final_T_K=350.0, max_temp=700.0)
    )
    assert result["status"] == "error"


# ── extend_only restart-continuation ──────────────────────────────────────────

def test_extend_only_requires_restart_file_and_base_stage_name(tmp_path):
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, extend_only=True)
    )
    assert result["status"] == "error"


def test_extend_only_rejects_ensemble_mismatch_for_nvt_stage(tmp_path):
    """anneal_hold is NVT -- extending it as npt (the signature default) would silently turn
    a barostat on mid-trajectory. Must be rejected, not silently accepted."""
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, extend_only=True, base_stage_name="anneal_hold",
                       restart_file=str(tmp_path / "anneal_hold_out.restart"))
    )
    assert result["status"] == "error"
    assert "extend_ensemble" in result["error"]


def test_extend_only_rejects_ensemble_mismatch_for_npt_stage(tmp_path):
    """npt_final is NPT -- extending it as nvt would silently drop the barostat."""
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, extend_only=True, base_stage_name="npt_final",
                       restart_file=str(tmp_path / "npt_final_out.restart"),
                       extend_ensemble="nvt")
    )
    assert result["status"] == "error"
    assert "extend_ensemble" in result["error"]


def test_extend_only_correct_ensemble_emits_matching_stage(tmp_path):
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, extend_only=True,
                      base_stage_name="anneal_hold", extend_ensemble="nvt",
                      restart_file=str(tmp_path / "anneal_hold_out.restart"))
    )
    assert result["status"] == "success", result
    assert result["run_order"] == ["anneal_hold"]
    stage = result["stages"][0]
    assert stage["template"] == "nvt"
    assert "P_START" not in stage["params"]
    assert stage["params"]["use_restart"] is True
    assert stage["params"]["LOG_APPEND"] is True
    assert stage["params"]["dump_append"] is True
    assert stage["params"]["init_velocity"] is None
    assert stage["input_data"] == str(tmp_path / "anneal_hold_out.restart")


def test_extend_only_cool_block_requires_extend_temp_k(tmp_path):
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, extend_only=True,
                      base_stage_name="cool_block_02", extend_ensemble="npt",
                      restart_file=str(tmp_path / "cool_block_02_out.restart"))
    )
    assert result["status"] == "error"
    assert "extend_temp_K" in result["error"]


def test_extend_only_cool_block_with_extend_temp_k_succeeds(tmp_path):
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, extend_only=True,
                      base_stage_name="cool_block_02", extend_ensemble="npt",
                      extend_temp_K=500.0,
                      restart_file=str(tmp_path / "cool_block_02_out.restart"))
    )
    assert result["status"] == "success", result
    stage = result["stages"][0]
    assert stage["params"]["T_START"] == 500.0
    assert stage["params"]["T_FINAL"] == 500.0


def test_extend_only_unrecognized_base_stage_name_rejected(tmp_path):
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, extend_only=True, base_stage_name="npt_compress",
                       restart_file=str(tmp_path / "x.restart"))
    )
    assert result["status"] == "error"


def test_extend_then_resume_uses_the_extend_stage_output(tmp_path):
    """The real adaptive-loop use case: extend npt_densify_hold's own trajectory (a separate
    run_lammps_chain submission, waited on to completion), then resume from that real endpoint
    to build anneal_heat onward."""
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    extend_result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, extend_only=True,
                      base_stage_name="npt_densify_hold", extend_ensemble="npt",
                      restart_file=str(tmp_path / "npt_densify_hold_out.restart"))
    )
    assert extend_result["status"] == "success", extend_result
    extend_output = extend_result["stages"][0]["output_data"]
    Path(extend_output).parent.mkdir(parents=True, exist_ok=True)
    Path(extend_output).write_text(Path(checkpoint).read_text())  # stand-in for the real output

    resume_result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=extend_output, resume_from="npt_densify_hold")
    )
    assert resume_result["status"] == "success", resume_result
    assert resume_result["stages"][0]["input_data"] == extend_output
    assert resume_result["run_order"][0] == "anneal_heat"
