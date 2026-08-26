"""Regression guard for the deterministic campaign executor.

run_campaign.py's --dry-run mode resolves every stage through stage_params.py. These tests
prove the executor and the protocol resolver cannot silently diverge.

Does NOT submit any simulation -- --dry-run never calls the MCP servers.
"""
import json
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
                 derived_backbone_types=None, workflow_stages=None, workflow_extra=None):
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

    def _sentinel(self):
        self._chain_n += 1
        p = self.tmp_path / f"sentinel_{self._chain_n}.json"
        p.write_text(json.dumps({"status": "completed", "run_id": f"chain-{self._chain_n}"}))
        return p

    def generate_equilibration_workflow(self, **kwargs):
        self.generate_equilibration_workflow_calls.append(kwargs)
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
