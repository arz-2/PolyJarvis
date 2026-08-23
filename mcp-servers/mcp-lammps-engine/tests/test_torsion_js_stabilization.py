"""_torsion_js_stabilization must detect when the backbone torsion distribution has stopped
changing between trajectory blocks (the stage-5 anneal-loop stopping signal), and must not
falsely claim stability from too little data.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis_scripts"))

from check_equilibration_comprehensive import (  # noqa: E402
    _dihedral_angle, _backbone_dihedrals, _torsion_js_stabilization,
)


def _rng_frames(n_frames, n_per_frame, low, high, seed):
    rng = np.random.default_rng(seed)
    return [rng.uniform(low, high, size=n_per_frame) for _ in range(n_frames)]


def test_identical_blocks_are_stable():
    frames = _rng_frames(n_frames=60, n_per_frame=200, low=-180, high=180, seed=0)
    # Reuse the same sampled distribution for every block by repeating one frame set.
    block_size = 10
    repeated = (frames[:block_size] * 6)[:60]
    result = _torsion_js_stabilization(repeated, block_count=6, js_threshold=0.05)
    assert result["available"]
    assert result["stable"]
    assert result["js_divergence_last"] <= 0.05


def test_shifting_distribution_is_not_stable():
    # Each block's torsion population is drawn from a progressively shifted, narrower
    # window -- the distribution is still visibly changing block-to-block.
    n_blocks = 6
    frames = []
    for b in range(n_blocks):
        block_frames = _rng_frames(n_frames=10, n_per_frame=200,
                                   low=-180 + b * 20, high=-100 + b * 20, seed=b)
        frames.extend(block_frames)
    result = _torsion_js_stabilization(frames, block_count=n_blocks, js_threshold=0.02)
    assert result["available"]
    assert not result["stable"]
    assert result["js_divergence_last"] > 0.02


def test_too_few_frames_reports_unavailable():
    frames = _rng_frames(n_frames=4, n_per_frame=50, low=-180, high=180, seed=1)
    result = _torsion_js_stabilization(frames, block_count=6, js_threshold=0.05)
    assert not result["available"]


def test_dihedral_angle_trans_and_gauche():
    p0 = np.array([0.0, 1.0, 0.0])
    p1 = np.array([0.0, 0.0, 0.0])
    p2 = np.array([1.0, 0.0, 0.0])

    # p3 on the same side as p0 (both "up") -> eclipsed/cis, 0 deg.
    p3_cis = np.array([1.0, 1.0, 0.0])
    angle_cis = _dihedral_angle(p0, p1, p2, p3_cis)
    assert abs(angle_cis) < 1e-6

    # p3 on the opposite side from p0 -> anti/trans, 180 deg.
    p3_trans = np.array([1.0, -1.0, 0.0])
    angle_trans = _dihedral_angle(p0, p1, p2, p3_trans)
    assert abs(abs(angle_trans) - 180.0) < 1e-6


def test_backbone_dihedrals_count_matches_n_minus_3():
    positions = np.array([[i, (i % 2), 0.0] for i in range(10)], dtype=float)
    dihedrals = _backbone_dihedrals(positions)
    assert len(dihedrals) == len(positions) - 3

    assert _backbone_dihedrals(positions[:3]) == []
