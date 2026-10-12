"""Deck-generation contract for the CORE equilibration chain.

The chain ends at the melt hold. Everything about the descent to the assessment temperature
(cool_block_NN, nvt_kinetic_stability, npt_final) moved to generate_cooling_workflow and is
covered by test_cooling_workflow.py.
"""
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
    "npt_melt_ramp", "nvt_melt_hold", "npt_melt_hold",
]


def _base_kwargs(tmp_path, **overrides):
    kwargs = dict(
        data_file=str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data"),
        params_file=str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.params"),
        work_dir_base=str(tmp_path), velocity_seed=4242,
        densify_ramp_steps=1111, densify_check_every_steps=2222, densify_steps_cap=99999,
        ff_activate_npt_steps=3333,
        anneal_heat_steps=4444, anneal_check_every_steps=5555, anneal_cap_steps=99999,
        melt_ramp_steps=6666, melt_hold_min_steps=7777, melt_hold_cap_steps=99999,
        nvt_melt_min_steps=8888, nvt_melt_cap_steps=99999,
        warmup_steps=9999,
        use_long_range=False, melt_hold_T=550.0, max_temp=700.0, press=2.0,
        max_press=60000.0, use_pcff=True, use_trappe=False, use_opls=False,
        engine="kokkos", thermostat_damp_fs=150.0, barostat_damp_fs=1500.0,
    )
    kwargs.update(overrides)
    return kwargs


def test_full_chain_order_and_step_counts_forward_correctly(tmp_path):
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
    # The melt tail: ceiling -> melt hold, then hold, then the fixed-volume window.
    assert by_name["npt_melt_ramp"]["params"]["N_STEPS"] == 6666
    assert by_name["npt_melt_ramp"]["params"]["T_START"] == 700.0
    assert by_name["npt_melt_ramp"]["params"]["T_FINAL"] == 550.0
    assert by_name["nvt_melt_hold"]["params"]["N_STEPS"] == 8888
    assert by_name["nvt_melt_hold"]["params"]["T_START"] == 550.0
    assert by_name["npt_melt_hold"]["params"]["N_STEPS"] == 7777
    assert by_name["npt_melt_hold"]["params"]["T_START"] == 550.0
    assert by_name["npt_melt_hold"]["params"]["T_FINAL"] == 550.0
    assert all(not stage["params"].get("use_pppm", False) for stage in result["stages"])


def test_the_melt_hold_is_npt_and_the_window_after_it_is_nvt(tmp_path):
    """The whole point of the pair. Melt density and the thermo gates need a barostat; MSD /
    kinetic-trap / C(t) need a FIXED volume, because a barostatted trajectory affine-scales
    coordinates every step and contaminates cumulative CoM displacement."""
    result = server.generate_equilibration_workflow(**_base_kwargs(tmp_path))
    by_name = {stage["name"]: stage for stage in result["stages"]}
    assert by_name["npt_melt_hold"]["template"] == "npt"
    assert "P_START" in by_name["npt_melt_hold"]["params"]
    assert by_name["nvt_melt_hold"]["template"] == "nvt"
    assert "P_START" not in by_name["nvt_melt_hold"]["params"]


def test_the_melt_cell_is_named_explicitly_in_the_return(tmp_path):
    """Downstream must never have to guess which stage is which by position. npt_melt_hold is
    terminal, so the gated cell and the handoff cell are one file, named under both keys."""
    result = server.generate_equilibration_workflow(**_base_kwargs(tmp_path))
    by_name = {stage["name"]: stage for stage in result["stages"]}
    assert result["melt_data_path"] == by_name["npt_melt_hold"]["output_data"]
    assert result["melt_start_data_path"] == by_name["npt_melt_hold"]["output_data"]
    # The ordering: the ramp sets the box, the NVT hold relaxes the structure at fixed volume,
    # the closing NPT corrects the residual and measures the density on a relaxed cell.
    assert by_name["nvt_melt_hold"]["input_data"] == by_name["npt_melt_ramp"]["output_data"]
    assert by_name["npt_melt_hold"]["input_data"] == by_name["nvt_melt_hold"]["output_data"]


def test_this_chain_never_cools(tmp_path):
    """Regression pin for the split itself: no cool_block, no npt_final, no final_T_K arg."""
    result = server.generate_equilibration_workflow(**_base_kwargs(tmp_path))
    names = set(result["run_order"])
    assert not any(n.startswith("cool_block") for n in names)
    assert "nvt_kinetic_stability" not in names
    assert "npt_final" not in names
    coldest = min(s["params"]["T_FINAL"] for s in result["stages"]
                  if "T_FINAL" in s["params"] and s["name"].startswith(("npt_melt", "nvt_melt")))
    assert coldest == 550.0


