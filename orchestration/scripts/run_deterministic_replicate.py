#!/usr/bin/env python3
"""
run_deterministic_replicate.py — scripted execution of a replicate whose exact canonical SMILES
is already protocol_validated in guides/system_characterization_cache.json (plan_mode=="deterministic").

For a validated protocol (plan_mode=="deterministic"), every execution-stage worker
(molecule-builder, equilibration-worker, equilibration-checker, tg-sweep-worker,
tg-analysis-worker, murnaghan-worker, deform-worker, bulk-modulus-extractor,
exp-lookup-worker, run-summary-worker) used to spawn as a full Claude subagent every run,
even though its prompt was byte-identical every time and it made no real judgment call
(orchestration/gen_prompt.py's own docstring: "worker prompts are byte-identical to the
pre-architecture pipeline"). This script replaces that ~10-agent-spawn chain with one plain
Python process that calls the same underlying MCP-server functions directly.

Feasibility (verified, not assumed): every MCP tool in mcp-servers/mcp-lammps-engine/server.py
and mcp-servers/mcp-emc-server/server.py is a plain function — FastMCP's @mcp.tool() decorator
registers but returns the original function unchanged, and mcp.run() is behind
`if __name__=="__main__"`, so importing server.py directly (bypassing MCP transport entirely)
is safe. mcp-lammps-engine/tests/test_watch_run.py already does exactly this as a committed
precedent. Async job completion is filesystem/sentinel-based (SENTINEL_DIR), written by a fully
detached `setsid nohup ... & disown` wrapper regardless of whether anything is still listening —
so this script just blocks on the sentinel instead of doing the BACKGROUND-WAIT
launch-detached/end-turn/wake-on-exit dance a live Claude session needs (a script has no "turn"
to yield in the first place).

Scope of this version: EMC build path only (18 of ~19 supported classes). PURA (the one
RadonPy-only class) is out of scope for now — do_build() raises a clear error rather than
attempting it; see the deferred build_via_radonpy.py cross-interpreter driver in the plan.

One invocation, end to end: this SMILES is always already covered by a
system_characterization_cache.json entry (protocol_validated==true requires it), so
system-characterization-analyzer's mandatory refine (FOUNDATION.md's `[Equilibration]` step,
reasoned-path only) never applies here — this script runs build through run-summary in one call.

Resumability: data/<RUN>/raw/executor_state.json tracks per-stage status, so a crash (reboot,
OOM-killed wrapper) doesn't discard hours of completed work — just re-running with the same
--plan skips any stage already marked "done".

Recovery scope matches .claude/commands/recover.md's plan_mode=="deterministic" rule exactly:
only EXTEND-type recovery (parameter tweaks that never touch decided_params) auto-applies, capped
at 2 attempts. STRUCTURAL_FAIL, or Murnaghan+deform both failing acceptance, halt immediately and
write the diagnostic for human review — never auto-changing a protocol that's supposed to be
identical across replicates.

Usage:
  <repo>/mcp-servers/.venv/bin/python orchestration/run_deterministic_replicate.py \\
      --run_name RUN --polymer_class CLASS --plan data/RUN/raw/run_plan.json \\
      [--dry-run] [--properties density,tg,bulk_modulus]

  (Invoking via a different interpreter is fine — the script re-execs itself under the venv
  python needed for fastmcp/numpy/scipy/MDAnalysis before importing the MCP servers.)
"""

import argparse
import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from gen_prompt import resolve_stage_params, apply_plan, resolve_hardware, load_plan  # noqa: E402
from hw_common import load_rules, get_class_entry  # noqa: E402
import execution_chain  # noqa: E402

LAMMPS_ENGINE_DIR = REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"
EMC_SERVER_DIR = REPO_ROOT / "mcp-servers" / "mcp-emc-server"
VENV_PY = REPO_ROOT / "mcp-servers" / ".venv" / "bin" / "python"
MCP_JSON = REPO_ROOT / ".mcp.json"

POLL_SECONDS = 30
EXTEND_MAX_ATTEMPTS = 2


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


# ─── Executor state (resumability) ─────────────────────────────────────────────

class ExecutorState:
    """Per-run persisted stage status (data/<RUN>/raw/executor_state.json). A stage marked
    "done" is never re-run; re-invoking with the same --plan picks up from the first non-done
    stage. Also what protocol-locker reads for "what did this run need to fix" when a
    locked-protocol replicate needed an EXTEND."""

    def __init__(self, path: Path, run_name: str, polymer_class: str, plan_path: str):
        self.path = path
        if path.exists():
            self.data = json.loads(path.read_text())
        else:
            self.data = {"run_name": run_name, "polymer_class": polymer_class,
                         "plan_path": str(plan_path), "stages": {}, "halted": None}
            self._save()

    def _save(self):
        self.path.write_text(json.dumps(self.data, indent=2) + "\n")

    def stage(self, name: str) -> dict:
        return self.data["stages"].get(name, {})

    def is_done(self, name: str) -> bool:
        return self.stage(name).get("status") == "done"

    def mark(self, name: str, status: str, **extra):
        self.data["stages"][name] = {"status": status,
                                     "updated_at": datetime.now(timezone.utc).isoformat(),
                                     **extra}
        self._save()

    def halt(self, stage: str, reason: str, detail: dict = None):
        self.data["halted"] = {"stage": stage, "reason": reason, "detail": detail or {},
                               "at": datetime.now(timezone.utc).isoformat()}
        self._save()


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
    label, verify release) enforced structurally rather than by convention."""

    def __init__(self, run_name: str, need: int):
        self.run_name, self.need = run_name, need

    def __enter__(self) -> str:
        result = _pick_gpu("claim", self.run_name, self.need)
        if "claimed" not in result:
            raise RuntimeError(f"GPU claim failed for {self.run_name} (need={self.need}): {result}")
        self.claimed = result["claimed"]
        return ",".join(str(i) for i in self.claimed)

    def __exit__(self, exc_type, exc, tb):
        rel = _pick_gpu("release", self.run_name)
        if "released" not in rel:
            print(f"WARNING: GPU release may have failed for {self.run_name}: {rel}", file=sys.stderr)
        return False


# ─── Run waiting (replaces BACKGROUND-WAIT — a script just blocks) ────────────

def wait_for_run(lammps, run_id: str, label: str) -> dict:
    """Block until run_id (a run_id or chain_id) reaches a terminal state: sentinel file first,
    pidfile liveness as a dead-process fallback — the same two signals the bash monitor_command
    checks, just polled natively in Python since this process has no Claude turn to yield."""
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


# ─── run_log.md writing (minimal but covers what enforce_gate.py's retrospective ─────
# lint checks: the Seeds line and a non-placeholder D-05 block) ────────────────

def _append_run_log(run_log_path: Path, text: str):
    with open(run_log_path, "a") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def log_seed(run_log_path: Path, label: str, seed):
    _append_run_log(run_log_path, f"\n_Seed logged ({label}): `{seed}`_\n")


def log_d05(run_log_path: Path, d05_markdown: str):
    _append_run_log(run_log_path, "\n## D-05 CONVERGENCE DETAIL (scripted)\n\n" + d05_markdown + "\n")


def log_recovery(run_log_path: Path, stage: str, attempt: int, trigger: str, action: str, outcome: str):
    _append_run_log(run_log_path, (
        f"\n## RECOVERY — {stage} attempt {attempt}\n"
        f"- **Trigger:** {trigger}\n- **Action:** {action}\n- **Outcome:** {outcome}\n"))


# ─── Base args namespace (mirrors gen_prompt.py's argparse defaults) ──────────

# Single definition, shared with the plan writer so the chain a plan records and the chain this
# executor runs are resolved from identical starting args.
_base_args = execution_chain.base_args


# ─── Frozen protocol accessors ────────────────────────────────────────────────

def _frozen(args) -> dict:
    """The plan's frozen_protocol block: what this exact molecule ACTUALLY RAN, per track."""
    return getattr(args, "_frozen_protocol", None) or {}


