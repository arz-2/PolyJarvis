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


def test_planned_anneal_cycles_materialize_and_forward_controls(tmp_path):
    result = server.generate_equilibration_workflow(
        data_file=str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data"),
        params_file=str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.params"),
        work_dir_base=str(tmp_path), velocity_seed=4242,
        npt_prod_steps=1111, nvt_prod_steps=2222, npt_prod300_steps=3333,
        npt_cool_steps=4444, npt_cool300_steps=5555, melt_npt_steps=None,
        extend_steps=None, anneal_cycles=2, anneal_cycle_steps=6666,
        use_long_range=False, temp=500.0, max_temp=700.0, press=2.0,
        max_press=60000.0, use_pcff=True, use_trappe=False, use_opls=False,
        engine="kokkos", thermostat_damp_fs=150.0, barostat_damp_fs=1500.0,
    )

    assert result["status"] == "success", result
    names = result["run_order"]
    assert names[1:5] == [
        "anneal_01_heat", "anneal_01_cool", "anneal_02_heat", "anneal_02_cool"
    ]
    by_name = {stage["name"]: stage for stage in result["stages"]}
    for name in names:
        params = by_name[name]["params"]
        if "T_DAMP" in params:
            assert params["T_DAMP"] == 150.0
        if "P_DAMP" in params:
            assert params["P_DAMP"] == 1500.0
    assert by_name["anneal_01_heat"]["params"]["N_STEPS"] == 6666
    assert by_name["npt_compress"]["params"]["P_FINAL"] == 60000.0
    assert by_name["nvt_production"]["params"]["N_STEPS"] == 2222
    assert by_name["npt_production"]["params"]["N_STEPS"] == 1111
    assert by_name["npt_prod300"]["params"]["N_STEPS"] == 3333
    assert all(not stage["params"].get("use_pppm", False) for stage in result["stages"])


def _base_kwargs(tmp_path, **overrides):
    kwargs = dict(
        data_file=str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data"),
        params_file=str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.params"),
        work_dir_base=str(tmp_path), velocity_seed=4242,
        npt_prod_steps=1111, nvt_prod_steps=2222, npt_prod300_steps=3333,
        npt_cool_steps=4444, npt_cool300_steps=5555, melt_npt_steps=None,
        extend_steps=None, anneal_cycles=2, anneal_cycle_steps=6666,
        use_long_range=False, temp=500.0, max_temp=700.0, press=2.0,
        max_press=60000.0, use_pcff=True, use_trappe=False, use_opls=False,
        engine="kokkos", thermostat_damp_fs=150.0, barostat_damp_fs=1500.0,
    )
    kwargs.update(overrides)
    return kwargs


def test_resume_from_npt_cool_skips_earlier_stages_and_starts_at_nvt_production(tmp_path):
    """A MELT_STAGE_DEFICIT retry that only wants to widen nvt_production/npt_production must not
    re-pay for minimize/anneal/nvt_softheat/npt_compress/npt_pppm/npt_cool -- resume_from='npt_cool'
    starts the returned chain directly at nvt_production, reading data_file as its own input
    (the caller passes a prior chain's real npt_cool_out.data)."""
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, resume_from="npt_cool",
                       nvt_prod_steps=9999999, npt_prod_steps=8888888)
    )

    assert result["status"] == "success", result
    assert result["run_order"] == ["nvt_production", "npt_production", "npt_cool300", "npt_prod300"]
    assert result["resumed_from"] == "npt_cool"
    by_name = {stage["name"]: stage for stage in result["stages"]}
    assert by_name["nvt_production"]["input_data"] == checkpoint
    assert by_name["nvt_production"]["params"]["N_STEPS"] == 9999999
    assert by_name["npt_production"]["params"]["N_STEPS"] == 8888888
    assert result["npt_prod300_data"] == by_name["npt_prod300"]["output_data"]


def test_resume_from_npt_cool_rubbery_stops_at_npt_production(tmp_path):
    """Rubbery (temp <= 300 K): add_300k_production never fires regardless of resume_from --
    the resumed chain is just the two production stages."""
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, resume_from="npt_cool", temp=280.0)
    )

    assert result["status"] == "success", result
    assert result["run_order"] == ["nvt_production", "npt_production"]


def test_resume_from_rejects_unsupported_value(tmp_path):
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, resume_from="npt_compress")
    )
    assert result["status"] == "error"
    assert "resume_from" in result["error"]


def test_resume_from_rejects_extend_only_combination(tmp_path):
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, resume_from="npt_cool", extend_only=True)
    )
    assert result["status"] == "error"


def test_resume_from_rejects_add_melt_npt_combination(tmp_path):
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, resume_from="npt_cool", add_melt_npt=True, t_equil_K=350.0,
                       temp=280.0)
    )
    assert result["status"] == "error"


def test_resume_from_anneal_skips_minimize_runs_fresh_cycles_then_full_tail(tmp_path):
    """resume_from='anneal' serves both the redo-annealing and extend-anneal-cycles remedies --
    it always runs exactly anneal_cycles fresh cycles from data_file (the caller decides whether
    that's minimize's output or a prior last-anneal-cycle output), then nvt_softheat onward."""
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, resume_from="anneal", anneal_cycles=3)
    )

    assert result["status"] == "success", result
    assert result["resumed_from"] == "anneal"
    names = result["run_order"]
    assert names[:6] == [
        "anneal_01_heat", "anneal_01_cool", "anneal_02_heat", "anneal_02_cool",
        "anneal_03_heat", "anneal_03_cool",
    ]
    assert "minimize" not in names
    assert names[6:] == ["nvt_softheat", "npt_compress", "npt_pppm", "npt_cool",
                         "nvt_production", "npt_production", "npt_cool300", "npt_prod300"]
    by_name = {stage["name"]: stage for stage in result["stages"]}
    assert by_name["anneal_01_heat"]["input_data"] == checkpoint


