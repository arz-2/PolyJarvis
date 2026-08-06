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
import run_deterministic_replicate as rdr  # noqa: E402
from run_deterministic_replicate import (  # noqa: E402
    _base_args, wait_for_analysis, do_equil_and_check, ExecutorState,
)

RULES = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())
# make_deterministic_plan.py/run_deterministic_replicate.py work uniformly for any class
# regardless of any per-SMILES validated status (that's an orchestrator-level gate, not a
# script-level one) -- the scripted path's only real scope restriction is the EMC-build-only
# limit DETERMINISTIC_REPLICATE.md documents (PURA is RadonPy-only, not yet supported here).
SCRIPTED_PATH_CLASSES = sorted(c for c, v in RULES["classes"].items()
                               if v.get("preferred_builder", "emc") == "emc")

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
    """One deterministic run_plan.json per EMC-build (scripted-path-eligible) class."""
    d = tmp_path_factory.mktemp("plans")
    paths = {}
    for cls in SCRIPTED_PATH_CLASSES:
        out = d / f"{cls}.json"
        _run([str(MAKE_PLAN), "--run_name", f"DRT_{cls}", "--polymer_class", cls, "--out", str(out)])
        paths[cls] = out
    return paths


def test_scripted_path_classes_nonempty():
    """Sanity: this test file's whole point is moot if polymer_rules.json has no EMC-build
    classes yet -- fail loudly rather than silently parametrizing over an empty list."""
    assert SCRIPTED_PATH_CLASSES, "no EMC-build classes found in guides/polymer_rules.json"


@pytest.mark.parametrize("cls", SCRIPTED_PATH_CLASSES)
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


@pytest.mark.parametrize("cls", SCRIPTED_PATH_CLASSES)
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


# ─── wait_for_analysis(): the async-analysis-tool polling helper (Finding 1) ──────────

class _StatusSequence:
    """Fake lammps.get_run_status(): returns a canned sequence of status dicts, one per call,
    holding on the last entry once exhausted (so a test can assert exact call counts by
    controlling how many entries it supplies)."""

    def __init__(self, statuses):
        self._statuses = list(statuses)
        self.calls = 0

    def get_run_status(self, run_id):
        self.calls += 1
        idx = min(self.calls - 1, len(self._statuses) - 1)
        return self._statuses[idx]


def test_wait_for_analysis_synchronous_passthrough():
    """A result with no run_id (already-synchronous tool, or an immediate error) is returned
    unchanged -- nothing to poll."""
    fake = _StatusSequence([])
    result = {"status": "ok", "plateau_density_mean": 1.18}
    assert wait_for_analysis(fake, result, "density") is result
    assert fake.calls == 0


def test_wait_for_analysis_polls_until_completed():
    fake = _StatusSequence([
        {"status": "running"},
        {"status": "running"},
        {"status": "completed", "result": {"Tg_K": 380.0}},
    ])
    got = wait_for_analysis(fake, {"status": "submitted", "run_id": "r1"}, "tg",
                            poll_seconds=0)
    assert got == {"Tg_K": 380.0}
    assert fake.calls == 3


def test_wait_for_analysis_failed_raises():
    fake = _StatusSequence([{"status": "failed", "error": "boom"}])
    with pytest.raises(SystemExit, match="analysis failed"):
        wait_for_analysis(fake, {"status": "submitted", "run_id": "r1"}, "murnaghan",
                          poll_seconds=0)


def test_wait_for_analysis_timeout_raises():
    fake = _StatusSequence([{"status": "running"}])
    with pytest.raises(SystemExit, match="timed out"):
        wait_for_analysis(fake, {"status": "submitted", "run_id": "r1"}, "deform",
                          poll_seconds=0, timeout_s=0)


# ─── do_equil_and_check(): backbone_types halt + EXTEND sizing (Findings 2/3) ─────────

class _FakeEquilLammps:
    """Minimal in-process stand-in for the lammps_engine server module, covering only what
    do_equil_and_check() calls. check_equilibration_comprehensive/extract_equilibrated_density
    return already-"finished" dicts (no run_id) so wait_for_analysis() passes them through
    unchanged -- this test is about do_equil_and_check()'s own logic, not the polling helper
    (covered separately above)."""

    def __init__(self, tmp_path, comp_results, gate_verdicts, atom_type_names=None):
        self.tmp_path = tmp_path
        self._comp_results = list(comp_results)
        self._gate_verdicts = list(gate_verdicts)
        self._chain_n = 0
        self.generate_equilibration_workflow_calls = []
        self.inspect_data_file_calls = []
        self._atom_type_names = atom_type_names or {}

    def _sentinel(self):
        self._chain_n += 1
        p = self.tmp_path / f"sentinel_{self._chain_n}.json"
        p.write_text(json.dumps({"status": "completed", "run_id": f"chain-{self._chain_n}"}))
        return p

    def generate_equilibration_workflow(self, **kwargs):
        self.generate_equilibration_workflow_calls.append(kwargs)
        stage = {"output_data": f"{self.tmp_path}/npt_prod_{self._chain_n}_out.data",
                 "work_dir": str(self.tmp_path), "params": {"DUMP_FILE": "npt_prod.dump"}}
        return {"stages": [stage]}

    def run_lammps_chain(self, **kwargs):
        return {"chain_id": f"pending-{self._chain_n + 1}"}

    def watch_run(self, run_id):
        return {"sentinel_path": str(self._sentinel()), "pidfile": None}

    def inspect_data_file(self, data_file):
        self.inspect_data_file_calls.append(data_file)
        return {"info": {"atom_type_names": self._atom_type_names}}

    def check_equilibration_comprehensive(self, **kwargs):
        return self._comp_results.pop(0)

    def extract_equilibrated_density(self, **kwargs):
        return {"plateau_density_mean": 1.18}

    def enforce_equilibration_gate(self, **kwargs):
        return self._gate_verdicts.pop(0)