def _frozen_seeds(args) -> dict:
    return (_frozen(args).get("foundation") or {}).get("seeds_used") or {}


def _frozen_route(args, track: str) -> dict:
    return (_frozen(args).get(track) or {}).get("route") or {}


def _pinned_steps(args, p: dict) -> dict:
    """Equilibration step counts to actually submit: the frozen protocol's resolved integers where
    it has them, the resolver's values otherwise.

    Load-bearing. Without this the executor would fall back to generate_equilibration_workflow's
    atom-count tier (5,000/15,000 boundaries) while the plan's execution_chain advertised the
    pinned counts — the plan would record a protocol the run did not execute, which is the exact
    failure this whole feature exists to prevent. Both this executor and --emit-decks go through
    here, and both share execution_chain's mapping so there is one definition of the pinning."""
    pinned = execution_chain._pin_steps_from_frozen(
        (_frozen(args).get("foundation") or {}).get("equil_stages"))
    return {
        "npt_prod_steps": pinned.get("npt_production", p["npt_prod_steps"]),
        "npt_cool_steps": pinned.get("npt_cool", p["npt_cool_steps"]),
        "npt_cool300_steps": pinned.get("npt_cool300", p["npt_cool300_steps"]),
        "melt_npt_steps": pinned.get("npt_melt", p["melt_npt_steps"]),
    }


def _assert_chain_matches_execution(args, cls: dict, plan: dict) -> dict:
    """The plan advertises an `execution_chain`; this executor then runs its own control flow.
    If the two ever disagree, the chain becomes exactly the kind of decorative artifact this
    whole feature exists to eliminate — a recorded protocol that is not the executed one.

    So compare them before submitting anything: re-resolve the chain from these same args and
    check the physics arguments of every stage against what the executor is about to pass.
    Halts on a mismatch rather than running a protocol the plan misdescribes."""
    recorded = plan.get("execution_chain")
    if not recorded:
        return {"checked": False, "reason": "plan carries no execution_chain"}

    properties = ({"density", "tg", "bulk_modulus"} if args.properties in (None, "all")
                  else {p.strip().lower() for p in args.properties.split(",") if p.strip()})
    live = execution_chain.build_execution_chain(args, cls, plan, properties, _frozen(args))

    rec_steps = [(s["stage"], s["tool"]) for s in recorded]
    live_steps = [(s["stage"], s["tool"]) for s in live]
    if rec_steps != live_steps:
        raise SystemExit(
            "Halting: the plan's execution_chain does not match what this executor would run.\n"
            f"  plan:     {rec_steps}\n  executor: {live_steps}\n"
            "Regenerate the plan (make_deterministic_plan.py) — never run against a stale chain.")

    # The equilibration step counts are the ones with two independent resolution paths (the
    # chain's _pin_steps_from_frozen and the executor's _pinned_steps), so check them by value.
    rec_equil = next((s["args"] for s in recorded
                      if s["tool"] == "generate_equilibration_workflow"), {})
    p = resolve_stage_params("equil", args, cls)
    live_equil = _pinned_steps(args, p)
    mismatched = {k: {"plan": rec_equil.get(k), "executor": v}
                  for k, v in live_equil.items() if rec_equil.get(k) != v}
    if mismatched:
        raise SystemExit(
            "Halting: the plan's execution_chain and this executor disagree on equilibration "
            f"step counts: {json.dumps(mismatched)}. The plan would record a protocol the run "
            "did not execute. Regenerate the plan.")
    return {"checked": True, "stages": len(live_steps)}


def _cis_lock_guard(plan: dict) -> dict:
    """Refuse to replicate a SMILES whose cache entry says its numbers only hold behind a
    microstructure lock stage this executor cannot reproduce. Previously written into the cache
    and read by nothing."""
    smiles = plan.get("canonical_smiles") or plan.get("smiles")
    cache_path = REPO_ROOT / "guides" / "system_characterization_cache.json"
    try:
        entry = json.loads(cache_path.read_text()).get(smiles) or {}
    except (OSError, json.JSONDecodeError):
        return {}
    if not entry.get("requires_cis_lock"):
        return {}
    return {"reason": "REQUIRES_MICROSTRUCTURE_LOCK", "canonical_smiles": smiles,
            "cis_lock_deck": entry.get("cis_lock_deck"),
            "detail": entry.get("note", "")[:400],
            "action": "This executor's EMC build path cannot reproduce the lock stage. Run this "
                      "SMILES through the agent-driven pipeline, or re-measure after locking."}


# ─── Stage: build ───────────────────────────────────────────────────────────

