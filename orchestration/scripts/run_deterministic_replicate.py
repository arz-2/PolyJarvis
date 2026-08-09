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

Two-phase invocation, split at the mandatory-refine boundary:
  IS_NOVEL=false (the common replicate-2+ case): one invocation, `--phase full` (default),
    runs build through run-summary end to end.
  IS_NOVEL=true: Build through Equil-check-PASS needs no agent judgment (do_equil_and_check()
    already runs its own headless EXTEND loop), but a plain script can't spawn Agent(...), and
    system-characterization-analyzer's post-PASS characterization (FOUNDATION.md's `[Equilibration]`
    mandatory refine step) is exactly that. So invoke with `--phase equil` first (runs Build
    through Equil-check to PASS, stops), let the orchestrator spawn system-characterization-analyzer against
    the resulting equilibration hold, then re-invoke with `--resume-from thermal` once
    decided_params is characterization-patched (or left at class defaults, if unreliable).

Resumability: data/<RUN>/raw/executor_state.json tracks per-stage status, so a crash (reboot,
OOM-killed wrapper) doesn't discard hours of completed work — `--resume-from` (or just
re-running with the same --plan) skips any stage already marked "done".

Recovery scope matches .claude/commands/recover.md's plan_mode=="deterministic" rule exactly:
only EXTEND-type recovery (parameter tweaks that never touch decided_params) auto-applies, capped
at 2 attempts. STRUCTURAL_FAIL, or Murnaghan+deform both failing acceptance, halt immediately and
write the diagnostic for human review — never auto-changing a protocol that's supposed to be
identical across replicates.

Usage:
  <repo>/mcp-servers/.venv/bin/python orchestration/run_deterministic_replicate.py \\
      --run_name RUN --polymer_class CLASS --plan data/RUN/raw/run_plan.json \\
      [--phase full|equil] [--resume-from STAGE] [--dry-run] [--properties density,tg,bulk_modulus]

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
    "done" is never re-run; --resume-from (or simply re-invoking with the same --plan) picks
    up from the first non-done stage. Also what protocol-locker reads for "what did this run
    need to fix" when a locked-protocol replicate needed an EXTEND."""

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