def test_null_step_counts_select_atom_count_tier_defaults(tmp_path):
    null_steps = dict(
        densify_ramp_steps=None, densify_check_every_steps=None, densify_steps_cap=None,
        ff_activate_npt_steps=None, anneal_heat_steps=None, anneal_check_every_steps=None,
        anneal_cap_steps=None, melt_ramp_steps=None, melt_hold_min_steps=None,
        melt_hold_cap_steps=None, nvt_melt_min_steps=None, nvt_melt_cap_steps=None,
        warmup_steps=None,
    )
    result = server.generate_equilibration_workflow(**_base_kwargs(tmp_path, **null_steps))
    assert result["status"] == "success", result
    by_name = {stage["name"]: stage for stage in result["stages"]}
    for name in FULL_CHAIN_ORDER:
        if name == "minimize":
            continue
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


def test_resume_from_a_cooling_stage_is_rejected(tmp_path):
    """The cooldown's checkpoints belong to generate_cooling_workflow now."""
    for name in ("cool_block", "nvt_kinetic_stability", "npt_final"):
        result = server.generate_equilibration_workflow(
            **_base_kwargs(tmp_path, resume_from=name)
        )
        assert result["status"] == "error", name


def test_resume_from_nvt_melt_hold_regenerates_only_the_terminal_npt(tmp_path):
    """The melt gate's two-step structural EXTEND depends on exactly this: after lengthening
    nvt_melt_hold, the terminal npt_melt_hold was built from a structure that no longer exists
    and is stale both as the gated cell and as the handoff cell."""
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, resume_from="nvt_melt_hold")
    )
    assert result["status"] == "success", result
    assert result["run_order"] == ["npt_melt_hold"]
    assert result["stages"][0]["input_data"] == checkpoint
    assert result["melt_data_path"] == result["stages"][0]["output_data"]
    assert result["melt_start_data_path"] == result["stages"][0]["output_data"]


_CHECKPOINTS = ["nvt_warmup", "npt_densify", "npt_ff_activate", "npt_densify_hold",
                "anneal_hold", "npt_melt_ramp", "nvt_melt_hold"]

# Maps each resume_from checkpoint name to the LAST concrete stage name it bundles (the point
# after which generation resumes) -- e.g. "anneal_hold" bundles anneal_heat+anneal_hold, so
# resuming from it starts after anneal_hold itself.
_LAST_STAGE_OF = {name: name for name in _CHECKPOINTS}


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


# ── anneal-ceiling validation ─────────────────────────────────────────────────

def test_max_temp_below_the_melt_hold_is_rejected(tmp_path):
    """npt_melt_ramp descends from the ceiling to the melt hold; a ceiling below it would make
    that an ascent."""
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, melt_hold_T=700.0, max_temp=600.0)
    )
    assert result["status"] == "error"
    assert "max_temp" in result["error"]


def test_max_temp_equal_to_the_melt_hold_is_accepted(tmp_path):
    """A soak with no headroom is legal (the ramp is then a no-op) and only warned about --
    how much hotter than the melt to soak is a planning-layer judgement, not a correctness
    one. The old hard >= temp + anneal_margin_K guard was an off-by-one that blocked a live
    a-PS/PSTR run in 2026-08-25; the invariant it protected now lives in stage_params."""
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, melt_hold_T=600.0, max_temp=600.0)
    )
    assert result["status"] == "success", result


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
    """npt_melt_hold is NPT -- extending it as nvt would silently drop the barostat, which is
    the one thing the melt-density measurement cannot lose."""
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, extend_only=True, base_stage_name="npt_melt_hold",
                       restart_file=str(tmp_path / "npt_melt_hold_out.restart"),
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


def test_extend_only_melt_holds_continue_at_the_melt_temperature(tmp_path):
    """Neither melt hold needs extend_temp_K: both hold at melt_hold_T, which the call already
    carries. (A cool_block_NN genuinely does need it -- that lives in the cooling tool now.)"""
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    for base, ensemble in (("npt_melt_hold", "npt"), ("nvt_melt_hold", "nvt")):
        result = server.generate_equilibration_workflow(
            **_base_kwargs(tmp_path, data_file=checkpoint, extend_only=True,
                           base_stage_name=base, extend_ensemble=ensemble,
                           restart_file=str(tmp_path / f"{base}_out.restart"))
        )
        assert result["status"] == "success", (base, result)
        assert result["stages"][0]["params"]["T_START"] == 550.0
        assert result["stages"][0]["params"]["T_FINAL"] == 550.0


def test_extend_only_names_no_melt_cells(tmp_path):
    """An extend-only call generates ONE stage. It must not claim a melt_start_data_path the
    caller could mistake for a regenerated handoff cell -- after extending npt_melt_hold, the
    real one does not exist until nvt_melt_hold is regenerated."""
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, extend_only=True,
                       base_stage_name="npt_melt_hold", extend_ensemble="npt",
                       restart_file=str(tmp_path / "npt_melt_hold_out.restart"))
    )
    assert result["status"] == "success", result
    assert result["melt_data_path"] is None
    assert result["melt_start_data_path"] is None


def test_extend_only_rejects_a_cooling_stage_name(tmp_path):
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, extend_only=True, base_stage_name="cool_block_02",
                       extend_ensemble="npt", extend_temp_K=500.0,
                       restart_file=str(tmp_path / "cool_block_02_out.restart"))
    )
    assert result["status"] == "error"
    assert "cooling" in result["error"] or "generate_cooling_workflow" in result["error"]


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