def do_build(state: ExecutorState, args, cls: dict, emc, lammps, run_log_path: Path) -> dict:
    preferred_builder = cls.get("preferred_builder", "emc")
    if preferred_builder != "emc":
        raise SystemExit(
            f"run_deterministic_replicate.py: preferred_builder={preferred_builder!r} is not "
            f"supported yet — this script only implements the EMC build path. RadonPy/PURA "
            f"needs the (deferred) cross-interpreter build_via_radonpy.py driver; run this "
            f"class through the normal agent-driven pipeline for now.")

    p = resolve_stage_params("build", args, cls)
    work_dir = Path(p["work_dir"])
    emc_seed = p["emc_seed"] if p["emc_seed"] is not None else random.randint(1, 999_999)
    frozen_seeds = _frozen_seeds(args)
    if frozen_seeds.get("emc_seed") is not None and emc_seed == frozen_seeds["emc_seed"]:
        # Redraw once rather than halt -- a chance collision in a 1e6 space is not an error.
        emc_seed = random.randint(1, 999_999)

    job = emc.submit_emc_cell_job(
        smiles=p["smiles"], polymer_class=args.polymer_class.upper(),
        dp=p["dp"], nchains=p["nchain"], density_initial=p["density_initial_gcm3"],
        temperature=300.0, seed=emc_seed, output_name="polymer",
    )
    if job.get("error"):
        state.mark("build", "failed", error=job["error"])
        raise SystemExit(f"submit_emc_cell_job failed: {job['error']}")
    job_id = job["job_id"]

    status = {}
    while True:
        status = emc.get_emc_job_status(job_id)
        if status.get("status") in ("completed", "failed"):
            break
        time.sleep(POLL_SECONDS)
    if status["status"] != "completed":
        state.mark("build", "failed", error=status)
        raise SystemExit(f"EMC build job {job_id} failed: {status}")

    out = emc.get_emc_job_output(job_id)["result"]
    # EMC echoes the seed it actually used. Trust that, not what we asked for: it has returned a
    # PREVIOUS run's seed while reporting a fresh draw (cis-PBD1 received cis-PBD4's 482913 with
    # a matching 68.178 A box). A replicate sharing the source run's packing is not a replicate,
    # and every downstream error bar computed from it would be understated.
    resolved_seed = out.get("resolved_seed", emc_seed)
    if frozen_seeds.get("emc_seed") is not None and resolved_seed == frozen_seeds["emc_seed"]:
        state.halt("build", "EMC_SEED_COLLISION", {
            "requested_seed": emc_seed, "resolved_seed": resolved_seed,
            "source_run_seed": frozen_seeds["emc_seed"],
            "reason": "EMC returned the seed the frozen protocol's source run used, so this "
                      "replicate would reuse that run's packing instead of sampling an "
                      "independent configuration.",
        })
        raise SystemExit(
            f"Halting: EMC resolved_seed={resolved_seed} equals the source run's seed. "
            "This is a known EMC failure mode (a reuse reported as a draw), not a coincidence "
            "to retry blindly — inspect the EMC job before re-running.")
    emc_seed = resolved_seed
    cell_dir = work_dir / "cell"
    cell_dir.mkdir(parents=True, exist_ok=True)
    dest_data = cell_dir / "cell.data"
    shutil.copy(out["data_path"], dest_data)
    # get_emc_job_output's result has no "params_path" key (only "output_dir") -- EMC always
    # writes the coefficients file as "emc_build.params" (fixed filename, independent of
    # output_name -- see smiles_to_emc.py's "'emc_build' never collides with the cluster name"
    # comment) inside output_dir. molecule-builder.md's agent-driven path locates it the same
    # way. PCFF/OPLS-AA builds store all Pair/Bond/Angle/... Coeffs here, not inline in .data.
    dest_params = None
    src_params_matches = sorted(Path(out["output_dir"]).glob("*.params"))
    if src_params_matches:
        dest_params = cell_dir / "emc_build.params"
        shutil.copy(src_params_matches[0], dest_params)

    # Size gate at the cheapest point: the built cell, before any MD. A too-small cell would
    # otherwise burn the whole equilibration chain before the equil-check gate said the same.
    ep = resolve_stage_params("equil", args, cls)
    info = lammps.inspect_data_file(
        data_file=str(dest_data), lj_cutoff=ep.get("cutoff_A") or 12.0,
        target_density_gcm3=ep.get("exp_density_gcm3"), nchain=ep.get("nchain"),
    )
    size_errors = [e for e in (info.get("validation", {}).get("errors") or [])
                   if e.startswith("SIZE_")]
    if size_errors:
        state.mark("build", "failed",
                   result={"finite_size_forecast": info.get("finite_size_forecast")})
        raise SystemExit(
            "Halting before equilibration — the built cell would self-image once compressed: "
            + " ".join(size_errors)
            + " A deterministic replicate must not silently rebuild at a different nchain; "
              "that is a decided_params change and needs human review."
        )

    result = {
        "data_path": str(dest_data),
        "emc_params_path": str(dest_params) if dest_params else None,
        "emc_seed": emc_seed,
        "lammps_flags": out["lammps_flags"],
        "n_atoms": info.get("info", {}).get("n_atoms"),
    }
    state.mark("build", "done", result=result)
    log_seed(run_log_path, "EMC", emc_seed)
    return result


# ─── Stage: equilibration + gate (EXTEND loop, STRUCTURAL_FAIL halt) ──────────

def _submit_equil_chain(args, cls: dict, lammps, extend_from_data: str = None,
                         extend_temp: float = None, extend_ns: float = 1.5) -> dict:
    p = resolve_stage_params("equil", args, cls)
    flags = p["lammps_flags"]
    velocity_seed = p["velocity_seed"]
    if extend_from_data is None:
        steps = _pinned_steps(args, p)
        workflow = lammps.generate_equilibration_workflow(
            data_file=p["data_path"], work_dir_base=p["work_dir"],
            polymer_name=args.run_name, temp=p["T_workflow_K"], max_temp=p["T_anneal_high_K"],
            press=p["P_equil_atm"], use_pcff=flags["use_pcff"], use_trappe=flags["use_trappe"],
            use_opls=flags["use_opls"], npt_prod_steps=steps["npt_prod_steps"],
            add_melt_npt=p["add_melt_npt"], t_equil_K=p["T_equil_K"] if p["add_melt_npt"] else None,
            melt_npt_steps=steps["melt_npt_steps"], engine=p["engine"], velocity_seed=velocity_seed,
            npt_cool_steps=steps["npt_cool_steps"], npt_cool300_steps=steps["npt_cool300_steps"],
            extend_steps=None,
        )
    else:
        dt = p["dt_fs"]
        extend_steps = int(extend_ns * 1e6 / dt)
        workflow = lammps.generate_equilibration_workflow(
            data_file=extend_from_data, work_dir_base=p["work_dir"], polymer_name=args.run_name,
            temp=extend_temp, press=p["P_equil_atm"], use_pcff=flags["use_pcff"],
            use_trappe=flags["use_trappe"], use_opls=flags["use_opls"], engine=p["engine"],
            velocity_seed=velocity_seed, extend_only=True, extend_steps=extend_steps,
            npt_prod_steps=None, npt_cool_steps=None, npt_cool300_steps=None,
            melt_npt_steps=None,
        )
    if workflow.get("status") == "error":
        raise SystemExit(f"generate_equilibration_workflow failed: {workflow}")

    chain = lammps.run_lammps_chain(
        stages=workflow["stages"], gpu_ids=p["gpu_ids"], mpi=p["mpi_ranks"],
        data_file=extend_from_data or p["data_path"], engine=p["engine"],
    )
    if chain.get("status") == "error":
        raise SystemExit(f"run_lammps_chain failed: {chain}")
    return {"chain_id": chain["chain_id"], "workflow": workflow}


