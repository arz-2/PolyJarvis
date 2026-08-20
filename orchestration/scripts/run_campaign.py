#!/usr/bin/env python3
"""Run a complete PolyJarvis campaign through the durable workflow engine.

The public CLI accepts a plan, never an individual stage. Builder, LAMMPS, validation,
and analysis functions are in-process adapters; workflow state and recovery belong to
``workflow_engine``.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from stage_params import resolve_stage_params, apply_plan, resolve_hardware, load_plan  # noqa: E402
from hw_common import load_rules, get_class_entry, resolve_member_value  # noqa: E402
from protocol_policy import select_pressure_ladder  # noqa: E402
from workflow_engine import (  # noqa: E402
    Finding, StageResult, WorkflowEngine, atomic_write_json, pressure_point_drop_allowed,
)
from validate_run_plan import validate_plan  # noqa: E402
from scientific_control import validate_overrides  # noqa: E402

LAMMPS_ENGINE_DIR = REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"
EMC_SERVER_DIR = REPO_ROOT / "mcp-servers" / "mcp-emc-server"
VENV_PY = REPO_ROOT / "mcp-servers" / ".venv" / "bin" / "python"
MCP_JSON = REPO_ROOT / ".mcp.json"

POLL_SECONDS = 30
EXTEND_MAX_ATTEMPTS = 2
# Finite-size forecast target density: density_initial_gcm3 is a build parameter we choose
# (how loosely to pack the initial cell before EMC/LAMMPS compress it), never experimental
# data -- always resolvable, unlike a curated per-SMILES experimental_density_gcm3. EMC's own
# convention packs at ~0.5x the eventual density; the archive's observed
# experimental_density_gcm3/density_initial_gcm3 ratio spans ~1.3x (PHYC) to ~2.0x
# (PSTR/PACR). 2.0 is the conservative (smaller-predicted-box) end of that range: this gate's
# false-positive cost (an unnecessary rebuild-larger, at the cheapest point in the pipeline)
# is far cheaper than its false-negative cost (a silently under-sized cell burning the whole
# equilibration chain).
COMPRESSION_RATIO = 2.0


# ─── Module loading (bypasses MCP transport entirely) ─────────────────────────

def _mcp_env(server_key: str) -> dict:
    """Read a server's env block from .mcp.json — the single source of truth for
    host-specific paths (LAMBDA_LAMMPS etc.), never duplicated here as a second hardcoded copy."""
    if not MCP_JSON.exists():
        return {}
    cfg = json.loads(MCP_JSON.read_text())
    return cfg.get("mcpServers", {}).get(server_key, {}).get("env", {})


def _load_server_module(name: str, path: Path, cwd: Path, extra_env: dict):
    """Import a standalone MCP server.py as a plain module. `name` must be unique per call
    since both mcp-lammps-engine/server.py and mcp-emc-server/server.py are literally both
    named server.py — a naive `import server` would collide.

    `cwd` must also be pushed onto sys.path: server.py does bare sibling imports (e.g.
    `from smiles_to_emc import build_cell`) that only resolve via sys.path, not cwd. This is
    easy to miss under an interactive `python -c`/REPL session, where sys.path[0]=='' tracks
    os.getcwd() dynamically and masks the gap — but a real script invocation's sys.path[0] is
    the *script's own* directory, so the chdir alone is not enough there."""
    old_cwd, old_env = os.getcwd(), dict(os.environ)
    cwd_str = str(cwd)
    path_inserted = cwd_str not in sys.path
    try:
        os.chdir(cwd)
        os.environ.update(extra_env)
        if path_inserted:
            sys.path.insert(0, cwd_str)
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if path_inserted:
            sys.path.remove(cwd_str)
        os.chdir(old_cwd)
        os.environ.clear()
        os.environ.update(old_env)


# ─── Stage halt with structured detail ─────────────────────────────────────────

class StageHalt(SystemExit):
    """Raised by a do_* function to abort its stage with structured detail attached (e.g. a
    finite-size forecast) — execute()'s except SystemExit handler reads .details instead of
    re-deriving it from a side-channel state file."""

    def __init__(self, message, details: dict = None):
        super().__init__(message)
        self.details = details or {}


# ─── GPU claim (A.6 — cross-track rules as code, not convention) ──────────────

