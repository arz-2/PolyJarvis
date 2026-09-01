"""Regression guard for the deterministic campaign executor.

run_campaign.py's --dry-run mode resolves every stage through stage_params.py. These tests
prove the executor and the protocol resolver cannot silently diverge.

Does NOT submit any simulation -- --dry-run never calls the MCP servers.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from stage_params import resolve_stage_params, apply_plan, resolve_hardware, load_plan  # noqa: E402
from hw_common import load_rules, get_class_entry  # noqa: E402
import run_campaign as rdr  # noqa: E402
from run_campaign import (  # noqa: E402
    _base_args, wait_for_analysis, do_equil_and_check, do_summary, do_build, COMPRESSION_RATIO,
    _bracket_tg_start_temp, _run_tg_sweep_adaptive, _bm_point_adaptive_extend,
    _anneal_hold_adaptive_extend, _record_anneal_hold_convergence, _submit_equil_chain,
)

RULES = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())
# The plan generator and campaign runner work uniformly for configured EMC-backed classes.
SCRIPTED_PATH_CLASSES = sorted(c for c, v in RULES["classes"].items()
                               if v.get("preferred_builder", "emc") == "emc")

EXECUTOR = REPO_ROOT / "orchestration" / "scripts" / "run_campaign.py"
MAKE_PLAN = REPO_ROOT / "orchestration" / "scripts" / "make_deterministic_plan.py"


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

    # Re-derive the expected params the same way run_campaign.main() does, and
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
        expected_stages |= {"tg", "analyze-tg"}
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


# ─── do_build(): finite-size forecast target density is never experimental data ────

class _FakeEmc:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        (tmp_path / "cell.data").write_text("# fake cell\n")

    def submit_emc_cell_job(self, **kwargs):
        return {"job_id": "job-1"}

    def get_emc_job_status(self, job_id):
        return {"status": "completed"}

    def get_emc_job_output(self, job_id):
        return {"result": {"data_path": str(self.tmp_path / "cell.data"),
                           "output_dir": str(self.tmp_path), "lammps_flags": ""}}


class _FakeBuildLammps:
    def __init__(self):
        self.inspect_data_file_calls = []

    def inspect_data_file(self, **kwargs):
        self.inspect_data_file_calls.append(kwargs)
        return {"info": {}, "validation": {"errors": [], "warnings": []},
                "finite_size_forecast": {"available": True}}


def test_do_build_target_density_ignores_resolvable_experimental_density(
        tmp_path, equil_check_args_cls, monkeypatch):
    """Even when experimental_density_gcm3 IS resolvable for this class/SMILES, the
    finite-size forecast must never read it -- target_density_gcm3 is always
    COMPRESSION_RATIO * density_initial_gcm3, unconditionally."""
    args, cls = equil_check_args_cls
    args.work_dir = str(tmp_path / "work")
    assert cls.get("experimental_density_gcm3") is not None, (
        "fixture class must have a resolvable experimental_density_gcm3 for this "
        "test to prove the forecast ignores it, not merely never needed it")

    emc = _FakeEmc(tmp_path)
    lammps = _FakeBuildLammps()

    do_build(args, cls, emc, lammps)

    assert len(lammps.inspect_data_file_calls) == 1
    call = lammps.inspect_data_file_calls[0]
    expected = COMPRESSION_RATIO * cls["density_initial_gcm3"]
    assert call["target_density_gcm3"] == pytest.approx(expected)


# ─── do_equil_and_check(): backbone_types halt + EXTEND sizing (Findings 2/3) ─────────

class _FakeEquilLammps:
    """Minimal in-process stand-in for the lammps_engine server module, covering only what
    do_equil_and_check() calls. check_equilibration_comprehensive/extract_equilibrated_density
    return already-"finished" dicts (no run_id) so wait_for_analysis() passes them through
    unchanged -- this test is about do_equil_and_check()'s own logic, not the polling helper
    (covered separately above)."""

    def __init__(self, tmp_path, comp_results, gate_verdicts, atom_type_names=None,
                 derived_backbone_types=None, workflow_stages=None, workflow_extra=None,
                 workflow_queue=None):
        self.tmp_path = tmp_path
        self._comp_results = list(comp_results)
        self._gate_verdicts = list(gate_verdicts)
        self._chain_n = 0
        self.generate_equilibration_workflow_calls = []
        self.inspect_data_file_calls = []
        self.derive_backbone_types_calls = []
        self.check_equilibration_comprehensive_calls = []
        self.enforce_equilibration_gate_calls = []
        self._inspect_errors = []
        self._inspect_forecast = {"available": False}
        self._atom_type_names = atom_type_names or {}
        # None -> derivation fails (genuine last resort); a list -> derivation succeeds with it.
        self._derived_backbone_types = derived_backbone_types
        # None -> the default single anonymous stage below; a list of named stage dicts (e.g.
        # nvt_production/npt_production) -> returned verbatim, for tests of the name-based
        # melt_dump_path/melt_data_path stage lookup.
        self._workflow_stages = workflow_stages
        self._workflow_extra = workflow_extra or {}
        # A list of full workflow dicts, one popped per generate_equilibration_workflow() call --
        # for the anneal_hold_msid_gate's chain1/chain2 split, where each call must return a
        # DIFFERENT stage list (workflow_stages/_extra only support one fixed shape reused every
        # call). Takes priority over workflow_stages when both are given.
        self._workflow_queue = list(workflow_queue) if workflow_queue is not None else None

    def _sentinel(self):
        self._chain_n += 1
        p = self.tmp_path / f"sentinel_{self._chain_n}.json"
        p.write_text(json.dumps({"status": "completed", "run_id": f"chain-{self._chain_n}"}))
        return p

    def generate_equilibration_workflow(self, **kwargs):
        self.generate_equilibration_workflow_calls.append(kwargs)
        if self._workflow_queue is not None:
            return self._workflow_queue.pop(0)
        if self._workflow_stages is not None:
            return {"stages": self._workflow_stages, **self._workflow_extra}
        stage = {"name": "npt_final",
                 "output_data": f"{self.tmp_path}/npt_prod_{self._chain_n}_out.data",
                 "output_restart": f"{self.tmp_path}/npt_prod_{self._chain_n}_out.restart",
                 "work_dir": str(self.tmp_path), "params": {"DUMP_FILE": "npt_prod.dump"}}
        return {"stages": [stage]}

    def run_lammps_chain(self, **kwargs):
        return {"chain_id": f"pending-{self._chain_n + 1}"}

    def watch_run(self, run_id):
        return {"sentinel_path": str(self._sentinel()), "pidfile": None}

    def inspect_data_file(self, data_file, **kwargs):
        # **kwargs so this fake keeps matching the real tool as its signature grows
        # (lj_cutoff / target_density_gcm3 / nchain arm the finite-size forecast).
        self.inspect_data_file_calls.append(data_file)
        return {
            "info": {"atom_type_names": self._atom_type_names},
            "validation": {"valid": True, "errors": list(self._inspect_errors),
                           "warnings": [], "stats": {}},
            "finite_size_forecast": self._inspect_forecast,
        }

    def derive_backbone_types(self, **kwargs):
        self.derive_backbone_types_calls.append(kwargs)
        if self._derived_backbone_types is None:
            return {"status": "failed", "error": "no chain yielded a resolvable backbone"}
        return {"status": "success", "backbone_types": self._derived_backbone_types,
                "method": "heavy_atom_graph_diameter", "n_chains": 1, "n_chains_resolved": 1}

    def check_equilibration_comprehensive(self, **kwargs):
        self.check_equilibration_comprehensive_calls.append(kwargs)
        return self._comp_results.pop(0)

    def extract_equilibrated_density(self, **kwargs):
        return {"plateau_density_mean": 1.18}

    def enforce_equilibration_gate(self, **kwargs):
        self.enforce_equilibration_gate_calls.append(kwargs)
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


def test_do_equil_and_check_routes_minimize_not_converged_as_halted_dict(
        tmp_path, equil_check_args_cls, monkeypatch):
    """The chain-script's post-minimize convergence check (Change 4a) signals via a distinct
    sentinel stage name ("minimize_not_converged", not the plain "minimize" a real LAMMPS
    crash would produce) -- do_equil_and_check must route this to the same halted-dict shape
    used by EXTEND_EXHAUSTED/STRUCTURAL_FAIL (which CampaignStageExecutor.execute already
    knows how to turn into a routable Finding), not the generic bare SystemExit fallback."""
    args, cls = equil_check_args_cls
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [0], "run": run_name} if action == "claim" else {"released": True}))
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: (
        {"status": "failed", "stage": "minimize_not_converged", "run_id": run_id}))
    fake = _FakeEquilLammps(tmp_path, comp_results=[], gate_verdicts=[])

    result = do_equil_and_check(args, cls, fake)

    assert result["halted"] is True
    assert result["reason"] == "MINIMIZE_NOT_CONVERGED"
    assert result["detail"]["stage"] == "minimize_not_converged"


def test_do_equil_and_check_other_chain_failures_still_raise(
        tmp_path, equil_check_args_cls, monkeypatch):
    """A plain "minimize" (or any other) stage failure -- a real LAMMPS crash, not the
    convergence check -- must still hit the generic bare-SystemExit fallback, unchanged."""
    args, cls = equil_check_args_cls
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [0], "run": run_name} if action == "claim" else {"released": True}))
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: (
        {"status": "failed", "stage": "minimize", "run_id": run_id}))
    fake = _FakeEquilLammps(tmp_path, comp_results=[], gate_verdicts=[])

    with pytest.raises(SystemExit, match="Equilibration chain did not complete"):
        do_equil_and_check(args, cls, fake)


def test_do_equil_and_check_halts_when_backbone_types_unresolved(tmp_path, equil_check_args_cls, monkeypatch):
    """Genuine last resort: bond-topology derivation is attempted first and fails (e.g. the
    chain has fewer than 2 heavy atoms, or no bond topology at all), so the halt still fires."""
    args, cls = equil_check_args_cls
    assert args.backbone_types is None  # default -- nothing explicit configured for this test
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [0], "run": run_name} if action == "claim" else {"released": True}))
    fake = _FakeEquilLammps(tmp_path, comp_results=[], gate_verdicts=[],
                            atom_type_names={"1": "c", "2": "c1"}, derived_backbone_types=None)

    result = do_equil_and_check(args, cls, fake)

    assert result["halted"] is True
    assert result["reason"] == "BACKBONE_TYPES_UNRESOLVED"
    assert fake.derive_backbone_types_calls == [{"data_file": "/fake/original/cell.data"}]
    # halted only after derivation itself failed -- no guessed [] silently submitted
    assert fake.inspect_data_file_calls == ["/fake/original/cell.data"]


def test_do_equil_and_check_auto_derives_backbone_types(tmp_path, equil_check_args_cls, monkeypatch):
    """The routine case: bond-topology derivation succeeds, so the halt never fires -- the
    derived value is used immediately and persisted into decided_params for future stages/runs."""
    args, cls = equil_check_args_cls
    assert args.backbone_types is None
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [0], "run": run_name} if action == "claim" else {"released": True}))
    fake = _FakeEquilLammps(
        tmp_path,
        comp_results=[{"chain": {"ct": {"tau_relax_ps": 100.0, "decay_fraction_at_end": 0.9}}}],
        gate_verdicts=[{"verdict": "PASS"}],
        derived_backbone_types=[1, 2],
    )

    result = do_equil_and_check(args, cls, fake)

    assert result["equil_verdict"] == "PASS"
    assert result["backbone_derivation"]["outcome"] == "RESOLVED — automatic"
    assert fake.derive_backbone_types_calls == [{"data_file": "/fake/original/cell.data"}]
    assert fake.inspect_data_file_calls == []  # never reached -- derivation succeeded
    assert cls["backbone_types"] == [1, 2]
    persisted = load_plan(args.plan)
    assert persisted["decided_params"]["backbone_types"] == [1, 2]


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

    result = do_equil_and_check(args, cls, fake)

    assert result["equil_verdict"] == "PASS"
    assert len(result["extend_history"]) == 1
    assert result["extend_history"][0]["attempt"] == 1
    # Two generate_equilibration_workflow calls: the initial submission, then the EXTEND.
    assert len(fake.generate_equilibration_workflow_calls) == 2
    extend_call = fake.generate_equilibration_workflow_calls[1]
    assert extend_call["extend_only"] is True
    assert extend_call["base_stage_name"] == "npt_final"
    assert extend_call["restart_file"] == f"{tmp_path}/npt_prod_0_out.restart"
    dt_fs = resolve_stage_params("equil", args, cls)["dt_fs"]
    # npt_final's continuation length comes through stage8_min_steps (the same knob
    # generate_equilibration_workflow reads for base_stage_name="npt_final"), not a generic
    # "extend_steps" param.
    extend_ns_used = extend_call["stage8_min_steps"] * dt_fs / 1e6
    expected_extend_ns = max(1.5, round(1.5 * tau_relax_ps / 1000, 2))
    assert extend_ns_used == pytest.approx(expected_extend_ns, rel=1e-6)
    # sanity: the measured signal actually moved the knob away from the old flat 1.5 ns default
    assert extend_ns_used > 1.5


# ─── do_summary(): generate_run_summary must be waited on, not read as a submission stub ──

class _FakeSummaryLammps:
    """generate_run_summary is a background-threaded analysis tool (same submitted/run_id
    shape as check_equilibration_comprehensive et al.) -- this fake returns the submission
    stub from the tool call itself and only returns the real completed result from
    get_run_status, so a caller that reads the tool's own return value directly (skipping
    wait_for_analysis) gets the stub, not the finished summary."""

    def __init__(self, completed_result):
        self._completed_result = completed_result
        self.generate_run_summary_calls = []
        self.get_run_status_calls = 0

    def generate_run_summary(self, **kwargs):
        self.generate_run_summary_calls.append(kwargs)
        return {"status": "submitted", "run_id": "summary-1",
                "message": "Poll with get_run_status(run_id)"}

    def get_run_status(self, run_id):
        self.get_run_status_calls += 1
        assert run_id == "summary-1"
        return {"status": "completed", "result": self._completed_result}


def test_do_summary_waits_for_generate_run_summary_completion(tmp_path):
    """PE1 2026-08-17: do_summary called generate_run_summary bare and returned its immediate
    {"status": "submitted", ...} stub as the stage's own result -- the workflow engine accepted
    the "summary" stage as done, and run_summary.json was never actually confirmed written."""
    cls = {
        "preferred_ff": "trappe-ua", "charge_method": "none", "electrostatics": "lj_cut",
        "dp_typical": 120, "nchain": 20, "experimental_tg_K": 195,
        "experimental_density_gcm3": 0.855, "exp_K_GPa": {"min": 1.5, "max": 2.0},
    }
    args = _base_args("SUMTEST1", "PHYC", "fake_plan.json")
    args.output_dir = str(tmp_path / "raw")
    args.smiles = "*CC*"
    args.n_replicates = 1
    (tmp_path / "raw").mkdir()
    fake = _FakeSummaryLammps(completed_result={
        "status": "success", "summary_json": str(tmp_path / "raw" / "run_summary.json"),
    })

    result = do_summary(args, cls, fake, is_glassy=False, thermal_result=None,
                        equil_verdict="PASS", raw_dir=tmp_path / "raw")

    assert fake.get_run_status_calls >= 1, "generate_run_summary's result was never polled"
    assert result["status"] == "success"
    assert result["summary_json"] == str(tmp_path / "raw" / "run_summary.json")
    assert result["run_summary_path"] == str(tmp_path / "raw" / "run_summary.json")
    assert result.get("status") != "submitted"


# ─── do_equil_and_check(): melt_dump_path/melt_data_path stage lookup ──────────────

def test_do_equil_and_check_resolves_melt_paths_by_stage_name(tmp_path, equil_check_args_cls, monkeypatch):
    """melt_dump_path (nvt_kinetic_stability's dump) must come from the real workflow's own
    named stage, not the flat-convention guess -- same bug class as npt_prod_log_path, fixed
    the same way analyze-tg's per_t_dump_file was: look up the real path instead of re-deriving
    one independently. melt_data_path (the assess_cooling_contraction melt reference) comes
    directly from the generator's own top-level melt_data_path field -- the cool_block tagged
    at `temp`/t_equil_K, which stage-name lookup can't find since its name varies (cool_block_NN
    for whichever N is tagged)."""
    args, cls = equil_check_args_cls
    args.backbone_types = [1, 2]  # skip the halt path
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [0], "run": run_name} if action == "claim" else {"released": True}))

    kinetic_dir = tmp_path / "work" / "nvt_kinetic_stability"
    final_dir = tmp_path / "work" / "npt_final"
    cool_block_dir = tmp_path / "work" / "cool_block_02"
    kinetic_dir.mkdir(parents=True)
    final_dir.mkdir(parents=True)
    cool_block_dir.mkdir(parents=True)
    workflow_stages = [
        {"name": "nvt_kinetic_stability", "work_dir": str(kinetic_dir),
         "params": {"DUMP_FILE": "nvt_kinetic_stability.dump"},
         "output_data": str(kinetic_dir / "nvt_kinetic_stability_out.data"),
         "output_restart": str(kinetic_dir / "nvt_kinetic_stability_out.restart")},
        {"name": "npt_final", "work_dir": str(final_dir),
         "params": {"DUMP_FILE": "npt_final.dump"},
         "output_data": str(final_dir / "npt_final_out.data"),
         "output_restart": str(final_dir / "npt_final_out.restart")},
    ]
    melt_data_path = str(cool_block_dir / "cool_block_02_out.data")
    fake = _FakeEquilLammps(
        tmp_path,
        comp_results=[{"chain": {"ct": {"tau_relax_ps": 100.0, "decay_fraction_at_end": 0.9}}}],
        gate_verdicts=[{"verdict": "PASS"}],
        workflow_stages=workflow_stages,
        workflow_extra={"melt_data_path": melt_data_path},
    )

    result = do_equil_and_check(args, cls, fake)

    assert result["equil_verdict"] == "PASS"
    comp_call = fake.check_equilibration_comprehensive_calls[0]
    assert comp_call["dump_file"] == str(kinetic_dir / "nvt_kinetic_stability.dump")
    # Rg/MSID/R_ee/torsion/P2/density_homogeneity/finite_size must read from npt_final's OWN
    # trajectory (struct_dump_file/struct_data_file), not nvt_kinetic_stability's fixed-volume
    # window -- only MSD/kinetic-trap/C(t) stay on dump_file/data_file above.
    assert comp_call["struct_dump_file"] == str(final_dir / "npt_final.dump")
    assert comp_call["struct_data_file"] == str(final_dir / "npt_final_out.data")
    assert comp_call["data_file"] == str(final_dir / "npt_final_out.data")
    gate_call = fake.enforce_equilibration_gate_calls[0]
    assert gate_call["melt_data"] == melt_data_path


# ─── do_thermal(): where the Tg staircase starts ──────────────────────────────────
#
# The sweep measures where a COOLING liquid stiffens, so it has to start from a liquid.
# The equilibration cooldown already wrote one at every waypoint on its way down; the
# alternative is reheating the finished final_T_K cell, which is not a ramp at all --
# _bracket_tg_start_temp's deck sets T_START and T_FINAL both to the candidate, a thermostat
# step change applied to a cell packed at its final_T_K density.


def _tg_start_params(tmp_path, **over):
    p = {"T_start_K": 600.0, "final_T_K": 300.0, "cool_block_dT_K": 25.0,
         "tg_start_data_path": None, "tg_start_T_K": None,
         "equil_data_path": str(tmp_path / "npt_final_out.data")}
    p.update(over)
    return p


def test_tg_sweep_starts_from_the_tagged_melt_cooled_cell(tmp_path):
    tagged = tmp_path / "cool_block_03_out.data"
    tagged.write_text("")
    p = _tg_start_params(tmp_path, tg_start_data_path=str(tagged), tg_start_T_K=610.0)

    def _never(*a, **k):
        raise AssertionError("reheat probe must not run when a tagged cell is available")

    result = rdr._select_tg_start_cell(None, {}, None, p)
    assert result["outcome"] == "MELT_COOLED_START"
    assert result["start_data_path"] == str(tagged)
    assert result["start_T_K"] == 610.0


def test_a_stale_tag_falls_back_to_reheating_rather_than_the_wrong_temperature(
        tmp_path, monkeypatch):
    """tg_t_high_K can be edited between the equilibration and thermal stages, or replayed from
    a frozen plan. The tagged file still exists, but at the OLD sweep top -- starting there
    would silently run the staircase from a different temperature than the deck declares."""
    tagged = tmp_path / "cool_block_09_out.data"
    tagged.write_text("")
    # Tagged at 480 K for a sweep that now starts at 600 K: more than one block adrift.
    p = _tg_start_params(tmp_path, tg_start_data_path=str(tagged), tg_start_T_K=480.0)
    monkeypatch.setattr(rdr, "_bracket_tg_start_temp",
                        lambda *a, **k: {"outcome": "PASS", "start_data_path": "probe.data"})

    result = rdr._select_tg_start_cell(None, {}, None, p)
    assert result["outcome"] == "PASS"
    assert result["stale_tg_start_tag_T_K"] == 480.0


def test_a_run_assessed_above_its_sweep_top_needs_no_probe(tmp_path):
    """A rubbery run whose final_T_K already sits at or above the staircase's first point: its
    npt_final IS an equilibrated cell there, so there is nothing to reheat and nothing tagged."""
    p = _tg_start_params(tmp_path, T_start_K=350.0, final_T_K=400.0)
    result = rdr._select_tg_start_cell(None, {}, None, p)
    assert result["outcome"] == "ASSESSED_ABOVE_SWEEP_TOP"
    assert result["start_data_path"] == p["equil_data_path"]


def test_no_tag_reheats(tmp_path, monkeypatch):
    """What a SMILES with an untrustworthy Tg estimate, or a legacy plan, lands on. The probe
    path is retained rather than deleted precisely for this case."""
    p = _tg_start_params(tmp_path)
    monkeypatch.setattr(rdr, "_bracket_tg_start_temp",
                        lambda *a, **k: {"outcome": "EXHAUSTED", "start_data_path": "probe.data"})
    result = rdr._select_tg_start_cell(None, {}, None, p)
    assert result["outcome"] == "EXHAUSTED"
    assert "stale_tg_start_tag_T_K" not in result


def test_a_tag_pointing_at_a_missing_file_reheats(tmp_path, monkeypatch):
    p = _tg_start_params(tmp_path, tg_start_data_path=str(tmp_path / "gone.data"),
                         tg_start_T_K=600.0)
    monkeypatch.setattr(rdr, "_bracket_tg_start_temp",
                        lambda *a, **k: {"outcome": "PASS", "start_data_path": "probe.data"})
    assert rdr._select_tg_start_cell(None, {}, None, p)["outcome"] == "PASS"


# ─── CampaignStageExecutor.execute(): STRUCTURAL_FAIL finding-code routing ─────────

def test_structural_fail_routes_to_cooling_verdict_not_a_passing_finite_size_string(
        tmp_path, monkeypatch):
    """detail["finite_size_verdict"] is "SIZE_PASS" -- a truthy string -- whenever finite size
    was merely *evaluated*, independent of whether it passed. A real UNDER_ANNEALED_COOLING
    halt with finite_size passing must still route to the cooling_verdict code, not fall into
    an `or`-chain trap that picks "SIZE_PASS" just because it's non-empty and comes first --
    that would hand RemedyRegistry a code with no registered remedy for a real, remediable
    finding."""
    from run_campaign import CampaignStageExecutor
    import run_campaign as rc

    halted_detail = {
        "verdict": "STRUCTURAL_FAIL", "finite_size_verdict": "SIZE_PASS",
        "cooling_verdict": "UNDER_ANNEALED_COOLING", "homogeneity_verdict": "HOMOG_PASS",
        "remedy_confidence": "high",
    }
    monkeypatch.setattr(rc, "do_equil_and_check", lambda args, cls, lammps: {
        "halted": True, "reason": "STRUCTURAL_FAIL", "detail": halted_detail,
    })

    attempt_dir = tmp_path / "attempt-0001"
    attempt_dir.mkdir()
    executor = CampaignStageExecutor(SimpleNamespace(engine_owned_recovery=False),
                                     {}, emc=None, lammps=None, plan_path="unused")
    context = {"attempt_dir": str(attempt_dir), "parameters": {}, "dependencies": {},
              "prior_attempts": []}

    result = executor.execute("equilibration", context)

    assert result.status == "remedy_required"
    assert result.findings[0].code == "UNDER_ANNEALED_COOLING"


def _write_prior_manifest(tmp_path, name, parameters, stage_checkpoints):
    manifest_path = tmp_path / f"{name}.json"
    manifest_path.write_text(json.dumps({
        "parameters": parameters,
        "outputs": {"stage_checkpoints": stage_checkpoints},
    }))
    return {"manifest": str(manifest_path)}


def test_equilibration_resume_from_anneal_hold_finds_its_checkpoint(tmp_path, monkeypatch):
    """_cooling (UNDER_ANNEALED_COOLING) sets equilibration_resume_from="anneal_hold" directly
    -- one of generate_equilibration_workflow's 8 fixed checkpoint names -- so the executor's
    job is a plain lookup in the prior attempt's own stage_checkpoints, no per-cycle delta
    computation (the retired eq_annealing_cycles concept no longer exists; annealing is one
    continuously-extendable hold, not a cycle count)."""
    import run_campaign as rc
    from run_campaign import CampaignStageExecutor

    captured = {}
    monkeypatch.setattr(rc, "do_equil_and_check", lambda args, cls, lammps: (
        captured.update(resume_from=getattr(args, "equil_resume_from", None),
                        data_path=getattr(args, "equil_resume_data_path", None))
        or {"halted": True, "reason": "STRUCTURAL_FAIL", "detail": {}}
    ))

    prior = _write_prior_manifest(
        tmp_path, "prior",
        parameters={"cool_block_hold_steps": 200000},
        stage_checkpoints={"anneal_hold": "/data/anneal_hold_out.data"},
    )

    executor = CampaignStageExecutor(SimpleNamespace(engine_owned_recovery=False),
                                     {}, emc=None, lammps=None, plan_path="unused")
    attempt_dir = tmp_path / "attempt-0002"
    attempt_dir.mkdir()
    context = {"attempt_dir": str(attempt_dir),
              "parameters": {"cool_block_hold_steps": 400000,
                             "equilibration_resume_from": "anneal_hold"},
              "dependencies": {}, "prior_attempts": [prior]}

    executor.execute("equilibration", context)

    assert captured["resume_from"] == "anneal_hold"
    assert captured["data_path"] == "/data/anneal_hold_out.data"


def test_equilibration_resume_from_missing_checkpoint_leaves_resume_unset(tmp_path, monkeypatch):
    """If the named checkpoint never actually ran in any prior attempt (nothing to resume
    from), the executor must not set equil_resume_from at all -- do_equil_and_check would then
    submit a from-scratch chain, which is the safe fallback, not a crash on a missing key."""
    import run_campaign as rc
    from run_campaign import CampaignStageExecutor

    captured = {}
    monkeypatch.setattr(rc, "do_equil_and_check", lambda args, cls, lammps: (
        captured.update(resume_from=getattr(args, "equil_resume_from", None))
        or {"halted": True, "reason": "STRUCTURAL_FAIL", "detail": {}}
    ))

    prior = _write_prior_manifest(
        tmp_path, "prior", parameters={},
        stage_checkpoints={"npt_densify": "/data/npt_densify_out.data"},
    )

    executor = CampaignStageExecutor(SimpleNamespace(engine_owned_recovery=False),
                                     {}, emc=None, lammps=None, plan_path="unused")
    attempt_dir = tmp_path / "attempt-0002"
    attempt_dir.mkdir()
    context = {"attempt_dir": str(attempt_dir),
              "parameters": {"equilibration_resume_from": "anneal_hold"},
              "dependencies": {}, "prior_attempts": [prior]}

    executor.execute("equilibration", context)

    assert captured["resume_from"] is None


def test_equilibration_resume_from_npt_production_finds_its_checkpoint(tmp_path, monkeypatch):
    import run_campaign as rc
    from run_campaign import CampaignStageExecutor

    captured = {}
    monkeypatch.setattr(rc, "do_equil_and_check", lambda args, cls, lammps: (
        captured.update(resume_from=getattr(args, "equil_resume_from", None),
                        data_path=getattr(args, "equil_resume_data_path", None))
        or {"halted": True, "reason": "UNDER_ANNEALED_COOLING", "detail": {}}
    ))

    prior = _write_prior_manifest(
        tmp_path, "prior", parameters={"npt_cool300_steps": 1000000},
        stage_checkpoints={"npt_production": "/data/npt_production_out.data"},
    )

    executor = CampaignStageExecutor(SimpleNamespace(engine_owned_recovery=False),
                                     {}, emc=None, lammps=None, plan_path="unused")
    attempt_dir = tmp_path / "attempt-0002"
    attempt_dir.mkdir()
    context = {"attempt_dir": str(attempt_dir),
              "parameters": {"npt_cool300_steps": 2000000,
                             "equilibration_resume_from": "npt_production"},
              "dependencies": {}, "prior_attempts": [prior]}

    executor.execute("equilibration", context)

    assert captured["resume_from"] == "npt_production"
    assert captured["data_path"] == "/data/npt_production_out.data"


def test_structural_fail_routes_to_real_finite_size_failure_code(tmp_path, monkeypatch):
    """A genuine finite-size failure must still win -- the fix must not overcorrect into
    ignoring finite_size_verdict altogether."""
    from run_campaign import CampaignStageExecutor
    import run_campaign as rc

    halted_detail = {
        "verdict": "STRUCTURAL_FAIL", "finite_size_verdict": "SIZE_MIN_IMAGE_VIOLATION",
        "cooling_verdict": None, "homogeneity_verdict": "HOMOG_PASS",
        "remedy_confidence": "high",
    }
    monkeypatch.setattr(rc, "do_equil_and_check", lambda args, cls, lammps: {
        "halted": True, "reason": "STRUCTURAL_FAIL", "detail": halted_detail,
    })

    attempt_dir = tmp_path / "attempt-0001"
    attempt_dir.mkdir()
    executor = CampaignStageExecutor(SimpleNamespace(engine_owned_recovery=False),
                                     {}, emc=None, lammps=None, plan_path="unused")
    context = {"attempt_dir": str(attempt_dir), "parameters": {}, "dependencies": {},
              "prior_attempts": []}

    result = executor.execute("equilibration", context)

    assert result.status == "remedy_required"
    assert result.findings[0].code == "SIZE_MIN_IMAGE_VIOLATION"


# ─── run_campaign_workflow() writes system_characterization_cache.json on acceptance ──────

def _stub_engine(result: dict):
    class _StubWorkflowEngine:
        def __init__(self, *a, **k):
            pass

        def run(self):
            return dict(result)

    return _StubWorkflowEngine


def _setup_workflow_fixture(tmp_path, monkeypatch, run_name="WCC_RUN"):
    """A minimal repo_root + run_plan.json sufficient to reach run_campaign_workflow()'s
    WorkflowEngine(...).run() call, with the heavy MCP server loads and WorkflowEngine itself
    stubbed out -- this test is about the cache-write WIRING, not stage execution."""
    import shutil
    (tmp_path / "orchestration").mkdir()
    shutil.copy(REPO_ROOT / "orchestration" / "decision_policy.json",
               tmp_path / "orchestration" / "decision_policy.json")
    plan = {"run_name": run_name, "polymer_class": "PHYC", "smiles": "*CC*",
           "properties": ["density"], "decided_params": {}, "decisions": [], "planned_stages": []}
    plan_path = tmp_path / "run_plan.json"
    plan_path.write_text(json.dumps(plan))
    monkeypatch.setattr(rdr, "_load_server_module", lambda *a, **k: SimpleNamespace())
    return plan_path


def test_run_campaign_workflow_writes_cache_on_acceptance(tmp_path, monkeypatch):
    plan_path = _setup_workflow_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(rdr, "WorkflowEngine", _stub_engine({"status": "accepted"}))

    import write_characterization_cache as wcc
    calls = []
    monkeypatch.setattr(wcc, "write_characterization_cache",
                        lambda run_name, **kw: calls.append((run_name, kw)))

    import ingest_internal_run_evidence as iire
    ingest_calls = []
    monkeypatch.setattr(iire, "ingest_from_completed_run",
                        lambda run_name, **kw: ingest_calls.append((run_name, kw)))

    result = rdr.run_campaign_workflow(plan_path, repo_root=tmp_path)

    assert result["status"] == "accepted"
    assert calls == [("WCC_RUN", {"repo_root": tmp_path})]
    assert ingest_calls == [("WCC_RUN", {"repo_root": tmp_path})]


def test_run_campaign_workflow_skips_cache_write_when_not_accepted(tmp_path, monkeypatch):
    plan_path = _setup_workflow_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(rdr, "WorkflowEngine", _stub_engine({"status": "failed"}))

    import write_characterization_cache as wcc
    calls = []
    monkeypatch.setattr(wcc, "write_characterization_cache",
                        lambda run_name, **kw: calls.append((run_name, kw)))

    import ingest_internal_run_evidence as iire
    ingest_calls = []
    monkeypatch.setattr(iire, "ingest_from_completed_run",
                        lambda run_name, **kw: ingest_calls.append((run_name, kw)))

    result = rdr.run_campaign_workflow(plan_path, repo_root=tmp_path)

    assert result["status"] == "failed"
    assert calls == []
    assert ingest_calls == []


def test_run_campaign_workflow_cache_write_failure_does_not_propagate(tmp_path, monkeypatch, capsys):
    plan_path = _setup_workflow_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(rdr, "WorkflowEngine", _stub_engine({"status": "accepted"}))

    import write_characterization_cache as wcc

    def _boom(run_name, **kw):
        raise RuntimeError("disk full")
    monkeypatch.setattr(wcc, "write_characterization_cache", _boom)

    import ingest_internal_run_evidence as iire
    monkeypatch.setattr(iire, "ingest_from_completed_run", lambda run_name, **kw: {"status": "written"})

    result = rdr.run_campaign_workflow(plan_path, repo_root=tmp_path)

    assert result["status"] == "accepted"  # the campaign result must survive a cache-write failure
    assert "WARNING" in capsys.readouterr().err


def test_run_campaign_workflow_evidence_ingest_failure_does_not_propagate(tmp_path, monkeypatch, capsys):
    # The two post-acceptance steps are independent failure domains: an evidence-ingest
    # crash must not affect the (already-successful) cache write, or the campaign result.
    plan_path = _setup_workflow_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(rdr, "WorkflowEngine", _stub_engine({"status": "accepted"}))

    import write_characterization_cache as wcc
    wcc_calls = []
    monkeypatch.setattr(wcc, "write_characterization_cache",
                        lambda run_name, **kw: wcc_calls.append((run_name, kw)))

    import ingest_internal_run_evidence as iire

    def _boom(run_name, **kw):
        raise RuntimeError("evidence store locked")
    monkeypatch.setattr(iire, "ingest_from_completed_run", _boom)

    result = rdr.run_campaign_workflow(plan_path, repo_root=tmp_path)

    assert result["status"] == "accepted"
    assert wcc_calls == [("WCC_RUN", {"repo_root": tmp_path})]  # cache write still ran
    assert "WARNING" in capsys.readouterr().err


# ─── Tg-sweep adaptive per-temperature sampling ───────────────────────────────
# _bracket_tg_start_temp (Phase 1: is T_start_K high enough?) and
# _run_tg_sweep_adaptive (Phase 2: is each temperature adequately sampled?) --
# see the plan file for the design this implements.

def _write_lammps_log(path, densities, append=False):
    """A minimal real LAMMPS-log-shaped thermo table -- parse_lammps_log (unmocked in these
    tests) reads this for real, exercising the real parsing/trend-check logic."""
    lines = ["   Step          Temp           Density"]
    for i, d in enumerate(densities):
        lines.append(f"      {i * 1000}            300.0         {d}")
    text = "\n".join(lines) + "\n"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a" if append else "w") as f:
        f.write(text)


class _FakeTgLammps:
    """Minimal in-process stand-in covering only what _bracket_tg_start_temp/
    _run_tg_sweep_adaptive call. Each generate_script call is remembered; the matching
    run_lammps_script call writes a real LAMMPS-log-shaped density trace (popped from a
    scripted per-job queue) to the log/data paths the real deck would have produced."""

    def __init__(self, density_queue, fail_on_call=None):
        self._density_queue = list(density_queue)
        self._pending = None
        self._call_n = 0
        self._fail_on_call = fail_on_call  # 1-indexed call number to simulate a run failure on

    def generate_script(self, template_name, data_file, output_script, velocity_seed, params):
        default_data = "npt_out.data" if template_name == "npt" else "tg_step_out.data"
        self._pending = {
            "log_file": params["LOG_FILE"],
            "log_append": bool(params.get("LOG_APPEND", False)),
            "write_data_file": params.get("WRITE_DATA_FILE", default_data),
        }
        return {"output_script": output_script}

    def run_lammps_script(self, script, work_dir, log_file, gpu_ids, mpi, engine,
                           data_file, lj_cutoff):
        self._call_n += 1
        p = self._pending
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        if self._fail_on_call == self._call_n:
            return {"run_id": f"run-{self._call_n}"}
        densities = self._density_queue.pop(0) if self._density_queue else [1.0] * 10
        _write_lammps_log(Path(work_dir) / p["log_file"], densities, append=p["log_append"])
        data_path = p["write_data_file"]
        (Path(data_path) if os.path.isabs(data_path) else Path(work_dir) / data_path).write_text("# fake\n")
        return {"run_id": f"run-{self._call_n}"}


@pytest.fixture
def tg_args_cls(tmp_path):
    args = _base_args("TGTEST1", "POXI", str(tmp_path / "plan.json"))
    args.data_path = str(tmp_path / "equil_out.data")
    args.work_dir = str(tmp_path / "thermal")
    args.gpu_ids = [0]
    args.mpi_ranks = 1
    args.engine = "gpu"
    args.velocity_seed = 12345
    cls = {
        "dt_fs": 1.0, "tg_rates_K_per_ns": [], "tg_t_step_K": 20, "tg_t_high_K": 440.0,
        "tg_t_low_K": 400.0, "tg_steps_per_t": 1000, "tg_min_steps_per_T": 1000,
        "electrostatics": "pppm", "P_equil_atm": 1.0, "thermostat_damp_fs": 100.0,
        "barostat_damp_fs": 1000.0, "cutoff_A": 12.0, "annealing_T_high_K": 700.0,
        "T_workflow_K": 300.0, "preferred_ff": "pcff",
        "tg_bracket_max_iters": 3, "tg_bracket_probe_steps": 1000,
        "tg_bracket_drift_threshold_pct": 0.5, "tg_per_t_max_extensions": 2,
        "tg_per_t_stability_pct": 1.0, "tg_per_t_min_n_eff": 5.0,
    }
    return args, cls


def _falling_densities(n=30, start=1.00, end=0.90):
    import random
    rng = random.Random(0)
    step = (end - start) / (n - 1)
    return [round(start + step * i + rng.uniform(-0.0005, 0.0005), 6) for i in range(n)]


def _flat_densities(n=30, value=0.95, noise=0.0005):
    import random
    rng = random.Random(1)
    return [round(value + rng.uniform(-noise, noise), 6) for i in range(n)]


def _rising_densities(n=30, start=0.90, end=0.95):
    return _falling_densities(n=n, start=start, end=end)


# ── Phase 1: _bracket_tg_start_temp ────────────────────────────────────────────

def _patch_wait_for_run(monkeypatch):
    """wait_for_run() polls lammps.watch_run(), which _FakeTgLammps doesn't implement --
    patch it to read status straight off the fake's own bookkeeping instead."""
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: (
        {"status": "failed"} if run_id == f"run-{lammps._fail_on_call}" else {"status": "completed"}
    ))


