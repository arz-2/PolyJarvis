"""_fit_msid_regime must fit small/intermediate-s and large-s separations independently.

A single whole-range MSID power-law fit can look Gaussian on average (slope near 1.0)
while masking a large-s-only distortion -- e.g. a badly initialized long-wavelength chain
configuration that ordinary MD cannot repair within reachable timescales (Auhl et al.,
cond-mat/0306026). The split is what lets a pre-anneal sanity gate
(GLOBAL_CHAIN_CONFIGURATION_NOT_RELAXED) fire on the large-s regime specifically, without
being averaged away by well-behaved small/intermediate-s statistics.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis_scripts"))

from check_equilibration_comprehensive import _fit_msid_regime  # noqa: E402


def test_pure_gaussian_chain_both_regimes_pass():
    n_vals = np.arange(2, 41)
    mean_vals = n_vals.astype(float)  # MSID(n) = n exactly -> slope == 1.0 everywhere
    small_mask = n_vals <= 13
    large_mask = ~small_mask

    small = _fit_msid_regime(n_vals, mean_vals, small_mask)
    large = _fit_msid_regime(n_vals, mean_vals, large_mask)

    assert small["available"] and large["available"]
    assert small["gaussian_pass"]
    assert large["gaussian_pass"]
    assert abs(small["slope"] - 1.0) < 1e-6
    assert abs(large["slope"] - 1.0) < 1e-6


def test_large_s_only_distortion_is_isolated_from_small_intermediate():
    # Small/intermediate-s behaves Gaussian (slope 1.0); large-s is stretched (slope 1.8) --
    # a distorted long-wavelength configuration riding on top of healthy local packing.
    n_vals = np.arange(2, 41)
    s_split = 13
    mean_vals = np.where(n_vals <= s_split, n_vals.astype(float),
                         float(s_split) * (n_vals.astype(float) / s_split) ** 1.8)
    small_mask = n_vals <= s_split
    large_mask = ~small_mask

    small = _fit_msid_regime(n_vals, mean_vals, small_mask)
    large = _fit_msid_regime(n_vals, mean_vals, large_mask)

    assert small["gaussian_pass"]
    assert not large["gaussian_pass"]
    assert large["slope"] > 1.2


def test_too_few_separations_in_a_regime_reports_unavailable():
    n_vals = np.arange(2, 8)  # only 6 separations total
    mean_vals = n_vals.astype(float)
    # split leaves only 2 points on the large side -- below the min_pts=5 floor
    small_mask = n_vals <= 5
    large_mask = ~small_mask

    large = _fit_msid_regime(n_vals, mean_vals, large_mask)
    assert not large["available"]
    assert large["n_separations"] == int(large_mask.sum())