def _base_args(run_name: str, polymer_class: str, plan_path: str) -> SimpleNamespace:
    return SimpleNamespace(
        run_name=run_name, polymer_class=polymer_class, plan=str(plan_path),
        smiles=None, data_path=None, tg_start_data=None, work_dir=None,
        gpu_ids=None, mpi_ranks=None, engine=None, emc_seed=None, velocity_seed=None,
        dp=None, nchain=None, n_atoms=None, charge_method=None, date_start=None, date_end=None,
        d01=None, d02=None, d03=None, d04=None, lammps_flags=None, is_glassy="true",
        tg_k=None, tg_fit_quality=None, deform_log=None, deform_log_slow=None,
        deform_rate_mode="primary", murnaghan_logs=None, d05=None, npt_prod_log=None,
        npt_prod_dump=None, ff=None, backbone_types=None, enthalpy_col="Enthalpy",
        output_dir=None, equil_data_path=None, npt_prod_ns=None, add_melt_npt=False,
        T_equil_K=None, T_anneal_high_K=None, tg_t_high_K=None, tg_t_low_K=None,
        tg_t_step_K=None, tg_steps_per_t=None, tg_rate_index=None, mr_rates=None,
        mr_tg_values=None, n_replicates=1, K_strain_max=None, K_deform_rate_inv_s=None,
        dt_fs=None, density_initial=None, properties="all", exp_K_min=None, exp_K_max=None,
        exp_tg_K=None, exp_tg_min=None, exp_tg_max=None, exp_density_min=None,
        exp_density_max=None, polymer_name=None, tg_path=None, slope_gate_pass=None,
    )


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

    info = lammps.inspect_data_file(data_file=str(dest_data))

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
    if extend_from_data is None:
        workflow = lammps.generate_equilibration_workflow(
            data_file=p["data_path"], work_dir_base=p["work_dir"],
            polymer_name=args.run_name, temp=p["T_workflow_K"], max_temp=p["T_anneal_high_K"],
            press=p["P_equil_atm"], use_pcff=flags["use_pcff"], use_trappe=flags["use_trappe"],
            use_opls=flags["use_opls"], npt_prod_steps=p["npt_prod_steps"],
            add_melt_npt=p["add_melt_npt"], t_equil_K=p["T_equil_K"] if p["add_melt_npt"] else None,
            melt_npt_steps=p["melt_npt_steps"], engine=p["engine"], velocity_seed=p["velocity_seed"],
            npt_cool_steps=p["npt_cool_steps"], npt_cool300_steps=p["npt_cool300_steps"],
        )
    else:
        dt = p["dt_fs"]
        extend_steps = int(extend_ns * 1e6 / dt)
        workflow = lammps.generate_equilibration_workflow(
            data_file=extend_from_data, work_dir_base=p["work_dir"], polymer_name=args.run_name,
            temp=extend_temp, press=p["P_equil_atm"], use_pcff=flags["use_pcff"],
            use_trappe=flags["use_trappe"], use_opls=flags["use_opls"], engine=p["engine"],
            velocity_seed=p["velocity_seed"], extend_only=True, extend_steps=extend_steps,
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
        backbone_types = args.backbone_types
        if backbone_types is None:
            # inspect_data_file only for diagnostics attached to the halt below — atom names
            # alone (e.g. "c"/"c1") don't determine which types are backbone vs. pendant branch
            # for a branched-backbone class (confirmed live: PACR/PMMA shares generic aliphatic
            # carbon types between CH2 backbone atoms and pendant methyl branches), so this is
            # never auto-derived into a backbone_types list — only ever an explicit
            # decided_params/CLI value, reviewed like any other protocol-lock decision.
            diag = lammps.inspect_data_file(data_file=build_data_path)
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
                params={"LOG_FILE": "tg_sweep.log", "DUMP_FILE": "",
                       "T_START": p["T_start_K"], "T_END": p["T_end_K"], "T_STEP": p["T_step_K"],
                       "N_STEPS_PER_T": p["n_steps_per_t"], "P_START": 1.0, "P_FINAL": 1.0,
                       "T_DAMP": 100.0, "TIMESTEP": p["dt_fs"], "use_pppm": not p["lammps_flags"]["use_trappe"],
                       "use_gpu": True, "engine": p["engine"], **{f"use_{k.split('_')[1]}": v
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
            enthalpy_col=ap["enthalpy_col"], output_dir=ap["output_dir"], graphs_dir=ap["graphs_dir"],
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
            run_name=args.run_name, gpu_ids=p["gpu_ids"], mpi=p["mpi_ranks"], npt_steps=p["npt_steps"],
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

    # Deform fallback: primary rate, then slow rate for the rate-sensitivity check
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
        **({"log_file_2": slow_log, "strain_rate_2": bp["strain_rate_slow_per_fs"]} if slow_log else {}),
    ), "bulk modulus (deform)")
    result = {"method": "deformation", "bulk_modulus_GPa": deform_extract.get("bulk_modulus_GPa"),
             "shear_modulus_GPa": deform_extract.get("shear_modulus_GPa"),
             "youngs_modulus_GPa": deform_extract.get("youngs_modulus_GPa")}
    state.mark("mechanical", "done", result=result)
    return result


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
        n_replicates=args.n_replicates, tg_path=tg_path,
    )
    state.mark("summary", "done", result={"run_summary_path": str(Path(sp["output_dir"]) / "run_summary.json")})
    return summary


# ─── Dry-run mode ───────────────────────────────────────────────────────────

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
    ap.add_argument("--phase", choices=["full", "equil"], default="full",
                    help="'equil' stops after Equil-check PASS for the IS_NOVEL=true mandatory "
                         "characterization hand-off to the live orchestrator session (a plain "
                         "script can't spawn system-characterization-analyzer); 'full' (default) runs "
                         "everything from the first non-done stage in executor_state.json onward.")
    ap.add_argument("--resume-from", default=None,
                    help="Informational — resumption is actually driven by executor_state.json; "
                         "this just asserts which stage you expect to resume from.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Resolve every stage's params without submitting anything; print JSON and exit.")
    ap.add_argument("--properties", default=None, help="Override properties_requested (else from plan).")
    args_cli = ap.parse_args()

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

    properties = ({"density", "tg", "bulk_modulus"} if args.properties in (None, "all")
                  else {p.strip().lower() for p in args.properties.split(",") if p.strip()})

    if args_cli.dry_run:
        _print_dry_run(args, cls, properties)
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

    if not state.is_done("build"):
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

    if args_cli.phase == "equil":
        print(json.dumps({"status": "equil_complete", **equil_result}))
        return

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