def test_resume_from_npt_production_only_regenerates_glassy_tail(tmp_path):
    """resume_from='npt_production' serves the extend-cooling remedy -- widen npt_cool300_steps
    without re-running any melt-phase stage."""
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, resume_from="npt_production",
                       npt_cool300_steps=7777777)
    )

    assert result["status"] == "success", result
    assert result["resumed_from"] == "npt_production"
    assert result["run_order"] == ["npt_cool300", "npt_prod300"]
    by_name = {stage["name"]: stage for stage in result["stages"]}
    assert by_name["npt_cool300"]["input_data"] == checkpoint
    assert by_name["npt_cool300"]["params"]["N_STEPS"] == 7777777
    assert result["npt_prod300_data"] == by_name["npt_prod300"]["output_data"]


def test_resume_from_npt_production_rejects_rubbery(tmp_path):
    """No glassy tail exists to regenerate for a rubbery chain (temp<=300) -- nothing would be
    left to run."""
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, resume_from="npt_production", temp=280.0)
    )
    assert result["status"] == "error"


def test_resume_from_anneal_with_zero_cycles_goes_straight_to_softheat(tmp_path):
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, resume_from="anneal", anneal_cycles=0)
    )
    assert result["status"] == "success", result
    assert result["run_order"][0] == "nvt_softheat"
    by_name = {stage["name"]: stage for stage in result["stages"]}
    assert by_name["nvt_softheat"]["input_data"] == checkpoint


def test_resume_from_nvt_production_only_regenerates_npt_production_and_tail(tmp_path):
    """Pairs with an nvt extend_only continuation: nvt_production's real trajectory is extended
    separately (not discarded), then this resumes from that new endpoint to rebuild only
    npt_production onward -- npt_production can never itself be 'extended' against a stale
    starting point, so it is always rebuilt fresh here regardless of resume_from."""
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, resume_from="nvt_production",
                       npt_prod_steps=6543210)
    )
    assert result["status"] == "success", result
    assert result["resumed_from"] == "nvt_production"
    assert result["run_order"] == ["npt_production", "npt_cool300", "npt_prod300"]
    by_name = {stage["name"]: stage for stage in result["stages"]}
    assert by_name["npt_production"]["input_data"] == checkpoint
    assert by_name["npt_production"]["params"]["N_STEPS"] == 6543210


def test_resume_from_nvt_production_rubbery_yields_only_npt_production(tmp_path):
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, resume_from="nvt_production", temp=280.0)
    )
    assert result["status"] == "success", result
    assert result["run_order"] == ["npt_production"]


def test_extend_only_nvt_ensemble_emits_nvt_stage_not_npt(tmp_path):
    """nvt_production is NVT -- extending it with the default (npt) ensemble would silently turn
    a barostat on mid-trajectory. extend_ensemble='nvt' must emit an nvt-templated stage with no
    pressure params."""
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, extend_only=True, extend_ensemble="nvt",
                       extend_steps=5000000, temp=550.0)
    )
    assert result["status"] == "success", result
    assert result["run_order"] == ["nvt_extend"]
    stage = result["stages"][0]
    assert stage["template"] == "nvt"
    assert "P_START" not in stage["params"]
    assert stage["params"]["N_STEPS"] == 5000000
    assert stage["input_data"] == checkpoint


def test_extend_only_default_ensemble_still_npt(tmp_path):
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, extend_only=True, extend_steps=1000000)
    )
    assert result["status"] == "success", result
    assert result["run_order"] == ["npt_extend"]
    assert result["stages"][0]["template"] == "npt"


def test_extend_ensemble_rejects_invalid_value(tmp_path):
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, extend_only=True, extend_ensemble="nve")
    )
    assert result["status"] == "error"


def test_nvt_extend_then_resume_from_nvt_production_uses_the_extend_stage_output(tmp_path):
    """The real Arm B use case: extend nvt_production's own trajectory (a separate
    run_lammps_chain submission, waited on to completion), then resume from that real endpoint
    to rebuild npt_production+tail. The second generate_equilibration_workflow call preflight-
    validates data_file against a real file on disk, so it can only run after the extend stage
    has actually produced its output -- simulate that here by writing a minimal valid one."""
    checkpoint = str(REPO_ROOT / "hardware" / "CALIB_PCFF" / "emc_build.data")
    extend_result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=checkpoint, extend_only=True, extend_ensemble="nvt",
                       extend_steps=5000000, temp=550.0)
    )
    assert extend_result["status"] == "success", extend_result
    extend_output = extend_result["stages"][0]["output_data"]
    Path(extend_output).parent.mkdir(parents=True, exist_ok=True)
    Path(extend_output).write_text(Path(checkpoint).read_text())  # stand-in for the real output

    resume_result = server.generate_equilibration_workflow(
        **_base_kwargs(tmp_path, data_file=extend_output, resume_from="nvt_production",
                       npt_prod_steps=10000000)
    )
    assert resume_result["status"] == "success", resume_result
    assert resume_result["stages"][0]["input_data"] == extend_output