def test_bracket_first_candidate_melt_like_passes_unchanged(tg_args_cls, monkeypatch):
    _patch_wait_for_run(monkeypatch)
    args, cls = tg_args_cls
    p = resolve_stage_params("tg", args, cls)
    lammps = _FakeTgLammps(density_queue=[_falling_densities()])

    result = _bracket_tg_start_temp(args, cls, lammps, p)

    assert result["outcome"] == "PASS"
    assert result["T_start_K"] == p["T_start_K"]
    assert len(result["iterations"]) == 1


def test_bracket_fail_then_pass_raises_candidate(tg_args_cls, monkeypatch):
    _patch_wait_for_run(monkeypatch)
    args, cls = tg_args_cls
    p = resolve_stage_params("tg", args, cls)
    lammps = _FakeTgLammps(density_queue=[_rising_densities(), _falling_densities()])

    result = _bracket_tg_start_temp(args, cls, lammps, p)

    assert result["outcome"] == "PASS"
    assert result["T_start_K"] == p["T_start_K"] + 2 * p["T_step_K"]
    assert len(result["iterations"]) == 2
    assert result["iterations"][0]["melt_like"] is False
    assert result["iterations"][1]["melt_like"] is True


def test_bracket_exhausts_and_clamps_at_ceiling(tg_args_cls, monkeypatch):
    _patch_wait_for_run(monkeypatch)
    args, cls = tg_args_cls
    cls["annealing_T_high_K"] = p_ceiling = cls["tg_t_high_K"] + 2 * cls["tg_t_step_K"]
    p = resolve_stage_params("tg", args, cls)
    lammps = _FakeTgLammps(density_queue=[_rising_densities()] * 5)  # always fails

    result = _bracket_tg_start_temp(args, cls, lammps, p)

    assert result["outcome"] == "EXHAUSTED"
    assert result["T_start_K"] <= p_ceiling
    assert len(result["iterations"]) == p["tg_bracket_max_iters"]


