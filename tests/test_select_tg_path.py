"""Behavioral tests for orchestration/select_tg_path.py.

The helper picks which per-rate tg_summary.json feeds run-summary: the slowest
rate when the multirate slope gate passed, else the class fallback rate from
decided_params.tg_slope_gate_fallback (highest_rate default; slowest_rate for
rigid aromatics PKTN/PSFO). CLAUDE.md Phase C evals its two stdout lines
(TG_PATH=..., SLOPE_GATE=...), so that contract is pinned here too.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "orchestration" / "select_tg_path.py"


def _invoke(tmp_path, rates, gate, fallback=None):
    plan = {"decided_params": {"tg_rates_K_per_ns": rates}}
    if fallback is not None:
        plan["decided_params"]["tg_slope_gate_fallback"] = fallback
    plan_path = tmp_path / "run_plan.json"
    plan_path.write_text(json.dumps(plan))
    multi = {} if gate is None else {"slope_gate_pass": gate}
    multi_path = tmp_path / "tg_multirate_result.json"
    multi_path.write_text(json.dumps(multi))
    r = subprocess.run([sys.executable, str(SCRIPT),
                        "--plan", str(plan_path), "--multirate", str(multi_path)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = dict(line.split("=", 1) for line in r.stdout.strip().splitlines())
    return out, r.stderr


def test_gate_pass_selects_slowest(tmp_path):
    out, _ = _invoke(tmp_path, [25, 50, 100], gate=True)
    assert out["TG_PATH"].endswith("tg_r25/tg_summary.json")
    assert out["SLOPE_GATE"] == "true"


def test_gate_fail_default_selects_highest(tmp_path):
    out, _ = _invoke(tmp_path, [25, 50, 100], gate=False)
    assert out["TG_PATH"].endswith("tg_r100/tg_summary.json")
    assert out["SLOPE_GATE"] == "false"


def test_gate_fail_slowest_rate_fallback(tmp_path):
    """Rigid-aromatic convention (PKTN/PSFO): gate fail -> slowest rate."""
    out, _ = _invoke(tmp_path, [25, 50, 100], gate=False, fallback="slowest_rate")
    assert out["TG_PATH"].endswith("tg_r25/tg_summary.json")
    assert out["SLOPE_GATE"] == "false"


def test_gate_fail_explicit_highest_rate_fallback(tmp_path):
    """PEST shape: gate fail + highest_rate -> highest rate."""
    out, _ = _invoke(tmp_path, [40, 80, 100], gate=False, fallback="highest_rate")
    assert out["TG_PATH"].endswith("tg_r100/tg_summary.json")


def test_gate_fail_unknown_fallback_warns_and_uses_highest(tmp_path):
    out, err = _invoke(tmp_path, [25, 50, 100], gate=False, fallback="typo_rate")
    assert out["TG_PATH"].endswith("tg_r100/tg_summary.json")
    assert "unknown tg_slope_gate_fallback" in err


def test_missing_gate_defaults_to_slowest_with_warning(tmp_path):
    out, err = _invoke(tmp_path, [25, 50, 100], gate=None)
    assert out["TG_PATH"].endswith("tg_r25/tg_summary.json")
    assert out["SLOPE_GATE"] == "true"
    assert "slope_gate_pass missing" in err


def test_non_integer_rate_formatting(tmp_path):
    out, _ = _invoke(tmp_path, [2.5, 50, 100], gate=True)
    assert out["TG_PATH"].endswith("tg_r2.5/tg_summary.json")
