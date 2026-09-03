"""Deck-generation contract for generate_cooling_workflow.

The cooling chain is the second half of what used to be one 10-substep equilibration chain:
the blockwise descent from the gated melt cell to final_T_K, then nvt_kinetic_stability and
npt_final. It runs only when a property needs a cell at the assessment temperature.
"""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_DIR = REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"
SPEC = importlib.util.spec_from_file_location("lammps_engine_cooling_server",
                                              SERVER_DIR / "server.py")
server = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(SERVER_DIR))
try:
    SPEC.loader.exec_module(server)
finally:
    sys.path.remove(str(SERVER_DIR))

MELT_CELL = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")


def _base_kwargs(tmp_path, **overrides):
    kwargs = dict(
        data_file=MELT_CELL,
        params_file=str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.params"),
        work_dir_base=str(tmp_path), velocity_seed=4242,
        T_melt_hold_K=700.0, final_T_K=300.0,
        cool_block_dT_K=100.0, cool_block_hold_steps=6666, cool_block_hold_cap_steps=99999,
        stage7_min_steps=7777, stage7_cap_steps=99999,
        stage8_min_steps=8888, stage8_cap_steps=99999,
        use_long_range=False, press=2.0,
        use_pcff=True, use_trappe=False, use_opls=False,
        engine="kokkos", thermostat_damp_fs=150.0, barostat_damp_fs=1500.0,
    )
    kwargs.update(overrides)
    return kwargs


def test_full_descent_order_and_step_counts(tmp_path):
    """700 -> 300 K at dT=100 -> exactly 4 cool blocks, then the two assessment stages."""
    result = server.generate_cooling_workflow(**_base_kwargs(tmp_path))
    assert result["status"] == "success", result
    assert result["run_order"] == ["cool_block_01", "cool_block_02", "cool_block_03",
                                   "cool_block_04", "nvt_kinetic_stability", "npt_final"]
    by_name = {s["name"]: s for s in result["stages"]}
    for i in range(1, 5):
        assert by_name[f"cool_block_{i:02d}"]["params"]["N_STEPS"] == 6666
    assert by_name["cool_block_01"]["params"]["T_START"] == 700.0
    assert by_name["cool_block_04"]["params"]["T_FINAL"] == 300.0
    assert by_name["nvt_kinetic_stability"]["params"]["N_STEPS"] == 7777
    assert by_name["npt_final"]["params"]["N_STEPS"] == 8888
    assert result["n_cool_blocks"] == 4
    assert result["assessment_data_path"] == by_name["npt_final"]["output_data"]
    for name in result["run_order"]:
        params = by_name[name]["params"]
        if "T_DAMP" in params:
            assert params["T_DAMP"] == 150.0
        if "P_DAMP" in params:
            assert params["P_DAMP"] == 1500.0


def test_it_starts_from_the_melt_cell_it_was_given(tmp_path):
    result = server.generate_cooling_workflow(**_base_kwargs(tmp_path))
    assert result["stages"][0]["input_data"] == MELT_CELL


def test_the_descent_is_contiguous(tmp_path):
    """Each block starts where the previous one ended, and each reads the previous one's own
    output -- one continuous trajectory, not a set of independent quenches."""
    result = server.generate_cooling_workflow(**_base_kwargs(tmp_path))
    blocks = [s for s in result["stages"] if s["name"].startswith("cool_block")]
    for prev, nxt in zip(blocks, blocks[1:]):
        assert nxt["params"]["T_START"] == prev["params"]["T_FINAL"]
        assert nxt["input_data"] == prev["output_data"]


def test_an_uneven_span_still_lands_exactly_on_final_T(tmp_path):
    """550 -> 300 at dT=100 is 2.5 blocks; the last one is short rather than overshooting."""
    result = server.generate_cooling_workflow(
        **_base_kwargs(tmp_path, T_melt_hold_K=550.0, final_T_K=300.0))
    assert result["status"] == "success", result
    blocks = [s for s in result["stages"] if s["name"].startswith("cool_block")]
    assert len(blocks) == 3
    assert blocks[-1]["params"]["T_FINAL"] == 300.0


def test_melt_hold_equal_to_final_T_emits_no_cool_blocks(tmp_path):
    """The rubbery-shaped case: the melt IS the assessment cell. Legal, and it still produces
    the two stages the gate needs."""
    result = server.generate_cooling_workflow(
        **_base_kwargs(tmp_path, T_melt_hold_K=300.0, final_T_K=300.0))
    assert result["status"] == "success", result
    assert result["run_order"] == ["nvt_kinetic_stability", "npt_final"]
    assert result["n_cool_blocks"] == 0


def test_final_T_above_the_melt_hold_is_rejected(tmp_path):
    result = server.generate_cooling_workflow(
        **_base_kwargs(tmp_path, T_melt_hold_K=400.0, final_T_K=500.0))
    assert result["status"] == "error"
    assert "final_T_K" in result["error"]


def test_null_step_counts_select_defaults(tmp_path):
    result = server.generate_cooling_workflow(
        **_base_kwargs(tmp_path, cool_block_dT_K=None, cool_block_hold_steps=None,
                       cool_block_hold_cap_steps=None, stage7_min_steps=None,
                       stage7_cap_steps=None, stage8_min_steps=None, stage8_cap_steps=None))
    assert result["status"] == "success", result
    assert all(s["params"]["N_STEPS"] > 0 for s in result["stages"])


def test_a_null_velocity_seed_is_rejected(tmp_path):
    result = server.generate_cooling_workflow(**_base_kwargs(tmp_path, velocity_seed=None))
    assert result["status"] == "error"
    assert "velocity_seed" in result["error"]