def test_bracket_run_failure_is_advisory_not_raising(tg_args_cls, monkeypatch):
    _patch_wait_for_run(monkeypatch)
    args, cls = tg_args_cls
    p = resolve_stage_params("tg", args, cls)
    lammps = _FakeTgLammps(density_queue=[_falling_densities()], fail_on_call=1)

    result = _bracket_tg_start_temp(args, cls, lammps, p)

    assert result["outcome"] == "PROBE_FAILED"
    assert result["T_start_K"] == p["T_start_K"]


# ── Phase 2: _run_tg_sweep_adaptive ────────────────────────────────────────────

def test_sweep_all_points_stable_no_extensions(tg_args_cls, monkeypatch):
    _patch_wait_for_run(monkeypatch)
    args, cls = tg_args_cls
    p = resolve_stage_params("tg", args, cls)
    # 3 waypoints (440, 420, 400) at tg_t_step_K=20 -- one flat, stable series each.
    lammps = _FakeTgLammps(density_queue=[_flat_densities() for _ in range(3)])

    result = _run_tg_sweep_adaptive(args, cls, lammps, p, p["equil_data_path"])

    assert result["outcome"] == "COMPLETE"
    assert len(result["per_t"]) == 3
    assert [pt["T_K"] for pt in result["per_t"]] == [440.0, 420.0, 400.0]
    assert all(pt["extensions_used"] == 0 and pt["outcome"] == "PASS" for pt in result["per_t"])