def _stage_dump_path(stage: dict) -> str:
    return f"{stage['work_dir']}/{stage['params']['DUMP_FILE']}"


def do_equil_and_check(state: ExecutorState, args, cls: dict, lammps, run_log_path: Path) -> dict:
    # Captured before args.data_path gets reassigned to the equilibration chain's own output
    # below — the original pre-simulation .data file is the only one whose Masses section still
    # has the "# <name>" comments inspect_data_file's atom_type_names parsing needs; a write_data
    # output (which npt_prod_data_path always is) has stripped them.
    build_data_path = args.data_path

    # generate_equilibration_workflow rejects a null seed; gen_prompt resolves one (pinned, else
    # derived from run_name) for the chain and every EXTEND continuation below. Log it like EMC's.
    log_seed(run_log_path, "velocity", resolve_stage_params("equil", args, cls)["velocity_seed"])

    gpu_per_run = cls.get("gpu_per_run") or 1
    with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
        args.gpu_ids = gpu_ids
        submission = _submit_equil_chain(args, cls, lammps)
        result = wait_for_run(lammps, submission["chain_id"], "equilibration chain")
    if result.get("status") != "completed":
        state.mark("equil_check", "failed", result=result)
        raise SystemExit(f"Equilibration chain did not complete: {result}")

    workflow = submission["workflow"]
    # Glassy (9-run chain, add_300k_production default True): the server exposes the terminal
    # npt_prod300 stage's output directly as npt_prod300_data/_dump. Rubbery (7-run chain, no
    # npt_prod300 stage): the terminal stage is npt_production itself — stages[-1] (no generic
    # top-level "..._data"/"..._dump" key exists for this case, per generate_equilibration_
    # workflow's own return-shape logic in server.py).
    npt_prod_data_path = workflow.get("npt_prod300_data") or workflow["stages"][-1]["output_data"]
    npt_prod_dump_path = workflow.get("npt_prod300_dump") or _stage_dump_path(workflow["stages"][-1])

    attempts = 0
    while True:
        args.data_path = npt_prod_data_path
        p = resolve_stage_params("equil-check", args, cls)
        # The resolver's value, not the raw CLI arg: the halt below says the list comes from
        # decided_params, and only the resolver reads it from there (via the plan-overlaid cls).
        backbone_types = p["backbone_types"]
        if backbone_types is None:
            # inspect_data_file only for diagnostics attached to the halt below — atom names
            # alone (e.g. "c"/"c1") don't determine which types are backbone vs. pendant branch
            # for a branched-backbone class (confirmed live: PACR/PMMA shares generic aliphatic
            # carbon types between CH2 backbone atoms and pendant methyl branches), so this is
            # never auto-derived into a backbone_types list — only ever an explicit
            # decided_params/CLI value, reviewed like any other protocol-lock decision.
            # Diagnostics only — this call exists to surface atom_type_names in the halt
            # below, not to run the size gate (do_build already ran that on this same file).
            # The forecast args are passed as explicit nulls to say so.
            diag = lammps.inspect_data_file(
                data_file=build_data_path, lj_cutoff=p["cutoff_A"] or 12.0,
                target_density_gcm3=None, nchain=None,
            )
            state.halt("equil_check", "BACKBONE_TYPES_UNRESOLVED", {
                "reason": "decided_params has no backbone_types for this class and none may be "
                          "auto-derived (atom-name-only lookup cannot distinguish backbone from "
                          "pendant-branch atoms sharing the same type ID)",
                "atom_type_names": diag.get("info", {}).get("atom_type_names"),
                "build_data_path": build_data_path,
            })
            log_recovery(run_log_path, "equilibration", attempts, "backbone_types unresolved",
                        "none — requires human/agent review of atom_type_names to populate "
                        "decided_params.backbone_types for this class",
                        "UNRESOLVED — human review")
            return {"halted": True, "reason": "BACKBONE_TYPES_UNRESOLVED"}

        comp = wait_for_analysis(lammps, lammps.check_equilibration_comprehensive(
            log_file=p["npt_prod_log_path"], dump_file=p["melt_dump_path"],
            data_file=p["npt_prod_data_path"], backbone_types=backbone_types,
            ct_min_decay=p["ct_min_decay_melt"], output_dir=p["output_dir"], graphs_dir=p["graphs_dir"],
            cutoff_A=p["cutoff_A"], timestep_fs=p["dt_fs"],
        ), "equil-check comprehensive")
        density = wait_for_analysis(lammps, lammps.extract_equilibrated_density(
            log_file=p["npt_prod_log_path"], target_temp=p["npt_prod_temp_K"], output_dir=p["output_dir"],
        ), "equil-check density")
        comprehensive_json = str(Path(p["output_dir"]) / "equilibration_comprehensive.json")
        verdict = lammps.enforce_equilibration_gate(
            comprehensive_json=comprehensive_json, regime=p["regime"], dp=p["dp"],
            ct_gate_reliable=p["ct_gate_reliable"], exp_density_gcm3=p["exp_density_point_gcm3"],
            tg_K=p["exp_tg_point_K"], t_equil_K=p["T_workflow_K"], glass_data=p["npt_prod_data_path"],
            melt_data=p["melt_data_path"], out_dir=p["output_dir"],
            alpha_glass_per_K=None if p["alpha_glass_per_K"] == "null" else p["alpha_glass_per_K"],
            alpha_melt_per_K=None if p["alpha_melt_per_K"] == "null" else p["alpha_melt_per_K"],
            # This executor runs the whole chain in one go, so its gate call is always the
            # post-cooldown one; the melt checkpoint is a reasoned-path split.
            phase="full", polymer_class=args.polymer_class.upper(),
            polymer_name=getattr(args, "polymer_name", None),
        )
        equil_verdict = verdict.get("verdict")
        if verdict.get("d05_markdown"):
            log_d05(run_log_path, verdict["d05_markdown"])

        if equil_verdict == "PASS":
            result = {"equil_verdict": "PASS", "npt_prod_data_path": p["npt_prod_data_path"],
                      "npt_prod_log_path": p["npt_prod_log_path"], "npt_prod_dump_path": npt_prod_dump_path,
                      "density_gcm3": density.get("plateau_density_mean")}
            state.mark("equil_check", "done", result=result)
            return result

        if equil_verdict == "EXTEND":
            attempts += 1
            if attempts > EXTEND_MAX_ATTEMPTS:
                state.halt("equil_check", "EXTEND_EXHAUSTED", {"attempts": attempts})
                log_recovery(run_log_path, "equilibration", attempts, "EXTEND verdict",
                            "exceeded max EXTEND attempts (deterministic cap=2)", "UNRESOLVED — human review")
                return {"halted": True, "reason": "EXTEND_EXHAUSTED"}
            # A measured relaxation signal from this run's own data beats a blind flat guess —
            # tau_relax_ps comes from comp's KWW fit (same field system-characterization-analyzer reads).
            tau_relax_ps = (((comp or {}).get("chain") or {}).get("ct") or {}).get("tau_relax_ps")
            extend_ns = 1.5
            if isinstance(tau_relax_ps, (int, float)) and tau_relax_ps > 0:
                extend_ns = max(1.5, round(1.5 * tau_relax_ps / 1000, 2))
            log_recovery(run_log_path, "equilibration", attempts, "equil_verdict=EXTEND",
                        f"npt_extend +{extend_ns} ns at {p['npt_prod_temp_K']} K", "pending")
            with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
                args.gpu_ids = gpu_ids
                submission = _submit_equil_chain(args, cls, lammps, extend_from_data=p["npt_prod_data_path"],
                                                 extend_temp=p["npt_prod_temp_K"], extend_ns=extend_ns)
                ext_result = wait_for_run(lammps, submission["chain_id"], "equilibration EXTEND")
            if ext_result.get("status") != "completed":
                state.mark("equil_check", "failed", result=ext_result)
                raise SystemExit(f"EXTEND chain did not complete: {ext_result}")
            npt_prod_data_path = submission["workflow"]["stages"][0]["output_data"]
            npt_prod_dump_path = _stage_dump_path(submission["workflow"]["stages"][0])
            continue

        # STRUCTURAL_FAIL or FAIL — plan_mode=="deterministic" NEVER auto-applies a protocol
        # change here (recover.md's rule); halt immediately for human review.
        state.halt("equil_check", equil_verdict, verdict)
        log_recovery(run_log_path, "equilibration", attempts + 1, f"equil_verdict={equil_verdict}",
                    "none — deterministic replicate, protocol changes are never auto-applied",
                    "UNRESOLVED — human review (see structural_fail_remedy in verdict detail above)")
        return {"halted": True, "reason": equil_verdict, "detail": verdict}


