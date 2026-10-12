"""_fluctuation_K_for_pressure_ladder (run_campaign.py): the glue between
do_mechanical and select_pressure_ladder's optional fluctuation-K sanity check.
Pure function of already-on-disk equilibration output -- no LAMMPS/GPU involved,
so this is tested directly rather than through do_mechanical's full pipeline.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from run_campaign import _fluctuation_K_for_pressure_ladder  # noqa: E402


def _write_log(path):
    lines = ["Step Volume Temp"]
    # deterministic small-variance series so a real K comes out positive and finite
    for i in range(200):
        lines.append(f"{i} {1000.0 + (i % 3) * 0.5:.3f} {300.0 + (i % 2) * 0.1:.3f}")
    path.write_text("\n".join(lines) + "\n")


def test_returns_none_when_resample_points_are_set(tmp_path):
    """A resample/extend retry's bm_pressures_atm is the remedy's own deliberately
    narrow override -- this precheck must never touch it."""
    log_path = tmp_path / "npt_final.log"
    _write_log(log_path)
    cls = {"mechanical_resample_points": [30000]}
    p = {"npt_prod_log_path": str(log_path)}

    assert _fluctuation_K_for_pressure_ladder(cls, p) is None


def test_returns_none_when_log_path_missing_from_params():
    assert _fluctuation_K_for_pressure_ladder({}, {}) is None


def test_returns_none_when_log_file_does_not_exist():
    assert _fluctuation_K_for_pressure_ladder({}, {"npt_prod_log_path": "/nonexistent.log"}) is None


def test_returns_a_positive_estimate_from_a_real_log(tmp_path):
    log_path = tmp_path / "npt_final.log"
    _write_log(log_path)
    K_GPa = _fluctuation_K_for_pressure_ladder({}, {"npt_prod_log_path": str(log_path)})
    assert K_GPa is not None
    assert K_GPa > 0