def test_sweep_one_point_needs_one_extension(tg_args_cls, monkeypatch):
    _patch_wait_for_run(monkeypatch)
    args, cls = tg_args_cls
    p = resolve_stage_params("tg", args, cls)
    # First waypoint: unstable (rising) hold, then a flat hold on its extension. Remaining
    # two waypoints pass on the first try.
    lammps = _FakeTgLammps(density_queue=[
        _rising_densities(), _flat_densities(), _flat_densities(), _flat_densities(),
    ])

    result = _run_tg_sweep_adaptive(args, cls, lammps, p, p["equil_data_path"])

    assert result["outcome"] == "COMPLETE"
    assert len(result["per_t"]) == 3
    assert result["per_t"][0]["extensions_used"] == 1
    assert result["per_t"][0]["outcome"] == "PASS"
    assert result["per_t"][1]["extensions_used"] == 0
    assert result["per_t"][2]["extensions_used"] == 0


def test_sweep_point_exhausts_extension_cap_and_continues(tg_args_cls, monkeypatch):
    _patch_wait_for_run(monkeypatch)
    args, cls = tg_args_cls
    p = resolve_stage_params("tg", args, cls)
    # First waypoint never stabilizes across its base attempt + 2 extensions (cap=2);
    # remaining waypoints pass on the first try.
    lammps = _FakeTgLammps(density_queue=[
        _rising_densities(), _rising_densities(), _rising_densities(),
        _flat_densities(), _flat_densities(),
    ])

    result = _run_tg_sweep_adaptive(args, cls, lammps, p, p["equil_data_path"])

    assert len(result["per_t"]) == 3
    assert result["per_t"][0]["extensions_used"] == p["tg_per_t_max_extensions"]
    assert result["per_t"][0]["outcome"] == "EXHAUSTED"
    assert result["per_t"][1]["outcome"] == "PASS"