# ─── Stage: thermal track ──────────────────────────────────────────────────

def do_thermal(state: ExecutorState, args, cls: dict, lammps, raw_dir: Path, graphs_dir: Path,
               run_log_path: Path) -> dict:
    """Single-rate-primary: run one sweep at the class's primary configured rate (highest by
    default; tg_slope_gate_fallback="slowest_rate" classes — PKTN, PSFO — run rates[0] instead,
    since their highest-rate fit is documented as degenerate/inverted). Multirate extrapolation
    is a legacy/opt-in capability (extract_tg_multirate.py, select_tg_path.py) not exercised here."""
    tg_rates = cls.get("tg_rates_K_per_ns", [])
    gpu_per_run = cls.get("gpu_per_run") or 1
    per_rate = []
    if tg_rates:
        fallback = cls.get("tg_slope_gate_fallback")
        idx = 0 if fallback == "slowest_rate" else len(tg_rates) - 1
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
                       "N_STEPS_PER_T": p["n_steps_per_t"], "P_START": 1.0, "P_FINAL": 1.0,
                       "T_DAMP": 100.0, "TIMESTEP": p["dt_fs"], "use_pppm": not p["lammps_flags"]["use_trappe"],
                       "use_gpu": True, "engine": p["engine"],
                       # An EMC cell carries no inline Coeffs, so a deck without this include
                       # dies at parse time. Resolved to the cell dir's copy, not work_dir --
                       # nothing writes a params copy into the thermal dir.
                       **({"params_file": p["emc_params_path"]} if p["emc_params_path"] else {}),
                       **{f"use_{k.split('_')[1]}": v
                       for k, v in p["lammps_flags"].items()}},
            )
            run = lammps.run_lammps_script(
                script=script["output_script"], work_dir=p["tg_sweep_dir"], log_file="tg_sweep_run.log",
                gpu_ids=p["gpu_ids"], mpi=p["mpi_ranks"], engine=p["engine"],
            )
            result = wait_for_run(lammps, run["run_id"], f"tg sweep rate={rate}")
        if result.get("status") != "completed":
            state.mark("thermal", "failed", result=result)
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
                         "output_dir": ap["output_dir"], "used_highest_rate": idx == len(tg_rates) - 1})

    highest = per_rate[-1] if per_rate else None

    # is_glassy determination (THERMAL_TRACK.md's single-sweep algorithm): only trust this
    # sweep's Tg for is_glassy when it ran at the class's highest configured rate — a class that
    # deliberately ran the slowest rate instead (PKTN, PSFO) falls through to the exp-Tg
    # decision, the same outcome those classes got via the old slope-gate-failure path.
    degenerate = (not highest) or highest["fit_quality"] == "POOR" or not highest["used_highest_rate"]
    if degenerate:
        exp_tg = cls.get("experimental_tg_K")
        exp_tg_val = exp_tg if isinstance(exp_tg, (int, float)) else None
        is_glassy = bool(exp_tg_val and exp_tg_val > 300)
    else:
        is_glassy = bool(highest and isinstance(highest["Tg_K"], (int, float)) and highest["Tg_K"] > 300)

    result = {"per_rate": per_rate, "is_glassy": is_glassy}
    state.mark("thermal", "done", result=result)
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
               "STRAIN_MAX": p["K_strain_max"], "TIMESTEP": p["dt_fs"], "use_gpu": True,
               "engine": p["engine"], **p["lammps_flags"]},
    )
    run = lammps.run_lammps_script(
        script=script["output_script"], work_dir=p["work_dir"], log_file=f"05_deform{suffix}.log",
        gpu_ids=p["gpu_ids"], mpi=p["mpi_ranks"], engine=p["engine"],
    )
    return {"run_id": run["run_id"], "log_path": f"{p['work_dir']}/05_deform{suffix}.log"}


