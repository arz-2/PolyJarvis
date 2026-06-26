"""Tests for the arm-3 (agent) RunMetrics adapter."""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import agent_metrics as am  # noqa: E402
from metrics import RunMetrics  # noqa: E402

REPO_ROOT = HERE.parents[2]
PMMA2 = REPO_ROOT / "data" / "PMMA2"


# --- fixture run_logs exercising both recovery-parse paths --------------------

_TAGGED = """# Foo Run 1 · 2026-01-01 → 2026-01-02
SMILES: `*CC*`  |  FF: PCFF
Requested: density
Plan: `x`  |  mode: deterministic  |  confidence: high  |  critic: approved (round 1)

## RECOVERIES

### R-01 · something
<!-- RECOVERY: error_class=ff_style_mismatch prescripted=true outcome=converged attempts=2 -->
Body text.

## SIMULATION STATE

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-stage) | abc | 06:00 | 09:00 | ~3h | done |
"""

_PROSE_UNRESOLVED = """# Bar Run 1 · 2026-01-01 → 2026-01-02
SMILES: `*CC*`  |  FF: PCFF
Requested: density
Plan: `x`  |  mode: reasoned  |  confidence: low  |  critic: escalate

## RECOVERIES

### R-01 · PPPM out of range
**Trigger:** PPPM out of range error in npt_compress.
**Outcome:** UNRESOLVED (stop after 2 attempts).

## SIMULATION STATE

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-stage) | abc | 06:00 | — | — | failed |
"""


def _write(tmp_path, text):
    d = tmp_path / "run"
    d.mkdir()
    (d / "run_log.md").write_text(text)
    return d


def test_tagged_path(tmp_path):
    d = _write(tmp_path, _TAGGED)
    m = am.metrics_from_run(d, "Foo", "PHYC", 1001, foundation_only=True)
    assert isinstance(m, RunMetrics)
    assert len(m.recovery_events) == 1
    ev = m.recovery_events[0]
    assert ev.fault == "ff_style_mismatch"
    assert ev.prescripted is True
    assert ev.resolved is True
    assert ev.attempts == 2
    assert m.interventions == 0
    assert m.wall_clock_s == pytest.approx(3 * 3600)
    assert m.terminal_state == "completed_foundation"
    assert "equil" in m.stages_completed


def test_prose_unresolved_path(tmp_path):
    d = _write(tmp_path, _PROSE_UNRESOLVED)
    m = am.metrics_from_run(d, "Bar", "PHYC", 1001, foundation_only=True)
    assert len(m.recovery_events) == 1
    assert m.recovery_events[0].resolved is False        # "UNRESOLVED" keyword
    assert m.interventions >= 1                            # UNRESOLVED + escalate
    assert m.terminal_state == "stalled"                  # failed stage / UNRESOLVED


@pytest.mark.skipif(not (PMMA2 / "run_log.md").exists(),
                    reason="PMMA2 run not present")
def test_real_pmma2_run():
    m = am.metrics_from_run(PMMA2, "PMMA2", "PACR", 734812)
    # PMMA2 has three documented recovery blocks (R-01, R-02, R-03), all resolved.
    assert len(m.recovery_events) == 3
    assert all(ev.resolved for ev in m.recovery_events)
    assert m.interventions == 0
    assert m.wall_clock_s > 0
    assert "equil" in m.stages_completed
    assert m.terminal_state == "completed"   # run_summary.json present


@pytest.mark.skipif(not (PMMA2 / "raw" / "run_summary.json").exists(),
                    reason="PMMA2 run_summary not present")
def test_accuracy_helper_reads_density():
    acc = am.accuracy_vs_exp(PMMA2)
    assert acc["density_gcm3"] is not None
    assert acc["density_gcm3"] > 0
