"""Regression guard for the scripted deterministic-replicate executor.

run_deterministic_replicate.py's --dry-run mode resolves every stage's params via
orchestration/gen_prompt.py's resolve_stage_params() -- the same function the agent-prompt
text-rendering path uses (A.0's refactor). This test proves the executor actually calls it the
same way the text-prompt path does, by re-deriving the expected params directly and comparing --
so a future change to either the executor's args-namespace construction or gen_prompt.py's
routing logic can never silently diverge between the two paths without failing a test.

Does NOT submit any simulation -- --dry-run never calls the MCP servers.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration"))

from gen_prompt import resolve_stage_params, apply_plan, resolve_hardware, load_plan  # noqa: E402
from hw_common import load_rules, get_class_entry  # noqa: E402
from run_deterministic_replicate import _base_args  # noqa: E402

RULES = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())
HIGH_CONF_CLASSES = sorted(c for c, v in RULES["classes"].items() if v.get("confidence") == "high")

EXECUTOR = REPO_ROOT / "orchestration" / "run_deterministic_replicate.py"
MAKE_PLAN = REPO_ROOT / "orchestration" / "make_deterministic_plan.py"


def _run(cmd):
    r = subprocess.run([sys.executable, *cmd], capture_output=True, text=True)
    assert r.returncode == 0, f"command failed: {cmd}\n{r.stderr}"
    return r.stdout


def _normalize(d):
    """Round-trip through JSON so both sides compare with identical type representations
    (tuples->lists, etc.) regardless of which side came from a subprocess's stdout."""
    return json.loads(json.dumps(d, default=str))


@pytest.fixture(scope="module")
def plan_files(tmp_path_factory):
    """One deterministic run_plan.json per confidence=='high' class."""
    d = tmp_path_factory.mktemp("plans")
    paths = {}
    for cls in HIGH_CONF_CLASSES:
        out = d / f"{cls}.json"
        _run([str(MAKE_PLAN), "--run_name", f"DRT_{cls}", "--polymer_class", cls, "--out", str(out)])
        paths[cls] = out
    return paths


def test_confidence_high_classes_nonempty():
    """Sanity: this test file's whole point is moot if polymer_rules.json has no confidence=high
    classes yet -- fail loudly rather than silently parametrizing over an empty list."""
    assert HIGH_CONF_CLASSES, "no confidence=='high' classes found in guides/polymer_rules.json"


@pytest.mark.parametrize("cls", HIGH_CONF_CLASSES)
def test_dry_run_matches_resolve_stage_params(cls, plan_files):
    plan_path = plan_files[cls]
    r = subprocess.run(
        [sys.executable, str(EXECUTOR), "--run_name", f"DRT_{cls}", "--polymer_class", cls,
         "--plan", str(plan_path), "--dry-run"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"--dry-run failed for {cls}: {r.stderr}"
    dry = json.loads(r.stdout)
    for stage, params in dry.items():
        assert "error" not in params, f"{cls}/{stage} resolver raised: {params.get('error')}"

    # Re-derive the expected params the same way run_deterministic_replicate.main() does, and
    # compare against the subprocess's --dry-run output stage by stage.
    rules = load_rules()
    cls_raw = get_class_entry(rules, cls, warn_on_miss=False)
    plan = load_plan(str(plan_path))
    args = _base_args(f"DRT_{cls}", cls, str(plan_path))
    effective_cls = apply_plan(cls_raw, plan, args)
    resolve_hardware(args, effective_cls, rules)

    for stage in dry:
        expected = resolve_stage_params(stage, args, effective_cls)
        assert _normalize(dry[stage]) == _normalize(expected), (
            f"{cls}/{stage}: --dry-run output diverges from a direct resolve_stage_params() call")


@pytest.mark.parametrize("cls", HIGH_CONF_CLASSES)
def test_dry_run_covers_expected_stages(cls, plan_files):
    """Every deterministic-plan class dry-runs at least the always-on stages, plus tg/mechanical
    stages iff the plan's properties include them -- catches a stage silently dropped from the
    dry-run stage list in _print_dry_run()."""
    plan = json.loads(plan_files[cls].read_text())
    properties = set(plan.get("properties", []))
    r = subprocess.run(
        [sys.executable, str(EXECUTOR), "--run_name", f"DRT_{cls}", "--polymer_class", cls,
         "--plan", str(plan_files[cls]), "--dry-run"],
        capture_output=True, text=True, check=True,
    )
    dry = json.loads(r.stdout)
    expected_stages = {"build", "equil", "equil-check", "run-summary"}
    if "tg" in properties:
        expected_stages |= {"tg", "analyze-tg", "analyze-tg-multirate"}
    if "bulk_modulus" in properties:
        expected_stages |= {"murnaghan", "deform", "analyze-bm"}
    assert expected_stages <= set(dry.keys()), (
        f"{cls}: dry-run missing expected stages {expected_stages - set(dry.keys())}")