def _pick_gpu(action: str, run_name: str, need: int = None) -> dict:
    cmd = [sys.executable, str(REPO_ROOT / "orchestration" / "scripts" / "pick_gpu.py"),
           "--json", action, "--run", run_name]
    if need is not None:
        cmd += ["--need", str(need)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": f"pick_gpu.py {action} produced no JSON: {r.stdout!r} {r.stderr!r}"}


class gpu_claim:
    """Context manager: claim `need` GPUs under `run_name`'s label, yield the comma-joined
    gpu_ids string, always release on exit (even on exception) — rule 4 (log the exact claim
    label, verify release) enforced structurally rather than by convention.

    A bare `kill`/SIGTERM skips __exit__ entirely (Python does not unwind `with` blocks on
    SIGTERM by default), leaving a stale claim in pick_gpu.py's ledger — observed directly:
    killing a test run left GPU 0 permanently marked busy under its run_name until released
    by hand. A SIGTERM handler released for the claim's lifetime closes that gap.
    """

    def __init__(self, run_name: str, need: int):
        self.run_name, self.need = run_name, need
        self._prev_sigterm = None

    def __enter__(self) -> str:
        result = _pick_gpu("claim", self.run_name, self.need)
        if "claimed" not in result:
            raise RuntimeError(f"GPU claim failed for {self.run_name} (need={self.need}): {result}")
        self.claimed = result["claimed"]
        self._prev_sigterm = signal.signal(signal.SIGTERM, self._on_sigterm)
        return ",".join(str(i) for i in self.claimed)

    def _on_sigterm(self, signum, frame):
        _pick_gpu("release", self.run_name)
        signal.signal(signal.SIGTERM, self._prev_sigterm)
        os._exit(128 + signum)

    def __exit__(self, exc_type, exc, tb):
        if self._prev_sigterm is not None:
            signal.signal(signal.SIGTERM, self._prev_sigterm)
        rel = _pick_gpu("release", self.run_name)
        if "released" not in rel:
            print(f"WARNING: GPU release may have failed for {self.run_name}: {rel}", file=sys.stderr)
        return False


# ─── Run waiting ─────────────────────────────────────────────────────────────

def wait_for_run(lammps, run_id: str, label: str) -> dict:
    """Block until run_id (a run_id or chain_id) reaches a terminal state: sentinel file first,
    pidfile liveness as a dead-process fallback."""
    w = lammps.watch_run(run_id)
    sentinel = Path(w["sentinel_path"])
    pidfile = Path(w["pidfile"]) if w.get("pidfile") else None
    print(f"[wait] {label}: watching {run_id}", file=sys.stderr)
    while True:
        if sentinel.exists():
            try:
                return json.loads(sentinel.read_text())
            except (json.JSONDecodeError, OSError):
                pass  # sentinel mid-write; retry next tick
        if pidfile and pidfile.exists():
            try:
                pid = int(pidfile.read_text().strip())
                os.kill(pid, 0)
            except ProcessLookupError:
                return {"status": "failed", "reason": "PROCESS_DEAD_NO_SENTINEL", "run_id": run_id}
            except (ValueError, OSError):
                pass  # pidfile empty/unreadable — benign race, keep waiting
        time.sleep(POLL_SECONDS)


def wait_for_analysis(lammps, submit_result: dict, label: str, poll_seconds: float = 2,
                       timeout_s: float = 1800) -> dict:
    """Poll get_run_status() for a non-chain analysis tool's background thread to finish, then
    return its result dict. check_equilibration_comprehensive/extract_equilibrated_density/
    extract_thermal/extract_bulk_modulus* all launch a background thread and return
    {"status": "submitted", "run_id": ...} immediately -- reading fields off that return value
    directly (as every call site here used to) reads an unfinished result."""
    if submit_result.get("run_id") is None:
        return submit_result  # already synchronous / an immediate error -- nothing to poll
    run_id = submit_result["run_id"]
    t0 = time.time()
    while True:
        status = lammps.get_run_status(run_id)
        st = status.get("status")
        if st == "completed":
            return status.get("result", status)
        if st == "failed":
            raise SystemExit(f"{label} analysis failed: {status}")
        if time.time() - t0 > timeout_s:
            raise SystemExit(f"{label} analysis timed out after {timeout_s}s: {status}")
        time.sleep(poll_seconds)


# ─── Base workflow arguments ──────────────────────────────────────────────────

def _base_args(run_name: str, polymer_class: str, plan_path: str) -> SimpleNamespace:
    return SimpleNamespace(
        run_name=run_name, polymer_class=polymer_class, plan=str(plan_path),
        smiles=None, data_path=None, tg_start_data=None, work_dir=None,
        gpu_ids=None, mpi_ranks=None, engine=None, emc_seed=None, velocity_seed=None,
        dp=None, nchain=None, n_atoms=None, charge_method=None, date_start=None, date_end=None,
        d01=None, d02=None, d03=None, d04=None, lammps_flags=None, is_glassy=None,
        tg_k=None, tg_fit_quality=None, deform_log=None, deform_log_slow=None,
        deform_rate_mode="primary", murnaghan_logs=None, d05=None, npt_prod_log=None,
        npt_prod_dump=None, melt_data_path=None, ff=None, backbone_types=None, enthalpy_col="Enthalpy",
        output_dir=None, equil_data_path=None, npt_prod_ns=None, add_melt_npt=False,
        melt_hold_ns=None, melt_only_continuation_ns=None, phase="full",
        pending_cooldown_path=None,
        T_equil_K=None, T_anneal_high_K=None, tg_t_high_K=None, tg_t_low_K=None,
        tg_t_step_K=None, tg_steps_per_t=None, tg_rate_index=None,
        n_replicates=1, K_strain_max=None, K_deform_rate_inv_s=None,
        dt_fs=None, density_initial=None, properties="all", exp_K_min=None, exp_K_max=None,
        exp_tg_K=None, exp_tg_min=None, exp_tg_max=None, exp_density_min=None,
        exp_density_max=None, polymer_name=None, tg_path=None,
    )


# ─── Stage: build ───────────────────────────────────────────────────────────

def do_build(args, cls: dict, emc, lammps) -> dict:
    preferred_builder = cls.get("preferred_builder", "emc")
    if preferred_builder != "emc":
        raise SystemExit(
            f"run_campaign.py: preferred_builder={preferred_builder!r} is not "
            f"supported by the deterministic campaign runner; use an EMC-backed class.")

    p = resolve_stage_params("build", args, cls)
    work_dir = Path(p["work_dir"])
    emc_seed = (p["emc_seed"] if p["emc_seed"] is not None else
                1 + int(hashlib.sha256(args.run_name.encode()).hexdigest(), 16) % 999_999)

    job = emc.submit_emc_cell_job(
        smiles=p["smiles"], polymer_class=args.polymer_class.upper(),
        dp=p["dp"], nchains=p["nchain"], density_initial=p["density_initial_gcm3"],
        temperature=p["build_temperature_K"], seed=emc_seed, output_name="polymer",
        field_override=p["preferred_ff"],
    )
    if job.get("error"):
        raise SystemExit(f"submit_emc_cell_job failed: {job['error']}")
    job_id = job["job_id"]

    status = {}
    while True:
        status = emc.get_emc_job_status(job_id)
        if status.get("status") in ("completed", "failed"):
            break
        time.sleep(POLL_SECONDS)
    if status["status"] != "completed":
        raise SystemExit(f"EMC build job {job_id} failed: {status}")

    out = emc.get_emc_job_output(job_id)["result"]
    cell_dir = work_dir / "cell"
    cell_dir.mkdir(parents=True, exist_ok=True)
    dest_data = cell_dir / "cell.data"
    shutil.copy(out["data_path"], dest_data)
    # get_emc_job_output's result has no "params_path" key (only "output_dir") -- EMC always
    # writes the coefficients file as "emc_build.params" (fixed filename, independent of
    # output_name -- see smiles_to_emc.py's "'emc_build' never collides with the cluster name"
    # comment) inside output_dir. PCFF/OPLS-AA builds store all Pair/Bond/Angle/... Coeffs
    # here, not inline in .data.
    dest_params = None
    src_params_matches = sorted(Path(out["output_dir"]).glob("*.params"))
    if src_params_matches:
        dest_params = cell_dir / "emc_build.params"
        shutil.copy(src_params_matches[0], dest_params)

    # Size gate at the cheapest point: the built cell, before any MD. A too-small cell would
    # otherwise burn the whole equilibration chain before the equil-check gate said the same.
    # target_density_gcm3 is always the density_initial_gcm3-derived estimate (COMPRESSION_RATIO,
    # module-level above) -- never a curated experimental value, so this forecast runs
    # unconditionally for every system, known or novel.
    ep = resolve_stage_params("equil", args, cls)
    info = lammps.inspect_data_file(
        data_file=str(dest_data), lj_cutoff=ep.get("cutoff_A") or 12.0,
        target_density_gcm3=COMPRESSION_RATIO * p["density_initial_gcm3"], nchain=ep.get("nchain"),
    )
    size_errors = [e for e in (info.get("validation", {}).get("errors") or [])
                   if e.startswith("SIZE_")]
    if size_errors:
        raise StageHalt(
            "Halting before equilibration — the built cell would self-image once compressed: "
            + " ".join(size_errors)
            + " A deterministic replicate must not silently rebuild at a different nchain; "
              "that is a decided_params change and needs human review.",
            details={"finite_size_forecast": info.get("finite_size_forecast")},
        )

    result = {
        "data_path": str(dest_data),
        "emc_params_path": str(dest_params) if dest_params else None,
        "emc_seed": emc_seed,
        "lammps_flags": out["lammps_flags"],
        "n_atoms": info.get("info", {}).get("n_atoms"),
    }
    return result


# ─── Stage: equilibration + gate (EXTEND loop, STRUCTURAL_FAIL halt) ──────────

def _submit_equil_chain(args, cls: dict, lammps, extend_from_data: str = None,
                         extend_temp: float = None, extend_ns: float = 1.5,
                         resume_from: str = None, resume_data_path: str = None,
                         resume_anneal_cycles: int = None) -> dict:
    p = resolve_stage_params("equil", args, cls)
    flags = p["lammps_flags"]
    velocity_seed = p["velocity_seed"]
    if resume_from is not None:
        # "anneal": run only the DELTA cycles the remedy computed (resume_anneal_cycles), not
        # the new absolute eq_annealing_cycles target -- that target already counts cycles the
        # prior attempt ran, which resume_data_path's checkpoint already reflects.
        # "npt_production": anneal_cycles is unused (nvt_production/npt_production are both
        # skipped) but generate_equilibration_workflow still validates it as a non-negative int.
        workflow = lammps.generate_equilibration_workflow(
            data_file=resume_data_path, work_dir_base=p["work_dir"],
            polymer_name=args.run_name, temp=p["T_workflow_K"], max_temp=p["T_anneal_high_K"],
            press=p["P_equil_atm"], use_pcff=flags["use_pcff"], use_trappe=flags["use_trappe"],
            use_opls=flags["use_opls"], npt_prod_steps=p["npt_prod_steps"],
            nvt_prod_steps=p["nvt_prod_steps"], npt_prod300_steps=p["npt_prod300_steps"],
            add_melt_npt=p["add_melt_npt"] if resume_from == "anneal" else False,
            t_equil_K=(p["T_equil_K"] if resume_from == "anneal" and p["add_melt_npt"] else None),
            add_300k_production=p["add_300k_production"],
            melt_npt_steps=p["melt_npt_steps"], engine=p["engine"], velocity_seed=velocity_seed,
            npt_cool_steps=p["npt_cool_steps"], npt_cool300_steps=p["npt_cool300_steps"],
            anneal_cycles=(resume_anneal_cycles or 0) if resume_from == "anneal" else 0,
            anneal_cycle_steps=p["anneal_cycle_steps"],
            thermostat_damp_fs=p["thermostat_damp_fs"],
            barostat_damp_fs=p["barostat_damp_fs"],
            max_press=p["compression_max_pressure_atm"],
            use_long_range=p["use_long_range_electrostatics"],
            extend_steps=None,
            params_file="",
            resume_from=resume_from,
        )
    elif extend_from_data is None:
        workflow = lammps.generate_equilibration_workflow(
            data_file=p["data_path"], work_dir_base=p["work_dir"],
            polymer_name=args.run_name, temp=p["T_workflow_K"], max_temp=p["T_anneal_high_K"],
            press=p["P_equil_atm"], use_pcff=flags["use_pcff"], use_trappe=flags["use_trappe"],
            use_opls=flags["use_opls"], npt_prod_steps=p["npt_prod_steps"],
            nvt_prod_steps=p["nvt_prod_steps"], npt_prod300_steps=p["npt_prod300_steps"],
            add_melt_npt=p["add_melt_npt"], t_equil_K=p["T_equil_K"] if p["add_melt_npt"] else None,
            add_300k_production=p["add_300k_production"],
            melt_npt_steps=p["melt_npt_steps"], engine=p["engine"], velocity_seed=velocity_seed,
            npt_cool_steps=p["npt_cool_steps"], npt_cool300_steps=p["npt_cool300_steps"],
            anneal_cycles=p["eq_annealing_cycles"],
            anneal_cycle_steps=p["anneal_cycle_steps"],
            thermostat_damp_fs=p["thermostat_damp_fs"],
            barostat_damp_fs=p["barostat_damp_fs"],
            max_press=p["compression_max_pressure_atm"],
            use_long_range=p["use_long_range_electrostatics"],
            extend_steps=None,
            params_file=p.get("emc_params_path") or "",
            minimize_etol=p["minimize_etol"], minimize_ftol=p["minimize_ftol"],
            minimize_maxiter=p["minimize_maxiter"], minimize_maxeval=p["minimize_maxeval"],
        )
    else:
        dt = p["dt_fs"]
        extend_steps = int(extend_ns * 1e6 / dt)
        workflow = lammps.generate_equilibration_workflow(
            data_file=extend_from_data, work_dir_base=p["work_dir"], polymer_name=args.run_name,
            temp=extend_temp, press=p["P_equil_atm"], use_pcff=flags["use_pcff"],
            use_trappe=flags["use_trappe"], use_opls=flags["use_opls"], engine=p["engine"],
            velocity_seed=velocity_seed, extend_only=True, extend_steps=extend_steps,
            npt_prod_steps=None, nvt_prod_steps=None, npt_prod300_steps=None,
            npt_cool_steps=None, npt_cool300_steps=None,
            melt_npt_steps=None,
            anneal_cycles=0, anneal_cycle_steps=None,
            thermostat_damp_fs=p["thermostat_damp_fs"],
            barostat_damp_fs=p["barostat_damp_fs"],
            use_long_range=p["use_long_range_electrostatics"],
        )
    if workflow.get("status") == "error":
        raise SystemExit(f"generate_equilibration_workflow failed: {workflow}")

    chain = lammps.run_lammps_chain(
        stages=workflow["stages"], gpu_ids=p["gpu_ids"], mpi=p["mpi_ranks"],
        data_file=resume_data_path or extend_from_data or p["data_path"], engine=p["engine"],
        params_file=(p.get("emc_params_path") or "")
                    if (extend_from_data is None and resume_from is None) else "",
    )
    if chain.get("status") == "error":
        raise SystemExit(f"run_lammps_chain failed: {chain}")
    return {"chain_id": chain["chain_id"], "workflow": workflow}


def _stage_dump_path(stage: dict) -> str:
    return f"{stage['work_dir']}/{stage['params']['DUMP_FILE']}"


def do_equil_and_check(args, cls: dict, lammps) -> dict:
    # Captured before args.data_path gets reassigned to the equilibration chain's own output
    # below — the original pre-simulation .data file is the only one whose Masses section still
    # has the "# <name>" comments inspect_data_file's atom_type_names parsing needs; a write_data
    # output (which npt_prod_data_path always is) has stripped them.
    build_data_path = getattr(args, "build_data_path", None) or args.data_path

    # generate_equilibration_workflow rejects a null seed; stage_params resolves one (pinned, else
    # derived from run_name) for the chain and every EXTEND continuation below.
    velocity_seed = resolve_stage_params("equil", args, cls)["velocity_seed"]
    extend_history = []
    backbone_derivation = None

    # Reattach guard: run_lammps_chain launches a detached (setsid nohup) shell that keeps
    # running and finishes independently of this process. If the orchestrator dies while
    # wait_for_run is blocked below, the chain itself is often still fine -- but nothing
    # previously recorded its chain_id anywhere, so a resumed run had no way to find it and
    # would call _submit_equil_chain again, silently discarding a possibly-completed chain and
    # burning the GPU time twice. Persist the submission the moment it's made (before waiting on
    # it), and reuse it on reattachment instead of resubmitting. WorkflowEngine._new_attempt only
    # reaches this function without minting a fresh attempt_dir when the prior attempt's own
    # status is "incomplete" (process death, not a real terminal verdict) -- see its reattach
    # branch -- so an existing file here always means "the same attempt tried this before".
    pending_path = (Path(args.work_dir).parent / "pending_equil_submission.json"
                    if args.work_dir else None)

    gpu_per_run = cls.get("gpu_per_run") or 1
    with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
        args.gpu_ids = gpu_ids
        if pending_path is not None and pending_path.is_file():
            submission = json.loads(pending_path.read_text())
        else:
            continuation_path = getattr(args, "pending_continuation_path", None)
            resume_from = getattr(args, "equil_resume_from", None)
            if resume_from is not None:
                submission = _submit_equil_chain(
                    args, cls, lammps, resume_from=resume_from,
                    resume_data_path=getattr(args, "equil_resume_data_path", None),
                    resume_anneal_cycles=getattr(args, "equil_resume_anneal_cycles", None),
                )
            elif continuation_path:
                submission = _submit_equil_chain(
                    args, cls, lammps, extend_from_data=continuation_path,
                    extend_temp=getattr(args, "continuation_temp_K", 300.0),
                    extend_ns=float(getattr(args, "npt_continuation_ns", 1.5)),
                )
            else:
                submission = _submit_equil_chain(args, cls, lammps)
            if pending_path is not None:
                atomic_write_json(pending_path, submission)
        result = wait_for_run(lammps, submission["chain_id"], "equilibration chain")
    if result.get("status") != "completed":
        if result.get("stage") == "minimize_not_converged":
            # minimize is stage 0 of the chain -- nothing else in THIS submission completed,
            # so there is no real stage_checkpoints to resume from (unlike EXTEND_EXHAUSTED/
            # STRUCTURAL_FAIL below, which fire after real stages have run).
            return {"halted": True, "reason": "MINIMIZE_NOT_CONVERGED", "detail": result,
                    "stage_checkpoints": {}}
        raise SystemExit(f"Equilibration chain did not complete: {result}")
    if pending_path is not None:
        pending_path.unlink(missing_ok=True)

    workflow = submission["workflow"]
    # Every stage THIS call actually built, by name -> its own write_data output. A later
    # attempt's remedy (melt_hold's anneal-cycle extension, a future npt_cool300 remedy) needs a
    # real checkpoint path to resume from — CampaignStageExecutor.execute locates it by walking
    # this attempt's outputs (via prior_attempts), the same pattern npt_continuation_ns already
    # uses for npt_prod_data_path. Surfaced on every return below, halted or not: a resumed chain
    # (resume_from set) only contains ITS OWN tail stages here, not the ones it skipped -- a
    # remedy resuming from one of those earlier stages must walk further back through
    # prior_attempts to find them, same as any other stage_checkpoints lookup.
    stage_checkpoints = {s["name"]: s["output_data"] for s in workflow["stages"] if s.get("name")}
    # Glassy (9-run chain, add_300k_production default True): the server exposes the terminal
    # npt_prod300 stage's output directly as npt_prod300_data/_dump. Rubbery (7-run chain, no
    # npt_prod300 stage): the terminal stage is npt_production itself — stages[-1] (no generic
    # top-level "..._data"/"..._dump" key exists for this case, per generate_equilibration_
    # workflow's own return-shape logic in server.py).
    npt_prod_data_path = workflow.get("npt_prod300_data") or workflow["stages"][-1]["output_data"]
    npt_prod_dump_path = workflow.get("npt_prod300_dump") or _stage_dump_path(workflow["stages"][-1])

    # melt_dump_path/melt_data_path (the CHAIN-structural checks' source -- rg/msd/ct/msid --
    # and the assess_cooling_contraction melt reference) had the same flat-convention bug as
    # npt_prod_log_path above, but couldn't be fixed the same way (a data_path suffix swap):
    # they name two DIFFERENT stages (nvt_production's dump, npt_production's data), neither of
    # which is npt_prod_data_path/_dump_path (the terminal stage, npt_prod300 for glassy chains).
    # Locate them by name in the real workflow, same as npt_prod_data_path/_dump_path do for the
    # terminal stage above, instead of guessing a path.
    def _find_stage(name):
        return next((s for s in workflow["stages"] if s.get("name") == name), None)
    _nvt_stage = _find_stage("nvt_production")
    if _nvt_stage:
        args.npt_prod_dump = _stage_dump_path(_nvt_stage)
    _melt_stage = _find_stage("npt_production")
    if _melt_stage:
        args.melt_data_path = _melt_stage.get("output_data")

    attempts = 0
    while True:
        args.data_path = npt_prod_data_path
        p = resolve_stage_params("equil-check", args, cls)
        # The resolver's value, not the raw CLI arg: the halt below says the list comes from
        # decided_params, and only the resolver reads it from there (via the plan-overlaid cls).
        backbone_types = p["backbone_types"]
        if backbone_types is None:
            # Atom-name-only lookup can't tell backbone from pendant-branch atoms (confirmed
            # live: PACR/PMMA shares a generic aliphatic carbon type between CH2 backbone atoms
            # and pendant methyl branches) — but bond TOPOLOGY can: derive_backbone_types walks
            # the heavy-atom bond graph's diameter, which needs no types at all and excludes
            # branches by construction (they're shorter than continuing along the main path).
            derived = wait_for_analysis(lammps, lammps.derive_backbone_types(
                data_file=build_data_path,
            ), "backbone_types derivation")
            if derived.get("status") == "success" and derived.get("backbone_types"):
                backbone_types = derived["backbone_types"]
                cls["backbone_types"] = backbone_types
                plan_on_disk = load_plan(args.plan)
                plan_on_disk.setdefault("decided_params", {})["backbone_types"] = backbone_types
                atomic_write_json(Path(args.plan), plan_on_disk)
                backbone_derivation = {
                    "trigger": "backbone_types unresolved",
                    "action": f"auto-derived {backbone_types} from build_data_path bond topology "
                              "(heavy_atom_graph_diameter) and persisted to decided_params",
                    "outcome": "RESOLVED — automatic",
                }
            else:
                # Genuine last resort — the chain itself has fewer than 2 heavy atoms, or no bond
                # topology at all. inspect_data_file only for diagnostics attached to this halt.
                diag = lammps.inspect_data_file(
                    data_file=build_data_path, lj_cutoff=p["cutoff_A"] or 12.0,
                    target_density_gcm3=None, nchain=None,
                )
                detail = {
                    "reason": "bond-topology derivation could not resolve a backbone for this "
                              "cell: " + str(derived.get("error", "unknown")),
                    "atom_type_names": diag.get("info", {}).get("atom_type_names"),
                    "build_data_path": build_data_path,
                }
                return {"halted": True, "reason": "BACKBONE_TYPES_UNRESOLVED", "detail": detail,
                        "stage_checkpoints": stage_checkpoints}

        comp = wait_for_analysis(lammps, lammps.check_equilibration_comprehensive(
            log_file=p["npt_prod_log_path"], dump_file=p["melt_dump_path"],
            data_file=p["npt_prod_data_path"], backbone_types=backbone_types,
            ct_min_decay=p["ct_min_decay_melt"], output_dir=p["output_dir"], graphs_dir=p["graphs_dir"],
            cutoff_A=p["cutoff_A"], timestep_fs=p["dt_fs"],
        ), "equil-check comprehensive")
        density = wait_for_analysis(lammps, lammps.extract_equilibrated_density(
            log_file=p["npt_prod_log_path"], target_temp=p["npt_prod_temp_K"], output_dir=p["output_dir"],
        ), "equil-check density")
        comprehensive_json = str(Path(p["output_dir"]) / "equilibration.json")
        verdict = lammps.enforce_equilibration_gate(
            comprehensive_json=comprehensive_json, regime=p["regime"], dp=p["dp"],
            ct_gate_reliable=p["ct_gate_reliable"],
            tg_K=p["exp_tg_point_K"], t_equil_K=p["T_workflow_K"], glass_data=p["npt_prod_data_path"],
            melt_data=p["melt_data_path"], out_dir=p["output_dir"],
        )
        equil_verdict = verdict.get("verdict")

        if equil_verdict == "PASS":
            result = {"equil_verdict": "PASS", "npt_prod_data_path": p["npt_prod_data_path"],
                      "npt_prod_log_path": p["npt_prod_log_path"], "npt_prod_dump_path": npt_prod_dump_path,
                      "density_gcm3": density.get("plateau_density_mean"),
                      "velocity_seed": velocity_seed, "extend_history": extend_history,
                      "backbone_derivation": backbone_derivation,
                      "stage_checkpoints": stage_checkpoints}
            return result

        if equil_verdict == "EXTEND":
            tau_relax_ps = (((comp or {}).get("chain") or {}).get("ct") or {}).get("tau_relax_ps")
            if getattr(args, "engine_owned_recovery", False):
                detail = dict(verdict)
                if isinstance(tau_relax_ps, (int, float)) and tau_relax_ps > 0:
                    detail["relaxation_time_ns"] = tau_relax_ps / 1000.0
                return {"halted": True, "reason": "EXTEND", "detail": detail,
                        "npt_prod_data_path": p["npt_prod_data_path"],
                        "npt_prod_dump_path": npt_prod_dump_path,
                        "stage_checkpoints": stage_checkpoints}
            attempts += 1
            if attempts > EXTEND_MAX_ATTEMPTS:
                return {"halted": True, "reason": "EXTEND_EXHAUSTED",
                        "detail": {"attempts": attempts}, "stage_checkpoints": stage_checkpoints}
            # A measured relaxation signal from this run's own data beats a blind flat guess —
            # tau_relax_ps comes from the comprehensive check's KWW fit.
            extend_ns = 1.5
            if isinstance(tau_relax_ps, (int, float)) and tau_relax_ps > 0:
                extend_ns = max(1.5, round(1.5 * tau_relax_ps / 1000, 2))
            extend_history.append({"attempt": attempts, "trigger": "equil_verdict=EXTEND",
                                   "extend_ns": extend_ns, "tau_relax_ps": tau_relax_ps,
                                   "npt_prod_temp_K": p["npt_prod_temp_K"]})
            with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
                args.gpu_ids = gpu_ids
                submission = _submit_equil_chain(args, cls, lammps, extend_from_data=p["npt_prod_data_path"],
                                                 extend_temp=p["npt_prod_temp_K"], extend_ns=extend_ns)
                ext_result = wait_for_run(lammps, submission["chain_id"], "equilibration EXTEND")
            if ext_result.get("status") != "completed":
                raise SystemExit(f"EXTEND chain did not complete: {ext_result}")
            npt_prod_data_path = submission["workflow"]["stages"][0]["output_data"]
            npt_prod_dump_path = _stage_dump_path(submission["workflow"]["stages"][0])
            continue

        # Structural or protocol failures never trigger an implicit protocol change. Halt with
        # structured evidence for the recovery-agent boundary.
        return {"halted": True, "reason": equil_verdict, "detail": verdict,
                "stage_checkpoints": stage_checkpoints}


# ─── Stage: thermal track ──────────────────────────────────────────────────

def do_thermal(args, cls: dict, lammps) -> dict:
    """Single-rate-primary: run one sweep at the class's primary configured rate (highest by
    default; tg_slope_gate_fallback="slowest_rate" classes — PKTN, PSFO — run rates[0] instead,
    since their highest-rate fit is documented as degenerate/inverted)."""
    tg_rates = cls.get("tg_rates_K_per_ns", [])
    gpu_per_run = cls.get("gpu_per_run") or 1
    per_rate = []
    if tg_rates:
        fallback = cls.get("tg_slope_gate_fallback")
        planned_index = cls.get("tg_primary_rate_index")
        idx = (int(planned_index) if planned_index is not None else
               (0 if fallback == "slowest_rate" else len(tg_rates) - 1))
        if not 0 <= idx < len(tg_rates):
            return {"halted": True, "reason": "TG_PRIMARY_RATE_INDEX_INVALID",
                    "detail": {"index": idx, "n_rates": len(tg_rates)}}
        rate = tg_rates[idx]
        args.tg_rate_index = idx
        p = resolve_stage_params("tg", args, cls)
        with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
            args.gpu_ids = gpu_ids
            script = lammps.generate_script(
                template_name="npt_tg_step", data_file=p["equil_data_path"],
                output_script=f"{p['tg_sweep_dir']}/tg_sweep.in",
                velocity_seed=p["velocity_seed"],
                # The per-T dump (one final frame per temperature) is what extract_thermal's
                # structural block reads. The reasoned path's tg prompt already asks for it;
                # emit it here too so both paths produce the same artifacts.
                params={"LOG_FILE": "tg_sweep.log", "DUMP_FILE": "",
                       "WRITE_PER_T_DUMP": True, "PER_T_DUMP_FILE": "per_t_structs.dump",
                       "T_START": p["T_start_K"], "T_END": p["T_end_K"], "T_STEP": p["T_step_K"],
                       "N_STEPS_PER_T": p["n_steps_per_t"],
                       "T_DAMP": p["thermostat_damp_fs"],
                       "P_DAMP": p["barostat_damp_fs"],
                       "P_START": p["pressure_atm"], "P_FINAL": p["pressure_atm"],
                       "TIMESTEP": p["dt_fs"],
                       "use_pppm": p["use_long_range_electrostatics"] and not p["lammps_flags"]["use_trappe"],
                       "use_gpu": True, "engine": p["engine"], **{f"use_{k.split('_')[1]}": v
                       for k, v in p["lammps_flags"].items()}},
            )
            run = lammps.run_lammps_script(
                script=script["output_script"], work_dir=p["tg_sweep_dir"], log_file="tg_sweep_run.log",
                gpu_ids=p["gpu_ids"], mpi=p["mpi_ranks"], engine=p["engine"],
                data_file=p["equil_data_path"], lj_cutoff=p["cutoff_A"],
            )
            result = wait_for_run(lammps, run["run_id"], f"tg sweep rate={rate}")
        if result.get("status") != "completed":
            raise SystemExit(f"Tg sweep (rate={rate}) did not complete: {result}")

        ap = resolve_stage_params("analyze-tg", args, cls)
        thermal = wait_for_analysis(lammps, lammps.extract_thermal(
            log_file=ap["tg_log_path"], tg_data_file=ap["tg_data_file"],
            per_t_dump_file=ap["per_t_dump_file"], backbone_types=ap["backbone_types"],
            enthalpy_col=ap["enthalpy_col"], output_dir=ap["output_dir"], graphs_dir=ap["graphs_dir"],
            method_gap_exempt=ap["method_gap_exempt"],
        ), f"tg analysis rate={rate}")
        per_rate.append({"rate": rate, "Tg_K": thermal.get("Tg_K"),
                         "fit_quality": thermal.get("fit_quality"), "r_squared": thermal.get("r_squared"),
                         "output_dir": ap["output_dir"], "used_highest_rate": idx == len(tg_rates) - 1,
                         "tg_gate_verdict": thermal.get("tg_gate_verdict"),
                         "velocity_seed": p["velocity_seed"]})

    highest = per_rate[-1] if per_rate else None

    # is_glassy determination (THERMAL_TRACK.md's single-sweep algorithm): only trust this
    # sweep's Tg for is_glassy when it ran at the class's highest configured rate — a class that
    # deliberately ran the slowest rate instead (PKTN, PSFO) falls through to the exp-Tg
    # decision, the same outcome those classes got via the old slope-gate-failure path.
    degenerate = (not highest) or highest["fit_quality"] == "POOR" or not highest["used_highest_rate"]
    if degenerate:
        exp_tg_val = resolve_member_value(cls, "experimental_tg_K", getattr(args, "smiles", None))
        is_glassy = bool(exp_tg_val and exp_tg_val > 300)
    else:
        is_glassy = bool(highest and isinstance(highest["Tg_K"], (int, float)) and highest["Tg_K"] > 300)

    result = {"per_rate": per_rate, "is_glassy": is_glassy,
              "tg_gate_verdict": (highest or {}).get("tg_gate_verdict")}
    return result


# ─── Stage: mechanical track ────────────────────────────────────────────────

def _submit_deform(args, cls: dict, lammps, mode: str) -> dict:
    args.deform_rate_mode = mode
    p = resolve_stage_params("deform", args, cls)
    rate_key = "K_deform_rate_inv_s" if mode == "primary" else "K_deform_rate_slow_inv_s"
    rate_val = p["K_deform_rate_inv_s"] if mode == "primary" else p["K_deform_rate_slow_inv_s"]
    if mode == "slow" and (rate_val in (None, "null")):
        return None  # class has no slow rate defined — no-op, matches deform-worker's guard
    suffix = "" if mode == "primary" else "_slow"
    strain_rate_per_fs = float(rate_val) * 1e-15
    script = lammps.generate_script(
        template_name="npt_deform", data_file=p["equil_data_path"],
        output_script=f"{p['work_dir']}/05_deform{suffix}.in",
        velocity_seed=p["velocity_seed"],
        # STRAIN_MAX drives N_STEPS inside generate_script (N_STEPS = STRAIN_MAX /
        # (STRAIN_RATE * TIMESTEP)); the template itself has no STRAIN_MAX placeholder, so
        # passing it without N_STEPS used to leave the deck on the 300000-step default.
        params={"LOG_FILE": f"05_deform{suffix}.log", "STRAIN_RATE": strain_rate_per_fs,
               "STRAIN_MAX": p["K_strain_max"], "N_EQ_STEPS": p["deform_eq_steps"],
               "T_DAMP": p["thermostat_damp_fs"],
               "use_pppm": cls.get("electrostatics", "pppm") == "pppm"
                           and not p["lammps_flags"]["use_trappe"],
               "TIMESTEP": p["dt_fs"], "use_gpu": True,
               "engine": p["engine"], **p["lammps_flags"]},
    )
    run = lammps.run_lammps_script(
        script=script["output_script"], work_dir=p["work_dir"], log_file=f"05_deform{suffix}.log",
        gpu_ids=p["gpu_ids"], mpi=p["mpi_ranks"], engine=p["engine"],
        data_file=p["equil_data_path"], lj_cutoff=p["cutoff_A"],
    )
    return {"run_id": run["run_id"], "log_path": f"{p['work_dir']}/05_deform{suffix}.log"}


def do_mechanical(args, cls: dict, lammps, is_glassy: bool, npt_prod_data_path: str) -> dict:
    args.is_glassy = "true" if is_glassy else "false"
    gpu_per_run = cls.get("gpu_per_run") or 1
    p = resolve_stage_params("murnaghan", args, cls)
    # ced_mpa (cohesive energy density) has no producer anywhere in this codebase yet --
    # select_pressure_ladder already treats None as "no CED-informed adjustment".
    pressure_selection = select_pressure_ladder(
        configured_pressures=p["bm_pressures_atm"], ced_mpa=None,
    )

    point_status = {}
    analysis_logs = []
    analysis_pressures = []
    point_state_path = Path(p["work_dir"]) / "pressure_points.json"
    for pressure in dict.fromkeys(pressure_selection.pressures_atm):
        point = {"pressure_atm": pressure, "status": "failed", "attempts": []}
        for point_attempt in range(1, 3):
            with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
                args.gpu_ids = gpu_ids
                series = lammps.run_bulk_modulus_series(
                    data_file=p["equil_data_path"],
                    work_dir=f"{p['work_dir']}/bm_series/p_{pressure:g}/attempt_{point_attempt}",
                    pressures_atm=[pressure], temp_K=p["temp_K"], run_name=args.run_name,
                    gpu_ids=p["gpu_ids"], mpi=p["mpi_ranks"], velocity_seed=p["velocity_seed"],
                    npt_steps=p["npt_steps"], dt_fs=p["dt_fs"],
                    thermo_freq=p["thermo_freq"],
                    thermostat_damp_fs=p["thermostat_damp_fs"],
                    barostat_damp_fs=p["barostat_damp_fs"],
                    use_long_range=cls.get("electrostatics", "pppm") == "pppm",
                    use_trappe=p["lammps_flags"]["use_trappe"],
                    use_pcff=p["lammps_flags"]["use_pcff"],
                    use_opls=p["lammps_flags"]["use_opls"], engine=p["engine"],
                )
                if series.get("status") == "error":
                    point["attempts"].append({"attempt": point_attempt, "status": "failed",
                                              "detail": series})
                    continue
                m_result = wait_for_run(lammps, series["chain_id"],
                                        f"murnaghan pressure={pressure:g}")
            point["attempts"].append({"attempt": point_attempt,
                                      "status": m_result.get("status"), "detail": m_result})
            if m_result.get("status") == "completed":
                point["status"] = "accepted"
                point["log_file"] = series["log_files"][0]
                analysis_logs.append(series["log_files"][0])
                analysis_pressures.append(pressure)
                break
        point_status[str(pressure)] = point
        atomic_write_json(point_state_path, {"points": point_status})

    status_for_policy = {float(key): value["status"] for key, value in point_status.items()}
    if any(value != "accepted" for value in status_for_policy.values()) and not pressure_point_drop_allowed(status_for_policy):
        result = {"method": "murnaghan", "point_status": point_status,
                  "workflow_finding": {"code": "MECHANICAL_IDENTIFIABILITY_FAILED",
                                       "details": {"point_status": point_status}}}
        return result

    bp = resolve_stage_params("analyze-bm", args, cls)
    prior_murn = cls.get("_prior_murnaghan_result") or {}
    if prior_murn and cls.get("mechanical_resample_points"):
        combined = dict(zip(prior_murn.get("pressures_atm") or (),
                            prior_murn.get("log_files") or ()))
        combined.update(zip(analysis_pressures, analysis_logs))
        analysis_pressures = sorted(combined)
        analysis_logs = [combined[pressure] for pressure in analysis_pressures]
    murn = wait_for_analysis(lammps, lammps.extract_bulk_modulus_murnaghan(
        log_files=analysis_logs, pressures_atm=analysis_pressures,
        output_dir=bp["output_dir"], graphs_dir=bp["graphs_dir"],
        npt_prod_log=bp["npt_prod_log_path"],
    ), "bulk modulus (murnaghan)")
    # Optimizer convergence is diagnostic only. Scientific acceptance is owned by the
    # reportability gate emitted by the analysis.
    accepted = murn.get("bm_gate_verdict") == "BM_REPORTABLE"

    if accepted:
        result = {"method": "murnaghan", "bulk_modulus_GPa": murn.get("bulk_modulus_GPa"),
                  "B0_prime": murn.get("B0_prime"),
                  "bm_gate_verdict": murn.get("bm_gate_verdict"),
                  "bm_gate_reasons": murn.get("bm_gate_reasons"),
                  "murnaghan_result": murn, "velocity_seed": p["velocity_seed"],
                  "pressure_selection": pressure_selection.to_dict()}
        return result

    result = {"method": "murnaghan", "bulk_modulus_GPa": murn.get("bulk_modulus_GPa"),
              "accepted": False, "reason": murn.get("bm_gate_verdict") or "BM_INADMISSIBLE",
              "bm_gate_verdict": murn.get("bm_gate_verdict"),
              "bm_gate_reasons": murn.get("bm_gate_reasons"), "is_glassy": is_glassy,
              "murnaghan_result": murn, "velocity_seed": p["velocity_seed"],
              "pressure_selection": pressure_selection.to_dict()}
    return result


def do_deformation(args, cls: dict, lammps) -> dict:
    """Run and gate the deformation fallback selected by the workflow engine."""
    gpu_per_run = cls.get("gpu_per_run") or 1
    with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
        args.gpu_ids = gpu_ids
        primary = _submit_deform(args, cls, lammps, "primary")
        d_result = wait_for_run(lammps, primary["run_id"], "deform primary")
    if d_result.get("status") != "completed":
        raise SystemExit(f"Deform (primary) did not complete: {d_result}")

    slow_log = None
    with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
        args.gpu_ids = gpu_ids
        slow = _submit_deform(args, cls, lammps, "slow")
        if slow is not None:
            s_result = wait_for_run(lammps, slow["run_id"], "deform slow")
            if s_result.get("status") == "completed":
                slow_log = slow["log_path"]

    bp = resolve_stage_params("analyze-bm", args, cls)
    deform_extract = wait_for_analysis(lammps, lammps.extract_bulk_modulus_deform(
        log_file=primary["log_path"], output_dir=bp["output_dir"], graphs_dir=bp["graphs_dir"],
        strain_rate=bp["strain_rate_per_fs"], strain_max=bp["K_strain_max"],
        # eps(step) = strain_rate * (step - step_0) * timestep -- must be the deck's own dt,
        # or a dt_fs != 1.0 class reports the strain, and hence K, off by that ratio.
        timestep=bp["dt_fs"],
        eq_steps=bp["deform_eq_steps"], strain_start=bp["deform_strain_start"],
        avg_window=bp["deform_avg_window"],
        **({"log_file_2": slow_log, "strain_rate_2": bp["strain_rate_slow_per_fs"]} if slow_log else {}),
    ), "bulk modulus (deform)")
    result = {"method": "deformation", "bulk_modulus_GPa": deform_extract.get("bulk_modulus_GPa"),
             "shear_modulus_GPa": deform_extract.get("shear_modulus_GPa"),
             "youngs_modulus_GPa": deform_extract.get("youngs_modulus_GPa"),
             "deform_gate_verdict": deform_extract.get("deform_gate_verdict"),
             "deform_gate_reasons": deform_extract.get("deform_gate_reasons"),
             "rate_sensitivity": deform_extract.get("rate_sensitivity"),
             "velocity_seed": resolve_stage_params("deform", args, cls)["velocity_seed"]}
    return result


# ─── Stage: summary ─────────────────────────────────────────────────────────

def do_summary(args, cls: dict, lammps, is_glassy: bool, thermal_result, equil_verdict: str,
               raw_dir: Path) -> dict:
    exp_lookup_path = raw_dir / "exp_lookup.json"
    properties = ({"density", "tg", "bulk_modulus"} if args.properties in (None, "all")
                  else {x.strip().lower() for x in args.properties.split(",") if x.strip()})
    # Provenance only: writes exp_lookup.json (the same artifact the exp-lookup-worker
    # produces) for a human to review. Deliberately NOT auto-applied into args.exp_*_min/max --
    # query_best_match.py's raw aggregates (pooled medians, single-point K rows at the wrong
    # condition) need human judgment before they can override a class's own cited
    # polymer_rules.json values; _resolve_run_summary_params's own priority chain (CLI >
    # polymer_rules > DB fallback) is what actually grades the run.
    subprocess.run([
        sys.executable, str(REPO_ROOT / "db" / "query_best_match.py"),
        "--polymer_name", args.polymer_name or args.run_name, "--polymer_class", args.polymer_class.upper(),
        "--T_sim_K", "300.0", "--is_glassy", "true" if is_glassy else "false",
        "--properties", ",".join(sorted(properties)), "--output_path", str(exp_lookup_path),
    ], check=False)

    tg_path = None
    if thermal_result is not None:
        # Single-rate-primary: the one sweep's thermal.json path is already known from the
        # analyze-tg stage's own output_dir — no rate ambiguity to resolve.
        if thermal_result.get("per_rate"):
            tg_path = str(Path(thermal_result["per_rate"][-1]["output_dir"]) / "thermal.json")
        args.tg_path = tg_path
        args.tg_fit_quality = (thermal_result["per_rate"][-1]["fit_quality"]
                               if thermal_result.get("per_rate") else "N/A (not requested)")

    # do_summary is only reached after equil_check returned PASS, but read the real verdict
    # (rather than assume the string) so a future non-PASS path to this stage can't silently lie.
    args.d05 = equil_verdict or "PASS"
    sp = resolve_stage_params("run-summary", args, cls)
    summary = wait_for_analysis(lammps, lammps.generate_run_summary(
        output_dir=sp["output_dir"], graphs_dir=sp["graphs_dir"], run_name=args.run_name,
        smiles=args.smiles or "", polymer_class=args.polymer_class.upper(), ff=sp["ff"],
        charge_method=sp["charge_method"] or "", dp=sp["dp"], n_chains=sp["nchain"],
        d01=sp["d01_ff"], d02=sp["d02_charges"], d03=sp["d03_electrostatics"], d04=sp["d04_system_size"],
        d05=args.d05, d06=args.tg_fit_quality or "N/A (not requested)",
        n_replicates=args.n_replicates, tg_path=tg_path,
    ), "run-summary generation")
    summary["run_summary_path"] = str(Path(sp["output_dir"]) / "run_summary.json")
    return summary


# ─── Dry-run mode ───────────────────────────────────────────────────────────

def _print_dry_run(args, cls: dict, properties: set):
    """Resolve every applicable stage without submitting anything."""
    stages = ["build", "equil", "equil-check"]
    if "tg" in properties:
        stages += ["tg", "analyze-tg"]
    if "bulk_modulus" in properties:
        stages += ["murnaghan", "deform", "analyze-bm"]
    stages.append("run-summary")
    out = {}
    for stage in stages:
        try:
            out[stage] = resolve_stage_params(stage, args, cls)
        except Exception as e:  # noqa: BLE001 — dry-run reports, never crashes on one stage
            out[stage] = {"error": str(e)}
    print(json.dumps(out, indent=2, default=str))


# ─── In-process engine adapter and CLI ──────────────────────────────────────

class CampaignStageExecutor:
    """Adapt the deterministic simulation functions to :class:`WorkflowEngine`.

    All writable resolver paths are redirected into the current attempt. Dependencies are
    taken exclusively from accepted manifests supplied by the engine.
    """

    def __init__(self, args, cls: dict, emc, lammps, plan_path: str):
        self.args = args
        self.base_cls = dict(cls)
        self.emc = emc
        self.lammps = lammps
        self.plan_path = plan_path

    @staticmethod
    def _outputs(context: dict, stage: str) -> dict:
        return dict(context.get("dependencies", {}).get(stage, {}).get("outputs") or {})

    def execute(self, stage: str, context: dict) -> StageResult:
        attempt_dir = Path(context["attempt_dir"])
        args = self.args
        cls = {**self.base_cls, **context["parameters"]}
        args.engine_owned_recovery = True
        if stage == "mechanical" and context["parameters"].get("mechanical_resample_points"):
            for prior in reversed(context.get("prior_attempts") or ()):
                manifest_path = prior.get("manifest")
                if not manifest_path or not Path(manifest_path).is_file():
                    continue
                prior_outputs = json.loads(Path(manifest_path).read_text()).get("outputs") or {}
                if prior_outputs.get("murnaghan_result"):
                    cls["_prior_murnaghan_result"] = prior_outputs["murnaghan_result"]
                    break
        for key, value in context["parameters"].items():
            if hasattr(args, key):
                setattr(args, key, value)
        args.work_dir = str(attempt_dir / "work")
        args.output_dir = str(attempt_dir / "raw")
        build = self._outputs(context, "build")
        equil = self._outputs(context, "equilibration")
        thermal = self._outputs(context, "thermal") or None
        if build:
            args.data_path = build.get("data_path")
            args.build_data_path = build.get("data_path")
            args.emc_params_path = build.get("emc_params_path")
            args.n_atoms = build.get("n_atoms")
        if equil:
            args.data_path = equil.get("npt_prod_data_path")
        if stage == "equilibration" and context["parameters"].get("npt_continuation_ns"):
            for prior in reversed(context.get("prior_attempts") or ()):
                manifest_path = prior.get("manifest")
                if not manifest_path or not Path(manifest_path).is_file():
                    continue
                prior_outputs = json.loads(Path(manifest_path).read_text()).get("outputs") or {}
                if prior_outputs.get("npt_prod_data_path"):
                    args.pending_continuation_path = prior_outputs["npt_prod_data_path"]
                    args.npt_continuation_ns = context["parameters"]["npt_continuation_ns"]
                    break
        # equilibration_resume_from: set by a remedy (melt_hold -> "anneal", a future
        # npt_cool300 remedy -> "npt_production") to signal do_equil_and_check should resume a
        # generate_equilibration_workflow(resume_from=...) chain instead of a fresh from-scratch
        # submission. Locate the real checkpoint from the most recent prior attempt's own
        # stage_checkpoints (do_equil_and_check surfaces it on every return, halted or not) --
        # same reversed(prior_attempts) walk as npt_continuation_ns above.
        if stage == "equilibration" and cls.get("equilibration_resume_from") in ("anneal", "npt_production"):
            resume_kind = cls["equilibration_resume_from"]
            for prior in reversed(context.get("prior_attempts") or ()):
                manifest_path = prior.get("manifest")
                if not manifest_path or not Path(manifest_path).is_file():
                    continue
                prior_manifest = json.loads(Path(manifest_path).read_text())
                checkpoints = (prior_manifest.get("outputs") or {}).get("stage_checkpoints") or {}
                if resume_kind == "npt_production":
                    if checkpoints.get("npt_production"):
                        args.equil_resume_from = "npt_production"
                        args.equil_resume_data_path = checkpoints["npt_production"]
                        break
                else:  # "anneal"
                    # How many cycles the MOST RECENT attempt actually ran -- not
                    # baseline_eq_annealing_cycles, which _melt_hold freezes at the value from
                    # BEFORE the first rung ever fired and reuses unchanged across both rungs.
                    prior_cycles = int((prior_manifest.get("parameters") or {})
                                      .get("eq_annealing_cycles") or 0)
                    checkpoint_name = f"anneal_{prior_cycles:02d}_cool" if prior_cycles > 0 else "minimize"
                    if checkpoints.get(checkpoint_name):
                        args.equil_resume_from = "anneal"
                        args.equil_resume_data_path = checkpoints[checkpoint_name]
                        new_cycles = int(cls.get("eq_annealing_cycles") or 0)
                        args.equil_resume_anneal_cycles = max(0, new_cycles - prior_cycles)
                        break
        try:
            if stage == "build":
                outputs = do_build(args, cls, self.emc, self.lammps)
            elif stage == "equilibration":
                outputs = do_equil_and_check(args, cls, self.lammps)
                if outputs.get("halted"):
                    code = outputs.get("reason") or "STRUCTURAL_FAIL"
                    detail = outputs.get("detail") or {}
                    if code == "STRUCTURAL_FAIL":
                        # finite_size_verdict is "SIZE_PASS" (a truthy string) whenever finite
                        # size was merely evaluated, pass or fail -- the common case is it
                        # passed while a *different* gate (cooling_verdict, homogeneity) is the
                        # real failure. An `or` chain on truthiness alone picked "SIZE_PASS" over
                        # the actual cause every time finite_size happened to pass, misrouting
                        # the finding to a code with no registered remedy. Only prefer it when it
                        # names a real failure (enforce_gate.py's own vocabulary: SIZE_MIN_IMAGE_
                        # VIOLATION | SIZE_CHAIN_SELF_IMAGE | SIZE_PASS | None).
                        finite_size_code = detail.get("finite_size_verdict")
                        code = (finite_size_code
                                if finite_size_code not in (None, "SIZE_PASS") else
                                detail.get("cooling_verdict") or
                                ("DENSITY_HETEROGENEITY"
                                 if detail.get("homogeneity_verdict") == "HOMOG_HETEROGENEOUS"
                                 else code))
                    confidence = detail.get("remedy_confidence") or "high"
                    return StageResult("remedy_required",
                                       (Finding(code, stage, confidence=confidence,
                                                details=detail),),
                                       self._artifacts(attempt_dir), outputs)
            elif stage == "thermal":
                outputs = do_thermal(args, cls, self.lammps)
            elif stage == "mechanical":
                is_glassy = (thermal.get("is_glassy") if thermal else
                              resolve_stage_params("equil", args, cls)["T_workflow_K"] != 300.0)
                if context["parameters"].get("mechanical_method") == "deformation":
                    args.is_glassy = "true" if is_glassy else "false"
                    outputs = do_deformation(args, cls, self.lammps)
                else:
                    outputs = do_mechanical(args, cls, self.lammps, is_glassy, args.data_path)
            elif stage == "summary":
                is_glassy = (thermal.get("is_glassy") if thermal else
                              resolve_stage_params("equil", args, cls)["T_workflow_K"] != 300.0)
                outputs = do_summary(args, cls, self.lammps, is_glassy, thermal,
                                     equil.get("equil_verdict"), attempt_dir / "raw")
            else:
                raise ValueError(f"unknown workflow stage {stage!r}")
        except SystemExit as exc:
            message = str(exc)
            code = "PROCESS_FAILED"
            details = dict(getattr(exc, "details", {}))
            details["error"] = message
            if "preferred_builder" in message:
                code = "UNSUPPORTED_BUILDER"
            elif "SIZE_" in message:
                code = next((token.strip(".,:") for token in message.split()
                             if token.startswith("SIZE_")), "FINITE_SIZE_FAILED")
                details["nchain"] = cls.get("nchain")
            return StageResult("failed", (Finding(code, stage, details=details),),
                               self._artifacts(attempt_dir))
        if outputs and outputs.get("halted"):
            details = outputs.get("detail") or {}
            finding = Finding(outputs.get("reason") or "STAGE_HALTED", stage,
                              confidence=details.get("remedy_confidence", "high"),
                              details=details)
            return StageResult("escalation_required", (finding,),
                               self._artifacts(attempt_dir), outputs)
        if outputs and outputs.get("workflow_finding"):
            finding = Finding.from_value(outputs["workflow_finding"], stage)
            return StageResult("escalation_required", (finding,), self._artifacts(attempt_dir),
                               outputs)
        return StageResult("accepted", (), self._artifacts(attempt_dir), outputs or {})

    # mcp-lammps-engine's own chain-completion housekeeping (_cleanup_chain_files in
    # server.py) unconditionally deletes these once a chain reaches "completed" -- they are
    # transient launcher scaffolding (the wrapper shell script, its progress feed, and its
    # captured stdout log on success), never a real simulation artifact. A live rglob() here
    # can still catch one moments before that async cleanup removes it, and _finish_attempt's
    # later re-check of the same declared path then crashes on a file that was never meant to
    # persist -- a real TOCTOU race hit on the PE1 2026-08-17 run. Exclude by the exact naming
    # convention _cleanup_chain_files uses, not by directory, so real per-stage LAMMPS logs
    # (which live nested one level down, e.g. work/npt_production/npt_production.log) are
    # unaffected.
    _TRANSIENT_CHAIN_FILE = re.compile(r"^chain_[^/]+(\.sh|\.log|_progress\.jsonl)$")

    @classmethod
    def _artifacts(cls, attempt_dir: Path) -> tuple[str, ...]:
        excluded = {"manifest.json", "executor_state.json"}
        return tuple(str(path) for path in sorted(attempt_dir.rglob("*"))
                     if path.is_file() and path.name not in excluded
                     and not cls._TRANSIENT_CHAIN_FILE.match(path.name))


def run_campaign_workflow(plan_path: Path, *, dry_run: bool = False,
                          repo_root: Path = REPO_ROOT, recovery_agent=None) -> dict:
    """Start or resume an entire campaign; stages are never externally selectable."""
    plan_path = Path(plan_path)
    plan = load_plan(str(plan_path))
    run_name = plan["run_name"]
    polymer_class = plan["polymer_class"]
    rules = load_rules()
    cls_raw = get_class_entry(rules, polymer_class, warn_on_miss=False)
    args = _base_args(run_name, polymer_class, str(plan_path))
    cls = apply_plan(cls_raw, plan, args)
    resolve_hardware(args, cls, rules)
    properties = set(plan.get("properties") or ())
    args.properties = ",".join(sorted(properties))
    if dry_run:
        stages = ["build", "equil", "equil-check"]
        if "tg" in properties:
            stages += ["tg", "analyze-tg"]
        if "bulk_modulus" in properties:
            stages += ["murnaghan", "deform", "analyze-bm"]
        stages.append("run-summary")
        return {name: resolve_stage_params(name, args, cls) for name in stages}
    lammps = _load_server_module("lammps_engine_server", LAMMPS_ENGINE_DIR / "server.py",
                                 LAMMPS_ENGINE_DIR, _mcp_env("mcp-lammps-engine"))
    emc = _load_server_module("emc_server_module", EMC_SERVER_DIR / "server.py",
                              EMC_SERVER_DIR, _mcp_env("mcp-emc-server"))
    run_dir = repo_root / "data" / run_name
    policy_hashes = {}
    for path in (repo_root / "guides" / "polymer_rules.json",
                 repo_root / "orchestration" / "decision_policy.json"):
        if path.exists():
            policy_hashes[str(path.relative_to(repo_root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    executor = CampaignStageExecutor(args, cls, emc, lammps, str(plan_path))
    decision_policy = json.loads((repo_root / "orchestration" / "decision_policy.json").read_text())
    engine_result = WorkflowEngine(run_dir, plan, executor, recovery_agent=recovery_agent,
                                   policy_hashes=policy_hashes, plan_path=plan_path,
                                   plan_validator=lambda candidate: validate_plan(candidate, decision_policy),
                                   override_validator=validate_overrides).run()
    if engine_result.get("status") == "accepted":
        # Freeze this run's actually-executed protocol into system_characterization_cache.json so
        # a future run of the exact same SMILES can replay it instead of re-deriving class
        # defaults (make_deterministic_plan.py's make_plan_from_cache). This is the single choke
        # point for every route that reaches an accepted WorkflowEngine result -- both a fresh
        # scientific_control.py-driven run (Workflow.execute() calls run_campaign_workflow
        # internally) and a campaign resumed directly via `run_campaign.py --plan`, which never
        # passes through scientific_control.py's own control_state.json bookkeeping at all.
        try:
            from write_characterization_cache import write_characterization_cache
            write_characterization_cache(run_name, repo_root=repo_root)
        except Exception as exc:  # never fail an accepted campaign on a cache-write problem
            print(f"WARNING: system_characterization_cache write failed for {run_name}: {exc}",
                 file=sys.stderr)
    return engine_result


def main():
    ap = argparse.ArgumentParser(description="Start or resume a deterministic PolyJarvis workflow.")
    ap.add_argument("--plan", required=True, help="Path to run_plan.json")
    ap.add_argument("--run_name", help="Optional consistency check against plan.run_name")
    ap.add_argument("--polymer_class", help="Optional consistency check against plan.polymer_class")
    ap.add_argument("--dry-run", action="store_true")
    args_cli = ap.parse_args()
    if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve() and not args_cli.dry_run:
        os.execv(str(VENV_PY), [str(VENV_PY), str(Path(__file__).resolve())] + sys.argv[1:])
    plan_identity = load_plan(args_cli.plan)
    if args_cli.run_name and args_cli.run_name != plan_identity.get("run_name"):
        ap.error("--run_name does not match the plan")
    if (args_cli.polymer_class and
            args_cli.polymer_class.upper() != str(plan_identity.get("polymer_class", "")).upper()):
        ap.error("--polymer_class does not match the plan")
    print(json.dumps(run_campaign_workflow(Path(args_cli.plan), dry_run=args_cli.dry_run),
                     indent=2, default=str))


if __name__ == "__main__":
    main()
