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
_ENGINE_SCRIPTS = REPO_ROOT / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"
if str(_ENGINE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_ENGINE_SCRIPTS))

from stage_params import (resolve_stage_params, apply_plan, resolve_hardware, load_plan,  # noqa: E402
                          select_primary_tg_rate_index)
from analysis_utils import estimate_fluctuation_K_GPa  # noqa: E402
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
                         extend_base_stage: str = None, extend_ensemble: str = "npt",
                         extend_temp_K: float = None,
                         resume_from: str = None, resume_data_path: str = None,
                         stop_after_stage: str = None) -> dict:
    """resume_from is one of generate_equilibration_workflow's 8 checkpoint names (see
    server.py) -- e.g. "anneal_hold" to regenerate cooling+tail with different parameters
    after a remedy adjusts them, or "cool_block"/"nvt_kinetic_stability" to redo only the
    tail. extend_from_data (paired with extend_base_stage/extend_ensemble) is a genuine
    restart-continuation of one already-run adaptive stage, not a resubmission.

    stop_after_stage (fresh-chain submissions only, i.e. extend_from_data and resume_from both
    None): submit only the leading slice of the 8-stage protocol through and including this
    stage name, e.g. "anneal_hold" for the anneal_hold_msid_gate's chain 1. A plain client-side
    slice of workflow["stages"]/["run_order"] before run_lammps_chain -- generate_
    equilibration_workflow itself is untouched, it always plans the full chain; only the
    submitted subset changes."""
    p = resolve_stage_params("equil", args, cls)
    flags = p["lammps_flags"]
    velocity_seed = p["velocity_seed"]
    if resume_from is not None:
        workflow = lammps.generate_equilibration_workflow(
            data_file=resume_data_path, work_dir_base=p["work_dir"],
            temp=p["T_workflow_K"], max_temp=p["T_anneal_high_K"],
            anneal_margin_K=p["anneal_margin_K"], final_T_K=p["final_T_K"],
            max_press=p["compression_max_pressure_atm"],
            warmup_steps=p["warmup_steps"],
            densify_ramp_steps=p["densify_ramp_steps"],
            densify_check_every_steps=p["densify_check_every_steps"],
            densify_steps_cap=p["densify_steps_cap"],
            ff_activate_npt_steps=p["ff_activate_npt_steps"],
            anneal_heat_steps=p["anneal_heat_steps"],
            anneal_check_every_steps=p["anneal_check_every_steps"],
            anneal_cap_steps=p["anneal_cap_steps"],
            cool_block_dT_K=p["cool_block_dT_K"],
            cool_block_hold_steps=p["cool_block_hold_steps"],
            cool_block_hold_cap_steps=p["cool_block_hold_cap_steps"],
            stage7_min_steps=p["stage7_min_steps"], stage7_cap_steps=p["stage7_cap_steps"],
            stage8_min_steps=p["stage8_min_steps"], stage8_cap_steps=p["stage8_cap_steps"],
            t_equil_K=p["t_equil_K"], tg_start_T_K=p["tg_start_T_K"],
            melt_hold_extra_steps=p["melt_hold_extra_steps"],
            params_file="",
            resume_from=resume_from,
            polymer_name=args.run_name, press=p["P_equil_atm"],
            use_pcff=flags["use_pcff"], use_trappe=flags["use_trappe"], use_opls=flags["use_opls"],
            engine=p["engine"], velocity_seed=velocity_seed,
            thermostat_damp_fs=p["thermostat_damp_fs"], barostat_damp_fs=p["barostat_damp_fs"],
            use_long_range=p["use_long_range_electrostatics"],
        )
    elif extend_from_data is None:
        workflow = lammps.generate_equilibration_workflow(
            data_file=p["data_path"], work_dir_base=p["work_dir"],
            temp=p["T_workflow_K"], max_temp=p["T_anneal_high_K"],
            anneal_margin_K=p["anneal_margin_K"], final_T_K=p["final_T_K"],
            max_press=p["compression_max_pressure_atm"],
            warmup_steps=p["warmup_steps"],
            densify_ramp_steps=p["densify_ramp_steps"],
            densify_check_every_steps=p["densify_check_every_steps"],
            densify_steps_cap=p["densify_steps_cap"],
            ff_activate_npt_steps=p["ff_activate_npt_steps"],
            anneal_heat_steps=p["anneal_heat_steps"],
            anneal_check_every_steps=p["anneal_check_every_steps"],
            anneal_cap_steps=p["anneal_cap_steps"],
            cool_block_dT_K=p["cool_block_dT_K"],
            cool_block_hold_steps=p["cool_block_hold_steps"],
            cool_block_hold_cap_steps=p["cool_block_hold_cap_steps"],
            stage7_min_steps=p["stage7_min_steps"], stage7_cap_steps=p["stage7_cap_steps"],
            stage8_min_steps=p["stage8_min_steps"], stage8_cap_steps=p["stage8_cap_steps"],
            t_equil_K=p["t_equil_K"], tg_start_T_K=p["tg_start_T_K"],
            melt_hold_extra_steps=p["melt_hold_extra_steps"],
            params_file=p.get("emc_params_path") or "",
            minimize_etol=p["minimize_etol"], minimize_ftol=p["minimize_ftol"],
            minimize_maxiter=p["minimize_maxiter"], minimize_maxeval=p["minimize_maxeval"],
            polymer_name=args.run_name, press=p["P_equil_atm"],
            use_pcff=flags["use_pcff"], use_trappe=flags["use_trappe"], use_opls=flags["use_opls"],
            engine=p["engine"], velocity_seed=velocity_seed,
            thermostat_damp_fs=p["thermostat_damp_fs"], barostat_damp_fs=p["barostat_damp_fs"],
            use_long_range=p["use_long_range_electrostatics"],
        )
    else:
        # Genuine restart-continuation of extend_base_stage's own trajectory (read_restart,
        # appended log/dump) -- NOT a fresh stage. extend_from_data is that stage's own
        # .restart file (not a .data file); extend_temp_K is required for a cool_block_NN
        # (its hold temperature can't be inferred from the name alone).
        dt = p["dt_fs"]
        extend_steps_val = int(extend_ns * 1e6 / dt)
        base = extend_base_stage or "npt_final"
        override = {
            "npt_densify_hold": {"densify_check_every_steps": extend_steps_val},
            "anneal_hold": {"anneal_check_every_steps": extend_steps_val},
            "nvt_kinetic_stability": {"stage7_min_steps": extend_steps_val},
            "npt_final": {"stage8_min_steps": extend_steps_val},
        }.get(base, {"cool_block_hold_steps": extend_steps_val})
        workflow = lammps.generate_equilibration_workflow(
            data_file=p["data_path"], work_dir_base=p["work_dir"],
            temp=extend_temp if extend_temp is not None else p["T_workflow_K"],
            max_temp=p["T_anneal_high_K"], anneal_margin_K=p["anneal_margin_K"],
            final_T_K=p["final_T_K"], max_press=p["compression_max_pressure_atm"],
            warmup_steps=p["warmup_steps"], densify_ramp_steps=p["densify_ramp_steps"],
            densify_check_every_steps=override.get("densify_check_every_steps",
                                                    p["densify_check_every_steps"]),
            densify_steps_cap=p["densify_steps_cap"],
            ff_activate_npt_steps=p["ff_activate_npt_steps"],
            anneal_heat_steps=p["anneal_heat_steps"],
            anneal_check_every_steps=override.get("anneal_check_every_steps",
                                                  p["anneal_check_every_steps"]),
            anneal_cap_steps=p["anneal_cap_steps"], cool_block_dT_K=p["cool_block_dT_K"],
            cool_block_hold_steps=override.get("cool_block_hold_steps",
                                               p["cool_block_hold_steps"]),
            cool_block_hold_cap_steps=p["cool_block_hold_cap_steps"],
            stage7_min_steps=override.get("stage7_min_steps", p["stage7_min_steps"]),
            stage7_cap_steps=p["stage7_cap_steps"],
            stage8_min_steps=override.get("stage8_min_steps", p["stage8_min_steps"]),
            stage8_cap_steps=p["stage8_cap_steps"],
            t_equil_K=p["t_equil_K"], tg_start_T_K=p["tg_start_T_K"],
            melt_hold_extra_steps=p["melt_hold_extra_steps"],
            extend_only=True, restart_file=extend_from_data, base_stage_name=base,
            extend_ensemble=extend_ensemble, extend_temp_K=extend_temp_K,
            polymer_name=args.run_name, press=p["P_equil_atm"],
            use_pcff=flags["use_pcff"], use_trappe=flags["use_trappe"], use_opls=flags["use_opls"],
            engine=p["engine"], velocity_seed=velocity_seed,
            thermostat_damp_fs=p["thermostat_damp_fs"], barostat_damp_fs=p["barostat_damp_fs"],
            use_long_range=p["use_long_range_electrostatics"],
        )
    if workflow.get("status") == "error":
        raise SystemExit(f"generate_equilibration_workflow failed: {workflow}")

    if stop_after_stage is not None:
        run_order = workflow.get("run_order") or [s["name"] for s in workflow["stages"]]
        idx = run_order.index(stop_after_stage)
        workflow = {**workflow, "stages": workflow["stages"][:idx + 1],
                    "run_order": run_order[:idx + 1]}

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