def do_mechanical(state: ExecutorState, args, cls: dict, lammps, is_glassy: bool,
                  npt_prod_data_path: str, raw_dir: Path, graphs_dir: Path) -> dict:
    args.is_glassy = "true" if is_glassy else "false"
    gpu_per_run = cls.get("gpu_per_run") or 1
    p = resolve_stage_params("murnaghan", args, cls)

    # Force the frozen route. A K from the deform fallback and a K from Murnaghan are different
    # measurements, so a replicate has to reproduce the branch the source run took rather than
    # re-decide it from its own fit. The forced branch is recorded either way -- forcing must
    # never silently discard the acceptance signal this run's own gate would have given.
    forced = _frozen_route(args, "mechanical").get("bm_method")
    if forced == "deform" and is_glassy:
        result = _run_deform_pair(state, args, cls, lammps, gpu_per_run, raw_dir, graphs_dir)
        result["route_forced"] = True
        result["own_gate_said"] = "not evaluated — frozen route went straight to deform"
        state.mark("mechanical", "done", result=result)
        return result

    if not (is_glassy or p["bm_pressures_atm"]):
        # rubbery + no pressures — fluctuation path, no submission
        bp = resolve_stage_params("analyze-bm", args, cls)
        bm = wait_for_analysis(lammps, lammps.extract_bulk_modulus(
            log_file=bp["npt_prod_log_path"], output_dir=bp["output_dir"], graphs_dir=bp["graphs_dir"],
        ), "bulk modulus (fluctuation)")
        result = {"method": "fluctuation", "bulk_modulus_GPa": bm.get("bulk_modulus_GPa")}
        state.mark("mechanical", "done", result=result)
        return result

    with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
        args.gpu_ids = gpu_ids
        series = lammps.run_bulk_modulus_series(
            data_file=p["equil_data_path"], work_dir=f"{p['work_dir']}/bm_series",
            pressures_atm=p["bm_pressures_atm"] or [-1000, 0, 3000, 7000, 15000], temp_K=p["temp_K"],
            run_name=args.run_name, gpu_ids=p["gpu_ids"], mpi=p["mpi_ranks"],
            velocity_seed=p["velocity_seed"], npt_steps=p["npt_steps"],
            dt_fs=p["dt_fs"], use_trappe=p["lammps_flags"]["use_trappe"],
            use_pcff=p["lammps_flags"]["use_pcff"], use_opls=p["lammps_flags"]["use_opls"], engine=p["engine"],
        )
        if series.get("status") == "error":
            raise SystemExit(f"run_bulk_modulus_series failed: {series}")
        m_result = wait_for_run(lammps, series["chain_id"], "murnaghan series")
    if m_result.get("status") != "completed":
        state.mark("mechanical", "failed", result=m_result)
        raise SystemExit(f"Murnaghan series did not complete: {m_result}")

    bp = resolve_stage_params("analyze-bm", args, cls)
    murn = wait_for_analysis(lammps, lammps.extract_bulk_modulus_murnaghan(
        log_files=series["log_files"], pressures_atm=series["pressures_atm"],
        output_dir=bp["output_dir"], graphs_dir=bp["graphs_dir"],
        npt_prod_log=bp["npt_prod_log_path"],
    ), "bulk modulus (murnaghan)")
    accepted = bool(murn.get("fit_converged"))

    if accepted:
        result = {"method": "murnaghan", "bulk_modulus_GPa": murn.get("bulk_modulus_GPa"),
                 "B0_prime": murn.get("B0_prime")}
        state.mark("mechanical", "done", result=result)
        return result

    if not is_glassy:
        # rubbery Murnaghan rejection has no deform fallback in this pipeline — report as-is
        result = {"method": "murnaghan", "bulk_modulus_GPa": murn.get("bulk_modulus_GPa"),
                 "accepted": False, "reason": "fit_converged=False"}
        state.mark("mechanical", "done", result=result)
        return result

    result = _run_deform_pair(state, args, cls, lammps, gpu_per_run, raw_dir, graphs_dir)
    if forced == "murnaghan":
        # The frozen route says the source run reported Murnaghan, but this replicate's fit was
        # rejected. Surfaced rather than swallowed: the two runs are no longer measuring K the
        # same way, so the comparison between them needs a human eye.
        result["route_diverged"] = True
        result["frozen_route"] = "murnaghan"
        result["own_gate_said"] = "fit_converged=False — fell back to deform"
    state.mark("mechanical", "done", result=result)
    return result


def _run_deform_pair(state: ExecutorState, args, cls: dict, lammps, gpu_per_run: int,
                     raw_dir: Path, graphs_dir: Path) -> dict:
    """Deform at the primary rate, then the slow rate for the rate-sensitivity check. Reached
    either as the Murnaghan fallback or because the frozen protocol's route says deform."""
    with gpu_claim(args.run_name, gpu_per_run) as gpu_ids:
        args.gpu_ids = gpu_ids
        primary = _submit_deform(args, cls, lammps, "primary")
        d_result = wait_for_run(lammps, primary["run_id"], "deform primary")
    if d_result.get("status") != "completed":
        state.mark("mechanical", "failed", result=d_result)
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
        **({"log_file_2": slow_log, "strain_rate_2": bp["strain_rate_slow_per_fs"]} if slow_log else {}),
    ), "bulk modulus (deform)")
    return {"method": "deformation", "bulk_modulus_GPa": deform_extract.get("bulk_modulus_GPa"),
            "shear_modulus_GPa": deform_extract.get("shear_modulus_GPa"),
            "youngs_modulus_GPa": deform_extract.get("youngs_modulus_GPa")}


# ─── Stage: summary ─────────────────────────────────────────────────────────