@pytest.fixture
def equil_check_args_cls():
    """Real args/cls for one EMC-build class, resolved via the same
    make_deterministic_plan.py -> apply_plan/resolve_hardware path main() uses -- so
    resolve_stage_params("equil"/"equil-check", ...) sees realistic values."""
    cls = SCRIPTED_PATH_CLASSES[0]
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    plan_path = tmp / f"{cls}.json"
    _run([str(MAKE_PLAN), "--run_name", f"DRTU_{cls}", "--polymer_class", cls, "--out", str(plan_path)])
    rules = load_rules()
    cls_raw = get_class_entry(rules, cls, warn_on_miss=False)
    plan = load_plan(str(plan_path))
    args = _base_args(f"DRTU_{cls}", cls, str(plan_path))
    args.data_path = "/fake/original/cell.data"
    effective_cls = apply_plan(cls_raw, plan, args)
    resolve_hardware(args, effective_cls, rules)
    yield args, effective_cls


def _fake_state(tmp_path):
    return ExecutorState(tmp_path / "executor_state.json", "DRTU", "PACR", "fake_plan.json")


def test_do_equil_and_check_halts_when_backbone_types_unresolved(tmp_path, equil_check_args_cls, monkeypatch):
    args, cls = equil_check_args_cls
    assert args.backbone_types is None  # default -- nothing explicit configured for this test
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [0], "run": run_name} if action == "claim" else {"released": True}))
    fake = _FakeEquilLammps(tmp_path, comp_results=[], gate_verdicts=[],
                            atom_type_names={"1": "c", "2": "c1"})
    state = _fake_state(tmp_path)

    result = do_equil_and_check(state, args, cls, fake, tmp_path / "run_log.md")

    assert result == {"halted": True, "reason": "BACKBONE_TYPES_UNRESOLVED"}
    assert state.data["halted"]["reason"] == "BACKBONE_TYPES_UNRESOLVED"
    # halted before ever calling the async analysis tools -- no guessed [] silently submitted
    assert fake.inspect_data_file_calls == ["/fake/original/cell.data"]


def test_do_equil_and_check_sizes_extend_off_measured_tau_relax(tmp_path, equil_check_args_cls, monkeypatch):
    args, cls = equil_check_args_cls
    args.backbone_types = [1, 2]  # explicit -- skip the halt path, exercise EXTEND sizing instead
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [0], "run": run_name} if action == "claim" else {"released": True}))
    tau_relax_ps = 6209.0
    fake = _FakeEquilLammps(
        tmp_path,
        comp_results=[
            {"chain": {"ct": {"tau_relax_ps": tau_relax_ps, "decay_fraction_at_end": 0.08}}},
            {"chain": {"ct": {"tau_relax_ps": tau_relax_ps, "decay_fraction_at_end": 0.3}}},
        ],
        gate_verdicts=[{"verdict": "EXTEND"}, {"verdict": "PASS"}],
    )
    state = _fake_state(tmp_path)

    result = do_equil_and_check(state, args, cls, fake, tmp_path / "run_log.md")

    assert result["equil_verdict"] == "PASS"
    # Two generate_equilibration_workflow calls: the initial submission, then the EXTEND.
    assert len(fake.generate_equilibration_workflow_calls) == 2
    extend_call = fake.generate_equilibration_workflow_calls[1]
    assert extend_call["extend_only"] is True
    dt_fs = resolve_stage_params("equil", args, cls)["dt_fs"]
    extend_ns_used = extend_call["extend_steps"] * dt_fs / 1e6
    expected_extend_ns = max(1.5, round(1.5 * tau_relax_ps / 1000, 2))
    assert extend_ns_used == pytest.approx(expected_extend_ns, rel=1e-6)
    # sanity: the measured signal actually moved the knob away from the old flat 1.5 ns default
    assert extend_ns_used > 1.5