def test_sweep_job_failure_is_advisory_and_continues(tg_args_cls, monkeypatch):
    _patch_wait_for_run(monkeypatch)
    args, cls = tg_args_cls
    p = resolve_stage_params("tg", args, cls)
    lammps = _FakeTgLammps(density_queue=[_flat_densities(), _flat_densities()], fail_on_call=1)

    result = _run_tg_sweep_adaptive(args, cls, lammps, p, p["equil_data_path"])

    assert len(result["per_t"]) == 3
    assert result["per_t"][0]["outcome"] == "PROBE_FAILED"
    assert result["per_t"][1]["outcome"] == "PASS"


# ── Executor wiring ─────────────────────────────────────────────────────────

def test_thermal_dispatch_passes_equil_density_when_present(tmp_path, monkeypatch):
    from run_campaign import CampaignStageExecutor
    import run_campaign as rc

    calls = []
    monkeypatch.setattr(rc, "do_thermal",
                        lambda args, cls, lammps, equil_density_gcm3=None:
                        calls.append(equil_density_gcm3) or {"per_rate": []})

    attempt_dir = tmp_path / "attempt-0001"
    attempt_dir.mkdir()
    executor = CampaignStageExecutor(SimpleNamespace(engine_owned_recovery=False),
                                     {}, emc=None, lammps=None, plan_path="unused")
    context = {"attempt_dir": str(attempt_dir), "parameters": {},
              "dependencies": {"equilibration": {"outputs": {"density_gcm3": 1.05}}},
              "prior_attempts": []}

    executor.execute("thermal", context)

    assert calls == [1.05]


def test_thermal_dispatch_passes_none_when_equil_density_absent(tmp_path, monkeypatch):
    from run_campaign import CampaignStageExecutor
    import run_campaign as rc

    calls = []
    monkeypatch.setattr(rc, "do_thermal",
                        lambda args, cls, lammps, equil_density_gcm3=None:
                        calls.append(equil_density_gcm3) or {"per_rate": []})

    attempt_dir = tmp_path / "attempt-0001"
    attempt_dir.mkdir()
    executor = CampaignStageExecutor(SimpleNamespace(engine_owned_recovery=False),
                                     {}, emc=None, lammps=None, plan_path="unused")
    context = {"attempt_dir": str(attempt_dir), "parameters": {},
              "dependencies": {"equilibration": {"outputs": {}}},
              "prior_attempts": []}

    executor.execute("thermal", context)

    assert calls == [None]


# ── Bulk modulus: _bm_point_adaptive_extend ─────────────────────────────────

def _write_bm_log(path, volumes, append=False):
    """A minimal real LAMMPS-log-shaped thermo table with a Volume column --
    parse_lammps_log (unmocked in these tests) reads this for real."""
    lines = ["   Step          Temp           Volume"]
    for i, v in enumerate(volumes):
        lines.append(f"      {i * 1000}            300.0         {v}")
    text = "\n".join(lines) + "\n"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a" if append else "w") as f:
        f.write(text)


class _FakeBmExtLammps:
    """Stand-in for _bm_point_adaptive_extend's extension-hold calls (generate_script +
    run_lammps_script against the "npt" template) only -- the initial hold's own log/data are
    pre-written directly by each test, mirroring do_mechanical's real flow where
    run_bulk_modulus_series already produced them before this helper is ever called."""

    def __init__(self, volume_queue, fail_on_call=None):
        self._volume_queue = list(volume_queue)
        self._pending = None
        self._call_n = 0
        self._fail_on_call = fail_on_call

    def generate_script(self, template_name, data_file, output_script, velocity_seed, params):
        self._pending = {
            "log_file": params["LOG_FILE"],
            "log_append": bool(params.get("LOG_APPEND", False)),
            "write_data_file": params["WRITE_DATA_FILE"],
        }
        return {"output_script": output_script}

    def run_lammps_script(self, script, work_dir, log_file, gpu_ids, mpi, engine,
                           data_file, lj_cutoff):
        self._call_n += 1
        p = self._pending
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        if self._fail_on_call == self._call_n:
            return {"run_id": f"run-{self._call_n}"}
        volumes = self._volume_queue.pop(0) if self._volume_queue else [8000.0] * 10
        _write_bm_log(p["log_file"], volumes, append=p["log_append"])
        Path(p["write_data_file"]).write_text("# fake\n")
        return {"run_id": f"run-{self._call_n}"}


@pytest.fixture
def bm_args_cls(tmp_path):
    args = _base_args("BMTEST1", "POXI", str(tmp_path / "plan.json"))
    args.data_path = str(tmp_path / "equil_out.data")
    args.work_dir = str(tmp_path / "mechanical")
    args.gpu_ids = [0]
    args.mpi_ranks = 1
    args.engine = "gpu"
    args.velocity_seed = 12345
    cls = {
        "dt_fs": 1.0, "bm_pressures_atm": [0, 1000, 3000], "bm_npt_steps": 1000,
        "bm_temperature_K": 300.0, "bm_thermo_freq": 100, "electrostatics": "pppm",
        "thermostat_damp_fs": 100.0, "barostat_damp_fs": 1000.0, "cutoff_A": 12.0,
        "preferred_ff": "pcff",
        "bm_per_point_max_extensions": 2, "bm_per_point_stability_pct": 1.0,
        "bm_per_point_min_n_eff": 5.0,
    }
    return args, cls


def _flat_volumes(n=30, value=8000.0, noise=4.0):
    import random
    rng = random.Random(2)
    return [round(value + rng.uniform(-noise, noise), 4) for _ in range(n)]


def _rising_volumes(n=30, start=7600.0, end=8400.0):
    import random
    rng = random.Random(3)
    step = (end - start) / (n - 1)
    return [round(start + step * i + rng.uniform(-4.0, 4.0), 4) for i in range(n)]


def _patch_wait_for_run_bm(monkeypatch):
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: (
        {"status": "failed"} if run_id == f"run-{lammps._fail_on_call}" else {"status": "completed"}
    ))


def test_bm_point_stable_first_hold_passes_no_extension(bm_args_cls, tmp_path):
    args, cls = bm_args_cls
    p = resolve_stage_params("murnaghan", args, cls)
    log_path = str(tmp_path / "bm_P0.log")
    data_path = str(tmp_path / "bm_P0_out.data")
    _write_bm_log(log_path, _flat_volumes())
    Path(data_path).write_text("# fake\n")
    lammps = _FakeBmExtLammps(volume_queue=[])

    result = _bm_point_adaptive_extend(cls, lammps, p, 0.0, str(tmp_path), log_path, data_path,
                                        gpu_per_run=1, run_name=args.run_name)

    assert result["outcome"] == "PASS"
    assert result["extensions_used"] == 0
    assert result["final_data_path"] == data_path
    assert lammps._call_n == 0  # no extension submitted -- no wasted compute in the common case


def test_bm_point_unstable_first_hold_passes_after_one_extension(bm_args_cls, tmp_path, monkeypatch):
    _patch_wait_for_run_bm(monkeypatch)
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [0], "run": run_name} if action == "claim" else {"released": True}))
    args, cls = bm_args_cls
    p = resolve_stage_params("murnaghan", args, cls)
    log_path = str(tmp_path / "bm_P0.log")
    data_path = str(tmp_path / "bm_P0_out.data")
    _write_bm_log(log_path, _rising_volumes())
    Path(data_path).write_text("# fake\n")
    lammps = _FakeBmExtLammps(volume_queue=[_flat_volumes()])

    result = _bm_point_adaptive_extend(cls, lammps, p, 0.0, str(tmp_path), log_path, data_path,
                                        gpu_per_run=1, run_name=args.run_name)

    assert result["outcome"] == "PASS"
    assert result["extensions_used"] == 1
    assert result["final_data_path"] == str(Path(tmp_path) / "ext_1_out.data")
    # the appended log now holds both the original (rising) rows and the extension's own rows,
    # each as its own thermo table (parse_lammps_log concatenates multiple tables in one file --
    # a real LAMMPS log looks the same across multiple `run` commands).
    logged = Path(log_path).read_text()
    assert logged.count("Volume") == 2


def test_bm_point_exhausts_extension_cap_without_stabilizing(bm_args_cls, tmp_path, monkeypatch):
    _patch_wait_for_run_bm(monkeypatch)
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [0], "run": run_name} if action == "claim" else {"released": True}))
    args, cls = bm_args_cls
    p = resolve_stage_params("murnaghan", args, cls)
    log_path = str(tmp_path / "bm_P0.log")
    data_path = str(tmp_path / "bm_P0_out.data")
    _write_bm_log(log_path, _rising_volumes())
    Path(data_path).write_text("# fake\n")
    lammps = _FakeBmExtLammps(volume_queue=[_rising_volumes(), _rising_volumes()])

    result = _bm_point_adaptive_extend(cls, lammps, p, 0.0, str(tmp_path), log_path, data_path,
                                        gpu_per_run=1, run_name=args.run_name)

    assert result["outcome"] == "EXHAUSTED"
    assert result["extensions_used"] == p["bm_per_point_max_extensions"]


def test_bm_point_extension_run_failure_is_advisory(bm_args_cls, tmp_path, monkeypatch):
    _patch_wait_for_run_bm(monkeypatch)
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [0], "run": run_name} if action == "claim" else {"released": True}))
    args, cls = bm_args_cls
    p = resolve_stage_params("murnaghan", args, cls)
    log_path = str(tmp_path / "bm_P0.log")
    data_path = str(tmp_path / "bm_P0_out.data")
    _write_bm_log(log_path, _rising_volumes())
    Path(data_path).write_text("# fake\n")
    lammps = _FakeBmExtLammps(volume_queue=[_flat_volumes()], fail_on_call=1)

    result = _bm_point_adaptive_extend(cls, lammps, p, 0.0, str(tmp_path), log_path, data_path,
                                        gpu_per_run=1, run_name=args.run_name)

    assert result["outcome"] == "PROBE_FAILED"
    assert result["extensions_used"] == 1
    assert result["final_data_path"] == data_path  # prior good data untouched, not the failed ext