def do_summary(state: ExecutorState, args, cls: dict, lammps, is_glassy: bool, thermal_result,
               raw_dir: Path, graphs_dir: Path, plan_path: str, run_log_path: Path) -> dict:
    exp_lookup_path = raw_dir / "exp_lookup.json"
    properties = ({"density", "tg", "bulk_modulus"} if args.properties in (None, "all")
                  else {x.strip().lower() for x in args.properties.split(",") if x.strip()})
    subprocess.run([
        sys.executable, str(REPO_ROOT / "db" / "query_best_match.py"),
        "--polymer_name", args.polymer_name or args.run_name, "--polymer_class", args.polymer_class.upper(),
        "--T_sim_K", "300.0", "--is_glassy", "true" if is_glassy else "false",
        "--properties", ",".join(sorted(properties)), "--output_path", str(exp_lookup_path),
    ], check=False)
    exp_lookup = json.loads(exp_lookup_path.read_text()) if exp_lookup_path.exists() else {}

    def _range(key_min, key_max):
        return exp_lookup.get(key_min), exp_lookup.get(key_max)

    args.exp_tg_min, args.exp_tg_max = _range("exp_tg_min_K", "exp_tg_max_K")
    args.exp_density_min, args.exp_density_max = _range("exp_density_min_gcm3", "exp_density_max_gcm3")
    args.exp_K_min, args.exp_K_max = _range("exp_K_min_GPa", "exp_K_max_GPa")

    tg_path = None
    if thermal_result is not None:
        # Single-rate-primary: the one sweep's tg_summary.json path is already known from the
        # analyze-tg stage's own output_dir — no rate ambiguity to resolve, no select_tg_path.py
        # call (that helper is kept for the legacy/opt-in multirate path only).
        if thermal_result.get("per_rate"):
            tg_path = str(Path(thermal_result["per_rate"][-1]["output_dir"]) / "tg_summary.json")
        args.tg_path = tg_path
        args.tg_fit_quality = (thermal_result["per_rate"][-1]["fit_quality"]
                               if thermal_result.get("per_rate") else "N/A (not requested)")

    args.d05 = "PASS"  # do_summary is only reached after equil_check returned PASS
    sp = resolve_stage_params("run-summary", args, cls)
    summary = lammps.generate_run_summary(
        output_dir=sp["output_dir"], graphs_dir=sp["graphs_dir"], run_name=args.run_name,
        smiles=args.smiles or "", polymer_class=args.polymer_class.upper(), ff=sp["ff"],
        charge_method=sp["charge_method"] or "", dp=sp["dp"], n_chains=sp["nchain"],
        d01=sp["d01_ff"], d02=sp["d02_charges"], d03=sp["d03_electrostatics"], d04=sp["d04_system_size"],
        d05=args.d05, d06=args.tg_fit_quality or "N/A (not requested)",
        exp_tg_min=sp["exp_tg_range"][0], exp_tg_max=sp["exp_tg_range"][1],
        exp_density_min=sp["exp_density_range"][0], exp_density_max=sp["exp_density_range"][1],
        exp_K_min=sp["exp_K_range"][0], exp_K_max=sp["exp_K_range"][1],
        tg_fox_flory_K=sp["tg_fox_flory_K"],
        n_replicates=args.n_replicates, tg_path=tg_path,
    )
    state.mark("summary", "done", result={"run_summary_path": str(Path(sp["output_dir"]) / "run_summary.json")})
    return summary


# ─── Dry-run mode ───────────────────────────────────────────────────────────

