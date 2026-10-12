"""Which density-homogeneity method each equilibration gate asks for, and the glass floor.

The melt gate compares the time-averaged voxel maps of the two halves of its hold; the cooling
gate cannot (a glass does not move, both halves are the same cell) and subtracts the melt's own
measured noise instead. See
check_equilibration_comprehensive.homogeneity_verdict for why the per-frame formula alone
failed a well-mixed PTFE melt.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import run_campaign as rc  # noqa: E402


def _melt_json(tmp_path, **dh):
    path = tmp_path / "equilibration.json"
    path.write_text(json.dumps({"spatial": {"density_homogeneity": dh}}))
    return SimpleNamespace(melt_equilibration_json_path=str(path))


@pytest.mark.parametrize("decided_by", ["split_half", "time_averaged"])
def test_the_glass_floor_is_the_melt_mean_plus_two_standard_deviations(tmp_path, decided_by):
    # time_averaged: the retired first form of the melt method, still on disk for runs gated
    # before the split_half change.
    args = _melt_json(tmp_path, decided_by=decided_by, **{"pass": True},
                      cv_mean=0.2795, cv_std=0.0131)
    assert rc._melt_homogeneity_floor(args) == pytest.approx(0.2795 + 2 * 0.0131)


@pytest.mark.parametrize("dh", [
    {"decided_by": "formula", "pass": True, "cv_mean": 0.28, "cv_std": 0.01},
    {"decided_by": "split_half", "pass": False, "cv_mean": 0.28, "cv_std": 0.01},
    {"decided_by": "split_half", "pass": True, "cv_mean": None},
])
def test_no_floor_unless_the_melt_passed_the_split_half_test(tmp_path, dh):
    # The floor claims the melt's per-frame spread is pure noise. Only the split_half test
    # shows that; a formula verdict or a failed melt licenses nothing.
    assert rc._melt_homogeneity_floor(_melt_json(tmp_path, **dh)) is None


def test_no_floor_without_a_readable_melt_result(tmp_path):
    assert rc._melt_homogeneity_floor(SimpleNamespace()) is None
    missing = SimpleNamespace(melt_equilibration_json_path=str(tmp_path / "absent.json"))
    assert rc._melt_homogeneity_floor(missing) is None


class _RecordingLammps:
    def __init__(self):
        self.comp_kwargs = []

    def check_equilibration_comprehensive(self, **kwargs):
        self.comp_kwargs.append(kwargs)
        return {"thermo": {"density_drift": {"pass": True}}, "chain": {"rg": {"pass": True}}}

    def extract_equilibrated_density(self, **kwargs):
        return {"plateau_density_mean": 1.0}

    def enforce_equilibration_gate(self, **kwargs):
        return {"verdict": "PASS"}


def _p(tmp_path):
    return {"npt_prod_log_path": "log", "melt_dump_path": "dump", "npt_prod_data_path": "data",
            "ct_min_decay_melt": None, "output_dir": str(tmp_path), "graphs_dir": None,
            "cutoff_A": 11.0, "dt_fs": 1.0, "struct_dump_path": "sdump",
            "npt_prod_temp_K": 700.0, "regime": "melt", "dp": 50, "ct_gate_reliable": True,
            "exp_tg_point_K": None, "T_melt_hold_K": 700.0, "melt_data_path": "mdata"}


def test_the_melt_gate_asks_for_split_half_by_default(tmp_path):
    lammps = _RecordingLammps()
    rc._run_equilibration_gate(lammps, _p(tmp_path), [1, 2], "equilibration.json", "melt gate")
    assert lammps.comp_kwargs[0]["homog_method"] == "split_half"
    assert lammps.comp_kwargs[0]["homog_melt_cv_floor"] is None


def test_the_cooling_gate_call_site_passes_measured_floor_and_the_melt_floor():
    src = Path(rc.__file__).read_text()
    call = src[src.index('lammps, p, backbone_types, "cooling.json", "cool-check"'):]
    call = call[:call.index(")\n")]
    assert 'homog_method="measured_floor"' in call
    assert "homog_melt_cv_floor=_melt_homogeneity_floor(args)" in call


def test_the_executor_hands_cooling_the_melt_result_path():
    src = Path(rc.__file__).read_text()
    assert 'args.melt_equilibration_json_path = equil.get("equilibration_json_path")' in src