# ── Summary dispatch: cross-attempt-directory paths (PEG1 run_summary bug fix) ─────────────

def test_summary_dispatch_threads_equilibration_and_mechanical_json_paths(tmp_path, monkeypatch):
    """generate_run_summary.py can only find equilibration.json/mechanical.json when the caller
    passes their real (cross-attempt-directory) paths explicitly -- do_equil_and_check/
    do_mechanical surface those paths as equilibration_json_path/mechanical_json_path in their
    own outputs dicts; CampaignStageExecutor.execute("summary", ...) must thread both through to
    do_summary, which must thread them into generate_run_summary's call. Locks in the fix without
    submitting any real simulation."""
    from run_campaign import CampaignStageExecutor
    import run_campaign as rc

    calls = []
    monkeypatch.setattr(rc, "do_summary",
                        lambda args, cls, lammps, is_glassy, thermal, equil_verdict, raw_dir,
                               equil_result=None, mechanical_result=None:
                        calls.append((equil_result, mechanical_result)) or {})

    attempt_dir = tmp_path / "attempt-0001"
    attempt_dir.mkdir()
    executor = CampaignStageExecutor(SimpleNamespace(engine_owned_recovery=False),
                                     {}, emc=None, lammps=None, plan_path="unused")
    context = {"attempt_dir": str(attempt_dir), "parameters": {},
              "dependencies": {
                  "equilibration": {"outputs": {"equil_verdict": "PASS",
                                                "equilibration_json_path": "/eq/attempt/raw/equilibration.json"}},
                  "thermal": {"outputs": {"is_glassy": False}},
                  "mechanical": {"outputs": {"mechanical_json_path": "/mech/attempt/raw/mechanical.json"}},
              },
              "prior_attempts": []}

    executor.execute("summary", context)

    assert len(calls) == 1
    equil_result, mechanical_result = calls[0]
    assert equil_result["equilibration_json_path"] == "/eq/attempt/raw/equilibration.json"
    assert mechanical_result["mechanical_json_path"] == "/mech/attempt/raw/mechanical.json"


class _FakeBmSeriesLammps(_FakeBmExtLammps):
    """Combines run_bulk_modulus_series (do_mechanical's initial per-point call) with the
    generate_script/run_lammps_script pair _bm_point_adaptive_extend uses for any extension --
    exercises do_mechanical's own wiring (path reconstruction, point_status/pressure_points.json
    bookkeeping), not just the helper in isolation."""

    def __init__(self, initial_volumes_by_pressure, extension_volume_queue=None):
        super().__init__(volume_queue=extension_volume_queue or [])
        self._initial_volumes_by_pressure = initial_volumes_by_pressure
        self.last_extract_call = None

    def run_bulk_modulus_series(self, data_file, work_dir, pressures_atm, temp_K, run_name,
                                 gpu_ids, mpi, velocity_seed, npt_steps, dt_fs, thermo_freq,
                                 thermostat_damp_fs, barostat_damp_fs, use_long_range,
                                 use_trappe, use_pcff, use_opls, engine):
        pressure = int(pressures_atm[0])
        tag = f"bm_P{pressure}"
        stage_dir = Path(work_dir) / tag
        log_path = stage_dir / f"{tag}.log"
        data_path = stage_dir / f"{tag}_out.data"
        _write_bm_log(str(log_path), self._initial_volumes_by_pressure[pressure])
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text("# fake\n")
        return {"status": "submitted", "chain_id": f"chain-{tag}", "log_files": [str(log_path)]}

    def extract_bulk_modulus_murnaghan(self, log_files, pressures_atm, output_dir, graphs_dir,
                                        npt_prod_log):
        self.last_extract_call = {"log_files": list(log_files), "pressures_atm": list(pressures_atm)}
        return {"run_id": None, "bm_gate_verdict": "BM_REPORTABLE", "bulk_modulus_GPa": 3.0}


def test_do_mechanical_point_extension_flows_into_analysis_call(bm_args_cls, monkeypatch):
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: {"status": "completed"})
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [0], "run": run_name} if action == "claim" else {"released": True}))
    args, cls = bm_args_cls
    lammps = _FakeBmSeriesLammps(
        initial_volumes_by_pressure={
            0: _rising_volumes(), 1000: _flat_volumes(), 3000: _flat_volumes(),
        },
        extension_volume_queue=[_flat_volumes()],
    )

    result = rdr.do_mechanical(args, cls, lammps, is_glassy=False, npt_prod_data_path=args.data_path)

    assert result["bm_gate_verdict"] == "BM_REPORTABLE"
    # The P=0 point needed one extension; its accepted log path is unchanged (the extension
    # appends to the same file run_bulk_modulus_series produced), so extract_bulk_modulus_murnaghan
    # still received exactly 3 logs, one per pressure -- zero contract change downstream.
    assert len(lammps.last_extract_call["pressures_atm"]) == 3
    assert set(lammps.last_extract_call["pressures_atm"]) == {0, 1000, 3000}

    pressure_points_path = Path(args.work_dir) / "pressure_points.json"
    saved = json.loads(pressure_points_path.read_text())["points"]
    by_pressure = {v["pressure_atm"]: v for v in saved.values()}
    assert by_pressure[0]["stability_check"]["extensions_used"] == 1
    assert by_pressure[0]["stability_check"]["outcome"] == "PASS"
    assert by_pressure[1000]["stability_check"]["extensions_used"] == 0
    assert by_pressure[3000]["stability_check"]["extensions_used"] == 0


# ─── _anneal_hold_adaptive_extend(): MSID-convergence gate (PEG1 remedy, Phase 0-validated) ──

class _FakeAnnealGateLammps:
    """Stand-in for _anneal_hold_adaptive_extend's own calls: check_equilibration_comprehensive
    (a scripted queue of large-s MSID probe results) and generate_equilibration_workflow/
    run_lammps_chain for each extend_only=True continuation (routed through the real
    _submit_equil_chain, exactly as production code calls it)."""

    def __init__(self, probe_queue):
        self._probe_queue = list(probe_queue)
        self._ext_n = 0
        self.check_equilibration_comprehensive_calls = []
        self.generate_equilibration_workflow_calls = []

    def check_equilibration_comprehensive(self, **kwargs):
        self.check_equilibration_comprehensive_calls.append(kwargs)
        return self._probe_queue.pop(0)

    def generate_equilibration_workflow(self, **kwargs):
        self.generate_equilibration_workflow_calls.append(kwargs)
        self._ext_n += 1
        stage_dir = f"/fake/anneal_hold_ext{self._ext_n}"
        stage = {"name": "anneal_hold", "work_dir": stage_dir,
                 "output_data": f"{stage_dir}/anneal_hold_out.data",
                 "output_restart": f"{stage_dir}/anneal_hold_out.restart",
                 "params": {"LOG_FILE": "anneal_hold.log", "DUMP_FILE": "anneal_hold.dump",
                            "DUMP_FREQ": 1000,
                            "N_STEPS": kwargs.get("anneal_check_every_steps")}}
        return {"status": "success", "stages": [stage], "run_order": ["anneal_hold"]}

    def run_lammps_chain(self, **kwargs):
        return {"chain_id": f"chain-{self._ext_n}"}


def _msid_probe(slope, gaussian_pass, mean_rg_A=None):
    return {"status": "success",
            "chain": {"msid": {"large_s": {"slope": slope, "gaussian_pass": gaussian_pass}},
                      "rg": {"mean_Rg_A": mean_rg_A}}}


@pytest.fixture
def anneal_gate_args_cls():
    args = _base_args("ANNEALGATE1", "POXI", "/fake/plan.json")
    args.gpu_ids = [1]
    args.mpi_ranks = 1
    args.engine = "gpu"
    args.velocity_seed = 777
    args.data_path = "/fake/original/cell.data"
    cls = {
        "dt_fs": 1.0, "annealing_T_high_K": 580.0, "electrostatics": "pppm",
        "thermostat_damp_fs": 100.0, "barostat_damp_fs": 1000.0, "cutoff_A": 9.5,
        "preferred_ff": "pcff",
        "anneal_hold_max_extensions": 2, "anneal_hold_stability_pct": 5.0,
        "anneal_hold_extend_ns": 2.5,
    }
    p = resolve_stage_params("equil", args, cls)
    return args, cls, p


def _initial_anneal_hold_stage():
    return {"name": "anneal_hold", "work_dir": "/fake/anneal_hold",
            "output_data": "/fake/anneal_hold/anneal_hold_out.data",
            "output_restart": "/fake/anneal_hold/anneal_hold_out.restart",
            "params": {"LOG_FILE": "anneal_hold.log", "DUMP_FILE": "anneal_hold.dump",
                       "DUMP_FREQ": 1000, "N_STEPS": 1000000}}


def test_anneal_hold_gate_passes_on_first_probe_zero_extensions(anneal_gate_args_cls):
    args, cls, p = anneal_gate_args_cls
    lammps = _FakeAnnealGateLammps(probe_queue=[_msid_probe(0.95, True)])

    result = _anneal_hold_adaptive_extend(args, cls, lammps, p, _initial_anneal_hold_stage(),
                                          backbone_types=[1, 4, 5], gpu_per_run=1)

    assert result["outcome"] == "PASS"
    assert result["extensions_used"] == 0
    assert result["anneal_hold_data_path"] == "/fake/anneal_hold/anneal_hold_out.data"
    assert lammps.generate_equilibration_workflow_calls == []  # no extension submitted