def _emit_decks(args, cls: dict, properties: set, out_dir: Path,
                data_file: str = None, params_file: str = None):
    """Generate every LAMMPS deck without submitting anything. This is the acceptance test for
    "same protocol, different seed": emit a replicate's decks and diff them against the source
    run's — the only differences may be seeds and paths. In particular the resolved N_STEPS must
    match even when the replicate's n_atoms falls in a different atom-count tier, which is exactly
    what the frozen protocol's pinned step counts guarantee."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lammps = _load_server_module("lammps_engine_server", LAMMPS_ENGINE_DIR / "server.py",
                                 LAMMPS_ENGINE_DIR, _mcp_env("mcp-lammps-engine"))
    emitted, errors = [], []

    p = resolve_stage_params("equil", args, cls)
    flags = p["lammps_flags"]
    # No build has run yet, so there is no cell of our own to point at. The source run's cell is
    # the right stand-in: this mode compares DECKS, and the deck's physics must not depend on
    # which packing produced the cell — only its atom count feeds the tier, and pinned step
    # counts make even that immaterial.
    src = data_file or args.data_path or p.get("data_path")
    if not src:
        raise SystemExit("--emit-decks needs a starting .data file: pass --data-file "
                         "(e.g. the source run's lammps/equil/cell.data).")
    steps = _pinned_steps(args, p)
    wf = lammps.generate_equilibration_workflow(
        data_file=src, params_file=params_file or "",
        work_dir_base=str(out_dir / "equil"), polymer_name=args.run_name,
        temp=p["T_workflow_K"], max_temp=p["T_anneal_high_K"], press=p["P_equil_atm"],
        use_pcff=flags["use_pcff"], use_trappe=flags["use_trappe"], use_opls=flags["use_opls"],
        npt_prod_steps=steps["npt_prod_steps"], add_melt_npt=p["add_melt_npt"],
        t_equil_K=p["T_equil_K"] if p["add_melt_npt"] else None,
        melt_npt_steps=steps["melt_npt_steps"], npt_cool_steps=steps["npt_cool_steps"],
        npt_cool300_steps=steps["npt_cool300_steps"], extend_steps=None,
        engine=p["engine"], velocity_seed=p["velocity_seed"],
    )
    if wf.get("status") == "success":
        emitted += [f"{s['work_dir']}/{s['name']}.in" for s in wf["stages"]]
    else:
        errors.append({"stage": "equil", "error": wf.get("error"),
                       "validation_errors": wf.get("validation_errors")})

    print(json.dumps({"status": "emitted" if not errors else "partial",
                      "out_dir": str(out_dir), "decks": emitted, "errors": errors,
                      "note": "seeds and absolute paths are expected to differ; nothing else may"},
                     indent=2, default=str))


def _print_dry_run(args, cls: dict, properties: set):
    """Resolve every applicable stage's params without submitting anything — the test this
    file's own resolve_stage_params() consumption is checked against
    (tests/test_run_deterministic_replicate.py)."""
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


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Scripted execution of a protocol_validated PolyJarvis replicate.")
    ap.add_argument("--run_name", required=True)
    ap.add_argument("--polymer_class", required=True)
    ap.add_argument("--plan", required=True, help="Path to run_plan.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="Resolve every stage's params without submitting anything; print JSON and exit.")
    ap.add_argument("--emit-decks", metavar="DIR",
                    help="Generate every LAMMPS deck into DIR without submitting anything, then "
                         "exit. Use to diff a replicate's decks against the source run's — the "
                         "acceptance test for 'same protocol, different seed'. (--dry-run only "
                         "resolves params; it writes no decks.)")
    ap.add_argument("--seed-mode", choices=["both", "velocity"], default="both",
                    help="both (default): rebuild the cell with a fresh EMC seed AND redraw "
                         "velocities — independent configurations, so the spread across "
                         "replicates is an honest uncertainty estimate. velocity: reuse the "
                         "source run's equilibrated cell and vary only the velocity seed "
                         "(requires --source-run).")
    ap.add_argument("--data-file", default=None,
                    help="--emit-decks only: starting .data file (no build has run yet).")
    ap.add_argument("--params-file", default=None,
                    help="--emit-decks only: EMC .params for a cell with no inline Coeffs.")
    ap.add_argument("--source-run", default=None,
                    help="--seed-mode velocity only: the run whose equilibrated .data to branch from.")
    ap.add_argument("--properties", default=None, help="Override properties_requested (else from plan).")
    args_cli = ap.parse_args()
    if args_cli.seed_mode == "velocity" and not args_cli.source_run:
        ap.error("--seed-mode velocity requires --source-run")

    if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
        os.execv(str(VENV_PY), [str(VENV_PY), str(Path(__file__).resolve())] + sys.argv[1:])

    rules = load_rules()
    cls_raw = get_class_entry(rules, args_cli.polymer_class, warn_on_miss=False)
    plan = load_plan(args_cli.plan)

    args = _base_args(args_cli.run_name, args_cli.polymer_class, args_cli.plan)
    if args_cli.properties:
        args.properties = args_cli.properties
    cls = apply_plan(cls_raw, plan, args)
    resolve_hardware(args, cls, rules)
    # What this exact molecule actually ran, if it has been frozen. Drives seed-collision
    # detection and mechanical route forcing.
    args._frozen_protocol = plan.get("frozen_protocol") or {}

    properties = ({"density", "tg", "bulk_modulus"} if args.properties in (None, "all")
                  else {p.strip().lower() for p in args.properties.split(",") if p.strip()})

    if args_cli.dry_run:
        _print_dry_run(args, cls, properties)
        return

    if args_cli.emit_decks:
        _emit_decks(args, cls, properties, Path(args_cli.emit_decks),
                    args_cli.data_file, args_cli.params_file)
        return

    run_name = args_cli.run_name
    raw_dir = REPO_ROOT / "data" / run_name / "raw"
    graphs_dir = REPO_ROOT / "data" / run_name / "graphs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir.mkdir(parents=True, exist_ok=True)
    run_log_path = REPO_ROOT / "data" / run_name / "run_log.md"
    if not run_log_path.exists():
        template = REPO_ROOT / "data" / "TEMPLATE" / "run_log.md"
        if template.exists():
            run_log_path.write_text(template.read_text())

    state = ExecutorState(raw_dir / "executor_state.json", run_name, args_cli.polymer_class, args_cli.plan)

    lammps = _load_server_module("lammps_engine_server", LAMMPS_ENGINE_DIR / "server.py",
                                 LAMMPS_ENGINE_DIR, _mcp_env("mcp-lammps-engine"))
    emc = _load_server_module("emc_server_module", EMC_SERVER_DIR / "server.py",
                              EMC_SERVER_DIR, _mcp_env("mcp-emc-server"))

    # A SMILES whose cache entry demands a microstructure lock (cis-PBD: EMC does NOT honour
    # SMILES double-bond stereo, so a plain build yields a ~48:52 cis/trans mixture, and that
    # entry's own numbers do not apply to it) must not be replicated by a plain rebuild.
    chain_check = _assert_chain_matches_execution(args, cls, plan)
    print(json.dumps({"status": "chain_verified", **chain_check}), flush=True)

    guard = _cis_lock_guard(plan)
    if guard:
        state.halt("build", "REQUIRES_MICROSTRUCTURE_LOCK", guard)
        print(json.dumps({"status": "halted", "stage": "build", "detail": guard}))
        return

    if args_cli.seed_mode == "velocity":
        # Branch from the source run's equilibrated cell: same packing, new velocities. Isolates
        # thermal-trajectory noise, so the spread understates true uncertainty -- deliberate,
        # and recorded here so a downstream aggregate cannot mistake it for --seed-mode both.
        src = REPO_ROOT / "data" / args_cli.source_run / "lammps" / "equil"
        src_data = next(iter(sorted(src.glob("npt_prod300/npt_prod300_out.data"))
                              or sorted(src.glob("npt_production/npt_production_out.data"))), None)
        if src_data is None:
            raise SystemExit(f"--seed-mode velocity: no equilibrated .data under {src}")
        state.mark("build", "done", result={"data_path": str(src_data), "emc_seed": None,
                                            "seed_mode": "velocity",
                                            "branched_from": args_cli.source_run})
        build_result = state.stage("build")["result"]
    elif not state.is_done("build"):
        build_result = do_build(state, args, cls, emc, lammps, run_log_path)
    else:
        build_result = state.stage("build")["result"]
    args.data_path = build_result["data_path"]
    args.n_atoms = build_result.get("n_atoms")

    if not state.is_done("equil_check"):
        equil_result = do_equil_and_check(state, args, cls, lammps, run_log_path)
        if equil_result.get("halted"):
            print(json.dumps({"status": "halted", "stage": "equil_check", "detail": equil_result}, default=str))
            return
    else:
        equil_result = state.stage("equil_check")["result"]
    args.data_path = equil_result["npt_prod_data_path"]

    thermal_result = None
    is_glassy = None
    if "tg" in properties:
        if not state.is_done("thermal"):
            thermal_result = do_thermal(state, args, cls, lammps, raw_dir, graphs_dir, run_log_path)
            if thermal_result.get("halted"):
                print(json.dumps({"status": "halted", "stage": "thermal", "detail": thermal_result}, default=str))
                return
        else:
            thermal_result = state.stage("thermal")["result"]
        is_glassy = thermal_result["is_glassy"]
    else:
        is_glassy = resolve_stage_params("equil", args, cls)["T_workflow_K"] != 300.0

    if "bulk_modulus" in properties:
        if not state.is_done("mechanical"):
            do_mechanical(state, args, cls, lammps, is_glassy, args.data_path, raw_dir, graphs_dir)
        # mechanical result not otherwise consumed here — generate_run_summary reads its JSON directly

    do_summary(state, args, cls, lammps, is_glassy, thermal_result, raw_dir, graphs_dir, args_cli.plan, run_log_path)

    print(json.dumps({"status": "complete", "run_name": run_name,
                      "run_summary": str(raw_dir / "run_summary.json")}))


if __name__ == "__main__":
    main()
