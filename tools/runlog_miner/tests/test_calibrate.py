"""Tests for the P0c confidence-calibration report."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.runlog_miner import build_calibration, calibrate  # noqa: E402
from tools.runlog_miner.parse import ResultRow, RunRecord  # noqa: E402


def _run(name, cls, tg_status="✓", tg_computed="420 K", tg_err="2%", rho_err="0.8%"):
    results = {
        "Tg": ResultRow(computed=tg_computed, experimental="420 K", error=tg_err,
                        status=tg_status, filled=True),
        "rho": ResultRow(computed="1.20 g/cm³", experimental="1.20 g/cm³", error=rho_err,
                         status="✓", filled=True),
    }
    return RunRecord(run_name=name, polymer_class=cls, results=results)


_RULES = {"classes": {
    "PCBN": {"confidence": "high"},
    "PHYC": {"confidence": "low"},
    "PKTN": {"confidence": "high"},
    "PSTR": {"confidence": "medium"},
}}
_CLASSES = _RULES["classes"]


def test_over_confident_flag():
    # high confidence but both runs Tg ⚠
    cal = calibrate(
        [_run("PC1", "PCBN", tg_status="⚠ outside bounds"),
         _run("PC2", "PCBN", tg_status="⚠ outside bounds")],
        _CLASSES,
    )
    assert cal["PCBN"]["tg_warn"] == 2 and cal["PCBN"]["tg_ok"] == 0
    assert any("over-confident" in f for f in cal["PCBN"]["flags"])


def test_promote_flag_for_low_confidence_all_ok():
    cal = calibrate([_run("H1", "PHYC"), _run("H2", "PHYC")], _CLASSES)
    assert any("promote" in f for f in cal["PHYC"]["flags"])


def test_density_error_flag_for_high_confidence():
    cal = calibrate([_run("K1", "PKTN", rho_err="8%"),
                     _run("K2", "PKTN", rho_err="9%")], _CLASSES)
    assert cal["PKTN"]["rho_err_mean"] == 8.5
    assert any("ρ error" in f for f in cal["PKTN"]["flags"])


def test_large_tg_error_alone_does_not_flag():
    # medium confidence, status ✓ but a huge raw Tg error → MUST NOT flag (MD-offset guard)
    cal = calibrate(
        [_run("S1", "PSTR", tg_status="✓", tg_computed="500 K", tg_err="34%"),
         _run("S2", "PSTR", tg_status="✓", tg_computed="498 K", tg_err="33%")],
        _CLASSES,
    )
    assert cal["PSTR"]["flags"] == []


def test_replica_spread_flag():
    cal = calibrate(
        [_run("S1", "PSTR", tg_computed="500 K"),
         _run("S2", "PSTR", tg_computed="420 K")],   # 80 K apart → σ=40 > 30
        _CLASSES,
    )
    assert any("replica spread" in f for f in cal["PSTR"]["flags"])


def test_build_calibration_markdown_and_offset_note():
    md = build_calibration(
        [_run("PC1", "PCBN", tg_status="⚠ outside bounds")], _RULES)
    assert "# Confidence Calibration" in md
    assert "| PCBN | high |" in md
    assert "over-predicts Tg" in md  # the MD-offset caveat note


def test_build_calibration_empty():
    assert "No runs with filled results" in build_calibration([], _RULES)
