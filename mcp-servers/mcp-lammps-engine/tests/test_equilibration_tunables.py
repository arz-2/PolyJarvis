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