def test_anneal_hold_gate_stabilizes_via_slope_diff_after_extension(anneal_gate_args_cls, monkeypatch):
    args, cls, p = anneal_gate_args_cls
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: {"status": "completed"})
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [1], "run": run_name} if action == "claim" else {"released": True}))
    # Two probes below gaussian_pass (|slope-1|>0.20) but their relative difference (~1.4%) is
    # comfortably under the 5% anneal_hold_stability_pct -- the STABLE stop condition must fire
    # from the pairwise slope comparison alone, independent of gaussian_pass ever being True.
    # (Mirrors PEG1 Phase 0's own 6.0/6.2/6.3ns plateau: 0.923/0.915/0.901, ~1-2.5% jitter.)
    lammps = _FakeAnnealGateLammps(probe_queue=[_msid_probe(0.663, False, mean_rg_A=18.2),
                                                 _msid_probe(0.672, False, mean_rg_A=18.5)])

    result = _anneal_hold_adaptive_extend(args, cls, lammps, p, _initial_anneal_hold_stage(),
                                          backbone_types=[1, 4, 5], gpu_per_run=1)

    assert result["outcome"] == "STABLE"
    assert result["extensions_used"] == 1
    assert result["slope_history"] == [0.663, 0.672]
    assert result["anneal_hold_data_path"] == "/fake/anneal_hold_ext1/anneal_hold_out.data"
    # Rg rides along as a free side-observation from the same probe call -- advisory only, never
    # part of the stop condition.
    assert [h["mean_rg_A"] for h in result["probe_history"]] == [18.2, 18.5]
    # extend_only continuation of anneal_hold's OWN restart, not a fresh stage
    ext_call = lammps.generate_equilibration_workflow_calls[0]
    assert ext_call["extend_only"] is True
    assert ext_call["base_stage_name"] == "anneal_hold"
    assert ext_call["extend_ensemble"] == "nvt"
    assert ext_call["restart_file"] == "/fake/anneal_hold/anneal_hold_out.restart"
    # Regression (real PEG1_gate_validation attempt-0001 failure, 2026-08-30): generate_
    # equilibration_workflow's own unconditional `max_temp >= temp + anneal_margin_K` gate runs
    # BEFORE its extend_only branch (which hardcodes T_START=T_FINAL=max_temp for
    # base_stage_name="anneal_hold" regardless of the `temp` argument anyway) -- passing
    # T_anneal_high_K as `temp` sets temp==max_temp, which can never clear a positive margin
    # over itself. `temp` must stay strictly below `max_temp` here.
    assert ext_call["temp"] < ext_call["max_temp"]


def test_anneal_hold_gate_exhausts_cap_without_stabilizing(anneal_gate_args_cls, monkeypatch):
    args, cls, p = anneal_gate_args_cls
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: {"status": "completed"})
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [1], "run": run_name} if action == "claim" else {"released": True}))
    # Each probe moves the slope a lot (never gaussian_pass, never within stability_pct of the
    # last one) -- the loop must stop at the cap (2), not run forever.
    lammps = _FakeAnnealGateLammps(probe_queue=[
        _msid_probe(0.60, False), _msid_probe(0.70, False), _msid_probe(0.80, False),
    ])

    result = _anneal_hold_adaptive_extend(args, cls, lammps, p, _initial_anneal_hold_stage(),
                                          backbone_types=[1, 4, 5], gpu_per_run=1)

    assert result["outcome"] == "EXHAUSTED"
    assert result["extensions_used"] == p["anneal_hold_max_extensions"] == 2
    assert len(lammps.generate_equilibration_workflow_calls) == 2


def test_anneal_hold_gate_rg_veto_defers_stable_until_rg_settles(anneal_gate_args_cls, monkeypatch):
    args, cls, p = anneal_gate_args_cls
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: {"status": "completed"})
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [1], "run": run_name} if action == "claim" else {"released": True}))
    # Probe 1->2: slope moves 0.833% (well under the 5% anneal_hold_stability_pct -- would call
    # STABLE on its own), but mean_Rg_A jumps 15.0->19.0 (26.7%, over the 10% default
    # anneal_hold_rg_veto_pct) -- a flat MSID slope isn't proof the chain has explored its
    # conformational space if Rg is still moving that much. The veto must defer STABLE and force
    # another extension. Probe 2->3: both slope (0.496%) AND Rg (1.58%) settle -- STABLE fires.
    lammps = _FakeAnnealGateLammps(probe_queue=[
        _msid_probe(0.600, False, mean_rg_A=15.0),
        _msid_probe(0.605, False, mean_rg_A=19.0),
        _msid_probe(0.608, False, mean_rg_A=19.3),
    ])

    result = _anneal_hold_adaptive_extend(args, cls, lammps, p, _initial_anneal_hold_stage(),
                                          backbone_types=[1, 4, 5], gpu_per_run=1)

    assert result["outcome"] == "STABLE"
    assert result["extensions_used"] == 2  # one extra extension forced by the veto
    assert result["rg_history"] == [15.0, 19.0, 19.3]
    assert result["rg_veto_triggered"] is True
    # the veto is recorded on the specific probe where it fired, not a global-only flag
    assert result["probe_history"][1].get("rg_veto") is True
    assert "rg_veto" not in result["probe_history"][0]
    assert "rg_veto" not in result["probe_history"][2]


def test_anneal_hold_gate_rg_veto_still_bounded_by_extension_cap(anneal_gate_args_cls, monkeypatch):
    args, cls, p = anneal_gate_args_cls
    cls["anneal_hold_max_extensions"] = 1
    p = resolve_stage_params("equil", args, cls)
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: {"status": "completed"})
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [1], "run": run_name} if action == "claim" else {"released": True}))
    # Slope stabilizes immediately but Rg keeps drifting past the veto threshold -- the veto is
    # advisory, not a second hard AND-condition: once the (now lowered) extension cap is hit, the
    # loop must still stop (EXHAUSTED), not extend forever chasing Rg convergence.
    lammps = _FakeAnnealGateLammps(probe_queue=[
        _msid_probe(0.600, False, mean_rg_A=15.0),
        _msid_probe(0.605, False, mean_rg_A=19.0),
    ])

    result = _anneal_hold_adaptive_extend(args, cls, lammps, p, _initial_anneal_hold_stage(),
                                          backbone_types=[1, 4, 5], gpu_per_run=1)

    assert result["outcome"] == "EXHAUSTED"
    assert result["extensions_used"] == 1
    assert result["rg_veto_triggered"] is True


def test_anneal_hold_gate_missing_rg_fails_open_on_stable(anneal_gate_args_cls, monkeypatch):
    args, cls, p = anneal_gate_args_cls
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: {"status": "completed"})
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [1], "run": run_name} if action == "claim" else {"released": True}))
    # Rg is an optional side-observation (check_equilibration_comprehensive can omit/fail to
    # compute it) -- a missing value must never block the pairwise-slope STABLE stop condition.
    lammps = _FakeAnnealGateLammps(probe_queue=[_msid_probe(0.663, False, mean_rg_A=None),
                                                 _msid_probe(0.672, False, mean_rg_A=None)])

    result = _anneal_hold_adaptive_extend(args, cls, lammps, p, _initial_anneal_hold_stage(),
                                          backbone_types=[1, 4, 5], gpu_per_run=1)

    assert result["outcome"] == "STABLE"
    assert result["rg_veto_triggered"] is False


def test_anneal_hold_gate_extension_failure_is_advisory(anneal_gate_args_cls, monkeypatch):
    args, cls, p = anneal_gate_args_cls
    # Phase 0 (PEG1) observed real extension-run crashes (PPPM out-of-range atoms;
    # cudaErrorIllegalAddress) -- the gate must fall back to the last good restart/data and
    # stop, not treat this as fatal (the caller still proceeds to chain 2 either way).
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: {"status": "failed"})
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [1], "run": run_name} if action == "claim" else {"released": True}))
    lammps = _FakeAnnealGateLammps(probe_queue=[_msid_probe(0.663, False)])

    result = _anneal_hold_adaptive_extend(args, cls, lammps, p, _initial_anneal_hold_stage(),
                                          backbone_types=[1, 4, 5], gpu_per_run=1)

    assert result["outcome"] == "EXTENSION_FAILED"
    assert result["extensions_used"] == 0  # the failed attempt never counted as a real extension
    # last GOOD data/restart untouched -- not the failed extension's (nonexistent) output
    assert result["anneal_hold_data_path"] == "/fake/anneal_hold/anneal_hold_out.data"


def test_anneal_hold_gate_probe_failure_is_advisory(anneal_gate_args_cls):
    args, cls, p = anneal_gate_args_cls
    lammps = _FakeAnnealGateLammps(probe_queue=[{"status": "failed", "error": "log unparseable"}])

    result = _anneal_hold_adaptive_extend(args, cls, lammps, p, _initial_anneal_hold_stage(),
                                          backbone_types=[1, 4, 5], gpu_per_run=1)

    assert result["outcome"] == "PROBE_FAILED"
    assert result["extensions_used"] == 0


def test_record_anneal_hold_convergence_merges_into_equilibration_json(tmp_path):
    output_dir = tmp_path / "raw"
    output_dir.mkdir()
    eq_json = output_dir / "equilibration.json"
    eq_json.write_text(json.dumps({"density": {"plateau_density_mean": 1.18}}))

    gate_result = {"outcome": "PASS", "extensions_used": 1, "slope_history": [0.849, 0.923],
                   "anneal_hold_stage": {"name": "anneal_hold", "work_dir": "/fake"},
                   "anneal_hold_data_path": "/fake/anneal_hold_out.data"}
    _record_anneal_hold_convergence(str(output_dir), gate_result)

    merged = json.loads(eq_json.read_text())
    assert merged["density"]["plateau_density_mean"] == 1.18  # prior section preserved
    assert merged["anneal_hold_convergence"]["outcome"] == "PASS"
    assert merged["anneal_hold_convergence"]["extensions_used"] == 1
    assert "anneal_hold_stage" not in merged["anneal_hold_convergence"]  # internal, not for disk


def test_submit_equil_chain_stop_after_stage_slices_the_workflow():
    """stop_after_stage is a plain client-side slice of workflow["stages"]/["run_order"] before
    run_lammps_chain -- generate_equilibration_workflow itself always plans the full 8-stage
    chain; only the submitted subset changes."""
    args = _base_args("SLICETEST1", "POXI", "/fake/plan.json")
    args.gpu_ids = [0]
    args.mpi_ranks = 1
    args.engine = "gpu"
    args.velocity_seed = 1
    args.data_path = "/fake/cell.data"
    cls = {"dt_fs": 1.0, "electrostatics": "pppm", "preferred_ff": "pcff"}

    stage_names = ["minimize", "nvt_warmup", "npt_densify", "npt_ff_activate",
                  "npt_densify_hold", "anneal_heat", "anneal_hold",
                  "cool_block_01", "nvt_kinetic_stability", "npt_final"]
    full_stages = [{"name": n, "output_data": f"/fake/{n}_out.data"} for n in stage_names]
    submitted_stage_lists = []

    class _Fake:
        def generate_equilibration_workflow(self, **kwargs):
            return {"status": "success", "stages": list(full_stages), "run_order": list(stage_names)}

        def run_lammps_chain(self, **kwargs):
            submitted_stage_lists.append(kwargs["stages"])
            return {"chain_id": "chain-1"}

    result = _submit_equil_chain(args, cls, _Fake(), stop_after_stage="anneal_hold")

    submitted_names = [s["name"] for s in submitted_stage_lists[0]]
    assert submitted_names == stage_names[:stage_names.index("anneal_hold") + 1]
    assert result["workflow"]["stages"][-1]["name"] == "anneal_hold"


def test_anneal_hold_gate_disabled_by_default_keeps_single_submission_path(
        tmp_path, equil_check_args_cls, monkeypatch):
    """Regression guard: anneal_hold_msid_gate_enabled defaults False -- do_equil_and_check must
    take the existing single-generate_equilibration_workflow-call path, byte-identical to every
    other class, unless a class explicitly opts in."""
    args, cls = equil_check_args_cls
    assert cls.get("anneal_hold_msid_gate_enabled", False) is False
    args.backbone_types = [1, 2]
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [0], "run": run_name} if action == "claim" else {"released": True}))
    fake = _FakeEquilLammps(
        tmp_path,
        comp_results=[{"chain": {"ct": {"tau_relax_ps": 100.0, "decay_fraction_at_end": 0.9}}}],
        gate_verdicts=[{"verdict": "PASS"}],
    )

    result = do_equil_and_check(args, cls, fake)

    assert result["equil_verdict"] == "PASS"
    assert result["anneal_hold_convergence"] is None
    assert len(fake.generate_equilibration_workflow_calls) == 1  # one chain, not two


