"""_resolve_equil_check_params / _resolve_analyze_bm_params must derive npt_prod_log_path from
the real npt_prod_data_path during real execution, not a nonexistent flat-convention guess.

args.npt_prod_log is never set anywhere in run_campaign.py's real execution path -- confirmed by
grep, zero assignment sites -- so `args.npt_prod_log or f'{lammps_base}/equil/{prod}/{prod}.log'`
ALWAYS fell to the flat data/<run>/lammps/... path, which doesn't exist under the attempt-based
layout (data/<run>/attempts/<stage>/attempt-N/work/...).

For _resolve_equil_check_params this is severe: npt_prod_log_path feeds
check_equilibration_comprehensive's log_file, the BINDING density/energy-drift and block-SEM
gate (not an advisory check) -- every real run's equilibration check would fail to parse any
thermo rows, triggering the transient_retry remedy's blind resubmission of the entire
multi-hour equilibration chain (up to 2x) before escalating. Avoided on PE1 only because a
manual repair supplied the correct path by hand, bypassing this code path entirely.

For _resolve_analyze_bm_params the same bug silently disabled the Murnaghan fluctuation
cross-check (PE1's real bulk_modulus_murnaghan.json carried fluctuation_bulk_modulus_GPa=null).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

from stage_params import _resolve_equil_check_params, _resolve_analyze_bm_params  # noqa: E402

RUBBERY_CLS = {"T_workflow_K": 300.0, "experimental_tg_K": 195}
GLASSY_CLS = {"T_workflow_K": 450.0, "experimental_tg_K": 450}


def _args(**overrides):
    base = dict(
        run_name="PE1", smiles="*CC*", data_path=None, npt_prod_log=None, npt_prod_dump=None,
        output_dir=None, phase=None, dp=None, exp_K_min=None, exp_K_max=None,
        dt_fs=None, backbone_types=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_equil_check_derives_log_from_real_data_path_rubbery():
    args = _args(
        data_path="/data/PE1/attempts/equilibration/attempt-0001/work/npt_final/npt_final_out.data",
    )
    p = _resolve_equil_check_params(args, RUBBERY_CLS)
    assert p["npt_prod_log_path"] == (
        "/data/PE1/attempts/equilibration/attempt-0001/work/npt_final/npt_final.log"
    )


def test_equil_check_derives_log_from_real_data_path_glassy():
    """npt_final is unconditionally the terminal stage now -- no separate glassy stage name."""
    args = _args(
        data_path="/data/PC1/attempts/equilibration/attempt-0001/work/npt_final/npt_final_out.data",
    )
    p = _resolve_equil_check_params(args, GLASSY_CLS)
    assert p["npt_prod_log_path"] == (
        "/data/PC1/attempts/equilibration/attempt-0001/work/npt_final/npt_final.log"
    )


def test_equil_check_dry_run_preview_falls_back_to_flat_convention():
    args = _args()  # data_path=None, matching --dry-run preview
    p = _resolve_equil_check_params(args, RUBBERY_CLS)
    assert p["npt_prod_log_path"] == (
        f"{REPO}/data/PE1/lammps/equil/npt_final/npt_final.log"
    )


def test_analyze_bm_derives_log_from_real_data_path():
    args = _args(
        data_path="/data/PE1/attempts/equilibration/attempt-0001/work/npt_final/npt_final_out.data",
    )
    p = _resolve_analyze_bm_params(args, RUBBERY_CLS)
    assert p["npt_prod_log_path"] == (
        "/data/PE1/attempts/equilibration/attempt-0001/work/npt_final/npt_final.log"
    )


def test_analyze_bm_dry_run_preview_falls_back_to_flat_convention():
    args = _args()
    p = _resolve_analyze_bm_params(args, RUBBERY_CLS)
    assert p["npt_prod_log_path"] == (
        f"{REPO}/data/PE1/lammps/equil/npt_final/npt_final.log"
    )


def test_explicit_cli_override_still_wins():
    args = _args(data_path="/data/PE1/.../npt_final_out.data", npt_prod_log="/explicit/override.log")
    assert _resolve_equil_check_params(args, RUBBERY_CLS)["npt_prod_log_path"] == "/explicit/override.log"
    assert _resolve_analyze_bm_params(args, RUBBERY_CLS)["npt_prod_log_path"] == "/explicit/override.log"