def test_no_stage_recreates_velocities(tmp_path):
    """Every stage inherits velocities from the incoming .data -- the melt's own. A
    `velocity all create` here would discard the equilibrated momenta the melt gate passed."""
    result = server.generate_cooling_workflow(**_base_kwargs(tmp_path))
    for stage in result["stages"]:
        assert stage["params"].get("init_velocity") in (None, False)


# ── resume_from ───────────────────────────────────────────────────────────────

def test_resume_from_cool_block_starts_at_the_assessment_stages(tmp_path):
    result = server.generate_cooling_workflow(
        **_base_kwargs(tmp_path, resume_from="cool_block"))
    assert result["status"] == "success", result
    assert result["run_order"] == ["nvt_kinetic_stability", "npt_final"]
    assert result["stages"][0]["input_data"] == MELT_CELL


def test_resume_from_nvt_kinetic_stability_starts_at_npt_final(tmp_path):
    result = server.generate_cooling_workflow(
        **_base_kwargs(tmp_path, resume_from="nvt_kinetic_stability"))
    assert result["status"] == "success", result
    assert result["run_order"] == ["npt_final"]


def test_resume_from_rejects_an_equilibration_checkpoint(tmp_path):
    for name in ("anneal_hold", "npt_melt_hold", "npt_final"):
        result = server.generate_cooling_workflow(
            **_base_kwargs(tmp_path, resume_from=name))
        assert result["status"] == "error", name


# ── extend_only ───────────────────────────────────────────────────────────────

def test_extend_only_cool_block_requires_extend_temp_k(tmp_path):
    """A cool_block's hold temperature depends on its position in the ramp and cannot be
    inferred from the name."""
    result = server.generate_cooling_workflow(
        **_base_kwargs(tmp_path, extend_only=True, base_stage_name="cool_block_02",
                       extend_ensemble="npt",
                       restart_file=str(tmp_path / "cool_block_02_out.restart")))
    assert result["status"] == "error"
    assert "extend_temp_K" in result["error"]


def test_extend_only_cool_block_with_extend_temp_k_succeeds(tmp_path):
    result = server.generate_cooling_workflow(
        **_base_kwargs(tmp_path, extend_only=True, base_stage_name="cool_block_02",
                       extend_ensemble="npt", extend_temp_K=500.0,
                       restart_file=str(tmp_path / "cool_block_02_out.restart")))
    assert result["status"] == "success", result
    stage = result["stages"][0]
    assert stage["params"]["T_START"] == 500.0
    assert stage["params"]["T_FINAL"] == 500.0
    assert stage["params"]["use_restart"] is True
    assert stage["params"]["LOG_APPEND"] is True


def test_extend_only_npt_final_holds_at_final_T(tmp_path):
    result = server.generate_cooling_workflow(
        **_base_kwargs(tmp_path, extend_only=True, base_stage_name="npt_final",
                       extend_ensemble="npt",
                       restart_file=str(tmp_path / "npt_final_out.restart")))
    assert result["status"] == "success", result
    assert result["stages"][0]["params"]["T_START"] == 300.0
    assert result["assessment_data_path"] is None


def test_extend_only_rejects_ensemble_mismatch(tmp_path):
    result = server.generate_cooling_workflow(
        **_base_kwargs(tmp_path, extend_only=True, base_stage_name="nvt_kinetic_stability",
                       extend_ensemble="npt",
                       restart_file=str(tmp_path / "nvt_kinetic_stability_out.restart")))
    assert result["status"] == "error"
    assert "extend_ensemble" in result["error"]


def test_extend_only_rejects_an_equilibration_stage_name(tmp_path):
    result = server.generate_cooling_workflow(
        **_base_kwargs(tmp_path, extend_only=True, base_stage_name="anneal_hold",
                       extend_ensemble="nvt",
                       restart_file=str(tmp_path / "anneal_hold_out.restart")))
    assert result["status"] == "error"


def test_both_chains_emit_the_same_force_field_styles(tmp_path):
    """The cooling chain reads the equilibration chain's own .data file. If the two disagreed
    on pair_style the second half would silently simulate a different system -- the class of
    bug _ff_base_for exists to make impossible."""
    equil = server.generate_equilibration_workflow(
        data_file=MELT_CELL,
        params_file=str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.params"),
        work_dir_base=str(tmp_path / "equil"), velocity_seed=4242,
        densify_ramp_steps=None, densify_check_every_steps=None, densify_steps_cap=None,
        ff_activate_npt_steps=None, anneal_heat_steps=None, anneal_check_every_steps=None,
        anneal_cap_steps=None, melt_ramp_steps=None, melt_hold_min_steps=None,
        melt_hold_cap_steps=None, nvt_melt_min_steps=None, nvt_melt_cap_steps=None,
        warmup_steps=None, use_long_range=False, melt_hold_T=700.0, max_temp=800.0,
        use_pcff=True, use_trappe=False, use_opls=False, engine="kokkos",
    )
    cool = server.generate_cooling_workflow(**_base_kwargs(tmp_path / "cool"))
    assert equil["status"] == "success" and cool["status"] == "success"
    ff_keys = ("use_pcff", "use_trappe", "use_opls", "use_shake", "engine")
    equil_ff = {k: equil["stages"][-1]["params"].get(k) for k in ff_keys}
    cool_ff = {k: cool["stages"][-1]["params"].get(k) for k in ff_keys}
    assert equil_ff == cool_ff