def test_do_equil_and_check_gated_path_merges_chain1_and_chain2_stages(
        tmp_path, equil_check_args_cls, monkeypatch):
    """The most intricate part of the gated path -- workflow merging (chain 1's leading stages +
    the gate's final anneal_hold stage + chain 2's tail), resume_data_path threading, and
    stage_checkpoints assembled from the merged list -- covered end to end through
    do_equil_and_check itself, not just _anneal_hold_adaptive_extend in isolation."""
    args, cls = equil_check_args_cls
    args.backbone_types = [1, 4, 5]  # explicit -- skip derivation, exercise the gate itself
    args.output_dir = str(tmp_path / "raw")
    args.work_dir = str(tmp_path / "work")
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    cls["anneal_hold_msid_gate_enabled"] = True
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [1], "run": run_name} if action == "claim" else {"released": True}))
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: {"status": "completed"})

    minimize_stage = {"name": "minimize", "output_data": f"{tmp_path}/minimize_out.data",
                      "work_dir": str(tmp_path), "params": {"DUMP_FILE": "minimize.dump"}}
    anneal_hold_stage = {"name": "anneal_hold", "output_data": f"{tmp_path}/anneal_hold_out.data",
                         "output_restart": f"{tmp_path}/anneal_hold_out.restart",
                         "work_dir": str(tmp_path),
                         "params": {"LOG_FILE": "anneal_hold.log", "DUMP_FILE": "anneal_hold.dump",
                                    "DUMP_FREQ": 1000, "N_STEPS": 1000000}}
    cool_block_stage = {"name": "cool_block_01", "output_data": f"{tmp_path}/cool_out.data",
                        "work_dir": str(tmp_path), "params": {"DUMP_FILE": "cool.dump"}}
    npt_final_stage = {"name": "npt_final", "output_data": f"{tmp_path}/npt_final_out.data",
                       "output_restart": f"{tmp_path}/npt_final_out.restart",
                       "work_dir": str(tmp_path), "params": {"DUMP_FILE": "npt_final.dump"}}

    fake = _FakeEquilLammps(
        tmp_path,
        comp_results=[
            # 1st call: the gate's own probe on anneal_hold's own trajectory -- passes on the
            # first probe, zero extensions.
            {"status": "success",
             "chain": {"msid": {"large_s": {"slope": 0.95, "gaussian_pass": True}}}},
            # 2nd call: the normal post-chain-2 equil-check comprehensive call, on npt_final.
            {"chain": {"ct": {"tau_relax_ps": 100.0, "decay_fraction_at_end": 0.9}}},
        ],
        gate_verdicts=[{"verdict": "PASS"}],
        workflow_queue=[
            {"status": "success", "stages": [minimize_stage, anneal_hold_stage],
             "run_order": ["minimize", "anneal_hold"]},
            {"status": "success", "stages": [cool_block_stage, npt_final_stage],
             "run_order": ["cool_block_01", "npt_final"]},
        ],
    )

    result = do_equil_and_check(args, cls, fake)

    assert result["equil_verdict"] == "PASS"
    assert result["anneal_hold_convergence"]["outcome"] == "PASS"
    assert result["anneal_hold_convergence"]["extensions_used"] == 0
    # merged stage_checkpoints carries BOTH chain 1's and chain 2's stages -- a later remedy
    # resuming from an earlier checkpoint (e.g. minimize) can still find it, even though chain 2
    # (resume_from="anneal_hold") never generated it itself.
    assert set(result["stage_checkpoints"]) == {"minimize", "anneal_hold", "cool_block_01", "npt_final"}
    assert result["stage_checkpoints"]["anneal_hold"] == f"{tmp_path}/anneal_hold_out.data"
    assert result["stage_checkpoints"]["npt_final"] == f"{tmp_path}/npt_final_out.data"
    assert result["npt_prod_data_path"] == f"{tmp_path}/npt_final_out.data"
    # exactly 2 generate_equilibration_workflow calls: chain 1 (sliced to stop at anneal_hold by
    # _submit_equil_chain itself -- see test_submit_equil_chain_stop_after_stage_slices_the_workflow
    # for that mechanism in isolation), chain 2 (resume_from="anneal_hold") -- no extension, since
    # the gate passed on its first probe.
    assert len(fake.generate_equilibration_workflow_calls) == 2
    chain2_call = fake.generate_equilibration_workflow_calls[1]
    assert chain2_call["resume_from"] == "anneal_hold"
    assert chain2_call["data_file"] == f"{tmp_path}/anneal_hold_out.data"
    # reattach-guard file cleaned up on success, not left behind
    pending_path = Path(args.work_dir).parent / "pending_equil_submission.json"
    assert not pending_path.exists()


def test_do_equil_and_check_gated_reattach_chain1_done_skips_resubmission(
        tmp_path, equil_check_args_cls, monkeypatch):
    """gate_phase="chain1_done" reattach: chain 1 already finished before an earlier process
    death -- must be reused from its persisted workflow with zero resubmission, not silently
    re-run the most expensive part of the protocol (minimize..anneal_hold)."""
    args, cls = equil_check_args_cls
    args.backbone_types = [1, 4, 5]
    args.output_dir = str(tmp_path / "raw")
    args.work_dir = str(tmp_path / "work")
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    cls["anneal_hold_msid_gate_enabled"] = True
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [1], "run": run_name} if action == "claim" else {"released": True}))
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: {"status": "completed"})

    anneal_hold_stage = {"name": "anneal_hold", "output_data": f"{tmp_path}/anneal_hold_out.data",
                         "output_restart": f"{tmp_path}/anneal_hold_out.restart",
                         "work_dir": str(tmp_path),
                         "params": {"LOG_FILE": "anneal_hold.log", "DUMP_FILE": "anneal_hold.dump",
                                    "DUMP_FREQ": 1000, "N_STEPS": 1000000}}
    chain1_workflow = {"stages": [
        {"name": "minimize", "output_data": f"{tmp_path}/minimize_out.data",
         "work_dir": str(tmp_path), "params": {"DUMP_FILE": "minimize.dump"}},
        anneal_hold_stage,
    ]}
    npt_final_stage = {"name": "npt_final", "output_data": f"{tmp_path}/npt_final_out.data",
                       "output_restart": f"{tmp_path}/npt_final_out.restart",
                       "work_dir": str(tmp_path), "params": {"DUMP_FILE": "npt_final.dump"}}

    pending_path = Path(args.work_dir).parent / "pending_equil_submission.json"
    pending_path.write_text(json.dumps({"gate_phase": "chain1_done", "workflow": chain1_workflow}))

    fake = _FakeEquilLammps(
        tmp_path,
        comp_results=[
            {"status": "success",
             "chain": {"msid": {"large_s": {"slope": 0.95, "gaussian_pass": True}}}},
            {"chain": {"ct": {"tau_relax_ps": 100.0, "decay_fraction_at_end": 0.9}}},
        ],
        gate_verdicts=[{"verdict": "PASS"}],
        workflow_queue=[
            {"status": "success", "stages": [npt_final_stage], "run_order": ["npt_final"]},
        ],
    )

    result = do_equil_and_check(args, cls, fake)

    assert result["equil_verdict"] == "PASS"
    # exactly ONE generate_equilibration_workflow call -- chain 2 only, chain 1 reused as-is
    assert len(fake.generate_equilibration_workflow_calls) == 1
    assert fake.generate_equilibration_workflow_calls[0]["resume_from"] == "anneal_hold"
    assert result["stage_checkpoints"]["minimize"] == f"{tmp_path}/minimize_out.data"
    assert result["stage_checkpoints"]["anneal_hold"] == f"{tmp_path}/anneal_hold_out.data"


def test_do_equil_and_check_gated_reattach_chain1_mid_wait_reuses_chain_id(
        tmp_path, equil_check_args_cls, monkeypatch):
    """gate_phase="chain1" reattach: death happened while waiting on chain 1 itself -- must
    reattach to the persisted chain_id directly, not resubmit chain 1."""
    args, cls = equil_check_args_cls
    args.backbone_types = [1, 4, 5]
    args.output_dir = str(tmp_path / "raw")
    args.work_dir = str(tmp_path / "work")
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    cls["anneal_hold_msid_gate_enabled"] = True
    monkeypatch.setattr(rdr, "_pick_gpu", lambda action, run_name, need=None: (
        {"claimed": [1], "run": run_name} if action == "claim" else {"released": True}))
    waited_run_ids = []
    monkeypatch.setattr(rdr, "wait_for_run", lambda lammps, run_id, label: (
        waited_run_ids.append(run_id) or {"status": "completed"}))

    anneal_hold_stage = {"name": "anneal_hold", "output_data": f"{tmp_path}/anneal_hold_out.data",
                         "output_restart": f"{tmp_path}/anneal_hold_out.restart",
                         "work_dir": str(tmp_path),
                         "params": {"LOG_FILE": "anneal_hold.log", "DUMP_FILE": "anneal_hold.dump",
                                    "DUMP_FREQ": 1000, "N_STEPS": 1000000}}
    chain1_workflow = {"stages": [anneal_hold_stage]}
    npt_final_stage = {"name": "npt_final", "output_data": f"{tmp_path}/npt_final_out.data",
                       "output_restart": f"{tmp_path}/npt_final_out.restart",
                       "work_dir": str(tmp_path), "params": {"DUMP_FILE": "npt_final.dump"}}

    pending_path = Path(args.work_dir).parent / "pending_equil_submission.json"
    pending_path.write_text(json.dumps({"gate_phase": "chain1", "chain_id": "reattached-chain-1",
                                        "workflow": chain1_workflow}))

    fake = _FakeEquilLammps(
        tmp_path,
        comp_results=[
            {"status": "success",
             "chain": {"msid": {"large_s": {"slope": 0.95, "gaussian_pass": True}}}},
            {"chain": {"ct": {"tau_relax_ps": 100.0, "decay_fraction_at_end": 0.9}}},
        ],
        gate_verdicts=[{"verdict": "PASS"}],
        workflow_queue=[
            {"status": "success", "stages": [npt_final_stage], "run_order": ["npt_final"]},
        ],
    )

    result = do_equil_and_check(args, cls, fake)

    assert result["equil_verdict"] == "PASS"
    assert waited_run_ids[0] == "reattached-chain-1"  # chain 1 waited on the PERSISTED chain_id
    # zero generate_equilibration_workflow calls for chain 1 -- only chain 2's own call
    assert len(fake.generate_equilibration_workflow_calls) == 1
    assert fake.generate_equilibration_workflow_calls[0]["resume_from"] == "anneal_hold"
