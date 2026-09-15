"""homogeneity_verdict: separating real density heterogeneity from counting noise.

The per-frame compound-Poisson floor assumes atoms occupy voxels independently. Atoms that
travel as a bonded group carrying most of the mass break that assumption, and a well-mixed melt
fails: PTFE_AI and PTFE_noAI (2026-09-14) both halted on cv_signal 0.19 while nothing in their
melt persisted from one half of the hold to the other.

These tests build that situation from first principles -- rigid three-atom clumps placed at
random each frame, so the cell is homogeneous by construction -- and a fixed void, so it is
heterogeneous by construction.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis_scripts"))

from check_equilibration_comprehensive import (  # noqa: E402
    HOMOG_METHOD_ALIASES, HOMOG_METHODS, _voxel_mass_map, homogeneity_verdict,
)

GRID = 5
L = np.array([38.6, 38.6, 38.6])
CLUMP_MASSES = (12.011, 18.998, 18.998)        # CF2: all three atoms share one position


def _clump_trajectory(n_frames=200, n_clumps=1000, void_fraction=0.0, seed=0, frozen=False):
    rng = np.random.default_rng(seed)
    masses = np.tile(CLUMP_MASSES, n_clumps)
    radius = (3 * void_fraction * L.prod() / (4 * np.pi)) ** (1 / 3) if void_fraction else 0.0
    centre = L * 0.37
    maps, cvs = [], []
    first = None
    for _ in range(n_frames):
        if frozen and first is not None:
            sites = first
        else:
            sites = rng.uniform(0, 1, size=(n_clumps, 3)) * L
            if radius:
                # rejection-sample every clump that landed in the void, so the rest of the cell
                # stays uniform and the only structure is the void itself
                while True:
                    d = sites - centre
                    d -= L * np.round(d / L)
                    inside = (d ** 2).sum(axis=1) <= radius ** 2
                    if not inside.any():
                        break
                    sites[inside] = rng.uniform(0, 1, size=(int(inside.sum()), 3)) * L
            first = sites
        pos = np.repeat(sites, 3, axis=0)
        vmap = _voxel_mass_map(pos, masses, L, GRID)
        occ = vmap[vmap > 0]
        maps.append(vmap)
        cvs.append(float(occ.std() / occ.mean()))
    return np.array(maps), np.array(cvs), masses


def _verdict(maps, cvs, masses, **kw):
    return homogeneity_verdict(maps, cvs, masses, len(masses), GRID, **kw)


def test_the_formula_fails_a_homogeneous_cell_of_bonded_clumps():
    maps, cvs, masses = _clump_trajectory()
    dh = _verdict(maps, cvs, masses, method="formula")
    assert dh["verdict"] == "HOMOG_HETEROGENEOUS", "the bug this module exists to fix"
    assert dh["cv_signal"] > 0.11


def test_split_half_passes_the_same_homogeneous_cell():
    maps, cvs, masses = _clump_trajectory()
    dh = _verdict(maps, cvs, masses, method="split_half")
    assert dh["decided_by"] == "split_half"
    assert dh["verdict"] == "HOMOG_PASS"
    assert dh["legacy_formula_verdict"] == "HOMOG_HETEROGENEOUS"
    assert dh["split_half"]["persistent_cv"] < 0.05


@pytest.mark.parametrize("n_frames", [120, 400, 1200])
def test_split_half_does_not_depend_on_trajectory_length(n_frames):
    # The retired time_averaged form failed polystyrene on 2 ns windows of holds it passed at
    # 6 ns. Pure noise must stay well under the limit however short the hold.
    maps, cvs, masses = _clump_trajectory(n_frames=n_frames, seed=n_frames)
    dh = _verdict(maps, cvs, masses, method="split_half")
    assert dh["verdict"] == "HOMOG_PASS"


@pytest.mark.parametrize("n_clumps", [1000, 4000])
def test_split_half_catches_a_fixed_void(n_clumps):
    maps, cvs, masses = _clump_trajectory(void_fraction=0.05, n_clumps=n_clumps)
    dh = _verdict(maps, cvs, masses, method="split_half")
    assert dh["decided_by"] == "split_half"
    assert dh["verdict"] == "HOMOG_HETEROGENEOUS"


def test_split_half_on_a_frozen_cell_reads_everything_as_persistent():
    # Documented limitation, not a feature: both halves are the same configuration. This is why
    # the cooling gate never asks for split_half.
    maps, cvs, masses = _clump_trajectory(frozen=True)
    dh = _verdict(maps, cvs, masses, method="split_half")
    assert dh["verdict"] == "HOMOG_HETEROGENEOUS"
    assert dh["split_half"]["half_map_corr"] == pytest.approx(1.0)


def test_split_half_falls_back_on_a_short_trajectory_and_says_so():
    maps, cvs, masses = _clump_trajectory(n_frames=20)
    dh = _verdict(maps, cvs, masses, method="split_half")
    assert dh["decided_by"] == "formula"
    assert "frames" in dh["fallback_reason"]


def test_time_averaged_is_accepted_as_the_retired_name_of_split_half():
    maps, cvs, masses = _clump_trajectory()
    dh = _verdict(maps, cvs, masses, method="time_averaged")
    assert dh["decided_by"] == "split_half"
    assert HOMOG_METHOD_ALIASES == {"time_averaged": "split_half"}


def _melt_floor(seed=1, n_clumps=1000):
    """What run_campaign._melt_homogeneity_floor hands the glass gate: mean + 2 SD."""
    _, melt_cvs, _ = _clump_trajectory(seed=seed, n_clumps=n_clumps)
    dh = homogeneity_verdict(np.zeros((len(melt_cvs), GRID ** 3)), melt_cvs,
                             np.tile(CLUMP_MASSES, n_clumps), 3 * n_clumps, GRID)
    return dh["cv_mean"] + 2 * dh["cv_std"]


@pytest.mark.parametrize("seed", range(5))
def test_measured_floor_passes_a_frozen_homogeneous_cell_whatever_the_draw(seed):
    # A glass is ONE frozen configuration: its CV is a single draw from the melt's per-frame
    # spread. A floor at the melt mean would fail roughly half of these.
    maps, cvs, masses = _clump_trajectory(frozen=True, seed=100 + seed)
    dh = _verdict(maps, cvs, masses, method="measured_floor", melt_cv_floor=_melt_floor())
    assert dh["decided_by"] == "measured_floor"
    assert dh["verdict"] == "HOMOG_PASS"


def test_measured_floor_still_catches_a_frozen_void():
    # An ideal gas of clumps is noisier than a liquid (8 clumps/voxel gives CV 0.35, where real
    # melts sit at 0.20-0.28), which would bury a 5% void. 32 clumps/voxel puts the noise where
    # real cells are, so this measures the method's sensitivity rather than the toy's noise.
    maps, cvs, masses = _clump_trajectory(frozen=True, void_fraction=0.05, n_clumps=4000)
    dh = _verdict(maps, cvs, masses, method="measured_floor",
                  melt_cv_floor=_melt_floor(n_clumps=4000))
    assert dh["verdict"] == "HOMOG_HETEROGENEOUS"


def test_the_result_reports_the_per_frame_spread_the_glass_floor_needs():
    maps, cvs, masses = _clump_trajectory(n_frames=50)
    dh = _verdict(maps, cvs, masses, method="formula")
    assert dh["cv_std"] == pytest.approx(float(np.std(cvs)), abs=1e-4)


def test_measured_floor_without_a_floor_falls_back_and_says_so():
    maps, cvs, masses = _clump_trajectory(n_frames=20)
    dh = _verdict(maps, cvs, masses, method="measured_floor", melt_cv_floor=None)
    assert dh["decided_by"] == "formula"
    assert dh["fallback_reason"]


def test_the_formula_result_is_unchanged_when_it_decides():
    maps, cvs, masses = _clump_trajectory(n_frames=20)
    dh = _verdict(maps, cvs, masses, method="formula")
    assert dh["signal"] == dh["cv_signal"]
    assert dh["signal_max"] == dh["cv_signal_max"] == 0.11
    assert dh["verdict"] == dh["legacy_formula_verdict"]


def test_an_unknown_method_is_rejected():
    maps, cvs, masses = _clump_trajectory(n_frames=5)
    with pytest.raises(ValueError):
        _verdict(maps, cvs, masses, method="auto")
    assert set(HOMOG_METHODS) == {"formula", "split_half", "measured_floor"}