def _resolve_backbone_types(args, cls: dict, lammps, build_data_path: str, p: dict):
    """Resolve backbone_types (from decided_params, else auto-derived from bond topology and
    persisted). Returns (backbone_types, backbone_derivation, halt_detail) -- exactly one of
    backbone_types or halt_detail is non-None. Factored out of do_equil_and_check's while-loop
    so the anneal_hold_msid_gate's chain-1-only probe (which needs backbone_types before chain
    2 even exists) and the post-chain equil-check loop share one derive-or-halt path."""
    backbone_types = p["backbone_types"]
    if backbone_types is not None:
        return backbone_types, None, None
    # Atom-name-only lookup can't tell backbone from pendant-branch atoms (confirmed live:
    # PACR/PMMA shares a generic aliphatic carbon type between CH2 backbone atoms and pendant
    # methyl branches) — but bond TOPOLOGY can: derive_backbone_types walks the heavy-atom bond
    # graph's diameter, which needs no types at all and excludes branches by construction (they
    # are shorter than continuing along the main path).
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
        return backbone_types, backbone_derivation, None
    # Genuine last resort — the chain itself has fewer than 2 heavy atoms, or no bond topology
    # at all. inspect_data_file only for diagnostics attached to this halt.
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
    return None, None, detail


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
    continuation_path = getattr(args, "pending_continuation_path", None)
    resume_from = getattr(args, "equil_resume_from", None)
    reattaching = pending_path is not None and pending_path.is_file()
    # A gated-path reattach state carries "gate_phase" ("chain1" mid-wait, or "chain1_done" —
    # chain 1 finished before death, gate loop/chain 2 never persisted); the normal path's own
    # flat {"chain_id", "workflow"} shape (also reused verbatim by chain 2's own persist below)
    # has no such key, so it stays routed to the plain else-branch unchanged.
    pending_state = json.loads(pending_path.read_text()) if reattaching else None
    gate_phase = (pending_state or {}).get("gate_phase")
    gate_enabled = (resolve_stage_params("equil", args, cls)["anneal_hold_msid_gate_enabled"]
                    and resume_from is None and not continuation_path
                    and (not reattaching or gate_phase is not None))
    anneal_hold_gate_result = None

    if gate_enabled:
        # Two-chain path: chain 1 (minimize..anneal_hold) -> adaptive MSID gate on anneal_hold's
        # own trajectory -> chain 2 (cool_block_01..npt_final, via resume_from="anneal_hold").
        # Opt-in (anneal_hold_msid_gate_enabled, default off) -- see _anneal_hold_adaptive_extend
        # for the validated remedy this implements and why. EXTEND/resume_from continuations of an
        # EARLIER attempt never take this branch -- gate_enabled is False for those -- so a
        # resumed run for one of THOSE remedies replays the normal single-chain path even for a
        # gate-enabled class.
        #
        # Reattach coverage: chain 1 is the expensive piece (minimize..anneal_hold, most of the
        # protocol) -- losing it to an unattached process death would silently double it. If
        # gate_phase=="chain1_done" (chain 1 finished, death happened later), chain 1 is reused
        # from its persisted workflow with no resubmission at all. If gate_phase=="chain1" (death
        # was mid-chain-1-wait), the persisted chain_id is reattached to directly. Only a death
        # DURING the gate loop's own extension(s) still re-does work -- the loop's own in-flight
        # extension state (probe history, which increment was running) isn't persisted, so a
        # chain1_done reattach restarts the loop fresh from chain 1's own un-extended anneal_hold
        # output. That's a bounded, small re-do (capped by anneal_hold_max_extensions), not the
        # multi-stage chain-1 resubmission this guard exists to prevent.
        if reattaching and gate_phase == "chain1_done":
            chain1 = {"workflow": pending_state["workflow"]}
        else:
            with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
                args.gpu_ids = gpu_ids
                if reattaching and gate_phase == "chain1":
                    chain1 = {"chain_id": pending_state["chain_id"], "workflow": pending_state["workflow"]}
                else:
                    chain1 = _submit_equil_chain(args, cls, lammps, stop_after_stage="anneal_hold")
                    if pending_path is not None:
                        atomic_write_json(pending_path, {
                            "gate_phase": "chain1", "chain_id": chain1["chain_id"],
                            "workflow": chain1["workflow"]})
                chain1_result = wait_for_run(lammps, chain1["chain_id"],
                                             "equilibration chain 1 (minimize..anneal_hold)")
            if chain1_result.get("status") != "completed":
                if chain1_result.get("stage") == "minimize_not_converged":
                    return {"halted": True, "reason": "MINIMIZE_NOT_CONVERGED", "detail": chain1_result,
                            "stage_checkpoints": {}}
                raise SystemExit(f"Equilibration chain 1 did not complete: {chain1_result}")
            if pending_path is not None:
                atomic_write_json(pending_path, {"gate_phase": "chain1_done",
                                                 "workflow": chain1["workflow"]})

        anneal_hold_stage = chain1["workflow"]["stages"][-1]
        p_bt = resolve_stage_params("equil-check", args, cls)
        backbone_types, derivation, halt_detail = _resolve_backbone_types(
            args, cls, lammps, build_data_path, p_bt)
        if halt_detail is not None:
            chain1_checkpoints = {s["name"]: s["output_data"]
                                  for s in chain1["workflow"]["stages"] if s.get("name")}
            return {"halted": True, "reason": "BACKBONE_TYPES_UNRESOLVED", "detail": halt_detail,
                    "stage_checkpoints": chain1_checkpoints}
        if derivation is not None:
            backbone_derivation = derivation

        p_anneal = resolve_stage_params("equil", args, cls)
        anneal_hold_gate_result = _anneal_hold_adaptive_extend(
            args, cls, lammps, p_anneal, anneal_hold_stage, backbone_types, gpu_per_run)
        _record_anneal_hold_convergence(args.output_dir, anneal_hold_gate_result)

        with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
            args.gpu_ids = gpu_ids
            submission = _submit_equil_chain(
                args, cls, lammps, resume_from="anneal_hold",
                resume_data_path=anneal_hold_gate_result["anneal_hold_data_path"])
            # Merge chain 1's own leading stages with the GATE's final (possibly extended)
            # anneal_hold stage and chain 2's tail -- resume_from chains only contain their own
            # tail stages, so a later remedy resuming from an EARLIER checkpoint (nvt_warmup,
            # npt_densify, ...) still needs chain 1's stages recorded here. Built BEFORE
            # wait_for_run and persisted to pending_path immediately, same reattach-guard reason
            # as the normal path (comment above pending_path's declaration): a death during this
            # multi-hour wait must reattach to chain 2's own chain_id and recover this exact
            # merged shape on resume, not resubmit it. This flat {"chain_id","workflow"} shape
            # (no "gate_phase" key) is deliberately the SAME shape the normal path's own reattach
            # branch already reads (see gate_phase's definition above) -- a reattach here falls
            # through to that plain else-branch, gate_enabled computed False, and just waits on
            # this chain_id directly.
            chain1_lead = chain1["workflow"]["stages"][:-1]
            merged_anneal_hold = anneal_hold_gate_result["anneal_hold_stage"]
            workflow = {**submission["workflow"],
                        "stages": chain1_lead + [merged_anneal_hold] + submission["workflow"]["stages"],
                        "run_order": ([s["name"] for s in chain1_lead] + ["anneal_hold"]
                                      + (submission["workflow"].get("run_order") or []))}
            if pending_path is not None:
                atomic_write_json(pending_path,
                                  {"chain_id": submission["chain_id"], "workflow": workflow})
            result = wait_for_run(lammps, submission["chain_id"],
                                  "equilibration chain 2 (cool_block_01..npt_final)")
        if result.get("status") != "completed":
            raise SystemExit(f"Equilibration chain 2 did not complete: {result}")
        if pending_path is not None:
            pending_path.unlink(missing_ok=True)
    else:
        with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
            args.gpu_ids = gpu_ids
            if reattaching:
                submission = json.loads(pending_path.read_text())
            else:
                if resume_from is not None:
                    submission = _submit_equil_chain(
                        args, cls, lammps, resume_from=resume_from,
                        resume_data_path=getattr(args, "equil_resume_data_path", None),
                    )
                elif continuation_path:
                    # continuation_path is the prior attempt's npt_prod_RESTART_path (a .restart
                    # file), not its .data output -- see CampaignStageExecutor.execute, which sets
                    # it from prior_outputs["npt_prod_restart_path"]. extend_base_stage defaults to
                    # "npt_final" (the terminal-stage EXTEND case); a remedy that instead wants to
                    # continue a different adaptive stage sets equilibration_extend_base_stage/
                    # _ensemble explicitly (see workflow_engine._continue_npt).
                    submission = _submit_equil_chain(
                        args, cls, lammps, extend_from_data=continuation_path,
                        extend_temp=getattr(args, "continuation_temp_K", None),
                        extend_ns=float(getattr(args, "npt_continuation_ns", 1.5)),
                        extend_base_stage=getattr(args, "equilibration_extend_base_stage", "npt_final"),
                        extend_ensemble=getattr(args, "equilibration_extend_ensemble", "npt"),
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
    # npt_final is unconditionally the terminal stage in the 8-stage adaptive protocol -- there
    # is no separate glassy-vs-rubbery terminal stage name anymore (cool_block always ramps
    # down to final_T_K regardless of regime).
    npt_prod_data_path = workflow["stages"][-1]["output_data"]
    npt_prod_dump_path = _stage_dump_path(workflow["stages"][-1])
    npt_prod_restart_path = workflow["stages"][-1].get("output_restart")

    # melt_dump_path (nvt_kinetic_stability's fixed-volume window) carries the ensemble-
    # sensitive checks -- rg/msd/ct/msid used to all read from here too (a known simplification,
    # now retired); Rg/MSID/R_ee/torsion/P2/density_homogeneity/finite_size now read from
    # struct_dump_path (npt_final's own trajectory) instead, set just below alongside
    # npt_prod_data_path each loop iteration. melt_data_path (the assess_cooling_contraction
    # melt reference) comes directly from the generator's own melt_data_path field -- the
    # cool_block tagged at `temp`/t_equil_K -- not a stage-name lookup, since which specific
    # cool_block_NN it is varies per run.
    def _find_stage(name):
        return next((s for s in workflow["stages"] if s.get("name") == name), None)
    _kinetic_stage = _find_stage("nvt_kinetic_stability")
    if _kinetic_stage:
        args.npt_prod_dump = _stage_dump_path(_kinetic_stage)
    if workflow.get("melt_data_path"):
        args.melt_data_path = workflow["melt_data_path"]
    # tg_start_data_path: the cool_block the Tg sweep should start its staircase from -- a
    # melt-cooled cell at (or at most one block above) the sweep's top, instead of reheating
    # the finished final_T_K one. Unlike melt_data_path this has NO formula fallback in the
    # resolver: which cool_block_NN it is varies per run, so it only survives a resume by being
    # persisted in this stage's outputs dict and re-read by CampaignStageExecutor.execute.
    if workflow.get("tg_start_data_path"):
        args.tg_start_data = workflow["tg_start_data_path"]
        args.tg_start_T_K = workflow.get("tg_start_T_K")

    attempts = 0
    while True:
        args.data_path = npt_prod_data_path
        args.struct_dump_path = npt_prod_dump_path
        p = resolve_stage_params("equil-check", args, cls)
        # The resolver's value, not the raw CLI arg: the halt below says the list comes from
        # decided_params, and only the resolver reads it from there (via the plan-overlaid cls).
        # Already resolved above when gate_enabled took the two-chain path (cls["backbone_types"]
        # is set as a side effect of a real derivation) -- this call then just returns it back.
        backbone_types, derivation, halt_detail = _resolve_backbone_types(
            args, cls, lammps, build_data_path, p)
        if halt_detail is not None:
            return {"halted": True, "reason": "BACKBONE_TYPES_UNRESOLVED", "detail": halt_detail,
                    "stage_checkpoints": stage_checkpoints}
        if derivation is not None:
            backbone_derivation = derivation

        comp = wait_for_analysis(lammps, lammps.check_equilibration_comprehensive(
            log_file=p["npt_prod_log_path"], dump_file=p["melt_dump_path"],
            data_file=p["npt_prod_data_path"], backbone_types=backbone_types,
            ct_min_decay=p["ct_min_decay_melt"], output_dir=p["output_dir"], graphs_dir=p["graphs_dir"],
            cutoff_A=p["cutoff_A"], timestep_fs=p["dt_fs"],
            struct_dump_file=p["struct_dump_path"], struct_data_file=p["npt_prod_data_path"],
        ), "equil-check comprehensive")
        density = wait_for_analysis(lammps, lammps.extract_equilibrated_density(
            log_file=p["npt_prod_log_path"], target_temp=p["npt_prod_temp_K"], output_dir=p["output_dir"],
        ), "equil-check density")
        comprehensive_json = str(Path(p["output_dir"]) / "equilibration.json")
        verdict = lammps.enforce_equilibration_gate(
            comprehensive_json=comprehensive_json, regime=p["regime"], dp=p["dp"],
            ct_gate_reliable=p["ct_gate_reliable"],
            tg_K=p["exp_tg_point_K"], t_equil_K=p["T_workflow_K"], glass_data=p["npt_prod_data_path"],
            final_T_K=p["npt_prod_temp_K"],
            melt_data=p["melt_data_path"], out_dir=p["output_dir"],
        )
        equil_verdict = verdict.get("verdict")

        if equil_verdict == "PASS":
            result = {"equil_verdict": "PASS", "npt_prod_data_path": p["npt_prod_data_path"],
                      "npt_prod_log_path": p["npt_prod_log_path"], "npt_prod_dump_path": npt_prod_dump_path,
                      "npt_prod_restart_path": npt_prod_restart_path,
                      "density_gcm3": density.get("plateau_density_mean"),
                      "velocity_seed": velocity_seed, "extend_history": extend_history,
                      "backbone_derivation": backbone_derivation,
                      "anneal_hold_convergence": ({k: v for k, v in anneal_hold_gate_result.items()
                                                   if k != "anneal_hold_stage"}
                                                  if anneal_hold_gate_result else None),
                      "stage_checkpoints": stage_checkpoints,
                      # equilibration.json's own on-disk path -- see do_mechanical's
                      # mechanical_json_path for why this needs to be explicit rather than
                      # searched (it lives under THIS equilibration attempt's raw dir, not the
                      # summary attempt's own output_dir).
                      "equilibration_json_path": comprehensive_json,
                      "tg_start_data_path": getattr(args, "tg_start_data", None),
                      "tg_start_T_K": getattr(args, "tg_start_T_K", None)}
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
                        "npt_prod_restart_path": npt_prod_restart_path,
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
                # Restart-continuation of npt_final's own trajectory -- extend_from_data is its
                # .restart output (not .data), read via read_restart with the log/dump appended
                # onto npt_final's own files, so the result is one continuous trajectory.
                submission = _submit_equil_chain(
                    args, cls, lammps, extend_from_data=npt_prod_restart_path,
                    extend_temp=p["npt_prod_temp_K"], extend_ns=extend_ns,
                    extend_base_stage="npt_final", extend_ensemble="npt")
                ext_result = wait_for_run(lammps, submission["chain_id"], "equilibration EXTEND")
            if ext_result.get("status") != "completed":
                raise SystemExit(f"EXTEND chain did not complete: {ext_result}")
            npt_prod_data_path = submission["workflow"]["stages"][0]["output_data"]
            npt_prod_dump_path = _stage_dump_path(submission["workflow"]["stages"][0])
            npt_prod_restart_path = submission["workflow"]["stages"][0].get("output_restart")
            continue

        # Structural or protocol failures never trigger an implicit protocol change. Halt with
        # structured evidence for the recovery-agent boundary.
        return {"halted": True, "reason": equil_verdict, "detail": verdict,
                "stage_checkpoints": stage_checkpoints}


# ─── Stage: thermal track ──────────────────────────────────────────────────

def _tg_lammps_common_params(p: dict) -> dict:
    """Shared LAMMPS deck knobs for both the bracket probes and the per-T sweep -- reused so
    the two never drift apart on FF/electrostatics/hardware selection."""
    return {
        "T_DAMP": p["thermostat_damp_fs"], "P_DAMP": p["barostat_damp_fs"],
        "TIMESTEP": p["dt_fs"], "use_gpu": True, "engine": p["engine"],
        "use_pppm": p["use_long_range_electrostatics"] and not p["lammps_flags"]["use_trappe"],
        **{f"use_{k.split('_')[1]}": v for k, v in p["lammps_flags"].items()},
    }


def _bracket_tg_start_temp(args, cls: dict, lammps, p: dict) -> dict:
    """RadonPy-inspired pre-sweep probe: verify T_start_K sits unambiguously in the melt
    branch before committing to the (multi-ns) per-temperature sweep, using this run's own
    measured density-vs-T trend rather than the class's static tg_t_high_K constant alone.

    A short NPT ramp from the cold T_workflow_K structure up to the candidate T_start_K is
    checked for a statistically significant, monotonically NEGATIVE density trend near its top
    (monotonic_trend alone is sign-agnostic -- an explicit slope<0 check is required). Density
    is a state function, not path-dependent: a bare ramp-and-read conflates "still relaxing
    from the jump" with "hasn't melted," so this bracket only decides WHETHER to raise the
    candidate -- genuine equilibration at the accepted candidate happens in Phase 2
    (_run_tg_sweep_adaptive), which holds every point (including the first) until stable.

    Necessary but not sufficient: the glassy branch also has negative dRho/dT (~half the melt
    branch's expansivity), so this cannot alone distinguish "comfortably melt" from "comfortably
    glass but still cooling normally." Advisory only -- never raises, never blocks do_thermal;
    an exhausted or failed bracket just proceeds with its best candidate. extract_thermal.py's
    own downstream fit-quality gates remain the real correctness backstop.
    """
    from check_block_gate import monotonic_trend
    from analysis_utils import parse_lammps_log

    T_workflow_K = p["T_workflow_K"]
    T_step_K = p["T_step_K"]
    ceiling_K = cls.get("annealing_T_high_K", 700.0)
    max_iters = p["tg_bracket_max_iters"]
    probe_steps = p["tg_bracket_probe_steps"]
    drift_threshold_pct = p["tg_bracket_drift_threshold_pct"]
    common = _tg_lammps_common_params(p)

    candidate = p["T_start_K"]
    from_data = p["equil_data_path"]
    from_T = T_workflow_K
    iterations: list[dict] = []

    for i in range(1, max_iters + 1):
        probe_dir = f"{p['work_dir']}/tg_bracket/probe_{i:02d}"
        script = lammps.generate_script(
            template_name="npt", data_file=from_data,
            output_script=f"{probe_dir}/probe.in", velocity_seed=p["velocity_seed"],
            params={**common, "LOG_FILE": "probe.log", "T_START": from_T, "T_FINAL": candidate,
                    "N_STEPS": probe_steps, "THERMO_FREQ": 500, "use_restart": False,
                    "P_START": p["pressure_atm"], "P_FINAL": p["pressure_atm"]},
        )
        run = lammps.run_lammps_script(
            script=script["output_script"], work_dir=probe_dir, log_file="probe_run.log",
            gpu_ids=p["gpu_ids"], mpi=p["mpi_ranks"], engine=p["engine"],
            data_file=from_data, lj_cutoff=p["cutoff_A"],
        )
        result = wait_for_run(lammps, run["run_id"], f"tg bracket probe {i}")
        if result.get("status") != "completed":
            iterations.append({"iteration": i, "candidate_T_K": candidate, "outcome": "run_failed"})
            return {"T_start_K": candidate, "start_data_path": from_data,
                    "iterations": iterations, "outcome": "PROBE_FAILED"}

        try:
            df = parse_lammps_log(f"{probe_dir}/probe.log")
        except Exception:
            df = None
        if df is None or "Density" not in df.columns or len(df) < 4:
            iterations.append({"iteration": i, "candidate_T_K": candidate, "outcome": "unparseable_log"})
            return {"T_start_K": candidate, "start_data_path": from_data,
                    "iterations": iterations, "outcome": "PROBE_FAILED"}

        window_frac = (1.0 / 3.0) if i == 1 else 0.8
        window = df["Density"].values[-max(int(len(df) * window_frac), 4):]
        trend = monotonic_trend(window, drift_threshold_pct=drift_threshold_pct)
        melt_like = bool(trend.get("available") and trend.get("monotonic_trend")
                          and trend.get("slope", 0.0) < 0)
        iterations.append({"iteration": i, "candidate_T_K": candidate, "trend": trend,
                            "melt_like": melt_like})
        from_data = f"{probe_dir}/npt_out.data"

        if melt_like:
            return {"T_start_K": candidate, "start_data_path": from_data,
                    "iterations": iterations, "outcome": "PASS"}

        from_T = candidate
        candidate = min(candidate + 2 * T_step_K, ceiling_K)

    return {"T_start_K": candidate, "start_data_path": from_data,
            "iterations": iterations, "outcome": "EXHAUSTED"}


def _select_tg_start_cell(args, cls: dict, lammps, p: dict) -> dict:
    """Which structure the Tg staircase starts from, in bracket-result shape.

    The sweep measures where a COOLING liquid stiffens, so it has to start from a liquid. The
    equilibration chain already made one and wrote it to disk: cool_block ramps the annealed
    melt down to final_T_K and saves a .data file at every waypoint, and the anneal ceiling now
    carries one block of headroom above the sweep top precisely so one of those waypoints sits
    there (see temperature_schedule's sweep_start_headroom term). Using it costs nothing -- the
    trajectory has already been run -- and it replaces a 150 ps reheat of the finished cell.

    Why the reheat was wrong, not merely slower: the fallback probe hands npt_final (a cell
    equilibrated at final_T_K) to a deck whose T_START and T_FINAL are BOTH the candidate
    temperature -- a thermostat step change, not a ramp. Worse, that cell is packed at its
    final_T_K density; a real melt is several percent less dense, and 150 ps is nowhere near
    enough for the barostat to expand the box. The top plateaus of the staircase are then read
    off a cell still relaxing from the jump, which biases the rubbery branch and hence the
    breakpoint. PKTN/PSFO's inverted rate dependence (Tg FALLING as cooling gets faster, i.e. as
    less time is spent contaminated at the top) is the signature of exactly this.

    Three cases; the fallback is retained rather than deleted because it is what a run with an
    untrustworthy Tg estimate legitimately lands on -- the ceiling carries no sweep headroom
    there, so no tagged cell is guaranteed to exist.
    """
    T_start = p["T_start_K"]
    tagged_path, tagged_T = p["tg_start_data_path"], p["tg_start_T_K"]
    dT = p["cool_block_dT_K"]

    # (a) The equilibration cooldown tagged a cell at or just above the sweep top. The
    # temperature match is not decoration: tg_t_high_K can be edited between the equilibration
    # and thermal stages (or replayed from a frozen plan), and a stale tag would silently start
    # the staircase from the wrong temperature. Reject it and reheat rather than guess.
    if tagged_path and isinstance(tagged_T, (int, float)) and Path(tagged_path).exists():
        if -1e-6 <= tagged_T - T_start <= dT + 1e-6:
            return {"T_start_K": T_start, "start_data_path": tagged_path,
                    "start_T_K": tagged_T, "iterations": [], "outcome": "MELT_COOLED_START"}
        fallback = _bracket_tg_start_temp(args, cls, lammps, p)
        return {**fallback, "stale_tg_start_tag_T_K": tagged_T}

    # (b) A rubbery run assessed at or above the sweep top: npt_final IS an equilibrated cell
    # at/above the staircase's first point, so there is nothing to reheat and nothing to tag.
    if p["final_T_K"] >= T_start - 1e-6:
        return {"T_start_K": T_start, "start_data_path": p["equil_data_path"],
                "start_T_K": p["final_T_K"], "iterations": [],
                "outcome": "ASSESSED_ABOVE_SWEEP_TOP"}

    # (c) No tagged cell -- an untrustworthy Tg estimate (class-default window, no headroom), a
    # legacy plan, or a chain generated before tagging existed.
    return _bracket_tg_start_temp(args, cls, lammps, p)


def _run_tg_sweep_adaptive(args, cls: dict, lammps, p: dict, start_data_path: str) -> dict:
    """Per-temperature adaptive sampling: one npt_tg_step hold per waypoint (T_start_K down to
    T_end_K in T_step_K decrements), chained via each point's own WRITE_DATA_FILE, all appending
    to the same shared tg_sweep.log/per_t_structs.dump -- so the accumulated files are
    shape-identical to the old monolithic staircase deck and extract_thermal.py's existing
    plateau-jump-detection parsing needs no changes.

    Extends ONLY the specific temperature whose hold isn't yet stable (half_window_stability)
    or adequately sampled (n_eff, the same autocorrelation-based estimator
    check_equilibration_comprehensive.py already uses), instead of the old _tg_sampling remedy's
    blind whole-sweep-doubling. Bounded per-point (tg_per_t_max_extensions); advisory only -- an
    unresolved point after its cap is still recorded and the sweep moves on, exactly as
    extract_thermal.py's own post-hoc plateau check would already flag it today.
    """
    from check_block_gate import half_window_stability
    from analysis_utils import parse_lammps_log, compute_tau_eff, effective_sample_size

    T_start_K, T_end_K, T_step_K = p["T_start_K"], p["T_end_K"], p["T_step_K"]
    n_steps_per_t = p["n_steps_per_t"]
    max_ext = p["tg_per_t_max_extensions"]
    stability_pct = p["tg_per_t_stability_pct"]
    min_n_eff = p["tg_per_t_min_n_eff"]
    common = _tg_lammps_common_params(p)

    temps: list[float] = []
    t = T_start_K
    while t > T_end_K + 1e-6:
        temps.append(t)
        t -= T_step_K
    if not temps or abs(temps[-1] - T_end_K) > 1e-6:
        temps.append(T_end_K)

    sweep_dir = p["tg_sweep_dir"]
    log_path = f"{sweep_dir}/tg_sweep.log"
    from_data = start_data_path
    per_t: list[dict] = []

    for T in temps:
        extensions = 0
        while True:
            n_before = 0
            if Path(log_path).exists():
                try:
                    n_before = len(parse_lammps_log(log_path))
                except Exception:
                    n_before = 0

            out_data = f"{sweep_dir}/tg_step_T{int(T)}_e{extensions}_out.data"
            script = lammps.generate_script(
                template_name="npt_tg_step", data_file=from_data,
                output_script=f"{sweep_dir}/tg_step_T{int(T)}_e{extensions}.in",
                velocity_seed=p["velocity_seed"],
                params={**common, "LOG_FILE": "tg_sweep.log", "LOG_APPEND": True,
                        "DUMP_FILE": "", "WRITE_DATA_FILE": out_data,
                        "WRITE_PER_T_DUMP": extensions == 0, "PER_T_DUMP_FILE": "per_t_structs.dump",
                        "T_TARGET": T, "N_STEPS": n_steps_per_t, "THERMO_FREQ": 500,
                        "P_TARGET": p["pressure_atm"]},
            )
            run = lammps.run_lammps_script(
                script=script["output_script"], work_dir=sweep_dir, log_file="tg_sweep_run.log",
                gpu_ids=p["gpu_ids"], mpi=p["mpi_ranks"], engine=p["engine"],
                data_file=from_data, lj_cutoff=p["cutoff_A"],
            )
            result = wait_for_run(lammps, run["run_id"], f"tg sweep T={T}K (ext {extensions})")
            if result.get("status") != "completed":
                per_t.append({"T_K": T, "outcome": "PROBE_FAILED", "extensions_used": extensions})
                break

            from_data = out_data
            try:
                df_after = parse_lammps_log(log_path)
            except Exception:
                df_after = None
            if df_after is None or "Density" not in df_after.columns or len(df_after) <= n_before:
                per_t.append({"T_K": T, "outcome": "PROBE_FAILED", "extensions_used": extensions})
                break

            window = df_after["Density"].values[n_before:]
            stability = half_window_stability(window, stability_pct)
            tau_frames, _ = compute_tau_eff(window)
            n_eff = effective_sample_size(len(window), tau_frames)
            stable = bool(stability.get("available") and stability.get("stable"))
            adequate = bool(n_eff >= min_n_eff)

            if (stable and adequate) or extensions >= max_ext:
                per_t.append({
                    "T_K": T, "outcome": "PASS" if (stable and adequate) else "EXHAUSTED",
                    "mean_density_gcm3": float(window[len(window) // 2:].mean()),
                    "n_eff": n_eff, "stable": stable, "extensions_used": extensions,
                })
                break
            extensions += 1

    return {"per_t": per_t, "outcome": "COMPLETE"}


def do_thermal(args, cls: dict, lammps, equil_density_gcm3=None) -> dict:
    """Single-rate-primary: run one sweep at the class's primary configured rate (highest by
    default; a tg_slope_gate_fallback="slowest_rate" class runs rates[0] instead, its
    highest-rate fit being documented as degenerate/inverted).

    No class carries that fallback as of 2026-09-01: PKTN and PSFO did, and their inversion was
    the cold-start artifact the melt-start sweep fixes (see _select_tg_start_cell). The branch
    stays because the fallback remains a valid, validated diagnosis for a class that genuinely
    cannot resolve its highest rate."""
    tg_rates = cls.get("tg_rates_K_per_ns", [])
    gpu_per_run = cls.get("gpu_per_run") or 1
    per_rate = []
    if tg_rates:
        # Shared with _resolve_equil_params' cool_block rate matching -- the cooldown and the
        # staircase are one continuous descent and must not drift apart on which rate that is.
        idx = select_primary_tg_rate_index(cls)
        if not 0 <= idx < len(tg_rates):
            return {"halted": True, "reason": "TG_PRIMARY_RATE_INDEX_INVALID",
                    "detail": {"index": idx, "n_rates": len(tg_rates)}}
        rate = tg_rates[idx]
        args.tg_rate_index = idx
        p = resolve_stage_params("tg", args, cls)
        with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
            args.gpu_ids = gpu_ids
            bracket = _select_tg_start_cell(args, cls, lammps, p)
            sweep = _run_tg_sweep_adaptive(args, cls, lammps, p, bracket["start_data_path"])

        # bracket["outcome"] may be PROBE_FAILED (the very first probe couldn't even run/parse,
        # almost certainly a real deck/hardware problem rather than a "wasn't melt enough" case)
        # or EXHAUSTED (candidate raised to its ceiling without ever confirming a melt-like
        # trend) -- both are advisory: _run_tg_sweep_adaptive still ran from bracket's best
        # candidate/structure either way, and any genuinely bad outcome is caught by
        # extract_thermal's own fit-quality gates below, not here.

        equil_sanity = None
        if equil_density_gcm3 is not None and sweep.get("per_t"):
            first_point = sweep["per_t"][0]
            probe_density = first_point.get("mean_density_gcm3")
            if probe_density is not None:
                equil_sanity = bool(probe_density < equil_density_gcm3)

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
                         "velocity_seed": p["velocity_seed"],
                         "tg_bracket": bracket, "tg_per_t_sampling": sweep.get("per_t"),
                         "tg_bracket_equil_density_sanity": equil_sanity})

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


def _fluctuation_K_for_pressure_ladder(cls: dict, p: dict):
    """This polymer's own volume-fluctuation K estimate, for select_pressure_ladder's
    optional fluctuation-K sanity check on the Murnaghan pressure ladder -- a pure,
    deterministic function of already-on-disk equilibration output (the ambient NPT
    production log do_equil_and_check already produced), so no new simulation is run
    to compute it.

    Returns None (no adjustment) on a resample/extend retry: cls["mechanical_resample_points"]
    is then set by murnaghan_resample or murnaghan_ladder_extend, so p["bm_pressures_atm"]
    is that remedy's own deliberately narrow override, not the class ladder this precheck
    exists to sanity-check -- adjusting THAT would corrupt the merge-by-pressure-value retry
    in do_mechanical below.
    """
    if cls.get("mechanical_resample_points") or not p.get("npt_prod_log_path"):
        return None
    if not Path(p["npt_prod_log_path"]).exists():
        return None
    return estimate_fluctuation_K_GPa(p["npt_prod_log_path"], eq_fraction=0.5)


def _bm_point_adaptive_extend(cls: dict, lammps, p: dict, pressure: float, bm_work_dir: str,
                               log_path: str, data_path: str, gpu_per_run: int,
                               run_name: str) -> dict:
    """Tg-Phase-2-style per-point sampling-adequacy check for one bulk-modulus pressure point.

    The initial hold (run_bulk_modulus_series, already completed by the time this is called) is
    checked for stability (half_window_stability on Volume) and adequate autocorrelation-corrected
    sampling (compute_tau_eff/effective_sample_size, the same n_eff estimator
    extract_bulk_modulus_murnaghan.py already computes per point but never gates on). If either
    check fails, one more hold at the SAME pressure is submitted directly against the "npt"
    template (bypassing run_bulk_modulus_series/run_lammps_chain, which has no LOG_APPEND support),
    chained from this point's own last WRITE_DATA_FILE and appended to the same log -- mirroring
    _run_tg_sweep_adaptive exactly, just condensed to a single point instead of a waypoint list.

    Bounded by bm_per_point_max_extensions; advisory only -- an unresolved point after its cap is
    still recorded and used, exactly as the aggregate Murnaghan fit's own plateau/leave-one-out
    diagnostics (and murnaghan_resample/murnaghan_ladder_extend) would already flag/handle it
    today. Those remedies are NOT redundant with this check: they answer a different question
    (relative cross-point nonmonotonicity; ladder-range inadequacy for the fit), not "did this
    one point's own hold converge" -- both stay untouched.
    """
    from check_block_gate import half_window_stability
    from analysis_utils import parse_lammps_log, compute_tau_eff, effective_sample_size

    extensions = 0
    n_before = 0  # extensions == 0: the log run_bulk_modulus_series just produced is entirely
                  # this point's own hold (a fresh single-pressure log, unlike the Tg sweep's
                  # shared multi-waypoint log) -- the whole file is this hold's own rows.
    while True:
        try:
            df = parse_lammps_log(log_path)
        except Exception:
            return {"outcome": "PROBE_FAILED", "extensions_used": extensions,
                    "final_data_path": data_path}
        vol_col = next((c for c in ("Volume", "Vol", "vol") if c in df.columns), None)
        if vol_col is None or len(df) < 4:
            return {"outcome": "PROBE_FAILED", "extensions_used": extensions,
                    "final_data_path": data_path}

        # On a later loop the log has grown by one more appended hold; isolate that hold's own
        # rows the same way _run_tg_sweep_adaptive does for each sweep waypoint.
        window = df[vol_col].values[n_before:]
        stability = half_window_stability(window, p["bm_per_point_stability_pct"])
        tau_frames, _ = compute_tau_eff(window)
        n_eff = effective_sample_size(len(window), tau_frames)
        stable = bool(stability.get("available") and stability.get("stable"))
        adequate = bool(n_eff >= p["bm_per_point_min_n_eff"])

        if (stable and adequate) or extensions >= p["bm_per_point_max_extensions"]:
            return {"outcome": "PASS" if (stable and adequate) else "EXHAUSTED",
                    "n_eff": n_eff, "stable": stable, "extensions_used": extensions,
                    "final_data_path": data_path}

        extensions += 1
        n_before = len(df)
        with gpu_claim(run_name, gpu_per_run) as gpu_ids:
            script = lammps.generate_script(
                template_name="npt", data_file=data_path,
                output_script=f"{bm_work_dir}/ext_{extensions}.in", velocity_seed=p["velocity_seed"],
                params={"T_START": p["temp_K"], "T_FINAL": p["temp_K"],
                        "P_START": pressure, "P_FINAL": pressure,
                        "T_DAMP": p["thermostat_damp_fs"], "P_DAMP": p["barostat_damp_fs"],
                        "N_STEPS": p["npt_steps"], "TIMESTEP": p["dt_fs"],
                        "THERMO_FREQ": p["thermo_freq"], "LOG_FILE": log_path, "LOG_APPEND": True,
                        "DUMP_FILE": "", "WRITE_DATA_FILE": f"{bm_work_dir}/ext_{extensions}_out.data",
                        "use_gpu": True, "engine": p["engine"],
                        "use_pppm": p["use_long_range"] and not p["lammps_flags"]["use_trappe"],
                        **p["lammps_flags"]},
            )
            run = lammps.run_lammps_script(
                script=script["output_script"], work_dir=bm_work_dir, log_file="ext_run.log",
                gpu_ids=gpu_ids, mpi=p["mpi_ranks"], engine=p["engine"],
                data_file=data_path, lj_cutoff=p["cutoff_A"],
            )
            result = wait_for_run(lammps, run["run_id"], f"bm point P={pressure:g} ext {extensions}")
        if result.get("status") != "completed":
            return {"outcome": "PROBE_FAILED", "extensions_used": extensions,
                    "final_data_path": data_path}
        data_path = f"{bm_work_dir}/ext_{extensions}_out.data"


def _anneal_hold_adaptive_extend(args, cls: dict, lammps, p: dict, anneal_hold_stage: dict,
                                  backbone_types: list, gpu_per_run: int) -> dict:
    """MSID-convergence gate for anneal_hold: extend it via genuine restart-continuation
    (extend_only=True, base_stage_name="anneal_hold" -- server.py:1888-1962, already
    implemented, never previously invoked with this base stage) until large-s MSID either
    passes the +-20% gaussian_pass band or stops moving, instead of committing to a fixed
    schedule and letting cool_block_01 lock in whatever bias anneal_hold hasn't yet erased.

    Mirrors _run_tg_sweep_adaptive/_bm_point_adaptive_extend's control-flow shape (run one
    increment -> compute a convergence criterion from fresh output -> extend-or-stop, capped,
    advisory-only) -- but unlike those two, which deliberately discard thermostat state between
    probes (read_data + LOG_APPEND, appropriate for independent short holds), this uses the
    codebase's actual restart-continuation mechanism, since anneal_hold is one genuine
    trajectory, not independent samples.

    Validated empirically (PEG1/POXI Phase 0, 2026-08-29): large-s MSID slope rose
    0.663 -> 0.849 -> 0.923 across two 2.5ns restart-continued extensions from a 1ns baseline,
    then plateaued (0.923 / 0.915 / 0.901, ~1-2.5% relative jitter at short separation) once
    inside the gaussian_pass band. Phase 0 also found that extensions from a converged
    checkpoint can themselves crash under real LAMMPS/CUDA errors (PPPM out-of-range atoms;
    cudaErrorIllegalAddress), each preceded by fmax spiking within a single thermo interval --
    consistent with a stochastic hot-atom event in a long uninterrupted NVT hold, not a setup
    bug. EXTENSION_FAILED below is a first-class, advisory outcome for exactly that: fall back
    to the last good restart/data and stop extending, never treat it as fatal.

    Bounded by anneal_hold_max_extensions; advisory only -- an unresolved hold after its cap
    (or a probe/extension failure) is still recorded in the returned dict and chain 2 proceeds
    from whatever anneal_hold data exists, exactly like the Tg/BM per-point loops' own
    EXHAUSTED/PROBE_FAILED handling.

    Rg veto (2026-08-30): a flat MSID pairwise slope-diff alone can call STABLE while Rg is
    still visibly drifting -- MSID measures backbone-length-scale scaling, Rg measures overall
    chain size, and the two need not converge in lockstep. The STABLE path (only that path --
    never PASS, never a second AND-condition on the whole gate) is vetoed when mean_Rg_A moved
    more than anneal_hold_rg_veto_pct between the last two probes, keeping the loop extending
    instead of stopping on a possibly-incomplete signal. Deliberately scoped this narrowly
    rather than mirroring RadonPy's own Rg-convergence check as a blanket requirement: RadonPy's
    own check_eq() bundles Rg with density/energy/etc into one flag and, on failure, still
    reports density/Rg/bulk_modulus after exhausting its retry budget -- only thermal
    conductivity gets suppressed (radonpy/sim/lammps.py:2613-2756, AutoMD_scripts/1_eq.py:
    210-247, verified directly 2026-08-30). Density/bulk_modulus are local-packing/EOS
    properties that don't need full chain-scale relaxation to be trustworthy; Tg and
    entanglement/viscoelastic properties do -- so the veto targets where a stale STABLE call
    would actually mislead (this hold, before the fixed cool-down schedule locks it in) without
    resurrecting a universal hard gate that RadonPy's own precedent (and its own polymer's
    4+ consecutive Rg-check failures) shows would rarely or never pass for this chemistry.
    """
    max_ext = p["anneal_hold_max_extensions"]
    stability_pct = p["anneal_hold_stability_pct"]
    rg_veto_pct = p["anneal_hold_rg_veto_pct"]
    extend_ns = p["anneal_hold_extend_ns"]
    dt = p["dt_fs"]
    extend_steps = int(extend_ns * 1e6 / dt)

    stage = anneal_hold_stage
    dump_every = int(stage["params"].get("DUMP_FREQ", 1000))
    steps_so_far = int(stage["params"].get("N_STEPS") or 0)
    restart_path = stage.get("output_restart")

    slope_history: list = []
    rg_history: list = []
    probe_history: list = []
    extensions = 0
    outcome = None
    rg_veto_triggered = False

    while True:
        # extensions==0: this probe covers the whole chain-1 anneal_hold hold, same as any
        # other equil-check probe (function default skip_frames applies). extensions>=1: skip
        # everything before THIS increment so the probe measures only its own relaxation, not
        # diluted by earlier (already-probed, possibly still-unrelaxed) frames.
        probe_dir = f"{stage['work_dir']}/msid_probe/ext_{extensions:02d}"
        probe_kwargs = dict(
            log_file=f"{stage['work_dir']}/{stage['params']['LOG_FILE']}",
            dump_file=_stage_dump_path(stage), data_file=stage["output_data"],
            backbone_types=backbone_types, ct_min_decay=None,
            output_dir=probe_dir, graphs_dir=f"{probe_dir}/graphs",
            cutoff_A=p["cutoff_A"], timestep_fs=dt, dump_every=dump_every,
        )
        if extensions > 0 and dump_every:
            probe_kwargs["skip_frames"] = steps_so_far // dump_every
        try:
            probe = wait_for_analysis(lammps, lammps.check_equilibration_comprehensive(
                **probe_kwargs), f"anneal_hold MSID probe (ext {extensions})")
        except SystemExit as exc:
            probe = {"status": "failed", "error": str(exc)}

        large_s = (((probe or {}).get("chain") or {}).get("msid") or {}).get("large_s") or {}
        slope = large_s.get("slope")
        gaussian_pass = bool(large_s.get("gaussian_pass"))
        # Rg is a free side-observation, not a gate condition: check_equilibration_comprehensive
        # already computes it in the same call as MSID (structural.rg), so recording it here costs
        # nothing and lets a later revision see whether Rg tracks or lags MSID's own convergence
        # before committing to a real temporal-Rg stopping condition (RadonPy's independent
        # equilibration of this same polymer has repeatedly failed ITS OWN Rg-convergence check --
        # corroborating evidence, but not yet a validated basis for a second AND-condition here).
        mean_rg_A = (((probe or {}).get("chain") or {}).get("rg") or {}).get("mean_Rg_A")
        probe_history.append({"extension": extensions, "slope": slope,
                              "gaussian_pass": gaussian_pass, "mean_rg_A": mean_rg_A,
                              "skip_frames": probe_kwargs.get("skip_frames")})

        if probe.get("status") != "success" or slope is None:
            outcome = "PROBE_FAILED"
            break
        slope_history.append(slope)
        rg_history.append(mean_rg_A)
        if gaussian_pass:
            outcome = "PASS"
            break
        if len(slope_history) >= 2 and slope_history[-2]:
            rel_diff = abs(slope_history[-1] - slope_history[-2]) / abs(slope_history[-2])
            if rel_diff <= stability_pct / 100.0:
                # MSID looks flat -- but a flat slope isn't proof the chain has explored its
                # conformational space if Rg is still visibly drifting alongside it. Veto only
                # this early-stop path (never PASS, never a second AND-condition on the whole
                # gate -- see anneal_hold_rg_veto_pct in stage_params.py for why this stays a
                # permissive placeholder rather than mirroring RadonPy's own near-unsatisfiable
                # 1%-of-mean Rg criterion). Missing/None Rg fails open -- Rg is still an
                # optional side-observation, not a hard prerequisite for this stop condition.
                rg_prev, rg_cur = rg_history[-2], rg_history[-1]
                if rg_prev is None or rg_cur is None or rg_prev == 0:
                    outcome = "STABLE"
                    break
                rg_rel_diff = abs(rg_cur - rg_prev) / abs(rg_prev)
                if rg_rel_diff <= rg_veto_pct / 100.0:
                    outcome = "STABLE"
                    break
                rg_veto_triggered = True
                probe_history[-1]["rg_veto"] = True
        if extensions >= max_ext:
            outcome = "EXHAUSTED"
            break

        attempt_idx = extensions + 1
        with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
            args.gpu_ids = gpu_ids
            # extend_temp is NOT the extension's actual hold temperature -- generate_equilibration_
            # workflow's own extend_only branch hardcodes T_START=T_FINAL=max_temp for
            # base_stage_name="anneal_hold" regardless of what's passed here (server.py's
            # `elif base_stage_name == "anneal_hold": ext_T = max_temp`). extend_temp only feeds
            # the unconditional `max_temp >= temp + anneal_margin_K` validation gate that runs
            # BEFORE that branch -- passing T_anneal_high_K (==max_temp for this class) here
            # trips that gate every time (max_temp can never exceed itself by a positive margin).
            # Leave it unset so _submit_equil_chain's own default (p["T_workflow_K"], always
            # comfortably below max_temp) satisfies the gate instead -- confirmed against a real
            # PROCESS_FAILED failure from this exact call (PEG1_gate_validation attempt-0001,
            # 2026-08-30: "max_temp=580.0 does not meet temp=580.0 plus ... anneal_margin_K=100.0").
            submission = _submit_equil_chain(
                args, cls, lammps, extend_from_data=restart_path, extend_ns=extend_ns,
                extend_base_stage="anneal_hold", extend_ensemble="nvt")
            ext_result = wait_for_run(lammps, submission["chain_id"],
                                      f"anneal_hold extend {attempt_idx}")
        if ext_result.get("status") != "completed":
            probe_history.append({"extension": attempt_idx, "outcome": "EXTENSION_FAILED",
                                  "detail": ext_result})
            outcome = "EXTENSION_FAILED"
            break
        extensions = attempt_idx
        stage = submission["workflow"]["stages"][0]
        restart_path = stage.get("output_restart")
        steps_so_far += extend_steps

    return {
        "outcome": outcome, "extensions_used": extensions,
        "slope_history": slope_history, "rg_history": rg_history,
        "probe_history": probe_history,
        "rg_veto_triggered": rg_veto_triggered,
        "cumulative_hold_ns": steps_so_far * dt / 1e6,
        "anneal_hold_stage": stage,
        "anneal_hold_data_path": stage["output_data"],
        "anneal_hold_restart_path": stage.get("output_restart"),
    }


def _record_anneal_hold_convergence(output_dir: str, gate_result: dict) -> None:
    """Merge the gate's outcome into equilibration.json under 'anneal_hold_convergence' --
    same read-merge-write convention extract_equilibrated_density.py already uses for its own
    'density' key (equilibration.json accumulates sections from several independent writers,
    never a single owner)."""
    path = Path(output_dir) / "equilibration.json"
    merged = {}
    if path.exists():
        try:
            merged = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            merged = {}
    merged["anneal_hold_convergence"] = {
        k: v for k, v in gate_result.items() if k != "anneal_hold_stage"
    }
    atomic_write_json(path, merged)


def do_mechanical(args, cls: dict, lammps, is_glassy: bool, npt_prod_data_path: str) -> dict:
    args.is_glassy = "true" if is_glassy else "false"
    gpu_per_run = cls.get("gpu_per_run") or 1
    p = resolve_stage_params("murnaghan", args, cls)
    # ced_mpa (cohesive energy density) has no producer anywhere in this codebase yet --
    # select_pressure_ladder already treats None as "no CED-informed adjustment".
    pressure_selection = select_pressure_ladder(
        configured_pressures=p["bm_pressures_atm"], ced_mpa=None,
        fluctuation_K_GPa=_fluctuation_K_for_pressure_ladder(cls, p),
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
                    use_long_range=p["use_long_range"],
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
        if point["status"] == "accepted":
            bm_work_dir = (f"{p['work_dir']}/bm_series/p_{pressure:g}/attempt_{point_attempt}"
                           f"/bm_P{int(pressure)}")
            data_path = f"{bm_work_dir}/bm_P{int(pressure)}_out.data"
            point["stability_check"] = _bm_point_adaptive_extend(
                cls, lammps, p, pressure, bm_work_dir, point["log_file"], data_path,
                gpu_per_run, args.run_name,
            )
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

    # mechanical.json's own on-disk path -- do_summary needs this explicitly, since it lives
    # under THIS (mechanical) attempt's raw dir, not the summary attempt's own output_dir that
    # generate_run_summary.py otherwise searches (see generate_run_summary.py's
    # equilibration_path/mechanical_path/bulk_modulus_deform_path args).
    mechanical_json_path = str(Path(bp["output_dir"]) / "mechanical.json")

    if accepted:
        result = {"method": "murnaghan", "bulk_modulus_GPa": murn.get("bulk_modulus_GPa"),
                  "B0_prime": murn.get("B0_prime"),
                  "bm_gate_verdict": murn.get("bm_gate_verdict"),
                  "bm_gate_reasons": murn.get("bm_gate_reasons"),
                  "bm_convergence_verdict": murn.get("bm_convergence_verdict"),
                  "bm_convergence_reasons": murn.get("bm_convergence_reasons"),
                  "bm_convergence_confidence": murn.get("bm_convergence_confidence"),
                  "murnaghan_result": murn, "velocity_seed": p["velocity_seed"],
                  "pressure_selection": pressure_selection.to_dict(),
                  "mechanical_json_path": mechanical_json_path}
        return result

    result = {"method": "murnaghan", "bulk_modulus_GPa": murn.get("bulk_modulus_GPa"),
              "accepted": False, "reason": murn.get("bm_gate_verdict") or "BM_INADMISSIBLE",
              "bm_gate_verdict": murn.get("bm_gate_verdict"),
              "bm_gate_reasons": murn.get("bm_gate_reasons"),
              "bm_convergence_verdict": murn.get("bm_convergence_verdict"),
              "bm_convergence_reasons": murn.get("bm_convergence_reasons"),
              "bm_convergence_confidence": murn.get("bm_convergence_confidence"),
              "is_glassy": is_glassy,
              "murnaghan_result": murn, "velocity_seed": p["velocity_seed"],
              "pressure_selection": pressure_selection.to_dict(),
              "mechanical_json_path": mechanical_json_path}
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
             "velocity_seed": resolve_stage_params("deform", args, cls)["velocity_seed"],
             # bulk_modulus_deform.json's own on-disk path -- see do_mechanical's
             # mechanical_json_path for why this needs to be explicit rather than searched.
             "bulk_modulus_deform_json_path": str(Path(bp["output_dir"]) / "bulk_modulus_deform.json")}
    return result


# ─── Stage: summary ─────────────────────────────────────────────────────────

def do_summary(args, cls: dict, lammps, is_glassy: bool, thermal_result, equil_verdict: str,
               raw_dir: Path, equil_result: dict = None, mechanical_result: dict = None) -> dict:
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
    # equilibration.json/mechanical.json/bulk_modulus_deform.json live under THEIR OWN stage's
    # attempt raw dir (data/<run>/attempts/<stage>/attempt-N/raw/), never under this summary
    # attempt's own output_dir (sp["output_dir"]) -- generate_run_summary.py's plain same-dir
    # lookup can never find them there, so these explicit cross-attempt-directory paths (already
    # known from each stage's own returned outputs) are required, mirroring tg_path's existing
    # precedent for exactly this reason.
    equilibration_path = (equil_result or {}).get("equilibration_json_path")
    mechanical_path = (mechanical_result or {}).get("mechanical_json_path")
    bulk_modulus_deform_path = (mechanical_result or {}).get("bulk_modulus_deform_json_path")
    summary = wait_for_analysis(lammps, lammps.generate_run_summary(
        output_dir=sp["output_dir"], graphs_dir=sp["graphs_dir"], run_name=args.run_name,
        smiles=args.smiles or "", polymer_class=args.polymer_class.upper(), ff=sp["ff"],
        charge_method=sp["charge_method"] or "", dp=sp["dp"], n_chains=sp["nchain"],
        d01=sp["d01_ff"], d02=sp["d02_charges"], d03=sp["d03_electrostatics"], d04=sp["d04_system_size"],
        d05=args.d05, d06=args.tg_fit_quality or "N/A (not requested)",
        n_replicates=args.n_replicates, tg_path=tg_path,
        equilibration_path=equilibration_path, mechanical_path=mechanical_path,
        bulk_modulus_deform_path=bulk_modulus_deform_path,
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
        if stage == "equilibration":
            # The tg-start tag is produced ONLY by the code path that builds cool_blocks. An
            # attempt that resumes at or past the "cool_block" checkpoint -- or an extend-only
            # continuation -- generates none, so generate_equilibration_workflow returns no tag
            # and the thermal stage would fall back to reheating npt_final even though the
            # tagged cell is still on disk from an earlier attempt.
            #
            # Reaching back is safe here for a structural reason, not a hopeful one. The
            # generator's checkpoint order is [... anneal_hold, cool_block, ...]: resuming from
            # "anneal_hold" or earlier REBUILDS the cooldown and emits a fresh tag, so this walk
            # never fires for it. The tag is missing only from "cool_block" onward -- which is
            # exactly the resume point whose meaning is "the cooldown already ran, do not redo
            # it", i.e. the prior attempt's blocks ARE the live cooldown this attempt stands on.
            # A remedy that genuinely changes the cooling (a slower cool_block_hold_steps)
            # resumes from "anneal_hold" and regenerates, so it can never inherit a cell from a
            # cooldown it replaced.
            #
            # do_thermal validates the recovered tag exactly as it validates a fresh one -- the
            # file must exist and its temperature must sit within one cool block of the sweep
            # top -- so a window edit between attempts falls back to reheating rather than
            # silently starting from the wrong temperature.
            args.tg_start_data = None       # never inherit across stage executions
            args.tg_start_T_K = None
            for prior in reversed(context.get("prior_attempts") or ()):
                manifest_path = prior.get("manifest")
                if not manifest_path or not Path(manifest_path).is_file():
                    continue
                prior_outputs = json.loads(Path(manifest_path).read_text()).get("outputs") or {}
                if prior_outputs.get("tg_start_data_path"):
                    args.tg_start_data = prior_outputs["tg_start_data_path"]
                    args.tg_start_T_K = prior_outputs.get("tg_start_T_K")
                    break
        for key, value in context["parameters"].items():
            if hasattr(args, key):
                setattr(args, key, value)
        args.work_dir = str(attempt_dir / "work")
        args.output_dir = str(attempt_dir / "raw")
        build = self._outputs(context, "build")
        equil = self._outputs(context, "equilibration")
        thermal = self._outputs(context, "thermal") or None
        mechanical = self._outputs(context, "mechanical") or None
        if build:
            args.data_path = build.get("data_path")
            args.build_data_path = build.get("data_path")
            args.emc_params_path = build.get("emc_params_path")
            args.n_atoms = build.get("n_atoms")
        if equil:
            args.data_path = equil.get("npt_prod_data_path")
            # The thermal stage's sweep starts here, not from npt_final -- see do_thermal.
            # Read back from the persisted manifest so a resumed run picks the same cool_block
            # the original chain tagged (there is no formula that recovers it).
            args.tg_start_data = equil.get("tg_start_data_path")
            args.tg_start_T_K = equil.get("tg_start_T_K")
        if stage == "equilibration" and context["parameters"].get("npt_continuation_ns"):
            for prior in reversed(context.get("prior_attempts") or ()):
                manifest_path = prior.get("manifest")
                if not manifest_path or not Path(manifest_path).is_file():
                    continue
                prior_outputs = json.loads(Path(manifest_path).read_text()).get("outputs") or {}
                # The .restart output (read_restart, appended log/dump), NOT .data -- a genuine
                # continuation of the prior attempt's own trajectory, not a fresh stage.
                if prior_outputs.get("npt_prod_restart_path"):
                    args.pending_continuation_path = prior_outputs["npt_prod_restart_path"]
                    args.npt_continuation_ns = context["parameters"]["npt_continuation_ns"]
                    args.equilibration_extend_base_stage = context["parameters"].get(
                        "equilibration_extend_base_stage", "npt_final")
                    args.equilibration_extend_ensemble = context["parameters"].get(
                        "equilibration_extend_ensemble", "npt")
                    break
        # equilibration_resume_from: set by a remedy (_cooling -> "anneal_hold", regenerating
        # the blockwise cooldown with a slower cool_block_hold_steps) to signal
        # do_equil_and_check should resume a generate_equilibration_workflow(resume_from=...)
        # chain instead of a fresh from-scratch submission. Locate the real checkpoint from the
        # most recent prior attempt's own stage_checkpoints (do_equil_and_check surfaces it on
        # every return, halted or not) -- same reversed(prior_attempts) walk as
        # npt_continuation_ns above. The checkpoint name IS the resume_from value directly now
        # (one of generate_equilibration_workflow's 8 fixed checkpoint names) -- no per-cycle
        # name derivation needed, since annealing is no longer cycle-counted.
        resume_kind = cls.get("equilibration_resume_from")
        if stage == "equilibration" and resume_kind:
            for prior in reversed(context.get("prior_attempts") or ()):
                manifest_path = prior.get("manifest")
                if not manifest_path or not Path(manifest_path).is_file():
                    continue
                prior_manifest = json.loads(Path(manifest_path).read_text())
                checkpoints = (prior_manifest.get("outputs") or {}).get("stage_checkpoints") or {}
                if checkpoints.get(resume_kind):
                    args.equil_resume_from = resume_kind
                    args.equil_resume_data_path = checkpoints[resume_kind]
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
                        #
                        # cooling_verdict was the second link in this chain until 2026-09-01.
                        # density_value_binding is now ADVISORY (enforce_gate.STRUCTURAL_GATES),
                        # so it can no longer BE the cause of a STRUCTURAL_FAIL -- and leaving it
                        # here would be worse than useless: it sat AHEAD of homogeneity, so a
                        # genuine homogeneity failure on a cell that also carried an advisory
                        # UNDER_ANNEALED_COOLING would route to slower_cooling instead of
                        # melt_homogeneity. Dropped with the demotion, not separately.
                        finite_size_code = detail.get("finite_size_verdict")
                        code = (finite_size_code
                                if finite_size_code not in (None, "SIZE_PASS") else
                                ("DENSITY_HETEROGENEITY"
                                 if detail.get("homogeneity_verdict") == "HOMOG_HETEROGENEOUS"
                                 else code))
                    confidence = detail.get("remedy_confidence") or "high"
                    return StageResult("remedy_required",
                                       (Finding(code, stage, confidence=confidence,
                                                details=detail),),
                                       self._artifacts(attempt_dir), outputs)
            elif stage == "thermal":
                outputs = do_thermal(args, cls, self.lammps, equil.get("density_gcm3"))
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
                                     equil.get("equil_verdict"), attempt_dir / "raw",
                                     equil_result=equil, mechanical_result=mechanical)
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
        # Separate, independently-failing step: turn this run's now-frozen
        # system_characterization_cache.json entry (if protocol_validated) into protocol
        # evidence for planning OTHER polymers, not just a same-SMILES replay. See
        # ingest_internal_run_evidence.py's module docstring for why this is a second
        # script rather than inlined into write_characterization_cache().
        try:
            from ingest_internal_run_evidence import ingest_from_completed_run
            ingest_from_completed_run(run_name, repo_root=repo_root)
        except Exception as exc:  # never fail an accepted campaign on an evidence-ingest problem
            print(f"WARNING: internal-run evidence ingest failed for {run_name}: {exc}",
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
