"""_resolve_analyze_tg_params must read the tg sweep's OWN log/dump, not the equilibration
attempt's structure file.

During real (attempt-based) execution, args.data_path holds the equilibration attempt's
npt_prod_data_path (CampaignStageExecutor sets it from the accepted equilibration manifest) --
it is a .data structure file, never a .log. _resolve_analyze_tg_params previously computed
tg_log_path as `args.data_path or <flat-convention path>`, and since args.data_path is always
non-null during real execution, it ALWAYS resolved to the equilibration .data file instead of
the tg sweep's own tg_sweep.log -- extract_thermal.py then failed with
"No thermo data found in <path>.data" (PE1, 2026-08-17), the sweep having genuinely completed.
per_t_dump_file had the same class of bug: it always used the flat data/<run>/lammps/thermal/...
convention instead of the current attempt's real work_dir, so it also pointed at a file that
was never written in the attempt-based layout.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

from stage_params import _resolve_analyze_tg_params  # noqa: E402

PHYC = {"tg_rates_K_per_ns": [10, 25, 40], "T_workflow_K": 300.0}


def _args(**overrides):
    base = dict(
        run_name="PE1", work_dir=None, data_path=None, equil_data_path=None,
        output_dir=None, tg_rate_index=None, enthalpy_col=None, backbone_types=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_real_execution_reads_the_sweeps_own_log_not_the_equilibration_data_file():
    args = _args(
        work_dir="/repo/data/PE1/attempts/thermal/attempt-0002/work",
        data_path="/repo/data/PE1/attempts/equilibration/attempt-0001/work/npt_production/npt_production_out.data",
    )
    p = _resolve_analyze_tg_params(args, PHYC)
    assert p["tg_log_path"] == (
        "/repo/data/PE1/attempts/thermal/attempt-0002/work/tg_sweep/tg_sweep.log"
    )
    assert p["per_t_dump_file"] == (
        "/repo/data/PE1/attempts/thermal/attempt-0002/work/tg_sweep/per_t_structs.dump"
    )
    # the equilibration attempt's real .data output is the correct structural reference here
    assert p["tg_data_file"] == args.data_path


def test_multirate_suffix_threaded_into_all_three_paths():
    args = _args(
        work_dir="/data/PE1/attempts/thermal/attempt-0001/work",
        data_path="/data/PE1/attempts/equilibration/attempt-0001/work/npt_production/npt_production_out.data",
        tg_rate_index=2,
    )
    p = _resolve_analyze_tg_params(args, PHYC)
    assert p["tg_log_path"] == "/data/PE1/attempts/thermal/attempt-0001/work/tg_sweep_r40/tg_sweep.log"
    assert p["per_t_dump_file"] == "/data/PE1/attempts/thermal/attempt-0001/work/tg_sweep_r40/per_t_structs.dump"
