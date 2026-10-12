"""estimate_fluctuation_K_GPa: a cheap, matplotlib-free volume-fluctuation K
estimate, callable in-process from orchestration BEFORE a Murnaghan pressure
ladder is chosen (unlike compute_fluctuation_cross_check in
extract_bulk_modulus_murnaghan.py, which only runs post-hoc after the ladder
already ran). Must agree exactly with compute_bulk_modulus on the same series,
and must never raise on a missing/short/malformed log.
"""
import numpy as np

from analysis_utils import compute_bulk_modulus, estimate_fluctuation_K_GPa


def _write_log(path, volumes, temps):
    lines = ["Step Volume Temp"]
    for i, (v, t) in enumerate(zip(volumes, temps)):
        lines.append(f"{i} {v:.6f} {t:.6f}")
    path.write_text("\n".join(lines) + "\n")


def test_estimate_matches_compute_bulk_modulus_on_the_production_window(tmp_path):
    rng = np.random.default_rng(11)
    n = 200
    volumes = rng.normal(1000.0, 5.0, n)
    temps = rng.normal(300.0, 1.0, n)
    log_path = tmp_path / "npt_prod.log"
    _write_log(log_path, volumes, temps)

    K_GPa = estimate_fluctuation_K_GPa(str(log_path), eq_fraction=0.5)

    prod_vol = volumes[n // 2:]
    prod_temp = temps[n // 2:]
    expected_K, _, _ = compute_bulk_modulus(prod_vol, float(np.mean(prod_temp)))

    assert K_GPa is not None
    # Small tolerance, not exact equality: parse_lammps_log round-trips through
    # %.6f-formatted text, so the read-back floats differ from the in-memory
    # arrays at the ~1e-6 relative level.
    assert abs(K_GPa - expected_K) / abs(expected_K) < 1e-4


def test_estimate_returns_none_on_missing_file():
    assert estimate_fluctuation_K_GPa("/nonexistent/path.log") is None


def test_estimate_returns_none_when_production_window_too_short(tmp_path):
    log_path = tmp_path / "short.log"
    _write_log(log_path, [1000.0] * 10, [300.0] * 10)
    assert estimate_fluctuation_K_GPa(str(log_path), eq_fraction=0.5) is None


def test_estimate_returns_none_without_volume_or_temp_columns(tmp_path):
    log_path = tmp_path / "no_vol.log"
    lines = ["Step Press"] + [f"{i} {100.0}" for i in range(100)]
    log_path.write_text("\n".join(lines) + "\n")
    assert estimate_fluctuation_K_GPa(str(log_path)) is None
