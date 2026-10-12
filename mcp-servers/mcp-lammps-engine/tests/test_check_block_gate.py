"""check_block_gate's half-window and monotonic-trend primitives, used by the
NPT-densification (stage 3) and blockwise-cooling (stage 6) adaptive segments.

These are log-only (no trajectory dump) so they stay cheap enough to run after every
restart-continuation block, not just post-hoc.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis_scripts"))

from check_block_gate import half_window_stability, monotonic_trend, check_block_gate  # noqa: E402


def test_flat_series_is_stable():
    values = np.full(40, 1.05) + np.random.default_rng(0).normal(0, 1e-5, 40)
    result = half_window_stability(values, threshold_pct=0.5)
    assert result["available"]
    assert result["stable"]


def test_shifted_series_is_not_stable():
    values = np.concatenate([np.full(20, 1.00), np.full(20, 1.10)])
    result = half_window_stability(values, threshold_pct=0.5)
    assert result["available"]
    assert not result["stable"]
    assert result["rel_diff_pct"] > 0.5


def test_too_few_points_reports_unavailable():
    result = half_window_stability([1.0, 1.0], threshold_pct=0.5)
    assert not result["available"]


def test_flat_volume_is_not_monotonic():
    rng = np.random.default_rng(1)
    values = 1000.0 + rng.normal(0, 0.5, 40)
    result = monotonic_trend(values, p_threshold=0.05)
    assert result["available"]
    assert not result["monotonic_trend"]


def test_steadily_shrinking_volume_is_monotonic():
    values = np.linspace(1200.0, 1000.0, 40)
    result = monotonic_trend(values, p_threshold=0.05)
    assert result["available"]
    assert result["monotonic_trend"]
    assert result["slope"] < 0


def test_check_block_gate_reads_a_real_archived_log(tmp_path):
    # A minimal synthetic LAMMPS log with a "Step ..." thermo table, matching the
    # format parse_lammps_log expects.
    log_path = tmp_path / "npt_densify.log"
    header = "Step Temp Density E_vdwl E_coul E_long Volume Press"
    rows = []
    for i in range(40):
        density = 0.85 + 1e-5 * i
        e_nb = -500.0 + 1e-4 * i
        volume = 5000.0 - 0.01 * i  # very slight residual shrink, but not enough to flag
        rows.append(f"{i*1000} 300.0 {density:.6f} {e_nb:.4f} 0.0 0.0 {volume:.4f} 1.0")
    log_path.write_text(header + "\n" + "\n".join(rows) + "\n")

    result = check_block_gate(str(log_path))
    assert result["status"] == "success"
    assert result["density"]["available"]
    assert result["nonbonded_energy"]["available"]
    assert result["nonbonded_energy"]["columns_used"] == ["E_vdwl", "E_coul", "E_long"]
    assert result["volume_trend"]["available"]
    assert result["stable"]


def test_check_block_gate_window_rows_uses_only_the_tail(tmp_path):
    # First half of the log is still shrinking (a densification in progress); the
    # last 20 rows have plateaued. --window_rows should only see the plateaued tail.
    log_path = tmp_path / "npt_densify.log"
    header = "Step Density E_vdwl E_coul E_long Volume"
    rows = []
    for i in range(40):
        if i < 20:
            volume = 6000.0 - 50.0 * i  # still shrinking
        else:
            volume = 5000.0 + np.sin(i) * 0.1  # plateaued
        rows.append(f"{i*1000} 0.9 -500.0 0.0 0.0 {volume:.4f}")
    log_path.write_text(header + "\n" + "\n".join(rows) + "\n")

    full = check_block_gate(str(log_path))
    tail_only = check_block_gate(str(log_path), window_rows=20)

    assert full["volume_trend"]["monotonic_trend"]
    assert not tail_only["volume_trend"]["monotonic_trend"]
