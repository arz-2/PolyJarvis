#!/usr/bin/env python3
"""
PolyJarvis LAMMPS Engine MCP Server
=====================================
Provides AI-driven, template-based LAMMPS script generation and remote execution.

Architecture:
  - RadonPy (existing) handles: SMILES -> polymer chain -> amorphous cell -> .data file
  - This server handles: .data file -> filled LAMMPS .in script -> execute on local GPU

Tools exposed:
  ── Simulation ────────────────────────────────────────────────────────────────
  1.  list_templates                  - List templates; pass template_name for defaults
  2.  inspect_data_file               - Parse + validate a .data file in one call
  3.  generate_script                 - Fill a template and write a .in file
  4.  run_lammps_script               - Execute a .in script on the local GPU
  5.  run_lammps_chain                - Submit ordered chain of scripts (nohup, crash-safe)
  6.  generate_equilibration_workflow - Auto-generate full 7-stage equilibration protocol
  ── Monitoring ────────────────────────────────────────────────────────────────
  7.  get_run_status                  - Check status of any run or analysis job
  8.  get_run_output                  - Results + log tail from a completed job
  9.  list_runs                       - List all submitted runs and analysis jobs
  10. watch_run                       - Return Monitor command to block until a run completes
  ── Analysis ──────────────────────────────────────────────────────────────────
  11. unwrap_coordinates                - Write new dump with image-flag-unwrapped coords
  12. extract_end_to_end_vectors        - End-to-end R vectors via MDAnalysis sort_backbone
  13. calculate_rdf                     - g(r) via MDAnalysis InterRDF
  14. check_equilibration_comprehensive - All convergence + structural checks, one call, one verdict
  15. extract_equilibrated_density      - Plateau density via reverse-cumulative-mean
  16. extract_thermal                   - Tg, CTE (α_g, α_r), ΔCp via bilinear curve_fit (standard polymer MD method)
  17. extract_bulk_modulus              - Isothermal K via NPT volume fluctuations
"""

import os
import sys
import json
import uuid
import shutil
import logging
import threading
import subprocess
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

# Load root .env (PolyJarvis/.env) — single source of truth for all MCP servers
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on shell env vars

# Add server directory to path so we can import script_generator
sys.path.insert(0, str(Path(__file__).parent))
from script_generator import ScriptGenerator, TEMPLATE_DOCS, TEMPLATE_DEFAULTS
from monitor_utils import build_watch_command, pidfile_path

from mcp.server.fastmcp import FastMCP

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [LAMMPS-ENGINE] %(levelname)s %(message)s",
)
logger = logging.getLogger("lammps_engine")

# ─── Config ───────────────────────────────────────────────────────────────────
LAMBDA_USER     = os.environ.get("LAMBDA_USER",    "arz2")
LAMBDA_WORKDIR  = os.environ.get("LAMBDA_WORKDIR", f"/home/{LAMBDA_USER}/simulations")
LAMBDA_LAMMPS   = os.environ.get("LAMBDA_LAMMPS",  f"/home/{LAMBDA_USER}/lammps-install/bin/lmp")
# KOKKOS full-offload binary (pair + class2 bonded + pppm + neigh on GPU). Separate prefix so the
# GPU-package binary above stays the production fallback; selected per run via engine="kokkos".
LAMBDA_LAMMPS_KOKKOS = os.environ.get("LAMBDA_LAMMPS_KOKKOS",
                                      f"/home/{LAMBDA_USER}/lammps-install-kokkos/bin/lmp")
CONDA_ENV       = os.environ.get("CONDA_ENV",      "mol-builder")
_openmpi_home = f"/home/{LAMBDA_USER}/openmpi"
_sys_openmpi_bin = "/usr/bin"
_sys_openmpi_lib = "/usr/lib/x86_64-linux-gnu"
_sys_openmpi_prefix = "/usr"
OPENMPI_BIN    = os.environ.get("OPENMPI_BIN",
                                _openmpi_home + "/bin" if os.path.isdir(_openmpi_home) else _sys_openmpi_bin)
OPENMPI_LIB    = os.environ.get("OPENMPI_LIB",
                                _openmpi_home + "/lib" if os.path.isdir(_openmpi_home) else _sys_openmpi_lib)
OPENMPI_PREFIX = os.environ.get("OPENMPI_PREFIX",
                                _openmpi_home if os.path.isdir(_openmpi_home) else _sys_openmpi_prefix)


def _engine_launch(engine: str, n_gpu: int) -> tuple[str, str]:
    """Map an execution engine to (lmp binary, mpirun offload flags).

      gpu    → GPU package: pairwise forces on GPU, bonded/kspace/neigh on CPU (current default)
      cpu    → no offload flags (CPU-only; selected when a caller passes use_gpu=False)
      kokkos → KOKKOS full-offload: -sf kk rewrites pair/bonded/kspace/neigh to /kk on the GPU

    n_gpu is the device count for this run (-pk gpu N / -k on g N)."""
    if engine == "kokkos":
        return LAMBDA_LAMMPS_KOKKOS, f"-k on g {n_gpu} -sf kk -pk kokkos"
    if engine == "cpu":
        return LAMBDA_LAMMPS, ""
    return LAMBDA_LAMMPS, f"-sf gpu -pk gpu {n_gpu}"
# Analysis scripts are bundled with the server; MDA_SCRIPTS_DIR env var overrides for dev use.
MDA_SCRIPTS_DIR = os.environ.get("MDA_SCRIPTS_DIR",
                                  str(Path(__file__).parent / "analysis_scripts"))


def _conda_run(cmd: str, workdir: str = None, timeout: int = 3600):
    """Run cmd inside the project conda env. Returns (stdout, stderr, returncode)."""
    script = (
        f"source ~/miniforge3/etc/profile.d/conda.sh\n"
        f"conda activate {CONDA_ENV}\n"
        f"cd {workdir or LAMBDA_WORKDIR}\n"
        f"{cmd}\n"
    )
    logger.info(f"Running: {cmd}")
    try:
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=timeout)
        if r.returncode != 0:
            logger.warning(f"Exit {r.returncode}: {r.stderr[:200]}")
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", f"Timed out after {timeout}s", 1


# ─── Double-launch guard ──────────────────────────────────────────────────────
# Processes that legitimately hold a run's log open (via the wrapper's
# `lmp … > stage.log 2>&1` redirect). Matching only these avoids false positives
# on benign holders (tail -f, an editor, an analysis reader).
_SIM_WRITER_CMDS = ("lmp", "lammps", "mpirun", "mpiexec", "orted")


def _live_sim_writers(log_paths: list, timeout: int = 8) -> list:
    """Return live LAMMPS/MPI processes currently holding any of log_paths open.

    Reads OS state via ``lsof`` (survives MCP-server/context restarts — exactly the
    failure that causes double-launch). Each element: {"pid","cmd","path"}.

    FAIL-OPEN: if lsof is missing, errors, or times out, returns [] (allow the
    launch) — the guard must never convert a tooling hiccup into a block. lsof
    exits 1 with empty stdout when none of the paths are open (or don't exist),
    which is the normal "no conflict" case.
    """
    paths = [p for p in log_paths if p]
    if not paths:
        return []
    try:
        # -w suppresses can't-stat warnings (docker overlays etc.) that lsof prints to
        # stderr on this host; the machine-readable records go to stdout regardless.
        r = subprocess.run(
            ["lsof", "-w", "-F", "pcn", "--", *paths],
            capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=timeout,
        )
    except FileNotFoundError:
        logger.warning("double-launch guard: lsof not found — allowing launch (fail-open)")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("double-launch guard: lsof timed out — allowing launch (fail-open)")
        return []
    except Exception as e:
        logger.warning(f"double-launch guard: lsof error ({e}) — allowing launch (fail-open)")
        return []

    if not r.stdout.strip():
        return []  # no process holds any of the paths open

    writers, pid, cmd = [], None, None
    for line in r.stdout.splitlines():
        if not line:
            continue
        tag, val = line[0], line[1:]
        if tag == "p":
            pid, cmd = val, None
        elif tag == "c":
            cmd = val
        elif tag == "n" and pid is not None:
            low = (cmd or "").lower()
            if any(low.startswith(s) for s in _SIM_WRITER_CMDS):
                writers.append({"pid": pid, "cmd": cmd, "path": val})
    return writers


def _double_launch_error(conflict: list) -> dict:
    """Structured refusal for a launch onto a log a live sim process is writing."""
    return {
        "status": "error",
        "error": "Refusing to launch: a live LAMMPS/MPI process is already writing the "
                 "target log. Launching now would corrupt the shared log "
                 "(Cross-Track Rule 3 / PLA3). Kill the stale writer (or coordinate with "
                 "the concurrent session), then resubmit.",
        "conflicting_writers": conflict,
        "hint": "Set allow_concurrent_writer=True only to override after confirming the "
                "writer is stale.",
    }


# ─── Completion sentinels ─────────────────────────────────────────────────────
# Each completed or failed run writes a small JSON file here for deterministic consumers.
SENTINEL_DIR = Path("/tmp/polyjarvis/sentinels")
SENTINEL_DIR.mkdir(parents=True, exist_ok=True)

def _write_sentinel(run_id: str, status: str, extra: dict = None):
    """Write a completion sentinel file for run_id."""
    payload = {"run_id": run_id, "status": status, "timestamp": datetime.now().isoformat()}
    if extra:
        payload.update(extra)
    path = SENTINEL_DIR / f"done_{run_id}.json"
    path.write_text(json.dumps(payload))
    logger.info(f"Sentinel written: {path}")

# ─── MCP Server ───────────────────────────────────────────────────────────────
mcp = FastMCP("PolyJarvis LAMMPS Engine")

# ─── Job Manager ─────────────────────────────────────────────────────────────
class JobStatus(Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"

# Persist run state here so chains survive server restarts
STATE_FILE = Path.home() / "Desktop" / "Research" / "mcp-lammps-engine" / "run_state.json"

class RunManager:
    def __init__(self):
        self.runs = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        """Load persisted run state from disk on startup."""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r") as f:
                    self.runs = json.load(f)
                # Migrate entries written by older server versions that used a
                # different schema (created_at/started_at, flat fields, no meta).
                for run_id, r in self.runs.items():
                    if "submitted_at" not in r:
                        r["submitted_at"] = r.get("created_at", "unknown")
                    if "completed_at" not in r:
                        r["completed_at"] = r.get("finished_at", None)
                    if "run_type" not in r:
                        r["run_type"] = r.get("chain_type", "unknown")
                    if "meta" not in r:
                        r["meta"] = {}
                logger.info(f"Loaded {len(self.runs)} runs from {STATE_FILE}")
            except Exception as e:
                # Preserve the unreadable file instead of silently discarding it -- resetting
                # straight to {} means the very next _save() overwrites it for good, turning a
                # corrupt-but-often-partially-recoverable file into unconditional, permanent
                # loss with no trace it ever happened. Never block startup on this: a run-state
                # cache is diagnostic bookkeeping, not the actual simulation results (those live
                # under each run's own data/<run>/ directory, untouched by this file).
                quarantine = STATE_FILE.with_name(
                    f"{STATE_FILE.name}.corrupt.{datetime.now():%Y%m%dT%H%M%S}"
                )
                try:
                    STATE_FILE.rename(quarantine)
                    logger.warning(f"Could not load run state ({e}); quarantined unreadable "
                                    f"file to {quarantine} and starting from empty run history")
                except Exception as rename_err:
                    logger.warning(f"Could not load run state ({e}); also failed to quarantine "
                                    f"it ({rename_err}) -- starting from empty run history")
                self.runs = {}

    def _save(self):
        """Persist run state to disk (call inside lock).

        Writes to a temp file in the same directory then os.replace()s it onto STATE_FILE --
        the rename is atomic on POSIX, so a reader always sees either the old or the new
        complete file, never a partial write. The previous plain open(STATE_FILE, "w") + dump
        truncated the target immediately and streamed into it; a process killed or crashed
        mid-write left a syntactically invalid, truncated file on disk. Multiple processes each
        importing this module (e.g. several short-lived diagnostic scripts run alongside a live
        orchestrator, all pointed at this one shared, cross-checkout file) each hold their own
        in-memory `runs` snapshot and can race to save around the same moment; a non-atomic
        write turns that ordinary race into disk corruption instead of just a lost update. Hit
        live 2026-08-17: corrupted this exact file, and _load()'s silent except-and-reset-to-{}
        meant the next load would have silently discarded the corrupted (but structurally
        recoverable) run history entirely on its next save had it not been manually recovered.
        """
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = STATE_FILE.with_name(f".{STATE_FILE.name}.{os.getpid()}.tmp")
            with open(tmp_path, "w") as f:
                json.dump(self.runs, f, indent=2)
            os.replace(tmp_path, STATE_FILE)
        except Exception as e:
            logger.warning(f"Could not save run state: {e}")

    def create(self, run_type: str, meta: dict) -> str:
        run_id = str(uuid.uuid4())[:8]
        with self._lock:
            self.runs[run_id] = {
                "run_id":       run_id,
                "run_type":     run_type,
                "status":       JobStatus.PENDING.value,
                "result":       None,
                "error":        None,
                "submitted_at": datetime.now().isoformat(),
                "completed_at": None,
                "meta":         meta,
            }
            self._save()
        return run_id

    def start(self, run_id: str):
        with self._lock:
            self.runs[run_id]["status"] = JobStatus.RUNNING.value
            self._save()

    def complete(self, run_id: str, result: dict):
        with self._lock:
            self.runs[run_id]["status"]       = JobStatus.COMPLETED.value
            self.runs[run_id]["result"]       = result
            self.runs[run_id]["completed_at"] = datetime.now().isoformat()
            self._save()

    def fail(self, run_id: str, error: str):
        with self._lock:
            self.runs[run_id]["status"] = JobStatus.FAILED.value
            self.runs[run_id]["error"]  = error
            self.runs[run_id]["completed_at"] = datetime.now().isoformat()
            self._save()

    def create_with_id(self, run_id: str, run_type: str, meta: dict):
        """Create a run entry with a pre-chosen ID (used by nohup chains)."""
        with self._lock:
            self.runs[run_id] = {
                "run_id":       run_id,
                "run_type":     run_type,
                "status":       JobStatus.PENDING.value,
                "result":       None,
                "error":        None,
                "submitted_at": datetime.now().isoformat(),
                "completed_at": None,
                "meta":         meta,
            }
            self._save()

    def get(self, run_id: str) -> dict:
        return self.runs.get(run_id, {})

    def all(self) -> list:
        return list(self.runs.values())

run_manager = RunManager()

# ─────────────────────────────────────────────────────────────────────────────
# Helper: execute LAMMPS in a background thread
# ─────────────────────────────────────────────────────────────────────────────

def _build_chain_script(chain_id: str, stages: list, mpi: int, gpu_ids: str,
                        engine: str = "gpu") -> str:
    """
    Generate a self-contained bash script that runs LAMMPS stages sequentially.
    Designed to run under nohup so it is fully independent of the MCP server process.

    Each completed stage appends a JSON line to chain_progress.jsonl:
        {"stage": "name", "status": "done"|"failed", "ts": "ISO timestamp"}
    A final line with stage=__chain__ marks overall completion or failure.
    """
    n_gpu = len(gpu_ids.split(","))
    lmp_bin, offload_flags = _engine_launch(engine, n_gpu)
    cuda_devices = "" if engine == "cpu" else gpu_ids
    lines = [
        "#!/bin/bash",
        f"# PolyJarvis chain {chain_id} — auto-generated, do not edit (engine={engine})",
        "set -euo pipefail",
        "",
        f"CHAIN_ID={chain_id}",
        f"LMP={lmp_bin}",
        f"OFFLOAD_FLAGS=\"{offload_flags}\"",
        f"MPI={mpi}",
        f"GPU_IDS={gpu_ids}",
        f"N_GPU={n_gpu}",
        "",
        "# Progress log — one JSON object per line",
        f"PROGRESS=$( dirname $0 )/chain_progress.jsonl",
        "",
        "log_done()  { echo \"{\\\"stage\\\":\\\"$1\\\",\\\"status\\\":\\\"done\\\",\\\"ts\\\":\\\"$(date -Iseconds)\\\"}\""
            " >> \"$PROGRESS\"; }",
        "log_fail()  { echo \"{\\\"stage\\\":\\\"$1\\\",\\\"status\\\":\\\"failed\\\",\\\"ts\\\":\\\"$(date -Iseconds)\\\"}\""
            " >> \"$PROGRESS\"; }",
        "log_start() { echo \"{\\\"stage\\\":\\\"$1\\\",\\\"status\\\":\\\"running\\\",\\\"ts\\\":\\\"$(date -Iseconds)\\\"}\""
            " >> \"$PROGRESS\"; }",
        "",
        "# Completion sentinel — written by THIS nohup'd script so it survives an",
        "# MCP-server restart (the in-process chain monitor is only a fast-path).",
        f"mkdir -p {SENTINEL_DIR}",
        f"SENTINEL={SENTINEL_DIR}/done_{chain_id}.json",
        f"PIDFILE={pidfile_path(chain_id, SENTINEL_DIR)}",
        f"sentinel_ok()   {{ echo \"{{\\\"run_id\\\":\\\"{chain_id}\\\",\\\"status\\\":\\\"completed\\\"}}\""
            " > \"$SENTINEL\"; }",
        f"sentinel_fail() {{ echo \"{{\\\"run_id\\\":\\\"{chain_id}\\\",\\\"status\\\":\\\"failed\\\",\\\"stage\\\":\\\"$1\\\"}}\""
            " > \"$SENTINEL\"; }",
        "",
        f"export CUDA_VISIBLE_DEVICES={cuda_devices}",
        f"export PATH={OPENMPI_BIN}:$PATH",
        f"export LD_LIBRARY_PATH={OPENMPI_LIB}:${{LD_LIBRARY_PATH:-}}",
        # Clear any stale inherited OPAL_PREFIX when using system OpenMPI (/usr);
        # only set it explicitly for a non-system installation.
        ("unset OPAL_PREFIX"
         if OPENMPI_PREFIX == _sys_openmpi_prefix
         else f"export OPAL_PREFIX={OPENMPI_PREFIX}"),
        "# Record our own PID so watch_run can check liveness ($$ is the long-lived chain).",
        'echo $$ > "$PIDFILE"',
        # mpirun -np 1 does not propagate CUDA_VISIBLE_DEVICES to the child process on OpenMPI.
        # For single-rank runs, skip mpirun and pin the GPU inline on the lmp command line.
        ('LAMMPS_LAUNCH="env CUDA_VISIBLE_DEVICES=$GPU_IDS $LMP $OFFLOAD_FLAGS"'
         if mpi == 1 else
         'LAMMPS_LAUNCH="mpirun -np $MPI $LMP $OFFLOAD_FLAGS"'),
        "",
    ]

    for i, stage in enumerate(stages):
        name  = stage.get("name", f"stage_{i+1}")
        script = stage["script"]
        wdir  = stage["work_dir"]
        log   = stage.get("log_file", f"{name}_run.log")

        lines += [
            f"# --- Stage {i+1}/{len(stages)}: {name} ---",
            f"mkdir -p {wdir}",
            f"cd {wdir}",  # FIX: cd into stage workdir so relative paths in .in files resolve correctly
            f"log_start {name}",
            f"$LAMMPS_LAUNCH "
            f"-in {script} >> {wdir}/{log} 2>&1 \\",
            f"  && log_done {name} \\",
            f"  || {{ log_fail {name}; sentinel_fail {name}; "
            f"echo \"{{\\\"stage\\\":\\\"__chain__\\\",\\\"status\\\":\\\"failed\\\","
            f"\\\"failed_at\\\":\\\"{name}\\\",\\\"ts\\\":\\\"$(date -Iseconds)\\\"}}\" >> \"$PROGRESS\"; exit 1; }}",
            "",
        ]
        if name == "minimize":
            # LAMMPS' minimize command always exits 0, even when it stops at MAXITER/MAXEVAL
            # without meeting ETOL/FTOL -- the && above never sees this as a failure. Grep the
            # stage's own log for its stopping-criterion line; two convergent forms are known
            # from this repo's archive: "energy tolerance" (matches "tolerance") and
            # "linesearch alpha is zero" (a legitimate stall, not an artificial cutoff --
            # distinct in kind from "max iterations"/"max force evaluations", which mean the
            # structure was cut off before finding a real minimum). Anything not matching
            # either convergent form is treated as non-convergent.
            # `if ! grep ...; then ...; fi` is required under this script's `set -euo pipefail`
            # -- a bare `grep -q` line would abort the whole script on exactly the
            # non-convergence case this exists to catch.
            lines += [
                "# --- Minimization-convergence check (not itself a LAMMPS exit-code failure) ---",
                f'if ! grep -Eq "Stopping criterion.*(tolerance|linesearch alpha is zero)" {wdir}/{log}; then',
                f"  log_fail {name}; sentinel_fail minimize_not_converged; "
                f'echo "{{\\"stage\\":\\"__chain__\\",\\"status\\":\\"failed\\","'
                f'"\\"failed_at\\":\\"{name}\\",\\"ts\\":\\"$(date -Iseconds)\\"}}" >> "$PROGRESS"; exit 1',
                "fi",
                "",
            ]

    lines += [
        f"echo \"{{\\\"stage\\\":\\\"__chain__\\\",\\\"status\\\":\\\"completed\\\","
        f"\\\"n_stages\\\":{len(stages)},\\\"ts\\\":\\\"$(date -Iseconds)\\\"}}\" >> \"$PROGRESS\"",
        "sentinel_ok",
        'rm -f "$PIDFILE"',
    ]

    return "\n".join(lines) + "\n"


def _lammps_run_background(
    run_id: str,
    work_dir: str,
    script: str,
    mpi: int,
    gpu_ids: str,
    log_file: str,
    use_gpu: bool = True,
    engine: str = "gpu",
):
    """Background thread: executes LAMMPS and updates run_manager.

    Uses nohup bash wrapper (same as chain runner) to avoid the conda PATH issue
    where conda's lmp shadows the GPU-enabled lmp at LAMBDA_LAMMPS and triggers
    a lmp_gpu search that fails.
    """
    try:
        run_manager.start(run_id)

        n_gpu = len(gpu_ids.split(","))
        full_log = f"{work_dir}/{log_file}"
        sentinel_path = SENTINEL_DIR / f"done_{run_id}.json"
        pidfile = pidfile_path(run_id, SENTINEL_DIR)

        # Write a small wrapper script and launch it under nohup — identical to
        # how run_lammps_chain launches stages, so it uses the system PATH (not
        # conda's) and finds the GPU-enabled lmp binary correctly.
        # Capture wrapper stdout to a separate file so it never overwrites the LAMMPS
        # internal log (e.g. tg_sweep.log opened with 'log ... append' in the script).
        wrapper_stdout = f"{work_dir}/{run_id}_wrapper.stdout"
        # use_gpu=False forces the CPU engine regardless of the engine arg; otherwise honor
        # engine (gpu | kokkos). _engine_launch picks binary + flags.
        eff_engine = "cpu" if not use_gpu else engine
        lmp_bin, offload_flags = _engine_launch(eff_engine, n_gpu)
        if eff_engine == "cpu":
            cuda_line = "export CUDA_VISIBLE_DEVICES=\n"  # hide GPUs from LAMMPS
        else:
            cuda_line = f"export CUDA_VISIBLE_DEVICES={gpu_ids}\n"
        flags = f"{offload_flags} " if offload_flags else ""
        # mpirun -np 1 does not propagate CUDA_VISIBLE_DEVICES on OpenMPI; skip it for mpi=1.
        if mpi == 1:
            lammps_cmd = (
                f"env CUDA_VISIBLE_DEVICES={gpu_ids} {lmp_bin} {flags}"
                f"-in {script} >> {wrapper_stdout} 2>&1\n"
            )
        else:
            lammps_cmd = (
                f"mpirun -np {mpi} {lmp_bin} {flags}"
                f"-in {script} >> {wrapper_stdout} 2>&1\n"
            )
        wrapper = (
            f"#!/bin/bash\n"
            f"{cuda_line}"
            f"export PATH={OPENMPI_BIN}:$PATH\n"
            f"export LD_LIBRARY_PATH={OPENMPI_LIB}:${{LD_LIBRARY_PATH:-}}\n"
            + ("unset OPAL_PREFIX\n"
               if OPENMPI_PREFIX == _sys_openmpi_prefix
               else f"export OPAL_PREFIX={OPENMPI_PREFIX}\n")
            # Record our own PID first so watch_run can check liveness. $$ is the
            # long-lived wrapper; $! at launch is the short-lived setsid parent.
            + f"mkdir -p {SENTINEL_DIR}\n"
            f"echo $$ > {pidfile}\n"
            f"cd {work_dir}\n"
            f"{lammps_cmd}"
            f"RC=$?\n"
            f"if [ $RC -eq 0 ]; then\n"
            f"  echo '{{\"run_id\":\"{run_id}\",\"status\":\"completed\","
            f"\"work_dir\":\"{work_dir}\"}}' > {sentinel_path}\n"
            f"else\n"
            f"  echo '{{\"run_id\":\"{run_id}\",\"status\":\"failed\","
            f"\"exit_code\":\"'$RC'\"}}' > {sentinel_path}\n"
            f"fi\n"
            f"rm -f {pidfile}\n"
        )
        wrapper_path = f"{work_dir}/{run_id}_run.sh"
        launch = (
            f"mkdir -p {work_dir} && "
            f"cat > {wrapper_path} << 'POLYJARVIS_EOF'\n{wrapper}\nPOLYJARVIS_EOF\n"
            f"chmod +x {wrapper_path} && "
            f"setsid nohup bash {wrapper_path} </dev/null & disown; echo $!"
        )

        logger.info(f"[{run_id}] Launching LAMMPS via nohup wrapper (engine={eff_engine}): {lmp_bin}")
        stdout, _, _ = _conda_run(launch, workdir=work_dir, timeout=30)
        pid = stdout.strip().splitlines()[-1] if stdout.strip() else "unknown"
        logger.info(f"[{run_id}] nohup PID={pid}")

        # Block until the sentinel file appears (written by the wrapper on exit)
        import time as _time
        deadline = _time.time() + 86400  # 24-hour max
        while not sentinel_path.exists() and _time.time() < deadline:
            _time.sleep(10)

        if sentinel_path.exists():
            import json as _json
            payload = _json.loads(sentinel_path.read_text())
            if payload.get("status") == "completed":
                run_manager.complete(run_id, {"work_dir": work_dir, "log_file": full_log})
                logger.info(f"[{run_id}] LAMMPS completed successfully")
            else:
                run_manager.fail(run_id, f"LAMMPS wrapper exited non-zero: {payload}")
                logger.error(f"[{run_id}] LAMMPS failed: {payload}")
        else:
            run_manager.fail(run_id, "Timed out waiting for completion sentinel")
            _write_sentinel(run_id, "failed", {"error": "timeout"})

    except Exception as e:
        run_manager.fail(run_id, str(e))
        logger.error(f"[{run_id}] Exception: {e}")
        _write_sentinel(run_id, "failed", {"error": str(e)[:500]})


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tools
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_templates(template_name: Optional[str] = None) -> dict:
    """
    List available LAMMPS templates, or get defaults for one template.

    Args:
        template_name: If omitted, lists all templates with descriptions.
                       If provided, returns all tunable parameters and defaults
                       for that template. One of: minimize, nvt, npt,
                       npt_compress, npt_tg_step, npt_deform, nemd_thermal.

    Returns:
        With no argument: dict mapping template_name -> description.
        With template_name: dict with defaults and explanations for each param.
    """
    if template_name is None:
        return {"templates": TEMPLATE_DOCS}

    if template_name not in TEMPLATE_DEFAULTS:
        return {"error": f"Unknown template '{template_name}'. "
                         f"Available: {list(TEMPLATE_DEFAULTS.keys())}"}

    defaults = TEMPLATE_DEFAULTS[template_name]
    explanations = {
        "LOG_FILE":         "LAMMPS log filename",
        "LOG_APPEND":       "Append to existing log (bool). Use True for Tg sweeps.",
        "DUMP_FILE":        "Trajectory dump filename (.dump)",
        "LAST_DUMP_FILE":   "Final snapshot dump filename",
        "WRITE_DATA_FILE":  "Output .data file written at end of run",
        "RESTART_FILE_1/2": "Alternating restart checkpoint filenames",
        "RESTART_FREQ":     "Steps between restart file writes",
        "T_START":          "Initial temperature (K)",
        "T_FINAL":          "Final temperature (K). Equal to T_START for constant T.",
        "T_TARGET":         "Target temperature for single-T runs (npt_tg_step)",
        "T_DAMP":           "Thermostat damping time (fs). Recommended: 100*timestep",
        "P_START":          "Initial pressure (atm)",
        "P_FINAL":          "Final pressure (atm). Equal to P_START for constant P.",
        "P_TARGET":         "Target pressure (atm) for single-P runs",
        "P_DAMP":           "Barostat damping time (fs). Recommended: 1000*timestep",
        "TIMESTEP":         "Integration timestep (fs). 1.0 with SHAKE, 0.5 without.",
        "N_STEPS":          "Number of MD integration steps",
        "THERMO_FREQ":      "Frequency of thermo output to log (steps)",
        "DUMP_FREQ":        "Frequency of coordinate dump (steps)",
        "use_gpu":          "Enable GPU acceleration (bool). Avoid with NPT+restart.",
        "use_pppm":         "Use PPPM long-range electrostatics (bool). False = lj/cut.",
        "use_restart":      "Read from restart file instead of data file (bool)",
        "use_shake":        "Apply SHAKE constraints to H-X bonds (bool)",
        "init_velocity":    "Set initial velocities at this temperature (K). None = read from data.",
        "write_restart":    "Write restart checkpoint files (bool)",
        "MIN_STYLE":        "Minimizer algorithm: 'cg' or 'hftn'",
        "ETOL":             "Energy tolerance for minimization convergence",
        "FTOL":             "Force tolerance for minimization convergence",
        "MAXITER":          "Max minimization iterations",
        "MAXEVAL":          "Max force evaluations during minimization",
        "NEMD_N_SLABS":     "Number of slabs for temperature profile (thermal conductivity)",
        "NEMD_SWAP_FREQ":   "Steps between momentum swaps (NEMD)",
        "NEMD_AXIS":        "Heat flux axis: 'x', 'y', or 'z'",
    }

    return {
        "template":     template_name,
        "description":  TEMPLATE_DOCS[template_name],
        "defaults":     defaults,
        "explanations": {k: explanations.get(k, "") for k in defaults},
    }


@mcp.tool()
def inspect_data_file(
    data_file: str,
    lj_cutoff: float,
    target_density_gcm3: Optional[float],
    nchain: Optional[int],
    h_type_ids: Optional[list] = None,
    backbone_types: Optional[list] = None,
    atom_type_pairs: Optional[list] = None,
    charge_tol: float = 0.01,
    params_file: str = "",
) -> dict:
    """
    Parse a LAMMPS .data file and run pre-simulation validation in one call.

    Returns system info (n_atoms, box, atom types, h_type_ids) together with
    validation results. Check validation.errors — if non-empty the file is not
    safe to submit.

    BLOCKING errors: charge non-neutrality, missing Coeffs sections,
    box smaller than 2×cutoff, type IDs out of range, and — when
    target_density_gcm3 is given — a forecast chain-self-imaging violation
    (the compressed cell would have L < 2*Rg).
    ADVISORY warnings: unusual density, H-mass mismatch, bad bond/atom ratio.

    THIS IS THE CHEAPEST PLACE TO CATCH A TOO-SMALL CELL. Pass
    target_density_gcm3 (the class experimental density) and the finite-size
    forecast runs here, before any MD: Rg is measured on the packed coordinates
    (it barely changes on equilibration) and the post-compression box edge is
    predicted from the cell's own mass. Catching it at the equilibration gate
    instead wastes the whole chain — 3–20 ns of t_equil by class, plus the
    cooling tail.

    Args:
        data_file:       Path to the .data file.
        h_type_ids:      SHAKE H type IDs to validate.
        backbone_types:  Backbone atom type IDs to validate (end-to-end, P2).
        atom_type_pairs: RDF atom type pairs to validate.
        lj_cutoff:       REQUIRED. LJ cutoff in Å — the class's own value, not a nominal one.
                         The old 12.0 default over-stated the minimum-image bound for the 18
                         classes that run 9.5 Å.
        charge_tol:      Maximum allowed |net charge| in e (default 0.01).
        params_file:     Optional path to an EMC-generated .params file. When
                         provided, "Coeffs section missing" errors are suppressed
                         — EMC TraPPE-UA and PCFF .data files store coefficients
                         in the params file, not in the .data file.
        target_density_gcm3: REQUIRED, may be null. Target (experimental) density the cell
                         will be compressed to. Enables the finite_size_forecast block below;
                         a null skips the forecast rather than grading the roomier as-built
                         box, so pass the null deliberately — this is the pre-submission size
                         gate and an omission disarms it silently.
        nchain:          REQUIRED, may be null. Chain count, used only to turn a forecast
                         violation into a concrete rebuild target (nchain_suggested).

    Returns:
        dict with:
            info                 — n_atoms, n_atom_types, box, atom type names, h_type_ids
            validation           — {valid, errors, warnings, stats}
            finite_size_forecast — predicted-equilibrated L vs 2*cutoff_A and 2*Rg,
                                   verdict, and a nchain rebuild target when it fails
    """
    try:
        content = Path(data_file).read_text(encoding="utf-8")
        gen = ScriptGenerator(data_file=data_file)
        info = gen.parse_data_file(content=content)
        vr = gen.validate_data_file(
            content=content,
            h_type_ids=h_type_ids,
            backbone_types=backbone_types,
            atom_type_pairs=atom_type_pairs,
            lj_cutoff=lj_cutoff,
            charge_tol=charge_tol,
        )
        if params_file:
            vr["errors"] = [e for e in vr["errors"] if "Coeffs' section missing" not in e]
            vr["valid"] = len(vr["errors"]) == 0

        # Finite-size forecast — blocking, and free: it reads the same .data file already
        # parsed above and needs no trajectory.
        forecast = {"available": False, "reason": "target_density_gcm3 not supplied"}
        if target_density_gcm3:
            if MDA_SCRIPTS_DIR not in sys.path:
                sys.path.insert(0, MDA_SCRIPTS_DIR)
            from finite_size import forecast_from_data_file
            forecast = forecast_from_data_file(
                data_file, lj_cutoff, target_density_gcm3, nchain=nchain
            )
            if forecast.get("available") and not forecast.get("pass"):
                rem = forecast.get("remedy") or {}
                suggest = (f" Rebuild with nchain x{rem['nchain_factor']}"
                           + (f" (>= {rem['nchain_suggested']})" if rem.get("nchain_suggested") else "")
                           + "." if rem else "")
                vr["errors"].append(
                    f"{forecast['verdict']}: compressed cell would have "
                    f"L={forecast.get('L_predicted_A')} A at {target_density_gcm3} g/cm3 vs "
                    f"2*Rg={2 * forecast.get('packed_Rg_A', 0):.1f} A "
                    f"(L/2Rg={forecast.get('L_over_2Rg')}, L/2cutoff={forecast.get('L_over_2cutoff')}). "
                    f"Every chain would overlap its own periodic image.{suggest}"
                )
                vr["valid"] = False

        return {
            "status":     "success",
            "data_file":  data_file,
            "info":       info,
            "validation": vr,
            "finite_size_forecast": forecast,
        }
    except Exception as e:
        return {
            "status":     "error",
            "error":      str(e),
            "data_file":  data_file,
            "validation": {"valid": False, "errors": [str(e)], "warnings": [], "stats": {}},
        }


@mcp.tool()
def generate_script(
    template_name: str,
    data_file: str,
    output_script: str,
    params: dict,
    velocity_seed: int,
) -> dict:
    """
    Generate a filled LAMMPS .in script from a template and write it to disk.

    Args:
        template_name: Template to use (minimize/nvt/npt/npt_compress/
                       npt_tg_step/npt_deform/nemd_thermal)
        data_file:     Path to the LAMMPS .data file.
        output_script: Path to write the generated .in file.
        params:        Parameter overrides (see list_templates(template_name) for options).
                       Common params: T_START, T_FINAL, N_STEPS, T_DAMP,
                       P_START, P_FINAL, P_DAMP, use_gpu, LOG_FILE, DUMP_FILE.
        velocity_seed: REQUIRED, non-null. Pins every RNG seed the script carries — the
                       `velocity all create` seed, and the nemd_langevin thermostat seeds
                       (SEED_HOT = seed, SEED_COLD = seed + 1, unless params sets them). Pass
                       the same value every call for a run and record it in run_log.md.
                       Templates that inherit velocities from the .data file ignore it. A Tg
                       sweep chains many single-temperature npt_tg_step calls (one per waypoint,
                       each reading the previous call's WRITE_DATA_FILE) rather than one
                       multi-temperature script — pass this run's one velocity_seed to every
                       call in the chain.

    Returns:
        dict with script content, output path, and params used.
    """
    try:
        if velocity_seed is None:
            return {
                "status": "error",
                "error": "velocity_seed is required and must not be null — a null seed makes "
                         "the script draw its own random seeds, so the run cannot be "
                         "reproduced. Pass the run's seed and record it in run_log.md.",
            }

        gen = ScriptGenerator(data_file=data_file)
        try:
            gen.parse_data_file(content=Path(data_file).read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Could not parse data file; using defaults")

        script = gen.generate(
            template_name=template_name,
            output_path=output_script,
            params=params,
            data_file_override=data_file,
            velocity_seed=velocity_seed,
        )

        return {
            "status":         "success",
            "template":       template_name,
            "output_script":  output_script,
            "params_used":    {**TEMPLATE_DEFAULTS[template_name], **params},
            "system_info":    gen.get_system_info(),
            "script_preview": script[:1500] + "\n..." if len(script) > 1500 else script,
        }

    except Exception as e:
        logger.error(f"generate_script failed: {e}")
        return {"status": "error", "error": str(e)}


@mcp.tool()
def run_lammps_script(
    script: str,
    work_dir: str,
    gpu_ids: str,
    mpi: int,
    engine: str,
    log_file: str = "lammps_run.log",
    use_gpu: bool = True,
    progress_file: str = "",
    n_stages: int = 0,
    allow_concurrent_writer: bool = False,
    data_file: Optional[str] = None,
    h_type_ids: Optional[list] = None,
    backbone_types: Optional[list] = None,
    lj_cutoff: float = 12.0,
) -> dict:
    """
    Execute a LAMMPS .in script on the local GPU in the background.

    Args:
        script:    Full path to .in file.
        work_dir:  Working directory for outputs.
        gpu_ids:          Comma-separated GPU IDs to use (e.g. "0" or "0,1").
                          Required — no default; the engine no longer falls back to
                          GPU 0,1. Pass exactly the device(s) you intend to use.
        mpi:              Number of MPI processes. Required — no default.
                          Use 1 for small systems (<5k atoms), 2 for medium (5-10k),
                          4 for large (>10k) or Tg sweeps.
        log_file:         Name of the stdout/stderr capture log (in work_dir).
        use_gpu:          If False, launch without -sf gpu/-pk gpu flags and hide GPUs
                          via CUDA_VISIBLE_DEVICES=. For CPU-only computes that are
                          incompatible with GPU device-side neighbor lists.
                          (use_gpu=False forces engine="cpu" regardless of engine.)
        engine:           Execution engine: "gpu" (default; GPU package, pairwise on GPU),
                          "kokkos" (full-offload — pair+class2 bonded+pppm+neigh on GPU via
                          the KOKKOS binary, -sf kk), or "cpu". The KOKKOS path uses
                          LAMBDA_LAMMPS_KOKKOS and is ~7.9× faster on PCFF at mpi=1.
        data_file:        Optional path to the .data file this script reads. When provided,
                          the same pre-flight validation run_lammps_chain already performs
                          (structural/charge/box checks) runs here too, before submission —
                          closes a gap where the thermal Tg sweep and the deformation
                          mechanical leg (both call this, not run_lammps_chain) previously got
                          no early checks at all.
        h_type_ids:       SHAKE H type IDs — validated against the data file.
        backbone_types:   Backbone type IDs — validated against the data file.
        lj_cutoff:        LJ cutoff (Å) used for the box-vs-cutoff preflight check. Pass the
                          run's real cutoff_A — the 12.0 default overstates the bound for
                          classes that run 9.5 Å.

    Returns:
        dict with run_id for status polling via get_run_status().
    """
    try:
        # Ensure remote work directory exists
        Path(work_dir).mkdir(parents=True, exist_ok=True)

        # Double-launch guard: refuse if a live sim process already writes the target log.
        if not allow_concurrent_writer:
            conflict = _live_sim_writers([f"{work_dir}/{log_file}"])
            if conflict:
                return _double_launch_error(conflict)

        # Pre-flight validation (same check run_lammps_chain performs when data_file is given).
        if data_file:
            try:
                content = Path(data_file).read_text(encoding="utf-8")
                gen = ScriptGenerator(data_file=data_file)
                gen.parse_data_file(content=content)
                vr = gen.validate_data_file(
                    content=content, h_type_ids=h_type_ids, backbone_types=backbone_types,
                    lj_cutoff=lj_cutoff,
                )
                if vr["errors"]:
                    return {
                        "status": "error",
                        "error": "Pre-flight validation failed — script not submitted",
                        "validation_errors": vr["errors"],
                        "validation_warnings": vr["warnings"],
                        "validation_stats": vr["stats"],
                    }
                if vr["warnings"]:
                    logger.warning(f"Pre-flight warnings for {data_file}: {vr['warnings']}")
            except Exception as ve:
                logger.warning(f"Pre-flight validation skipped (error reading data file): {ve}")

        meta = {
            "script":        script,
            "work_dir":      work_dir,
            "log_file":      log_file,
            "mpi":           mpi,
            "gpu_ids":       gpu_ids,
            "use_gpu":       use_gpu,
            "engine":        engine,
            "progress_file": progress_file,
            "n_stages":      n_stages,
        }
        run_id = run_manager.create("lammps_run", meta)

        thread = threading.Thread(
            target=_lammps_run_background,
            args=(run_id, work_dir, script, mpi, gpu_ids, log_file, use_gpu, engine),
            daemon=True,
        )
        thread.start()

        return {
            "status":          "submitted",
            "run_id":          run_id,
            "work_dir": work_dir,
            "script":   script,
            "log_file":        f"{work_dir}/{log_file}",
            "mpi":             mpi,
            "gpu_ids":         gpu_ids,
            "poll_tip":        "Use get_run_status(run_id) to check progress.",
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
def run_lammps_chain(
    stages: list,
    gpu_ids: str,
    mpi: int,
    engine: str,
    data_file: Optional[str] = None,
    h_type_ids: Optional[list] = None,
    backbone_types: Optional[list] = None,
    params_file: str = "",
    allow_concurrent_writer: bool = False,
) -> dict:
    """
    Execute a sequence of LAMMPS scripts as a fully chained pipeline.
    Each stage runs to completion before the next begins.

    The chain process is fully independent of the MCP server — it survives
    server restarts, disconnections, and conversation resets.

    Progress is written to chain_progress.jsonl (one JSON line per event)
    in the same directory as the chain script. Poll with get_run_status().

    Pre-flight validation: when data_file is provided, inspect_data_file()
    is called before submission. Blocking errors stop the chain immediately
    with a clear error message. Warnings are returned alongside chain_id.

    Args:
        stages:         Ordered list of stage dicts, each with:
                          - name            (str)  human-readable label
                          - script   (str)  full path to .in file
                          - work_dir (str)  working directory for outputs
                          - log_file        (str)  run log filename (optional)
        gpu_ids:        Comma-separated GPU IDs (same for all stages). Required —
                        no default; the engine no longer falls back to GPU 0,1.
        mpi:            MPI processes (same for all stages). Required — no default.
        data_file:      Optional path to the .data file. When provided, runs
                        pre-flight validation before launching the chain.
        h_type_ids:     SHAKE H type IDs — validated against the data file.
        backbone_types: Backbone type IDs — validated against the data file.
        params_file:    Optional path to an EMC-generated .params file. When
                        provided, "Coeffs section missing" pre-flight errors are
                        suppressed — EMC TraPPE-UA and PCFF .data files store
                        coefficients in the params file, not the .data file.
        engine:         Execution engine for every stage: "gpu" (default; GPU package)
                        or "kokkos" (full-offload via LAMBDA_LAMMPS_KOKKOS, -sf kk).
                        The generated decks must match (KOKKOS decks omit `package gpu`).

    Returns:
        dict with chain_id, paths, and poll instructions.
        Includes preflight_warnings if validation found advisory issues.
    """
    try:
        if not stages:
            return {"status": "error", "error": "stages list is empty"}

        for i, s in enumerate(stages):
            for field in ("script", "work_dir"):
                if field not in s:
                    return {"status": "error",
                            "error": f"Stage {i} missing required field '{field}'"}
        for s in stages:
            if "log_file" not in s:
                s["log_file"] = f"{s.get('name', 'stage')}_run.log"

        # Double-launch guard: refuse if a live sim process writes any target stage log
        # (covers a prior chain stalled on any stage). Reads OS state, so it catches
        # orphans left by a context/server restart — the PLA3 corruption class.
        if not allow_concurrent_writer:
            conflict = _live_sim_writers(
                [f"{s['work_dir']}/{s['log_file']}" for s in stages]
            )
            if conflict:
                return _double_launch_error(conflict)

        # ── Pre-flight validation ─────────────────────────────────────────────
        preflight_warnings = []
        if data_file:
            try:
                content = Path(data_file).read_text(encoding="utf-8")
                gen = ScriptGenerator(data_file=data_file)
                gen.parse_data_file(content=content)
                vr = gen.validate_data_file(
                    content=content,
                    h_type_ids=h_type_ids,
                    backbone_types=backbone_types,
                )
                preflight_errors = vr["errors"]
                if params_file:
                    preflight_errors = [e for e in preflight_errors if "Coeffs' section missing" not in e]
                if preflight_errors:
                    return {
                        "status": "error",
                        "error": "Pre-flight validation failed — chain not submitted",
                        "validation_errors": preflight_errors,
                        "validation_warnings": vr["warnings"],
                        "validation_stats": vr["stats"],
                    }
                preflight_warnings = vr["warnings"]
                if preflight_warnings:
                    logger.warning(f"Pre-flight warnings for {data_file}: {preflight_warnings}")
            except Exception as ve:
                logger.warning(f"Pre-flight validation skipped (error reading data file): {ve}")

        chain_id = str(uuid.uuid4())[:8]

        # Place the chain script and its progress log next to the first stage
        chain_dir  = stages[0]["work_dir"].rsplit("/", 1)[0]  # parent dir
        chain_script  = f"{chain_dir}/chain_{chain_id}.sh"
        progress_file = f"{chain_dir}/chain_{chain_id}_progress.jsonl"

        # Build and upload the bash script
        script_body = _build_chain_script(chain_id, stages, mpi, gpu_ids, engine)
        # Override progress path to the one we computed
        script_body = script_body.replace(
            "PROGRESS=$( dirname $0 )/chain_progress.jsonl",
            f"PROGRESS={progress_file}"
        )

        # FIX: collapse mkdir + write + chmod + launch into ONE heredoc SSH command
        # to avoid 4 sequential conda-activate round trips (~5-15s each) that
        # cause the MCP tool response to timeout before returning.
        escaped_body = script_body.replace("'", "'\"'\"'")
        one_shot = (
            f"mkdir -p {chain_dir} && "
            f"cat > {chain_script} << 'POLYJARVIS_EOF'\n{script_body}\nPOLYJARVIS_EOF\n"
            f"chmod +x {chain_script} && "
            f"setsid nohup bash {chain_script} > {chain_dir}/chain_{chain_id}.log 2>&1 </dev/null & disown; echo $!"
        )
        stdout, _, _ = _conda_run(one_shot, timeout=30)
        pid = stdout.strip().splitlines()[-1] if stdout.strip() else "unknown"

        meta = {
            "chain_type":    "lammps_nohup_chain",
            "n_stages":      len(stages),
            "stage_names":   [s.get("name", f"stage_{i}") for i, s in enumerate(stages)],
            "stages":        stages,
            "mpi":           mpi,
            "gpu_ids":       gpu_ids,
            "chain_script":  chain_script,
            "progress_file": progress_file,
            "chain_log":     f"{chain_dir}/chain_{chain_id}.log",
            "pid":           pid,
        }
        run_manager.create_with_id(chain_id, "lammps_nohup_chain", meta)
        run_manager.start(chain_id)

        # Poll remote progress and write a local completion sentinel.
        threading.Thread(
            target=_chain_completion_monitor,
            args=(chain_id, progress_file),
            daemon=True,
        ).start()

        result = {
            "status":        "submitted",
            "chain_id":      chain_id,
            "n_stages":      len(stages),
            "stage_names":   meta["stage_names"],
            "pid":           pid,
            "chain_script":  chain_script,
            "progress_file": progress_file,
            "poll_tip":      "Use get_run_status(chain_id) to check progress. "
                             "Call watch_run(chain_id) immediately after this to "
                             "be notified automatically when the chain finishes.",
        }
        if preflight_warnings:
            result["preflight_warnings"] = preflight_warnings
        return result

    except Exception as e:
        return {"status": "error", "error": str(e)}


def _cleanup_chain_files(chain_id: str, progress_file: str, keep_log: bool = False):
    """Remove ephemeral chain bookkeeping files after completion.

    Always removes the .sh script and _progress.jsonl.
    Removes the .log only on success (keep_log=False); on failure the log is
    the primary post-mortem artifact so it is preserved.
    """
    chain_dir = Path(progress_file).parent
    to_remove = [
        Path(progress_file),
        chain_dir / f"chain_{chain_id}.sh",
    ]
    if not keep_log:
        to_remove.append(chain_dir / f"chain_{chain_id}.log")
    for p in to_remove:
        try:
            p.unlink(missing_ok=True)
            logger.info(f"[{chain_id}] Removed {p.name}")
        except Exception as e:
            logger.warning(f"[{chain_id}] Could not remove {p}: {e}")


def _chain_completion_monitor(chain_id: str, progress_file: str, poll_interval: int = 60):
    """
    Background thread: polls chain_progress.jsonl every poll_interval seconds.
    Writes a sentinel file when the chain completes or fails.
    """
    logger.info(f"[{chain_id}] Chain monitor started (polling every {poll_interval}s)")
    while True:
        time.sleep(poll_interval)
        try:
            stdout, _, exit_code = _conda_run(f"tail -5 {progress_file} 2>/dev/null || echo ''")
            if not stdout:
                continue
            for line in reversed(stdout.strip().splitlines()):
                try:
                    event = json.loads(line)
                    if event.get("stage") == "__chain__":
                        if event.get("status") == "completed":
                            _write_sentinel(chain_id, "completed")
                            logger.info(f"[{chain_id}] Chain monitor: completed")
                            _cleanup_chain_files(chain_id, progress_file, keep_log=False)
                            return
                        elif event.get("status") == "failed":
                            _write_sentinel(chain_id, "failed",
                                            {"stage": event.get("failed_stage", "unknown")})
                            logger.info(f"[{chain_id}] Chain monitor: failed")
                            _cleanup_chain_files(chain_id, progress_file, keep_log=True)
                            return
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.warning(f"[{chain_id}] Chain monitor poll error: {e}")


@mcp.tool()
def get_run_status(run_id: str) -> dict:
    """
    Get the current status of a submitted LAMMPS run or chain.

    For nohup chains, status is read live from the progress file so it
    always reflects reality regardless of server restarts.

    Args:
        run_id: Run ID returned by run_lammps_script() or run_lammps_chain().

    Returns:
        dict with status, completed_stages, current_stage, timing, etc.
    """
    run = run_manager.get(run_id)
    if not run:
        return {"error": f"Run '{run_id}' not found"}

    # For nohup chains, derive live status from the progress file
    if run.get("run_type") == "lammps_nohup_chain":
        progress_file = run["meta"].get("progress_file", "")
        try:
            stdout, _, rc = _conda_run(
                f"cat {progress_file} 2>/dev/null || echo ''"
            )
            events = [json.loads(line) for line in stdout.strip().splitlines() if line.strip()]
        except Exception:
            events = []

        completed = [e["stage"] for e in events if e.get("status") == "done"]
        failed    = [e for e in events if e.get("status") == "failed" and e.get("stage") != "__chain__"]
        running   = [e["stage"] for e in events if e.get("status") == "running"]
        chain_end = next((e for e in events if e.get("stage") == "__chain__"), None)

        stage_names = run["meta"].get("stage_names", [])
        n_stages    = run["meta"].get("n_stages", 0)

        # Completion sentinel fallback: the live `cat` of the progress file can fail silently
        # (file rotated/removed/unreadable) → events=[] → a false 'pending' on a chain that has
        # actually completed. The sentinel (done_<run_id>.json) is written by the nohup wrapper on
        # exit and is authoritative for terminal status, so consult it before concluding 'pending'.
        sentinel_status = None
        try:
            sentinel_file = SENTINEL_DIR / f"done_{run_id}.json"
            if sentinel_file.exists():
                sentinel_status = json.loads(sentinel_file.read_text()).get("status")
        except Exception:
            sentinel_status = None

        if chain_end:
            if chain_end["status"] == "completed":
                status = "completed"
            else:
                status = "failed"
        elif sentinel_status in ("completed", "failed"):
            status = sentinel_status
        elif not events:
            status = "pending"
        else:
            status = "running"

        current_stage = running[-1] if running else (completed[-1] if completed else None)
        next_idx = len(completed)
        next_stage = stage_names[next_idx] if next_idx < len(stage_names) else None

        return {
            "run_id":           run_id,
            "run_type":         "lammps_nohup_chain",
            "status":           status,
            "submitted_at":     run["submitted_at"],
            "n_stages":         n_stages,
            "completed_stages": completed,
            "n_completed":      len(completed),
            "current_stage":    current_stage,
            "next_stage":       next_stage if status == "running" else None,
            "failed_stages":    [f["stage"] for f in failed],
            "chain_end_event":  chain_end,
            "sentinel_status":  sentinel_status,
            "progress_file":    progress_file,
            "pid":              run["meta"].get("pid"),
            "note":             "Status read live from progress file (sentinel fallback) — survives MCP restarts.",
        }

    # Non-chain (single-script / analysis) run: return a COMPACT view. The full result dict for
    # analysis tools (extract_thermal etc.) can carry large per-frame lists
    # (structural_metrics_per_T, relaxation_metrics) that overflow the client (~73k chars). Keep
    # scalar result fields; replace big collections with a pointer — callers read the written JSON
    # artifact (e.g. thermal.json) for full detail.
    result = run.get("result")
    if not isinstance(result, dict):
        return run
    compact = {k: v for k, v in run.items() if k != "result"}
    _BIG_KEYS = {"structural_metrics_per_T", "relaxation_metrics", "structural_metrics",
                 "per_frame", "raw_data", "timeseries", "structural_analysis"}
    slim = {}
    for k, v in result.items():
        if k in _BIG_KEYS or (isinstance(v, (list, dict)) and len(v) > 50):
            _n = len(v) if isinstance(v, (list, dict)) else "?"
            slim[k] = f"<omitted: {type(v).__name__} len={_n}; read the JSON artifact for detail>"
        else:
            slim[k] = v
    compact["result"] = slim
    if isinstance(result.get("output_dir"), str):
        compact["result_artifact_dir"] = result["output_dir"]
    return compact


@mcp.tool()
def get_run_output(run_id: str) -> dict:
    """
    Get detailed output from a completed LAMMPS run, including the
    last 100 lines of the LAMMPS log.

    Args:
        run_id: Run ID returned by run_lammps_script().

    Returns:
        dict with result, log tail, and list of output files.
    """
    run = run_manager.get(run_id)
    if not run:
        return {"error": f"Run '{run_id}' not found"}

    if run["status"] != JobStatus.COMPLETED.value:
        return {"status": run["status"], "message": "Run not yet completed"}

    result = dict(run)
    work_dir = run["meta"].get("work_dir", "")

    # Tail the LAMMPS log
    try:
        lammps_log = os.path.join(work_dir, "log.lammps")
        stdout, _, _ = _conda_run(f"tail -100 {lammps_log}")
        result["lammps_log_tail"] = stdout
    except Exception:
        result["lammps_log_tail"] = "(could not read log.lammps)"

    # List output files
    try:
        files = os.listdir(work_dir)
        result["output_files"] = sorted(files)
    except Exception:
        result["output_files"] = []

    return result


@mcp.tool()
def list_runs(status_filter: Optional[str] = None) -> dict:
    """
    List all submitted LAMMPS runs.

    Args:
        status_filter: Optional filter: 'pending', 'running', 'completed', 'failed'

    Returns:
        List of run summaries.
    """
    runs = run_manager.all()
    if status_filter:
        runs = [r for r in runs if r["status"] == status_filter]

    # Return compact summary
    summaries = []
    for r in runs:
        summaries.append({
            "run_id":       r.get("run_id", "unknown"),
            "status":       r.get("status", "unknown"),
            "run_type":     r.get("run_type", "unknown"),
            "submitted_at": r.get("submitted_at", "unknown"),
            "completed_at": r.get("completed_at"),
            "script":       r.get("meta", {}).get("script", ""),
        })

    return {"runs": summaries, "total": len(summaries)}


@mcp.tool()
def watch_run(run_id: str) -> dict:
    """
    Return completion-sentinel metadata for a submitted run.

    Deterministic callers can poll the sentinel path or process-liveness command.

    Args:
        run_id: The run_id or chain_id to watch.

    Returns:
        monitor_command:        shell command that waits for the sentinel.
        recommended_timeout_ms: 3600000 (the Monitor max; runs may exceed it —
                                re-arm by calling watch_run again on a bare timeout).
        sentinel_path:          completion sentinel JSON (status: completed|failed).
        pidfile:                liveness pidfile the command reads for the run.
    """
    sentinel_path = SENTINEL_DIR / f"done_{run_id}.json"
    pidfile = pidfile_path(run_id, SENTINEL_DIR)
    run = run_manager.get(run_id) or {}
    meta = run.get("meta", {})
    progress_file = meta.get("progress_file", "")
    n_stages = meta.get("n_stages", 0) if progress_file else 0
    monitor_command = build_watch_command(str(sentinel_path), pidfile, progress_file, n_stages)
    return {
        "run_id":                run_id,
        "sentinel_path":         str(sentinel_path),
        "pidfile":               pidfile,
        "progress_file":         progress_file,
        "monitor_command":       monitor_command,
        "recommended_timeout_ms": 3600000,
        "usage":                 (
            "Pass monitor_command to the Monitor tool with timeout_ms=3600000 (the max). "
            "When it prints RUN_COMPLETE, read sentinel_path for the status, then continue. "
            "If Monitor exits with NO 'RUN_COMPLETE' or 'PROCESS_DEAD' line, that is a "
            "timeout (not completion) — the run is still going; call watch_run again and "
            "re-issue Monitor. 'PROCESS_DEAD_NO_SENTINEL' or a sentinel with status=failed "
            "means the run died → use /recover."
        ),
    }



def _ff_base_for(use_pcff: bool, use_trappe: bool, use_opls: bool,
                 params_file: str, engine: str) -> dict:
    """The force-field/engine keys every stage deck in a chain must carry.

    Shared by generate_equilibration_workflow and generate_cooling_workflow so the two halves
    of one run cannot drift onto different styles -- the cooling chain reads the equilibration
    chain's own .data file, and a mismatch there is the "deck emits CHARMM regardless" class of
    bug this repo has hit more than once.

    PCFF class2 cells from EMC start at ~0.5x experimental density -- no separate soft-heat or
    cutoff-only compression phase needed. SHAKE is off: PCFF runs stably at 1 fs all-atom
    without constraints. TraPPE-UA is united-atom (no H), pure lj/cut, no kspace; SHAKE is
    disabled there too -- UA removes the fast C-H stretch modes, so 2 fs is stable WITHOUT bond
    constraints, and fix shake on a continuous backbone would fail in LAMMPS anyway (interior
    atoms have 2 bonds; cluster-build requires terminal atoms). The 2 fs speedup comes from the
    timestep alone (see _dt_prod_for).
    """
    if use_pcff:
        ff_base = {"use_pcff": True, "use_shake": False}
    elif use_trappe:
        ff_base = {"use_trappe": True, "use_shake": False, "use_pppm": False,
                   "LJ_CUTOFF": 14.0}
    elif use_opls:
        ff_base = {"use_opls": True, "use_shake": False}
    else:
        ff_base = {}
    if params_file:
        ff_base["params_file"] = params_file
    # Carry the execution engine into every stage deck. GPU-enabled stages render the matching
    # accelerator package (gpu -> `package gpu`; kokkos -> none, -sf kk handles it); use_gpu=False
    # stages ignore it and stay CPU. Submit the chain with the SAME engine (run_lammps_chain).
    ff_base["engine"] = engine
    return ff_base


def _make_stage_builders(gen, work_dir_base: str, ff_base: dict, velocity_seed: int):
    """Return (_stage, _continue_stage) bound to one chain's generator and output directory.

    Both build the same {name, template, script, work_dir, input_data, output_data,
    output_restart, params} shape, and both put ff_base LAST so use_shake/use_pcff/params_file
    always win over a stage's own params.
    """

    def _stage(name, template, p, prev_data):
        stage_dir = f"{work_dir_base}/{name}"
        script = f"{stage_dir}/{name}.in"
        out_data = f"{stage_dir}/{name}_out.data"
        out_restart = f"{stage_dir}/{name}_out.restart"
        p = {
            "LOG_FILE":           f"{name}.log",
            "DUMP_FILE":          f"{name}.dump",
            "LAST_DUMP_FILE":     f"{name}_last.dump",
            "WRITE_DATA_FILE":    out_data,
            "WRITE_RESTART_FILE": out_restart,
            **p,        # stage params first (lower priority for FF keys)
            **ff_base,  # ff_base last -- ensures use_shake/use_pcff/params_file always win
        }
        Path(stage_dir).mkdir(parents=True, exist_ok=True)
        gen.generate(template_name=template, output_path=script, params=p,
                     data_file_override=prev_data, velocity_seed=velocity_seed)
        return {"name": name, "template": template, "script": script, "work_dir": stage_dir,
                "input_data": prev_data, "output_data": out_data,
                "output_restart": out_restart, "params": p}

    def _continue_stage(base_name, template, p, restart_path):
        """Genuinely CONTINUE base_name's own trajectory: read_restart (not read_data),
        log/dump appended onto base_name's own files, no velocity re-initialization.
        Returns the same shape as _stage(), keyed by the SAME name so callers can't
        mistake this for a new, independently-numbered stage."""
        stage_dir = f"{work_dir_base}/{base_name}"
        script = f"{stage_dir}/{base_name}.in"
        out_data = f"{stage_dir}/{base_name}_out.data"
        out_restart = f"{stage_dir}/{base_name}_out.restart"
        p = {
            "LOG_FILE":           f"{base_name}.log",
            "DUMP_FILE":          f"{base_name}.dump",
            "LAST_DUMP_FILE":     f"{base_name}_last.dump",
            "WRITE_DATA_FILE":    out_data,
            "WRITE_RESTART_FILE": out_restart,
            "use_restart":        True,
            "LOG_APPEND":         True,
            "dump_append":        True,
            "init_velocity":      None,
            **p,
            **ff_base,
        }
        Path(stage_dir).mkdir(parents=True, exist_ok=True)
        gen.generate(template_name=template, output_path=script, params=p,
                     data_file_override=restart_path, velocity_seed=velocity_seed)
        return {"name": base_name, "template": template, "script": script,
                "work_dir": stage_dir, "input_data": restart_path, "output_data": out_data,
                "output_restart": out_restart, "params": p}

    return _stage, _continue_stage


@mcp.tool()
def generate_equilibration_workflow(
    data_file: str,
    work_dir_base: str,
    velocity_seed: int,
    densify_ramp_steps: Optional[int],
    densify_check_every_steps: Optional[int],
    densify_steps_cap: Optional[int],
    ff_activate_npt_steps: Optional[int],
    anneal_heat_steps: Optional[int],
    anneal_check_every_steps: Optional[int],
    anneal_cap_steps: Optional[int],
    melt_ramp_steps: Optional[int],
    melt_hold_min_steps: Optional[int],
    melt_hold_cap_steps: Optional[int],
    nvt_melt_min_steps: Optional[int],
    nvt_melt_cap_steps: Optional[int],
    warmup_steps: Optional[int],
    use_long_range: bool,
    melt_hold_T: float,
    use_pcff: bool,
    use_trappe: bool,
    use_opls: bool,
    engine: str,
    polymer_name: str = "polymer",
    max_temp: float = 600.0,
    press: float = 1.0,
    max_press: float = 50000.0,
    n_chains: int = 6,
    n_atoms: Optional[int] = None,
    params_file: str = "",
    anneal_margin_K: float = 100.0,
    extend_only: bool = False,
    restart_file: Optional[str] = None,
    base_stage_name: Optional[str] = None,
    extend_temp_K: Optional[float] = None,
    thermostat_damp_fs: float = 100.0,
    barostat_damp_fs: float = 1000.0,
    resume_from: Optional[str] = None,
    extend_ensemble: str = "npt",
    minimize_etol: float = 1e-6,
    minimize_ftol: float = 1e-6,
    minimize_maxiter: int = 50000,
    minimize_maxeval: int = 100000,
) -> dict:
    """
    Auto-generate a complete adaptive equilibration workflow as a sequence of LAMMPS
    scripts, replacing the earlier anneal-before-densify pipeline.

    Protocol (fixed stage names, adaptive stages EXTEND via restart-continuation — see
    extend_only — rather than by lengthening this call's own N_STEPS):
      minimize               - energy minimization in the as-built amorphous cell
      nvt_warmup             - fixed, short NVT settle at 300 K (removes build artifacts)
      npt_densify            - fixed, short NPT compress ramp 1->max_press atm at 300 K
                               (voids removal). PPPM off during compression for OPLS (rapid
                               box shrink guard). A ramp is one-shot by construction (LAMMPS
                               interpolates P_START->P_FINAL monotonically over one `run`) —
                               not itself adaptive.
      npt_ff_activate        - fixed, short NPT decompress ramp max_press->press at 300 K,
                               PPPM restored. Also one-shot.
      npt_densify_hold       - ADAPTIVE: constant 300 K/press NPT hold, gated on
                               density/non-bonded-energy half-window stability and no
                               monotonic volume trend — the actual "has densification
                               converged" question, asked only once the pressure shock
                               (npt_densify/npt_ff_activate) is over.
      anneal_heat            - fixed, short NVT ramp 300 K -> max_temp (one-shot, same reason)
      anneal_hold            - ADAPTIVE: NVT hold AT max_temp (accessible conformational
                               relaxation — NOT a claim of reptation/terminal relaxation)
      npt_melt_ramp          - fixed, one-shot NPT ramp max_temp -> melt_hold_T. The first
                               barostatted stage after an NVT anneal_hold, so the box is
                               still the densified 300 K one and the barostat expands it to
                               melt density here.
      npt_melt_hold          - ADAPTIVE: NPT at melt_hold_T/press. THE GATED CELL — melt
                               density, the thermo drift/SEM gates and the per-frame
                               geometry checks (Rg/MSID/R_ee/torsion/P2/homogeneity/
                               finite_size) all come from this stage's own log/trajectory.
      nvt_melt_hold          - ADAPTIVE: NVT at melt_hold_T, FIXED volume (npt_melt_hold's
                               own endpoint). Supplies the uncontaminated (non-barostat-
                               rescaled) window MSD/kinetic-trap/C(t) need, and its endpoint
                               is the cell every downstream track starts from.

    This chain does NOT cool. The descent to the assessment temperature — cool_block_NN,
    cool_block_NN and npt_final — is generate_cooling_workflow's, and runs only when a
    property needs a cell at that temperature. A melt-only run stops here.

    Required args — no defaults. Every step count and the velocity seed must be passed on
    every call, including as an explicit null where the value does not apply to this path.
    Omitting one is what let two identically-prompted runs of the same system emit different
    `run N` counts, so omission is a schema error rather than a silent substitution.

    Each adaptive stage is generated here with only its FIRST block's step count (the
    *_check_every_steps / *_min_steps args) — this function never loops an adaptive stage
    to convergence itself. Further blocks are separate restart-continuation calls
    (extend_only=True, restart_file=<this stage's own .restart output>,
    base_stage_name=<this stage's name>), driven by the orchestration layer's own
    gate-and-extend loop, bounded by the matching *_cap_steps ceiling.

    Args:
        data_file:      Path to the .data file.
        work_dir_base:  Base directory for all stage subdirectories.
        velocity_seed:  REQUIRED, non-null. Pins the `velocity all create` RNG seed for every
                        stage that initialises velocities. Draw once per run, pass the same
                        value to every call for that run, and record it in run_log.md.
        densify_ramp_steps: REQUIRED. Step count for the fixed npt_densify compress ramp
                        (1->max_press). Null selects the atom-count tier default (steps_comp).
        densify_check_every_steps: REQUIRED. Step count for npt_densify_hold's first block
                        (the adaptive post-decompression hold). Null selects the atom-count
                        tier default (steps_comp).
        densify_steps_cap: REQUIRED. Ceiling on cumulative npt_densify_hold steps across all
                        restart-continuation extensions. Null selects 3x the tier default.
        ff_activate_npt_steps: REQUIRED. Step count for the fixed npt_ff_activate decompress
                        ramp (max_press->press, PPPM restored). Null selects int(1.0e5/dt_prod)
                        (~100 ps).
        anneal_heat_steps: REQUIRED. Step count for the fixed 300 K -> max_temp anneal_heat
                        ramp. Null selects the atom-count tier default (steps_heat).
        anneal_check_every_steps: REQUIRED. Step count for anneal_hold's first block. Null
                        selects the atom-count tier default (steps_heat).
        anneal_cap_steps: REQUIRED. Ceiling on cumulative anneal_hold steps across all
                        restart-continuation extensions. Null selects 3x the tier default.
                        This is a TIME cap, not a cycle count — the retired eq_annealing_cycles
                        knob no longer exists; annealing is one continuously-extendable hold.
        melt_ramp_steps: REQUIRED. Step count for the fixed max_temp -> melt_hold_T
                        npt_melt_ramp. Null selects the atom-count tier default (steps_heat).
                        Size it generously: this is where the densified 300 K box expands to
                        melt density, and a ramp is one-shot.
        melt_hold_min_steps: REQUIRED. Step count for npt_melt_hold's first block. Null
                        selects int(5.0e5/dt_prod) (~0.5 ns).
        melt_hold_cap_steps: REQUIRED. Ceiling on cumulative npt_melt_hold steps across all
                        restart-continuation extensions. Null selects int(5.0e6/dt_prod).
        nvt_melt_min_steps: REQUIRED. Step count for nvt_melt_hold's first block. Null
                        selects int(5.0e5/dt_prod) (~0.5 ns). NOTE this window is
                        uncalibrated: MSD/C(t) decorrelate far faster at melt temperatures
                        than at 300 K, so the 0.5 ns default is a placeholder, not a measured
                        floor. This is now the ONLY fixed-volume window in the whole protocol.
        nvt_melt_cap_steps: REQUIRED. Ceiling on cumulative nvt_melt_hold steps. Null selects
                        int(2.0e6/dt_prod) (~2 ns).
        warmup_steps:   REQUIRED. Step count for the fixed nvt_warmup stage. Null selects
                        int(1.0e5/dt_prod) (~100 ps).
        extend_ensemble: "npt" (default) or "nvt" — which ensemble extend_only continues.
                        Must match base_stage_name's own ensemble (e.g. "nvt" for
                        anneal_hold/nvt_melt_hold, "npt" for npt_densify_hold/npt_melt_hold)
                        — mismatches would silently add or remove a barostat
                        mid-trajectory. Ignored unless extend_only=True.
        minimize_etol:  Energy-tolerance stopping criterion for the minimize stage (default
                        1e-6, matches script_generator.py's own default). Escalated (looser,
                        x10/attempt) by the raise_minimize_tolerance remedy on
                        MINIMIZE_NOT_CONVERGED. Ignored unless resume_from is None (a resumed
                        chain skips minimize entirely).
        minimize_ftol:  Force-tolerance stopping criterion (default 1e-6). Same remedy/scope.
        minimize_maxiter: Max minimizer iterations (default 50000). Escalated x4/attempt by the
                        same remedy.
        minimize_maxeval: Max force evaluations (default 100000). Same remedy/scope.
        polymer_name:   Label used in filenames and log comments.
        melt_hold_T:    REQUIRED. The melt hold temperature (K) — where this chain ENDS and
                        every downstream track begins. Melt density and the binding melt gate
                        are measured here. Resolved per-SMILES by the planning layer as
                        max(class T_equil_K, Tg + 200) so it clears the MD glass transition
                        (which sits ~120 K above the experimental Tg at accessible cooling
                        rates); the Tg staircase starts from this cell and cools, so a melt
                        hold below the MD transition would begin the sweep inside the glass.
        max_temp:       Peak annealing temperature (K). Must be at or above melt_hold_T
                        (enforced below) — npt_melt_ramp descends from it to the melt hold.
                        A margin of anneal_margin_K is expected but only warned about, since
                        the soak's value is a planning-layer judgement, not a correctness one.
        anneal_margin_K: Expected margin between max_temp and melt_hold_T (default 100 K).
                        Below it the ramp is near a no-op and the soak does no de-knotting;
                        logged as a warning rather than rejected. See stage_params.py's own
                        floor on this same invariant, which is where it is actually decided.
        press:          Target pressure (atm), typically 1.
        max_press:      Compression pressure (atm), typically 50000.
        n_chains:       NO-OP — accepted for backward compatibility but never read. Chain
                        count comes from the .data file. Do not use it as a protocol knob.
        n_atoms:        Total atom count. Auto-detected if not provided.
        engine:         REQUIRED. Execution engine stamped into every GPU stage deck: "gpu"
                        (renders `package gpu`) or "kokkos" (renders no GPU
                        package — `-sf kk` rewrites styles to /kk at launch). Submit
                        the chain with the matching engine= in run_lammps_chain().
        use_pcff:       REQUIRED. All three FF flags must be passed on every call: they are
                        mutually exclusive, and all three defaulting to False emits GAFF2
                        styles against whatever the cell actually is.
                        Set True for EMC/PCFF class2 systems (PCBN, PAMD, PKTN,
                        PSFO, PIMD, POXI, PEST, PSUL, PURT, PANH, PPHS, PACR,
                        PIMN, PVNL, PPNL). Switches all templates to class2
                        styles, sixthpower mixing, and full 1-4 interactions.
                        SHAKE is disabled (PCFF runs cleanly at 1 fs without it).
        use_trappe:     Set True for EMC/TraPPE-UA systems (PHYC, PDIE).
                        Switches all templates to pair_style lj/cut 14.0 (no
                        kspace), multi/harmonic dihedrals, and SHAKE on all
                        C-C bond types (enables dt=2 fs for npt_ff_activate onward).
        use_opls:       Set True for EMC/OPLS-AA systems (PHAL, PSIL).
                        Switches all templates to pair_style lj/cut/coul/long 9.5,
                        multi/harmonic dihedrals, geometric mixing, special_bonds
                        lj/coul 0 0 0.5, and SHAKE disabled (OPLS H-type mix
                        h1/h1o/h1si untested with SHAKE; 1 fs is stable without it).
        params_file:    Optional path to an EMC-generated .params file containing
                        force field coefficients (pair_coeff, bond_coeff, etc.).
                        When provided, Coeffs validation is skipped on the .data
                        file (EMC stores coefficients separately) and each script
                        includes the file via `include {params_file}`.
        resume_from:    None (default, full chain from minimize) or one of "nvt_warmup" |
                        "npt_densify" | "npt_ff_activate" | "npt_densify_hold" | "anneal_hold" |
                        "npt_melt_ramp" | "npt_melt_hold" — skip every stage up to and
                        including the named checkpoint and start the returned chain AFTER it,
                        reading data_file as that checkpoint's own write_data output.
                        Every resumable stage runs with init_velocity=None (no `velocity all
                        create`), so it always inherits velocities from whatever .data file
                        it's given — resuming is not a special case, it's how every stage
                        boundary in the full chain already works. "anneal_hold" means both
                        anneal_heat and anneal_hold already ran — starts at npt_melt_ramp.
                        "npt_melt_hold" generates nvt_melt_hold alone, which is exactly what
                        the melt gate's two-step EXTEND needs after lengthening npt_melt_hold:
                        the NVT window and the handoff cell were both built from the
                        pre-extension endpoint and are stale until regenerated. To continue a
                        single already-run block rather than redo it, use extend_only.
        extend_only:    If True, generate ONE restart-continuation stage (not a fresh chain) —
                        see restart_file/base_stage_name below. This is the ONLY way any
                        adaptive stage gets more steps; it is never done by re-generating that
                        stage with a larger N_STEPS.
        restart_file:   REQUIRED when extend_only=True. Path to base_stage_name's own
                        <name>_out.restart file (NOT a .data file) — the continuation reads
                        this via `read_restart`, preserving thermostat/barostat extended-system
                        state and step count, and issues no `velocity create`.
        extend_temp_K:  Unused by this tool — every adaptive stage of the core chain holds at
                        a fixed, known condition (npt_densify_hold: 300 K; anneal_hold:
                        max_temp; npt_melt_hold/nvt_melt_hold: melt_hold_T). Accepted for
                        signature symmetry with generate_cooling_workflow, where a cool_block_NN
                        genuinely does need it.
        base_stage_name: REQUIRED when extend_only=True. The stage being continued — one of
                        "npt_densify_hold", "anneal_hold", "npt_melt_hold", "nvt_melt_hold".
                        The continuation's log/dump are opened in APPEND mode onto that stage's
                        own LOG_FILE/DUMP_FILE, so the result is one continuous trajectory
                        split across runs, not a new one.

    Returns:
        dict with:
            stages          - list of stage dicts (script_path, work_dir, params)
            run_order       - ordered list of stage names
            melt_data_path  - npt_melt_hold's output_data: the GATED melt cell. What the melt
                              gate adjudicates, and the cooling stage's contraction reference.
            melt_start_data_path - nvt_melt_hold's output_data: the HANDOFF cell. What the
                              cooling stage and the Tg staircase both start from. Its box is
                              npt_melt_hold's own, since NVT cannot move it.
            instructions    - how to execute this workflow
    """
    try:
        if velocity_seed is None:
            return {
                "status": "error",
                "error": "velocity_seed is required and must not be null — a null seed makes "
                         "every stage draw its own random `velocity all create` seed, so the "
                         "chain cannot be reproduced. Draw one seed per run, pass it here, and "
                         "record it in run_log.md.",
            }
        _CHECKPOINTS = ["nvt_warmup", "npt_densify", "npt_ff_activate", "npt_densify_hold",
                       "anneal_hold", "npt_melt_ramp", "nvt_melt_hold"]
        if resume_from not in (None, *_CHECKPOINTS):
            return {"status": "error",
                    "error": f"resume_from={resume_from!r} is not supported — must be one of "
                             f"None, {', '.join(repr(c) for c in _CHECKPOINTS)}."}
        if resume_from is not None and extend_only:
            return {"status": "error", "error": "resume_from and extend_only are mutually exclusive"}
        if extend_ensemble not in ("npt", "nvt"):
            return {"status": "error",
                    "error": f"extend_ensemble={extend_ensemble!r} must be 'npt' or 'nvt'"}
        if extend_only and (not restart_file or not base_stage_name):
            return {"status": "error",
                    "error": "extend_only=True requires both restart_file (the base stage's own "
                             ".restart output) and base_stage_name (the stage being continued) — "
                             "a continuation reads restart state onto that stage's own log/dump, "
                             "it does not start a new stage from a plain .data file."}
        _STAGE_ENSEMBLE = {"npt_densify_hold": "npt", "anneal_hold": "nvt",
                          "npt_melt_hold": "npt", "nvt_melt_hold": "nvt"}
        if extend_only and base_stage_name:
            _required_ensemble = _STAGE_ENSEMBLE.get(base_stage_name)
            if _required_ensemble is not None and extend_ensemble != _required_ensemble:
                return {"status": "error",
                        "error": f"extend_ensemble={extend_ensemble!r} does not match "
                                 f"base_stage_name={base_stage_name!r}'s own ensemble "
                                 f"({_required_ensemble!r}) — continuing an {_required_ensemble} "
                                 f"stage as {extend_ensemble} would silently add or remove a "
                                 "barostat mid-trajectory."}
        temp = melt_hold_T
        if max_temp < melt_hold_T:
            return {"status": "error",
                    "error": f"max_temp={max_temp} is below melt_hold_T={melt_hold_T} — "
                             "npt_melt_ramp descends from the anneal ceiling to the melt hold, "
                             "so the ceiling must be at or above it. Raise max_temp (or the "
                             "class's annealing_T_high_K)."}
        if max_temp == melt_hold_T:
            # Only the degenerate case is worth saying anything about. anneal_margin_K is a
            # margin over T_equil_K -- the melt-EQUILIBRATION temperature -- and that is where
            # stage_params enforces it; this generator never sees T_equil_K, so comparing the
            # margin against melt_hold_T here would fire on every perfectly-correct run whose
            # per-SMILES melt sits above T_equil (PS: melt 573 K, ceiling 650 K, a 77 K gap
            # that is exactly the intended 100 K over T_equil=550).
            logger.warning(
                "max_temp == melt_hold_T == %s — npt_melt_ramp is a no-op and the anneal soak "
                "runs at the melt temperature, so it does no de-knotting above it. Legal, but "
                "probably not what was intended.", melt_hold_T)
        if resume_from == "nvt_melt_hold":
            # Legal and meaningful: it regenerates the closing npt_melt_hold from an
            # already-extended nvt_melt_hold, which is exactly what the melt gate's two-step
            # structural EXTEND needs. Left explicit so the asymmetry is visible.
            pass
        if thermostat_damp_fs <= 0 or barostat_damp_fs <= 0:
            return {"status": "error", "error": "thermostat/barostat damping must be positive"}

        # Parse data file to get system info
        content = Path(data_file).read_text(encoding="utf-8")
        gen = ScriptGenerator(data_file=data_file)
        info = gen.parse_data_file(content=content)

        # Pre-flight validation — block on errors, surface warnings.
        # When params_file is set (EMC output), Coeffs live in the params file
        # rather than the .data file — filter those specific errors out.
        vr = gen.validate_data_file(content=content, h_type_ids=info.get("h_type_ids"))
        errors = vr["errors"]
        if params_file:
            errors = [e for e in errors if "Coeffs' section missing" not in e]
        if errors:
            return {
                "status": "error",
                "error": "Pre-flight validation failed — workflow not generated",
                "validation_errors": errors,
                "validation_warnings": vr["warnings"],
                "validation_stats": vr["stats"],
            }

        n_atoms = n_atoms or info.get("n_atoms", 0)

        # Select step counts based on system size
        if n_atoms < 5000:
            steps_min   = 50000
            steps_comp  = 300000
            steps_heat  = 500000
            steps_npt   = 1000000
            steps_nvt   = 1000000
        elif n_atoms < 15000:
            steps_min   = 50000
            steps_comp  = 500000
            steps_heat  = 1000000
            steps_npt   = 2000000
            steps_nvt   = 2000000
        else:
            steps_min   = 50000
            steps_comp  = 1000000
            steps_heat  = 2000000
            steps_npt   = 3000000
            steps_nvt   = 3000000

        ff_base = _ff_base_for(use_pcff, use_trappe, use_opls, params_file, engine)
        # TraPPE-UA's united-atom sites permit 2 fs; the early ramps still pin 0.5 fs inline.
        dt_prod = 2.0 if use_trappe else 1.0

        stages = []

        _stage, _continue_stage = _make_stage_builders(
            gen, work_dir_base, ff_base, velocity_seed)

        # --- Extend-only mode: restart-based continuation of an already-submitted adaptive
        # stage. This is the ONLY way any adaptive stage (npt_densify, anneal_hold, any
        # npt_melt_hold, nvt_melt_hold) gets more steps — never by
        # re-generating that stage with a larger N_STEPS. read_restart preserves
        # thermostat/barostat extended-system state and step count; log/dump are opened in
        # append mode onto base_stage_name's OWN files, so the result is one continuous
        # trajectory, not a new independently-numbered stage.
        if extend_only:
            # The continuation's own block length comes from whichever *_check_every_steps /
            # *_min_steps arg governs base_stage_name — the SAME knob
            # the orchestration layer passed (possibly escalated by a remedy) when it first
            # submitted that stage, not a separate generic "how long to extend" parameter.
            if base_stage_name == "npt_densify_hold":
                ext_steps = densify_check_every_steps
            elif base_stage_name == "anneal_hold":
                ext_steps = anneal_check_every_steps
            elif base_stage_name == "npt_melt_hold":
                ext_steps = melt_hold_min_steps
            elif base_stage_name == "nvt_melt_hold":
                ext_steps = nvt_melt_min_steps
            else:
                return {"status": "error",
                        "error": f"base_stage_name={base_stage_name!r} is not a recognized "
                                 "adaptive stage of the CORE chain — must be one of "
                                 "npt_densify_hold, anneal_hold, npt_melt_hold, nvt_melt_hold. "
                                 "The cooldown's stages (cool_block_NN, npt_final) belong to "
                                 "generate_cooling_workflow."}
            ext_steps = int(ext_steps) if ext_steps else int(1.0e6 / dt_prod)
            template = "nvt" if extend_ensemble == "nvt" else "npt"
            # Each adaptive stage holds at its OWN fixed condition; a continuation must hold
            # at the SAME one, not silently default to the workflow's temp/press.
            if base_stage_name == "npt_densify_hold":
                ext_T = 300.0
            elif base_stage_name == "anneal_hold":
                ext_T = max_temp
            elif base_stage_name in ("npt_melt_hold", "nvt_melt_hold"):
                ext_T = melt_hold_T
            else:
                ext_T = temp  # unreachable: base_stage_name already validated above
            params = {
                "T_START": ext_T, "T_FINAL": ext_T, "T_DAMP": thermostat_damp_fs,
                "TIMESTEP": dt_prod, "N_STEPS": ext_steps,
                "use_pppm": use_long_range and not use_trappe,
                "use_gpu": True,
            }
            if extend_ensemble == "npt":
                params.update({"P_START": press, "P_FINAL": press, "P_DAMP": barostat_damp_fs})
            sx = _continue_stage(base_stage_name, template, params, restart_file)
            stages.append(sx)
            return {
                "status":             "success",
                "polymer":            polymer_name,
                "n_atoms":            n_atoms,
                "melt_hold_T":        melt_hold_T,
                "max_temp":           max_temp,
                "n_stages":           1,
                "engine":             engine,
                "extend_only":        True,
                "extend_ensemble":    extend_ensemble,
                "stages":             stages,
                "run_order":          [sx["name"]],
                # An extend-only call generates ONE continuation stage and nothing else, so it
                # names no melt cells. The caller keeps the paths it already had -- and, when it
                # extended npt_melt_hold, must regenerate nvt_melt_hold (resume_from=
                # "npt_melt_hold") before those paths are valid again.
                "melt_data_path":       None,
                "melt_start_data_path": None,
                "preflight_warnings":  vr["warnings"],
                "preflight_stats":     vr["stats"],
                "instructions": (
                    f"Extend-only: continued {base_stage_name} ({extend_ensemble.upper()}, "
                    f"{ext_steps} more steps) via read_restart from {restart_file}, "
                    f"appending onto {sx['work_dir']}/{sx['params']['LOG_FILE']} "
                    f"(engine={engine}). Submit with run_lammps_chain(engine='{engine}'); "
                    f"then re-run the block gate on {sx['output_data']}."
                ),
            }

        # --- minimize: only for the full chain -------------------------------------------------
        if resume_from is None:
            s_min = _stage("minimize", "minimize", {
                "use_pppm":  use_long_range and not use_trappe,
                "use_gpu":   True,
                "MIN_STYLE": "cg",
                "ETOL":      minimize_etol,
                "FTOL":      minimize_ftol,
                "MAXITER":   minimize_maxiter,
                "MAXEVAL":   minimize_maxeval,
            }, data_file)
            stages.append(s_min)
            prev_output = s_min["output_data"]
        else:
            prev_output = data_file  # stand-in for whatever checkpoint resume_from names

        _resume_idx = _CHECKPOINTS.index(resume_from) if resume_from is not None else -1

        # 1. nvt_warmup — fixed, short 300 K settle (removes build artifacts)
        if _resume_idx < 0:
            s = _stage("nvt_warmup", "nvt", {
                "T_START": 300.0, "T_FINAL": 300.0, "T_DAMP": thermostat_damp_fs,
                "TIMESTEP": 0.5,
                "N_STEPS": int(warmup_steps) if warmup_steps else int(1.0e5 / dt_prod),
                "use_pppm": use_long_range and not use_trappe, "use_gpu": True,
                "use_shake": False, "init_velocity": 300.0,
            }, prev_output)
            stages.append(s)
            prev_output = s["output_data"]

        # 2. npt_densify — fixed compress ramp 1->max_press at 300 K. A ramp is one-shot:
        # LAMMPS interpolates P_START->P_FINAL monotonically over one `run`, so this is never
        # itself an adaptive/extendable stage (npt_densify_hold, below, is).
        # OPLS-AA: short-range Coulomb during compression (rapid box-shrink PPPM crash guard);
        # full PPPM resumes at npt_ff_activate. ff_base temporarily overridden so it wins.
        if _resume_idx < 1:
            saved_ff_base = ff_base
            ff_base = {**ff_base, "use_pppm": False} if use_opls else ff_base
            s = _stage("npt_densify", "npt_compress", {
                "T_START": 300.0, "T_FINAL": 300.0, "T_DAMP": thermostat_damp_fs,
                "P_START": 1.0, "P_FINAL": max_press, "P_DAMP": barostat_damp_fs,
                "TIMESTEP": 0.5,
                "N_STEPS": int(densify_ramp_steps) if densify_ramp_steps else steps_comp,
                "use_pppm": False, "use_gpu": True,
            }, prev_output)
            stages.append(s)
            ff_base = saved_ff_base  # restore PPPM for all subsequent stages
            prev_output = s["output_data"]

        # 3. npt_ff_activate — fixed decompress ramp max_press->press at 300 K, PPPM restored.
        if _resume_idx < 2:
            s = _stage("npt_ff_activate", "npt", {
                "T_START": 300.0, "T_FINAL": 300.0, "T_DAMP": thermostat_damp_fs,
                "P_START": max_press, "P_FINAL": press, "P_DAMP": barostat_damp_fs,
                "TIMESTEP": dt_prod,
                "N_STEPS": int(ff_activate_npt_steps) if ff_activate_npt_steps else int(1.0e5 / dt_prod),
                "use_pppm": use_long_range and not use_trappe, "use_gpu": True,
                "write_restart": True,
            }, prev_output)
            stages.append(s)
            prev_output = s["output_data"]

        # 4. npt_densify_hold — ADAPTIVE: constant 300 K/press NPT hold, gated (by the
        # orchestration layer, via check_block_gate.py) on density/non-bonded-energy
        # half-window stability and no monotonic volume trend. Generated here with only its
        # FIRST block; further blocks are extend_only=True restart-continuations of THIS
        # stage, capped at densify_steps_cap.
        if _resume_idx < 3:
            s = _stage("npt_densify_hold", "npt", {
                "T_START": 300.0, "T_FINAL": 300.0, "T_DAMP": thermostat_damp_fs,
                "P_START": press, "P_FINAL": press, "P_DAMP": barostat_damp_fs,
                "TIMESTEP": dt_prod,
                "N_STEPS": int(densify_check_every_steps) if densify_check_every_steps else steps_comp,
                "use_pppm": use_long_range and not use_trappe, "use_gpu": True,
                "write_restart": True,
            }, prev_output)
            stages.append(s)
            prev_output = s["output_data"]

        # 5/6. anneal_heat (fixed ramp) + anneal_hold (ADAPTIVE, first block only). One
        # continuous high-T hold rather than repeated heat/cool cycling — supported by this
        # repo's own cited literature (Wu2017, polymer_rules.json: single high-T equilibration
        # + monotonic cooling is statistically equivalent to repeated thermal cycling once the
        # melt is adequately equilibrated at T_max).
        if _resume_idx < 4:
            s = _stage("anneal_heat", "nvt", {
                "T_START": 300.0, "T_FINAL": max_temp, "T_DAMP": thermostat_damp_fs,
                "TIMESTEP": dt_prod,
                "N_STEPS": int(anneal_heat_steps) if anneal_heat_steps else steps_heat,
                "use_pppm": use_long_range and not use_trappe, "use_gpu": True,
                "write_restart": True,
            }, prev_output)
            stages.append(s)
            prev_output = s["output_data"]

            s = _stage("anneal_hold", "nvt", {
                "T_START": max_temp, "T_FINAL": max_temp, "T_DAMP": thermostat_damp_fs,
                "TIMESTEP": dt_prod,
                "N_STEPS": int(anneal_check_every_steps) if anneal_check_every_steps else steps_heat,
                "use_pppm": use_long_range and not use_trappe, "use_gpu": True,
                "write_restart": True,
            }, prev_output)
            stages.append(s)
            prev_output = s["output_data"]
        # resume_from == "anneal_hold": prev_output already = data_file, standing in
        # correctly for anneal_hold's own (already-run) output.

        # 7. npt_melt_ramp — fixed one-shot NPT ramp from the anneal ceiling down to the melt
        # hold. This is the FIRST barostatted stage after an NVT anneal_hold, so the cell still
        # carries the densified 300 K box and the barostat has to expand it to melt density
        # here. That expansion used to happen inside cool_block_01, ungated; now the adaptive
        # hold that follows gates it.
        if _resume_idx < 5:
            s = _stage("npt_melt_ramp", "npt", {
                "T_START": max_temp, "T_FINAL": melt_hold_T, "T_DAMP": thermostat_damp_fs,
                "P_START": press, "P_FINAL": press, "P_DAMP": barostat_damp_fs,
                "TIMESTEP": dt_prod,
                "N_STEPS": int(melt_ramp_steps) if melt_ramp_steps else steps_heat,
                "use_pppm": use_long_range and not use_trappe, "use_gpu": True,
                "write_restart": True,
            }, prev_output)
            stages.append(s)
            prev_output = s["output_data"]

        # 8. nvt_melt_hold — ADAPTIVE: NVT at melt_hold_T, FIXED volume (npt_melt_ramp's own
        # endpoint, which is a barostatted melt). This is where the expensive work happens:
        # chain relaxation, and the ideal-chain / decorrelation statistics that decide whether
        # this melt is equilibrated at all (MSID, C(t), Rg, torsion, MSD). It runs at fixed
        # volume because MSD and C(t) require it -- a barostatted trajectory affine-rescales
        # coordinates every step, contaminating cumulative displacement -- and because the
        # structural work is the long part, doing it here means the expensive stage is also the
        # clean one. Extending THIS is how an under-relaxed melt is fixed.
        if _resume_idx < 6:
            s = _stage("nvt_melt_hold", "nvt", {
                "T_START": melt_hold_T, "T_FINAL": melt_hold_T, "T_DAMP": thermostat_damp_fs,
                "TIMESTEP": dt_prod,
                "N_STEPS": int(nvt_melt_min_steps) if nvt_melt_min_steps
                           else int(5.0e6 / dt_prod),
                "use_pppm": use_long_range and not use_trappe, "use_gpu": True,
                "write_restart": True,
            }, prev_output)
            stages.append(s)
            prev_output = s["output_data"]

        # 9. npt_melt_hold — ADAPTIVE: NPT at melt_hold_T/press. TERMINAL, and THE GATED CELL.
        # Melt density is measured here, on a structure the NVT hold has already relaxed --
        # the ordering matters: measuring it before convergence would gate a density whose
        # chains had not yet moved. npt_melt_ramp set the box near melt density, the NVT hold
        # pinned it while the structure relaxed, and this stage lets the barostat correct the
        # residual. Its endpoint is the cell every downstream track starts from.
        s = _stage("npt_melt_hold", "npt", {
            "T_START": melt_hold_T, "T_FINAL": melt_hold_T, "T_DAMP": thermostat_damp_fs,
            "P_START": press, "P_FINAL": press, "P_DAMP": barostat_damp_fs,
            "TIMESTEP": dt_prod,
            "N_STEPS": int(melt_hold_min_steps) if melt_hold_min_steps
                       else int(2.0e6 / dt_prod),
            "use_pppm": use_long_range and not use_trappe, "use_gpu": True,
            "write_restart": True,
        }, prev_output)
        stages.append(s)
        prev_output = s["output_data"]

        final_stage = stages[-1]

        ret = {
            "status":     "success",
            "polymer":    polymer_name,
            "n_atoms":    n_atoms,
            "melt_hold_T": melt_hold_T,
            "max_temp":   max_temp,
            "n_stages":   len(stages),
            "engine":     engine,
            "stages":     stages,
            "run_order":  [s["name"] for s in stages],
            "npt_production_log": f"{final_stage['work_dir']}/{final_stage['params']['LOG_FILE']}",
            "npt_production_dir": final_stage["work_dir"],
            # ONE terminal cell now, named under both keys it is read by: npt_melt_hold is
            # both the gated melt (what the gate adjudicates, and the cooling stage's
            # contraction reference) and the handoff cell (what cooling and thermal start
            # from). Before the NVT/NPT reorder these were two different stages.
            "melt_data_path":       final_stage["output_data"],
            "melt_start_data_path": final_stage["output_data"],
            "preflight_warnings": vr["warnings"],
            "preflight_stats":    vr["stats"],
            "instructions": (
                f"Generated {len(stages)} staged scripts for {polymer_name} (engine={engine}).\n"
                "Execute in order using run_lammps_script().\n"
                "GPU is ON for all stages.\n"
                f"Pass engine='{engine}' to run_lammps_chain() so the launch flags match the decks.\n"
                f"npt_melt_hold is the GATED melt cell at {melt_hold_T} K — melt density and "
                "every thermo/geometry gate come from its own log and trajectory.\n"
                "nvt_melt_hold is the handoff cell: the cooling stage and the Tg staircase both "
                "start from its endpoint, whose box is npt_melt_hold's own.\n"
                "This chain does NOT cool. Call generate_cooling_workflow() with "
                "melt_start_data_path to descend to the assessment temperature.\n"
                "Adaptive stages (npt_densify_hold, anneal_hold, npt_melt_hold, nvt_melt_hold) "
                "are generated here with only their FIRST block — further steps come from "
                "extend_only=True restart-continuation calls (read_restart, appended log/dump), "
                "never from re-generating that stage with a larger N_STEPS.\n"
                "Submit stages as a chain using run_lammps_chain()."
            ),
        }
        if resume_from is not None:
            ret["resumed_from"] = resume_from
        return ret

    except Exception as e:
        logger.error(f"generate_equilibration_workflow failed: {e}")
        return {"status": "error", "error": str(e)}

@mcp.tool()
def generate_cooling_workflow(
    data_file: str,
    work_dir_base: str,
    velocity_seed: int,
    T_melt_hold_K: float,
    final_T_K: float,
    cool_block_dT_K: Optional[float],
    cool_block_hold_steps: Optional[int],
    cool_block_hold_cap_steps: Optional[int],
    stage8_min_steps: Optional[int],
    stage8_cap_steps: Optional[int],
    use_long_range: bool,
    use_pcff: bool,
    use_trappe: bool,
    use_opls: bool,
    engine: str,
    polymer_name: str = "polymer",
    press: float = 1.0,
    n_atoms: Optional[int] = None,
    params_file: str = "",
    thermostat_damp_fs: float = 100.0,
    barostat_damp_fs: float = 1000.0,
    extend_only: bool = False,
    restart_file: Optional[str] = None,
    base_stage_name: Optional[str] = None,
    extend_temp_K: Optional[float] = None,
    extend_ensemble: str = "npt",
    resume_from: Optional[str] = None,
) -> dict:
    """
    Cool an already-equilibrated melt to the assessment temperature and produce the gated
    assessment cell.

    Runs only when a property needs a cell at final_T_K -- a density there, or any mechanical
    property. A melt-only or Tg-only run never calls this: the Tg staircase descends from the
    same melt cell on its own, sampling as it goes.

    Protocol (fixed stage names, adaptive stages EXTEND via restart-continuation):
      cool_block_NN          - ADAPTIVE (one segment per block): NPT blockwise cooldown,
                               T_melt_hold_K -> final_T_K in cool_block_dT_K decrements. Each
                               block is generated with its FIRST hold only; further holds are
                               extend_only=True continuations of that SPECIFIC block, capped
                               at cool_block_hold_cap_steps.
      npt_final              - ADAPTIVE: NPT at final_T_K/press -- the assessment cell.
                               Density, Rg/Ree/RDF/dihedrals/MSID/P2/homogeneity/finite-size
                               and K_T are all computed from its own trajectory.

    There is deliberately NO fixed-volume NVT window here. One existed (nvt_kinetic_stability,
    3-20 ns depending on class) to give MSD/kinetic-trap and C(t) an uncontaminated trajectory
    -- but at the assessment temperature both are ADVISORY in every regime (a glass cannot
    satisfy them), so it fed nothing that could fail a run. Chain relaxation is adjudicated
    where it is physically attainable: the melt gate, on nvt_melt_hold. Removed 2026-09-02.

    The descent rate is the caller's business, not this tool's: cool_block_hold_steps is
    resolved upstream (stage_params.rate_matched_cool_block_hold_steps) so the cooldown runs at
    the same K/ns the Tg staircase uses. Two descents from one melt cell at two different rates
    would mean a run's density and its Tg describe glasses with different thermal histories.

    T_melt_hold_K == final_T_K is legal and emits ZERO cool blocks -- the melt IS the
    assessment cell, and only npt_final is generated.

    Args:
        data_file:      The melt-start cell: nvt_melt_hold's own output_data from
                        generate_equilibration_workflow (its melt_start_data_path).
        velocity_seed:  REQUIRED, non-null. Same value as the equilibration chain's -- one seed
                        per run. No stage here issues `velocity all create` (every one inherits
                        velocities from the incoming .data), but the generator still requires
                        it rather than silently drawing its own.
        T_melt_hold_K:  Where the melt was held; the top of the descent. Must be >= final_T_K.
        final_T_K:      The assessment temperature (300 K by default). cool_block's last block,
                        and npt_final both run here.
        cool_block_dT_K: REQUIRED. Nominal temperature decrement per cool_block. Null selects
                        25.0 K.
        cool_block_hold_steps: REQUIRED. Step count for each cool_block's first (base) hold.
                        Null selects int(2.0e5/dt_prod) (~200 ps at dt=1fs).
        cool_block_hold_cap_steps: REQUIRED. Ceiling on cumulative steps for any ONE
                        cool_block's restart-continuation extensions. Null selects 3x the base.
        stage8_min_steps / stage8_cap_steps: REQUIRED. First block and cumulative ceiling for
                        npt_final. Null selects int(5.0e5/dt_prod) / int(5.0e6/dt_prod).
        resume_from:    None (default, the whole descent) or "cool_block" (the entire blockwise
                        cooldown already ran -- start at npt_final, reading data_file as the
                        last block's own output).
                        To regenerate the cooldown itself with a different rate, invalidate this
                        stage rather than resuming: its input is the gated melt cell, so a fresh
                        call rebuilds the whole descent without touching the core chain.
        extend_temp_K:  REQUIRED when extend_only=True AND base_stage_name is a cool_block_NN
                        name -- that block's own hold temperature, which cannot be inferred
                        from the name alone. Ignored for npt_final, which holds at final_T_K.
        (Force-field, engine and damping args behave exactly as in
        generate_equilibration_workflow; the two chains share _ff_base_for so they cannot
        emit different styles for the same cell.)

    Returns:
        dict with stages / run_order / npt_production_log / npt_production_dir /
        assessment_data_path (npt_final's output_data) / instructions.
    """
    try:
        if not velocity_seed:
            return {"status": "error",
                    "error": "velocity_seed is required and must not be null — pass the same "
                             "seed the equilibration chain used for this run."}
        _CHECKPOINTS = ["cool_block"]
        if resume_from not in (None, *_CHECKPOINTS):
            return {"status": "error",
                    "error": f"resume_from={resume_from!r} is not supported — must be one of "
                             f"None, {', '.join(repr(c) for c in _CHECKPOINTS)}."}
        if resume_from is not None and extend_only:
            return {"status": "error",
                    "error": "resume_from and extend_only are mutually exclusive"}
        if extend_ensemble not in ("npt", "nvt"):
            return {"status": "error",
                    "error": f"extend_ensemble={extend_ensemble!r} must be 'npt' or 'nvt'"}
        if extend_only and (not restart_file or not base_stage_name):
            return {"status": "error",
                    "error": "extend_only=True requires both restart_file (the base stage's own "
                             ".restart output) and base_stage_name (the stage being continued)."}
        _STAGE_ENSEMBLE = {"npt_final": "npt"}
        if extend_only and base_stage_name:
            _required = ("npt" if base_stage_name.startswith("cool_block_")
                         else _STAGE_ENSEMBLE.get(base_stage_name))
            if _required is not None and extend_ensemble != _required:
                return {"status": "error",
                        "error": f"extend_ensemble={extend_ensemble!r} does not match "
                                 f"base_stage_name={base_stage_name!r}'s own ensemble "
                                 f"({_required!r}) — continuing an {_required} stage as "
                                 f"{extend_ensemble} would silently add or remove a barostat "
                                 "mid-trajectory."}
        if final_T_K > T_melt_hold_K:
            return {"status": "error",
                    "error": f"final_T_K={final_T_K} exceeds T_melt_hold_K={T_melt_hold_K} — "
                             "this chain only cools. A run that needs an assessment temperature "
                             "above the melt hold needs a higher melt hold, not a heating ramp "
                             "from an equilibrated melt."}
        if thermostat_damp_fs <= 0 or barostat_damp_fs <= 0:
            return {"status": "error", "error": "thermostat/barostat damping must be positive"}

        content = Path(data_file).read_text(encoding="utf-8")
        gen = ScriptGenerator(data_file=data_file)
        info = gen.parse_data_file(content=content)
        vr = gen.validate_data_file(content=content, h_type_ids=info.get("h_type_ids"))
        errors = vr["errors"]
        if params_file:
            errors = [e for e in errors if "Coeffs' section missing" not in e]
        if errors:
            return {"status": "error",
                    "error": "Pre-flight validation failed — workflow not generated",
                    "validation_errors": errors, "validation_warnings": vr["warnings"],
                    "validation_stats": vr["stats"]}

        n_atoms = n_atoms or info.get("n_atoms", 0)
        ff_base = _ff_base_for(use_pcff, use_trappe, use_opls, params_file, engine)
        dt_prod = 2.0 if use_trappe else 1.0
        _stage, _continue_stage = _make_stage_builders(
            gen, work_dir_base, ff_base, velocity_seed)

        stages = []

        if extend_only:
            if base_stage_name and base_stage_name.startswith("cool_block_"):
                ext_steps = cool_block_hold_steps
                if extend_temp_K is None:
                    return {"status": "error",
                            "error": "extend_only for a cool_block_NN stage requires "
                                     "extend_temp_K (that block's own hold temperature) — it "
                                     "cannot be inferred from base_stage_name alone."}
                ext_T = extend_temp_K
            elif base_stage_name == "npt_final":
                ext_steps, ext_T = stage8_min_steps, final_T_K
            else:
                return {"status": "error",
                        "error": f"base_stage_name={base_stage_name!r} is not a recognized "
                                 "adaptive stage of the cooling chain — must be a cool_block_NN "
                                 "name or npt_final."}
            ext_steps = int(ext_steps) if ext_steps else int(1.0e6 / dt_prod)
            template = "nvt" if extend_ensemble == "nvt" else "npt"
            params = {"T_START": ext_T, "T_FINAL": ext_T, "T_DAMP": thermostat_damp_fs,
                      "TIMESTEP": dt_prod, "N_STEPS": ext_steps,
                      "use_pppm": use_long_range and not use_trappe, "use_gpu": True}
            if extend_ensemble == "npt":
                params.update({"P_START": press, "P_FINAL": press,
                               "P_DAMP": barostat_damp_fs})
            sx = _continue_stage(base_stage_name, template, params, restart_file)
            stages.append(sx)
            return {
                "status": "success", "polymer": polymer_name, "n_atoms": n_atoms,
                "T_melt_hold_K": T_melt_hold_K, "final_T_K": final_T_K, "n_stages": 1,
                "engine": engine, "extend_only": True, "extend_ensemble": extend_ensemble,
                "stages": stages, "run_order": [sx["name"]],
                "assessment_data_path": None,
                "npt_production_log": f"{sx['work_dir']}/{sx['params']['LOG_FILE']}",
                "npt_production_dir": sx["work_dir"],
                "preflight_warnings": vr["warnings"], "preflight_stats": vr["stats"],
                "instructions": (
                    f"Extend-only: continued {base_stage_name} ({extend_ensemble.upper()}, "
                    f"{ext_steps} more steps) via read_restart from {restart_file}, appending "
                    f"onto {sx['work_dir']}/{sx['params']['LOG_FILE']} (engine={engine}). "
                    f"Submit with run_lammps_chain(engine='{engine}'); then re-run the gate on "
                    f"{sx['output_data']}."
                ),
            }

        _resume_idx = _CHECKPOINTS.index(resume_from) if resume_from is not None else -1
        prev_output = data_file

        # 1. cool_block_NN — the blockwise descent. Walking down from the melt hold in dT
        # decrements; the final block lands exactly on final_T_K however short it is.
        if _resume_idx < 0:
            dT = float(cool_block_dT_K) if cool_block_dT_K else 25.0
            base_hold = (int(cool_block_hold_steps) if cool_block_hold_steps
                         else int(2.0e5 / dt_prod))
            waypoints = []
            t = T_melt_hold_K
            while t > final_T_K + 1e-6:
                waypoints.append(t)
                t -= dT
            waypoints.append(final_T_K)
            for block_idx, (w_start, w_end) in enumerate(
                    zip(waypoints[:-1], waypoints[1:]), start=1):
                s = _stage(f"cool_block_{block_idx:02d}", "npt", {
                    "T_START": w_start, "T_FINAL": w_end, "T_DAMP": thermostat_damp_fs,
                    "P_START": press, "P_FINAL": press, "P_DAMP": barostat_damp_fs,
                    "TIMESTEP": dt_prod, "N_STEPS": base_hold,
                    "use_pppm": use_long_range and not use_trappe, "use_gpu": True,
                    "write_restart": True,
                }, prev_output)
                stages.append(s)
                prev_output = s["output_data"]

        # 2. npt_final — ADAPTIVE, the assessment cell at final_T_K/press.
        s = _stage("npt_final", "npt", {
            "T_START": final_T_K, "T_FINAL": final_T_K, "T_DAMP": thermostat_damp_fs,
            "P_START": press, "P_FINAL": press, "P_DAMP": barostat_damp_fs,
            "TIMESTEP": dt_prod,
            "N_STEPS": int(stage8_min_steps) if stage8_min_steps else int(5.0e5 / dt_prod),
            "use_pppm": use_long_range and not use_trappe, "use_gpu": True,
            "write_restart": True,
        }, prev_output)
        stages.append(s)

        final_stage = stages[-1]
        n_blocks = sum(1 for st in stages if st["name"].startswith("cool_block_"))
        ret = {
            "status": "success", "polymer": polymer_name, "n_atoms": n_atoms,
            "T_melt_hold_K": T_melt_hold_K, "final_T_K": final_T_K,
            "n_cool_blocks": n_blocks, "n_stages": len(stages), "engine": engine,
            "stages": stages, "run_order": [st["name"] for st in stages],
            "npt_production_log": f"{final_stage['work_dir']}/{final_stage['params']['LOG_FILE']}",
            "npt_production_dir": final_stage["work_dir"],
            "assessment_data_path": final_stage["output_data"],
            "preflight_warnings": vr["warnings"], "preflight_stats": vr["stats"],
            "instructions": (
                f"Generated {len(stages)} staged scripts for {polymer_name} (engine={engine}): "
                f"{n_blocks} cool blocks from {T_melt_hold_K} K to {final_T_K} K, then "
                "npt_final.\n"
                f"Pass engine='{engine}' to run_lammps_chain() so the launch flags match.\n"
                "npt_final is the assessment cell — compute density/Rg/Ree/RDF/dihedrals/MSID/"
                "K_T from its own trajectory.\n"
                "Adaptive stages (each cool_block_NN and npt_final) are "
                "generated with only their FIRST block — further steps come from "
                "extend_only=True restart-continuation calls, never from re-generating with a "
                "larger N_STEPS.\n"
                "Submit stages as a chain using run_lammps_chain()."
            ),
        }
        if resume_from is not None:
            ret["resumed_from"] = resume_from
        return ret

    except Exception as e:
        logger.error(f"generate_cooling_workflow failed: {e}")
        return {"status": "error", "error": str(e)}



# ─── Analysis tools (Tg, density, convergence, bulk modulus) ─────────────────
#
# These tools run Python analysis scripts locally and track their
# progress through run_manager — poll with get_run_status() / get_run_output().

def _parse_json_from_stdout(stdout: str, stderr: str) -> dict:
    """Scan stdout bottom-up for valid JSON — a single line (compact json.dumps) or a
    pretty-printed multi-line block (json.dumps(..., indent=N), e.g. assess_cooling_contraction.py).
    Tries every '{' from the last occurrence backward, parsing from there to end-of-string, so a
    pretty-printed block at the end of stdout (the common case) is found even though its opening
    line alone isn't valid JSON. Returns error dict on failure."""
    text = stdout.strip()
    idx = text.rfind("{")
    while idx != -1:
        candidate = text[idx:]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            idx = text.rfind("{", 0, idx)
    return {"status": "failed", "error": "No JSON found in stdout",
            "stdout": stdout, "stderr": stderr}


def _require_output_dir(output_dir, tool: str, legacy: str):
    """Every extraction tool used to fall back to a subdirectory of its own input file when
    output_dir came in null. generate_run_summary reads only the flat output_dir, so those runs
    wrote their JSON somewhere nothing ever looks (data/cis-PBD1/raw/bulk_analysis/bulk_modulus.json).
    A null is now an error: the caller has the run's raw/ path and must pass it."""
    if not output_dir:
        raise ValueError(
            f"{tool}: output_dir is required (it used to default to {legacy}, which "
            f"generate_run_summary never reads — the JSON was written and silently lost)."
        )
    # The analysis CLIs run with cwd=LAMBDA_WORKDIR, so a relative output_dir resolves under
    # that operator-specific directory instead of the run's raw/ dir — the JSON lands outside
    # the workspace and only a filesystem-wide find recovers it. Same failure as a null, so
    # it is the same error.
    if not os.path.isabs(output_dir):
        raise ValueError(
            f"{tool}: output_dir must be an absolute path (got {output_dir!r}); relative "
            f"paths resolve against LAMBDA_WORKDIR ({LAMBDA_WORKDIR}), not the run directory."
        )


def _save_gate_verdict(out_dir, result: dict, output_name: str = "equilibration.json") -> dict:
    """Persist the gate verdict under the "gate" key of <out_dir>/<output_name>.

    The decision that authorises (or blocks) every downstream property extraction used to exist
    only in the calling worker's reply, leaving nothing to audit — unlike every other stage,
    which leaves a JSON in raw/. Failures are written too: a probe that blew up is the case most
    worth having a record of. The file is shared with check_equilibration_comprehensive
    (top-level thermo/chain/spatial keys) and extract_equilibrated_density ("density" key) —
    read-merge-write so this producer's own section replaces wholesale without clobbering theirs.

    output_name selects which cell's file this is: equilibration.json for the melt gate,
    cooling.json for the assessment gate. All three producers must be given the SAME name for
    one cell, or the gate verdict lands in a different file from the measurements it adjudicates.
    """
    if not out_dir:
        return result
    try:
        verdict_path = Path(out_dir) / (output_name or "equilibration.json")
        verdict_path.parent.mkdir(parents=True, exist_ok=True)
        merged = {}
        if verdict_path.exists():
            try:
                merged = json.loads(verdict_path.read_text())
            except (OSError, json.JSONDecodeError):
                merged = {}
        merged["gate"] = result
        verdict_path.write_text(json.dumps(merged, indent=2, default=str))
        result["saved_to"] = str(verdict_path)
    except Exception as e:  # never let an audit-trail write mask the verdict itself
        logger.error(f"could not save equilibration gate verdict: {e}")
        result["save_error"] = str(e)
    return result


def _analysis_run_background(run_id: str, func, kwargs: dict):
    """Background thread: runs an analysis helper function and updates run_manager."""
    try:
        run_manager.start(run_id)
        result = func(**kwargs)
        run_manager.complete(run_id, result)
        _write_sentinel(run_id, "completed")
    except Exception as e:
        logger.error(f"Analysis run {run_id} failed: {e}")
        run_manager.fail(run_id, str(e))
        _write_sentinel(run_id, "failed", {"error": str(e)[:500]})


# ── Tool: unwrap_coordinates ─────────────────────────────────────────────────

def _run_unwrap_coordinates(dump_file: str, output_file: str) -> dict:
    """Background worker — runs unwrap_dump.py via CLI."""

    parts = [f"python {MDA_SCRIPTS_DIR}/unwrap_dump.py"]
    parts.append(f"--dump_file {dump_file}")
    parts.append(f"--output_file {output_file}")

    command = " ".join(parts)
    logger.info(f"Running unwrap via CLI: {command}")

    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=36000)

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def unwrap_coordinates(
    dump_file: str,
    output_file: Optional[str] = None,
) -> dict:
    """
    Write a new LAMMPS dump file with fully unwrapped coordinates.

    Reads every frame of dump_file, unwraps coordinates using image flags
    (x += ix*Lx), and writes a new dump with zeroed ix/iy/iz. All other
    columns are preserved. Requires columns: x y z ix iy iz.

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        dump_file:   Full path to the wrapped LAMMPS dump file.
        output_file: Destination path for the unwrapped dump.
                     Defaults to <original_stem>_unwrapped.dump in the same directory.

    Returns:
        dict with run_id.  Completed result includes output_file,
        frames_written, natoms, size_bytes.
    """
    if output_file is None:
        stem = dump_file.replace(".dump", "").rstrip(".")
        output_file = stem + "_unwrapped.dump"

    run_id = run_manager.create("unwrap_coordinates", {"dump_file": dump_file, "output_file": output_file})
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_unwrap_coordinates, dict(
            dump_file   = dump_file,
            output_file = output_file,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":      "submitted",
        "run_id":      run_id,
        "run_type":    "unwrap_coordinates",
        "dump_file":   dump_file,
        "output_file": output_file,
        "message":     "Poll with get_run_status(run_id)",
    }


# ── Tool: extract_end_to_end_vectors ─────────────────────────────────────────

def _run_extract_end_to_end(
    dump_file: str,
    data_file: Optional[str],
    backbone_types: Optional[list],
    num_chains: Optional[int],
    chain_ids: Optional[list],
    skip_frames: int,
    max_frames: Optional[int],
    output_dir: str,
    graphs_dir: Optional[str] = None,
    atom_style: str = "id resid type charge x y z",
) -> dict:
    """Background worker — runs mda_end_to_end.py via CLI."""

    parts = [f"python {MDA_SCRIPTS_DIR}/mda_end_to_end.py"]
    parts.append(f"--data_file {data_file}")
    parts.append(f"--dump_file {dump_file}")
    if backbone_types:
        parts.append(f"--backbone_types {' '.join(str(t) for t in backbone_types)}")
    if num_chains is not None:
        parts.append(f"--num_chains {num_chains}")
    if chain_ids is not None:
        parts.append(f"--chain_ids {' '.join(str(c) for c in chain_ids)}")
    parts.append(f"--skip_frames {skip_frames}")
    if max_frames is not None:
        parts.append(f"--max_frames {max_frames}")
    parts.append(f"--output_dir {output_dir}")
    if graphs_dir:
        parts.append(f"--graphs_dir {graphs_dir}")
    parts.append(f'--atom_style "{atom_style}"')

    command = " ".join(parts)
    logger.info(f"Running E2E via MDAnalysis: {command}")

    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=36000)

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def extract_end_to_end_vectors(
    dump_file: str,
    data_file: str,
    backbone_types: list,
    num_chains: Optional[int] = None,
    chain_ids: Optional[list] = None,
    skip_frames: int = 0,
    max_frames: Optional[int] = None,
    output_dir: Optional[str] = None,
    graphs_dir: Optional[str] = None,
    atom_style: str = "id resid type charge x y z",
) -> dict:
    """
    Extract end-to-end vectors and distances from a polymer simulation trajectory.

    Uses MDAnalysis with sort_backbone() for robust backbone-aware terminal
    atom identification via bond connectivity from the topology file.
    Coordinates are unwrapped using MDAnalysis transformations.

    Terminal atom identification:
        MDAnalysis reads bonds from the LAMMPS data file, then
        sort_backbone() traces the backbone bond graph to order atoms
        from one end to the other.  The first and last atoms of the
        sorted backbone are the chain termini.  This correctly handles
        all-atom models, hydrogen mass repartitioning, and polymers
        with heavy-atom side groups.

    backbone_types should be the LAMMPS integer atom type IDs corresponding
    to backbone atoms.  Determine these from the Masses section of the data
    file.  For example, for PE with GAFF types (hc=1, c3=2), use [2].
    For PEO with types (hc=1, c3=2, os=3), use [2, 3].

    Output files written to output_dir:
        end_to_end_vectors.csv   — frame, timestep, chain, rx, ry, rz, distance
        end_to_end_summary.json  — per-chain mean/std R and R², overall averages,
                                   backbone_types used, and terminal atom IDs

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        dump_file:      Full path to LAMMPS dump file.
        data_file:      Path to LAMMPS .data file (required for topology/bonds).
        backbone_types: List of LAMMPS atom type IDs forming the polymer backbone
                        (e.g. [2] for PE where type 2 is c3 carbon).
        num_chains:     Chain count; auto-detected from resids if None.
        chain_ids:      Subset of chain resids to analyse; all chains if None.
        skip_frames:    Initial frames to skip (burn-in).
        max_frames:     Cap on frames to analyse after skip.
        output_dir:     Output directory. Required — the run's raw/ dir.
        atom_style:     LAMMPS atom_style column order for the data file.

    Returns:
        dict with run_id.  Completed result includes per_chain stats and csv_file path.
    """
    _require_output_dir(output_dir, "extract_end_to_end_vectors", "<dump_file dir>/analysis")

    run_id = run_manager.create("extract_end_to_end_vectors", {"dump_file": dump_file, "output_dir": output_dir})
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_extract_end_to_end, dict(
            dump_file      = dump_file,
            data_file      = data_file,
            backbone_types = backbone_types,
            num_chains     = num_chains,
            chain_ids      = chain_ids,
            skip_frames    = skip_frames,
            max_frames     = max_frames,
            output_dir     = output_dir,
            graphs_dir     = graphs_dir,
            atom_style     = atom_style,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":     "submitted",
        "run_id":     run_id,
        "run_type":   "extract_end_to_end_vectors",
        "dump_file":  dump_file,
        "output_dir": output_dir,
        "message":    "Poll with get_run_status(run_id)",
    }


# ── Tool: calculate_rdf ───────────────────────────────────────────────────────

def _run_calculate_rdf(
    dump_file: str,
    data_file: str,
    atom_type_pairs: Optional[list],
    rmax: float,
    nbins: int,
    skip_frames: int,
    max_frames: Optional[int],
    output_dir: str,
    graphs_dir: Optional[str] = None,
    atom_style: str = "id resid type charge x y z",
) -> dict:
    """Background worker — runs mda_rdf.py via CLI."""

    import json as _json
    parts = [f"python {MDA_SCRIPTS_DIR}/mda_rdf.py"]
    parts.append(f"--data_file {data_file}")
    parts.append(f"--dump_file {dump_file}")
    if atom_type_pairs is not None:
        parts.append(f"--atom_type_pairs '{_json.dumps(atom_type_pairs)}'")
    parts.append(f"--rmax {rmax}")
    parts.append(f"--nbins {nbins}")
    parts.append(f"--skip_frames {skip_frames}")
    if max_frames is not None:
        parts.append(f"--max_frames {max_frames}")
    parts.append(f"--output_dir {output_dir}")
    if graphs_dir:
        parts.append(f"--graphs_dir {graphs_dir}")
    parts.append(f'--atom_style "{atom_style}"')

    command = " ".join(parts)
    logger.info(f"Running RDF via MDAnalysis: {command}")

    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=36000)

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def calculate_rdf(
    dump_file: str,
    data_file: str,
    atom_type_pairs: Optional[list] = None,
    rmax: float = 15.0,
    nbins: int = 150,
    skip_frames: int = 0,
    max_frames: Optional[int] = None,
    output_dir: Optional[str] = None,
    graphs_dir: Optional[str] = None,
    atom_style: str = "id resid type charge x y z",
) -> dict:
    """
    Calculate radial distribution function g(r) from a simulation trajectory.

    Output files written to output_dir:
        rdf_t<T1>-t<T2>.csv   — columns: r, g_r  (one file per pair)
        rdf_summary.json       — metadata and file paths

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        dump_file:        Full path to LAMMPS dump file.
        data_file:        Full path to LAMMPS .data file (topology).
        atom_type_pairs:  List of [type1, type2] pairs, e.g. [[1,1],[2,2],[1,2]].
                          All type pairs computed if None.
        rmax:             Maximum distance in Å (default 15.0).
        nbins:            Histogram bin count (default 150).
        skip_frames:      Frames to skip at the start.
        max_frames:       Cap on frames after skip.
        output_dir:       Output directory. Required — the run's raw/ dir.
        atom_style:       LAMMPS atom_style column order for the data file.

    Returns:
        dict with run_id.  Completed result includes rdf_files paths and
        pairs_computed list.
    """
    _require_output_dir(output_dir, "calculate_rdf", "<dump_file dir>/analysis")

    run_id = run_manager.create("calculate_rdf", {"dump_file": dump_file, "output_dir": output_dir})
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_calculate_rdf, dict(
            dump_file       = dump_file,
            data_file       = data_file,
            atom_type_pairs = atom_type_pairs,
            rmax            = rmax,
            nbins           = nbins,
            skip_frames     = skip_frames,
            max_frames      = max_frames,
            output_dir      = output_dir,
            graphs_dir      = graphs_dir,
            atom_style      = atom_style,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":     "submitted",
        "run_id":     run_id,
        "run_type":   "calculate_rdf",
        "dump_file":  dump_file,
        "output_dir": output_dir,
        "message":    "Poll with get_run_status(run_id)",
    }


# ── Tool: extract_thermal ─────────────────────────────────────────────────────

def _run_extract_thermal(
    log_file: str,
    output_dir: str,
    initial_tg_guess: Optional[float],
    equilibration_fraction: float,
    temp_col: str,
    density_col: str,
    enthalpy_col: str = "Enthalpy",
    graphs_dir: Optional[str] = None,
    per_t_dump_file: Optional[str] = None,
    tg_data_file: Optional[str] = None,
    backbone_types: Optional[List[str]] = None,
    method_gap_exempt: bool = False,
    fit_t_max_K: Optional[float] = None,
) -> dict:
    """Background worker — runs extract_thermal.py via CLI."""

    parts = [f"python {MDA_SCRIPTS_DIR}/extract_thermal.py"]
    parts.append(f"--log_file {log_file}")
    parts.append(f"--output_dir {output_dir}")
    if initial_tg_guess is not None:
        parts.append(f"--initial_tg_guess {initial_tg_guess}")
    parts.append(f"--equilibration_fraction {equilibration_fraction}")
    parts.append(f"--temp_col {temp_col}")
    parts.append(f"--density_col {density_col}")
    parts.append(f"--enthalpy_col {enthalpy_col}")
    if graphs_dir:
        parts.append(f"--graphs_dir {graphs_dir}")
    if per_t_dump_file:
        parts.append(f"--per_t_dump_file {per_t_dump_file}")
    if tg_data_file:
        parts.append(f"--tg_data_file {tg_data_file}")
    if backbone_types:
        parts.append(f"--backbone_types {' '.join(str(t) for t in backbone_types)}")
    if method_gap_exempt:
        parts.append("--method_gap_exempt")
    if fit_t_max_K is not None:
        parts.append(f"--fit_t_max_K {fit_t_max_K}")

    command = " ".join(parts)
    logger.info(f"Running thermal extraction via CLI: {command}")

    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=36000)

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    result = _parse_json_from_stdout(stdout, stderr)
    r2 = result.get("r_squared", 0) or 0
    n_bins = result.get("n_temperature_bins", 0) or 0
    if n_bins < 4 or r2 < 0.80:
        result["recovery_hint"] = (
            "ABORT: R² < 0.80 or < 4 temperature bins — "
            "the sweep starts at the melt hold, so widen it by raising T_melt_hold_K (via md_tg_ceiling_K) or lowering tg_t_low_K."
        )
    elif r2 < 0.90:
        result["recovery_hint"] = (
            "BORDERLINE: R² 0.80–0.90 — "
            "re-spawn tg-sweep-worker with --tg_t_step_K halved."
        )
    elif r2 < 0.95:
        result["recovery_hint"] = "ACCEPTABLE: R² 0.90–0.95 — report Tg with caveat."
    else:
        result["recovery_hint"] = "EXCELLENT: R² ≥ 0.95 — report Tg with confidence."
    return result


@mcp.tool()
def extract_thermal(
    log_file: str,
    output_dir: str,
    graphs_dir: str,
    tg_data_file: Optional[str],
    per_t_dump_file: Optional[str],
    method_gap_exempt: bool,
    backbone_types: Optional[List[str]],
    initial_tg_guess: Optional[float] = None,
    equilibration_fraction: float = 0.5,
    temp_col: str = "Temp",
    density_col: str = "Density",
    enthalpy_col: str = "Enthalpy",
    fit_t_max_K: Optional[float] = None,
) -> dict:
    """
    Extract thermal properties (Tg, CTE, ΔCp) from a LAMMPS MD temperature-sweep log.

    Methodology (v5 — June 2026):
      Data: Plateau detection (|ΔT|>15 K jump = new set-point) with
      equilibration burn-in, producing one clean (T, ρ, H) point per plateau.
      Plateaus with density drift > 1% are excluded from fitting: ≥20-row
      plateaus require drift > 1% AND p < 0.01; 3–19-row plateaus use
      magnitude-only (p-value unreliable for short autocorrelated series).
      Log-based relaxation: each plateau gets an effective-sample count (n_eff)
      via integrated density ACF.  n_eff < 5 raises relax_warning (soft flag).
      Fitting: Bilinear curve_fit — two OLS lines simultaneously fit to the
      glassy and rubbery regions; Tg = line intersection.  Physics constraints
      enforced (both slopes negative, rubbery steeper than glassy).  This is
      the standard method used in polymer MD literature (Afzal 2021, Hayashi/
      RadonPy 2022, Klajmon 2023, NkepsuMbitou 2025).
      CTE: α = -(1/ρ) dρ/dT = -a_branch / ρ_mean_branch from the density fit.
      ΔCp: bilinear fit of H(T) from the Enthalpy thermo column (kcal/mol);
           normalised by system mass parsed from tg_data_file.  Skipped if
           Enthalpy column absent or tg_data_file not provided.
      Structural (optional): if per_t_dump_file + tg_data_file are given,
      computes per-T Rg and P2 nematic order.

    References:
      Afzal et al., ACS Appl. Polym. Mater. 3 (2021) 6213–6228
      Hayashi et al., npj Comput. Mater. 8 (2022) 222
      Patrone et al., Polymer 87 (2016) 246–259

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        log_file:               Full path to the LAMMPS log file.
        output_dir:             Output directory.
        initial_tg_guess:       Initial Tg hint for curve_fit optimizer (K).
        equilibration_fraction: Fraction of steps at each T used for density
                                averaging (0.5 = last 50 %).
        temp_col:               Temperature column name (default: 'Temp').
        density_col:            Density column name (default: 'Density').
        enthalpy_col:           Enthalpy column name (default: 'Enthalpy').
                                Used for ΔCp calculation.
        per_t_dump_file:        REQUIRED, may be null. Path to the per-T structural dump
                                written by the Tg staircase (one frame per T step, cooling
                                order). With tg_data_file it enables the dump-based
                                structural block; null skips it.
        tg_data_file:           REQUIRED, may be null. LAMMPS .data file used as input to
                                the Tg sweep (topology/masses). Null silently skips ΔCp
                                entirely — pass the null deliberately, never by omission.
        method_gap_exempt:      REQUIRED. True records a >20 K primary-vs-alternative Tg gap
                                as a reason without forcing TG_REVIEW (classes with
                                documented highest-rate degeneracy). Pass the false too.
        backbone_types:         REQUIRED. Backbone atom type IDs (list of strings/ints).
                                Null is legal and leaves P2 null at every temperature —
                                structural_p2_status records that it was not computable.

    Returns:
        dict with run_id.  Result includes Tg_K, Tg_alternative_K,
        r_squared, fit_quality, fit_method, binning_method,
        cte_glassy_per_K, cte_rubbery_per_K (always when fit succeeds),
        dCp_J_per_g_K, dCp_status (when Enthalpy column + tg_data_file present),
        n_plateaus_skipped_drift, n_plateaus_low_n_eff,
        relaxation_metrics (per-plateau n_eff + tau_int),
        fit_params, n_temperature_bins, temp_range_K, bins_csv, summary_json.
        When per_t_dump_file is provided: also Tg_dynamic_K (Rg-kink),
        n_T_steps_p2_flag, n_T_steps_rg_cv_flag, structural_metrics_per_T.
    """
    _require_output_dir(output_dir, "extract_thermal", "<log_file dir>/tg_analysis")

    run_id = run_manager.create("extract_thermal", {"log_file": log_file, "output_dir": output_dir})
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_extract_thermal, dict(
            log_file               = log_file,
            output_dir             = output_dir,
            initial_tg_guess       = initial_tg_guess,
            equilibration_fraction = equilibration_fraction,
            temp_col               = temp_col,
            density_col            = density_col,
            enthalpy_col           = enthalpy_col,
            graphs_dir             = graphs_dir,
            per_t_dump_file        = per_t_dump_file,
            tg_data_file           = tg_data_file,
            backbone_types         = backbone_types,
                    method_gap_exempt   = method_gap_exempt,
            fit_t_max_K            = fit_t_max_K,
)),
        daemon=True,
    )
    t.start()
    return {
        "status":     "submitted",
        "run_id":     run_id,
        "run_type":   "extract_thermal",
        "log_file":   log_file,
        "output_dir": output_dir,
        "message":    "Poll with get_run_status(run_id)",
    }


# ── Tool: check_equilibration_comprehensive ───────────────────────────────────

def _run_check_equilibration_comprehensive(
    log_file: str,
    dump_file: str,
    data_file: str,
    backbone_types: list,
    output_dir: str,
    skip_frames: int,
    timestep_fs: float,
    dump_every: int,
    n_backbone_bonds: Optional[int],
    bond_length_A: float,
    eq_fraction: float,
    drift_threshold_pct: float,
    drift_pvalue: float,
    block_count: int,
    temp_col: str,
    density_col: str,
    energy_col: str,
    atom_style: str,
    graphs_dir: Optional[str] = None,
    ct_min_decay: Optional[float] = None,
    cv_signal_max: float = 0.11,
    cutoff_A: Optional[float] = None,
    struct_dump_file: Optional[str] = None,
    struct_data_file: Optional[str] = None,
    output_name: str = "equilibration.json",
) -> dict:
    """Background worker — runs check_equilibration_comprehensive.py via CLI."""
    bt_str = " ".join(str(t) for t in backbone_types)
    parts = [
        f"python {MDA_SCRIPTS_DIR}/check_equilibration_comprehensive.py",
        f"--log_file {log_file}",
        f"--dump_file {dump_file}",
        f"--data_file {data_file}",
        f"--backbone_types {bt_str}",
        f"--output_dir {output_dir}",
        f"--skip_frames {skip_frames}",
        f"--timestep_fs {timestep_fs}",
        f"--dump_every {dump_every}",
        f"--bond_length_A {bond_length_A}",
        f"--eq_fraction {eq_fraction}",
        f"--drift_threshold_pct {drift_threshold_pct}",
        f"--drift_pvalue {drift_pvalue}",
        f"--block_count {block_count}",
        f"--temp_col {temp_col}",
        f"--density_col {density_col}",
        f"--energy_col {energy_col}",
        f'--atom_style "{atom_style}"',
        f"--cv_signal_max {cv_signal_max}",
        f"--output_name {output_name}",
    ]
    if cutoff_A is not None:
        parts.append(f"--cutoff_A {cutoff_A}")
    if n_backbone_bonds is not None:
        parts.append(f"--n_backbone_bonds {n_backbone_bonds}")
    if graphs_dir:
        parts.append(f"--graphs_dir {graphs_dir}")
    if ct_min_decay is not None:
        parts.append(f"--ct_min_decay {ct_min_decay}")
    if struct_dump_file is not None:
        parts.append(f"--struct_dump_file {struct_dump_file}")
    if struct_data_file is not None:
        parts.append(f"--struct_data_file {struct_data_file}")

    command = " ".join(parts)
    logger.info(f"Running comprehensive equilibration check: {command}")
    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=72000)
    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    result = _parse_json_from_stdout(stdout, stderr)
    overall_pass = result.get("overall_pass", False)
    if overall_pass:
        result["recovery_hint"] = "PASS → proceed to Tg sweep (step 10)."
    else:
        result["recovery_hint"] = (
            "EXTEND → extend final NPT by 1 ns, re-run check; max 2 extensions. "
            "If density ≥ 110% of experimental after extensions, re-spawn build with lower density_initial. "
            "ESCALATE (after 2 failed extensions) → re-run --stage build with "
            "--density_initial = class_default − 0.05 g/cm³. "
            "C(t) gate: pass ct_min_decay=0.25 for melt/NVT log; omit for 300K NPT and rubbery."
        )
    return result


@mcp.tool()
def check_equilibration_comprehensive(
    log_file: str,
    dump_file: str,
    data_file: str,
    backbone_types: list,
    output_dir: str,
    graphs_dir: str,
    timestep_fs: float,
    ct_min_decay: Optional[float],
    cutoff_A: Optional[float],
    skip_frames: int = 50,
    dump_every: int = 1000,
    n_backbone_bonds: Optional[int] = None,
    bond_length_A: float = 1.54,
    eq_fraction: float = 0.5,
    drift_threshold_pct: float = 1.0,
    drift_pvalue: float = 0.01,
    block_count: int = 10,
    temp_col: str = "Temp",
    density_col: str = "Density",
    energy_col: str = "TotEng",
    atom_style: str = "id resid type charge x y z",
    cv_signal_max: float = 0.11,
    struct_dump_file: Optional[str] = None,
    struct_data_file: Optional[str] = None,
    output_name: str = "equilibration.json",
) -> dict:
    """
    Comprehensive polymer equilibration validator — thermo + structural checks in
    a single call, single overall_pass verdict, auto-generated D-05 markdown block.

    Hard gates (block overall_pass=True):
      A. Density drift (regression p-value + magnitude)
      B. Energy drift (aggregate TotEng, plus each present bond/angle/dihedral/vdW/coul/kspace
         term independently -- a canceling drift between terms can otherwise hide inside a flat
         TotEng; mirrors RadonPy's own per-term check_eq() gates)
      C. Density block-SEM < 1% of mean (Flyvbjerg-Petersen)
      D. Energy block-SEM < 1% of mean
      E. Rg CV across chains < 30%  (unequal conformation flag)
      F. P2 nematic order < 0.10    (residual backbone alignment)
      G. Poisson-corrected density homogeneity CV < cv_signal_max (default 0.11; the raw
         voxel CV's noise floor moves with cell size, so the signal CV is gated instead).
      H. Finite size (spatial.finite_size), when cutoff_A is supplied: minimum image
         L >= 2*cutoff_A (below it the pair potential itself is wrong) and chain
         self-imaging L >= 2*Rg. L >= R_ee is reported but advisory.

    Soft warnings (reported but never block unless ct_min_decay supplied):
      - τ_eff / T_traj > 10%  (trajectory too short for good statistics)
      - C∞ outside broad expected range
      - MSID(n) power-law slope deviation > 20% from Gaussian (slope=1)
      - C(t) end-to-end autocorrelation not fully decayed (τ_relax reported);
        promoted to hard gate H when ct_min_decay is provided (use 0.25 for melt)
      - MSD kinetic-trap  (MSD_max < Rg² — expected below Tg)

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        log_file:            LAMMPS log file (thermo output, e.g. 06_nvt_production.log).
        dump_file:           LAMMPS dump trajectory carrying the ensemble-sensitive checks
                             (MSD/kinetic-trap, C(t)) — must be a fixed-volume NVT window
                             (e.g. nvt_melt_hold.dump); a barostatted trajectory
                             affine-scales coordinates every step and contaminates cumulative
                             CoM displacement.
        data_file:           LAMMPS .data topology file paired with dump_file.
        struct_dump_file:    Optional second trajectory carrying the ensemble-INsensitive
                             per-frame geometry checks (Rg, MSID, R_ee, torsion, P2, density
                             homogeneity, finite-size) instead of dump_file — normally
                             npt_final's own dump, the actual equilibrated parent state. Omit
                             to fall back to dump_file for everything. Must be paired with
                             struct_data_file.
        struct_data_file:    LAMMPS .data topology file paired with struct_dump_file. Required
                             iff struct_dump_file is given.
        backbone_types:      List of LAMMPS atom type IDs that form the backbone.
                             Determine from inspect_data_file() — do not guess.
        output_dir:          Output directory. Required — the run's raw/ dir.
        timestep_fs:         REQUIRED. MD timestep in femtoseconds — must match the deck. The
                             dump time axis is dt_ps = timestep_fs * dump_every / 1000, and
                             unlike dump_every this is NOT auto-detected, so a dt=2 fs deck left
                             on 1.0 reports tau_relax_ps and MSD at half their real values.
        ct_min_decay:        REQUIRED, may be null. Promotes the C(t) end-to-end decay warning to
                             a hard gate (use 0.25 for melt). Null leaves it advisory — pass the
                             null explicitly; omission is a schema error, not a default.
        cutoff_A:            REQUIRED, may be null. Arms the minimum-image half of the finite-size
                             gate (L >= 2*cutoff_A). Null evaluates chain self-imaging only.
        skip_frames:         Frames to skip at start of dump (production window start).
        dump_every:          Dump frequency in steps (auto-detected from dump header if possible).
        n_backbone_bonds:    Backbone bonds per chain (DP − 1); enables C∞ calculation.
        bond_length_A:       Backbone bond length in Å for C∞ (default: 1.54 C-C).
        eq_fraction:         Fraction of thermo rows used as production window.
        drift_threshold_pct: Max allowed thermo drift as % of mean.
        drift_pvalue:        p-value threshold for drift significance.
        block_count:         Blocks for Flyvbjerg-Petersen block averaging.
        temp_col:            Temperature column name in thermo output.
        density_col:         Density column name.
        energy_col:          Total energy column name.
        atom_style:          LAMMPS dump atom_style columns.
        ct_min_decay:        Optional. Minimum C(t) decay fraction (0–1) to pass a
                             hard gate. Use 0.25 for melt equilibration checks (flags
                             kinetic traps where τ_relax >> T_traj). Omit for
                             soft-warning-only behaviour (backwards compatible default).
                             Do NOT set for production checks below Tg — C(t) never
                             decays in the glassy state.

    Returns:
        dict with run_id. When completed, result includes:
            overall_pass      — bool: True iff all hard gates pass
            thermo            — density/energy drift and block-SEM results
            chain             — rg (Rg CV, C∞), msid (Gaussian slope), ct (C(t) autocorr), msd
            spatial           — p2 (nematic order), density_homogeneity (voxel CV)
            warnings          — list of soft-flag descriptions
            d05_markdown      — formatted D-05 block for direct paste into run_log.md
            d05_markdown_path — path to saved d05_block.md
            summary_json      — path to full JSON
    """
    _require_output_dir(output_dir, "check_equilibration_comprehensive",
                        "<dump_file dir>/eq_comprehensive")

    run_id = run_manager.create(
        "check_equilibration_comprehensive",
        {"log_file": log_file, "dump_file": dump_file, "output_dir": output_dir},
    )
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_check_equilibration_comprehensive, dict(
            log_file            = log_file,
            dump_file           = dump_file,
            data_file           = data_file,
            backbone_types      = backbone_types,
            output_dir          = output_dir,
            skip_frames         = skip_frames,
            timestep_fs         = timestep_fs,
            dump_every          = dump_every,
            n_backbone_bonds    = n_backbone_bonds,
            bond_length_A       = bond_length_A,
            eq_fraction         = eq_fraction,
            drift_threshold_pct = drift_threshold_pct,
            drift_pvalue        = drift_pvalue,
            block_count         = block_count,
            temp_col            = temp_col,
            density_col         = density_col,
            energy_col          = energy_col,
            atom_style          = atom_style,
            graphs_dir          = graphs_dir,
            ct_min_decay        = ct_min_decay,
            cv_signal_max       = cv_signal_max,
            cutoff_A            = cutoff_A,
            struct_dump_file    = struct_dump_file,
            struct_data_file    = struct_data_file,
            output_name         = output_name,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":     "submitted",
        "run_id":     run_id,
        "run_type":   "check_equilibration_comprehensive",
        "log_file":   log_file,
        "dump_file":  dump_file,
        "output_dir": output_dir,
        "message":    "Poll with get_run_status(run_id). Result includes overall_pass and d05_markdown.",
    }


# ── Tool: extract_equilibrated_density ───────────────────────────────────────

def _run_extract_equilibrated_density(
    log_file: str,
    output_dir: str,
    eq_fraction: float,
    target_temp: Optional[float],
    temp_tolerance: float,
    plateau_shift_sigma: float,
    density_col: str,
    temp_col: str,
) -> dict:
    """Background worker — runs extract_equilibrated_density.py via CLI."""

    parts = [f"python {MDA_SCRIPTS_DIR}/extract_equilibrated_density.py"]
    parts.append(f"--log_file {log_file}")
    parts.append(f"--output_dir {output_dir}")
    parts.append(f"--eq_fraction {eq_fraction}")
    if target_temp is not None:
        parts.append(f"--target_temp {target_temp}")
    parts.append(f"--temp_tolerance {temp_tolerance}")
    parts.append(f"--plateau_shift_sigma {plateau_shift_sigma}")
    parts.append(f"--density_col {density_col}")
    parts.append(f"--temp_col {temp_col}")
    parts.append(f"--output_name {output_name}")

    command = " ".join(parts)
    logger.info(f"Running equilibrated density extraction via CLI: {command}")

    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=36000)

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


# ── Tool: derive_backbone_types ───────────────────────────────────────────────

def _run_derive_backbone_types(data_file: str) -> dict:
    """Background worker — runs derive_backbone_types.py via CLI."""

    command = f"python {MDA_SCRIPTS_DIR}/derive_backbone_types.py --data_file {data_file}"
    logger.info(f"Running backbone_types derivation via CLI: {command}")

    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=300)

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def derive_backbone_types(data_file: str) -> dict:
    """
    Derive backbone_types from a .data file's bond topology alone — no simulation,
    no atom-type-name guessing.

    Finds each chain's backbone as the graph diameter of its heavy-atom bond graph
    (BFS twice: farthest atom from an arbitrary start, then farthest atom from
    there — the walk between them is the backbone; side branches are excluded by
    construction since they're shorter than continuing along the main path).
    Unions the atom type IDs found along every chain's backbone path.

    Args:
        data_file: Path to the .data file (the original pre-simulation cell, so
                   Masses/Bonds are intact).

    Returns:
        dict with run_id. When completed, result includes:
            backbone_types     — sorted list of backbone atom type IDs
            method              — "heavy_atom_graph_diameter"
            n_chains            — chains found (resids)
            n_chains_resolved   — chains with >= 2 heavy atoms and bond topology
    """
    run_id = run_manager.create("derive_backbone_types", {"data_file": data_file})
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_derive_backbone_types, dict(data_file=data_file)),
        daemon=True,
    )
    t.start()
    return {
        "status":    "submitted",
        "run_id":    run_id,
        "run_type":  "derive_backbone_types",
        "data_file": data_file,
        "message":   "Poll with get_run_status(run_id). Result includes backbone_types.",
    }


@mcp.tool()
def assess_cooling_contraction(
    glass_data: str,
    tg_K: float,
    t_equil_K: float,
    melt_data: Optional[str] = None,
    final_T_K: float = 300.0,
) -> dict:
    """
    Cooling-contraction self-consistency check — distinguishes an UNDER-ANNEALED (kinetically
    trapped) glass from a normally-cooled one, purely from the run's own data.

    A converged density only means the cell stopped moving, not that it densified as
    much as it should have: a trapped glass converges low because free volume froze in during
    cooling. This computes densities directly from the final structures (box + masses),
    compares the melt→glass contraction against the system's own thermal-expansion prediction
    (alpha_glass/alpha_melt — literature-typical-polymer constants, not specific to any one
    material), and reports:

      - UNDER_ANNEALED_COOLING : the cell under-contracted relative to its own predicted
        contraction → re-melt + SLOW re-cool (NOT EXTEND at final_T_K — a glass cannot
        densify below Tg).
      - OK                     : cooling contraction is self-consistent with the prediction.
      - INSUFFICIENT_DATA      : glass-state density could not be measured.

    Deliberately never compares to an experimental/curated density or thermal-expansion
    value — a novel system may have neither, and this check does not need either.
    `extrapolation_reliable=False` (cooling span > 300 K) means treat the verdict as
    indicative, not firm.

    Args:
        glass_data:  npt_final_out.data at final_T_K (the assessed state). Required.
        tg_K:        (class) Tg in K. If <=final_T_K the cell is never a glass at the
                     temperature it is graded at -> rubbery/equilibrium (no-op).
        t_equil_K:   melt/equilibration temperature (T_workflow) in K.
        melt_data:   the melt-reference cool_block output at T_equil. Optional but required for
                     the self-consistency computation; without it the verdict is OK/non-blocking.
        final_T_K:   assessment temperature (K) -- where glass_data was written, and the cold
                     endpoint of the contraction. 300 is its default, not its definition.

    Returns:
        dict with rho_melt, rho_glass, expected_contraction, actual_contraction,
        contraction_shortfall, under_annealed_cooling (bool), verdict, remedy,
        extrapolation_reliable, markdown.
    """
    parts = [f"python {MDA_SCRIPTS_DIR}/assess_cooling_contraction.py",
             f"--glass_data {glass_data}",
             f"--tg_K {tg_K}",
             f"--t_equil_K {t_equil_K}",
             f"--final_T_K {final_T_K}"]
    if melt_data:
        parts.append(f"--melt_data {melt_data}")
    command = " ".join(parts)
    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=600)
    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def enforce_equilibration_gate(
    comprehensive_json: str,
    regime: str,
    dp: Optional[float],
    ct_gate_reliable: bool,
    tg_K: Optional[float],
    t_equil_K: Optional[float],
    glass_data: Optional[str],
    melt_data: Optional[str],
    out_dir: Optional[str],
    final_T_K: float = 300.0,
    output_name: str = "equilibration.json",
) -> dict:
    """
    Mechanized equilibration gate verdict — replaces prose PASS/EXTEND/FAIL judgment with a
    programmatic cross-check of check_equilibration_comprehensive's per-gate results against
    decision_policy.json's require_glassy / require_rubbery clauses, plus density_value_binding
    (an unconditional self-consistency check on a glassy run's melt→glass contraction vs. its
    own thermal-expansion prediction — a check overall_pass never performs on its own, since it
    only tests that density stopped moving, not that it stopped at a physically consistent
    value). Never compares to any experimental/curated density or thermal-expansion value.

    Single-call: if density_value_binding is triggered and no cached diagnosis exists at
    <out_dir>/cooling_contraction.json, this calls assess_cooling_contraction.py internally
    (same script the assess_cooling_contraction tool wraps) and saves the result itself —
    no round-trip back to the caller required, unlike enforce_gate.py's --live CLI mode (which
    this wraps and is kept for retrospective/offline auditing of completed runs).

    Every argument is required — no defaults. Several may be null, and at the phase=melt
    checkpoint most of them are: no post-cool glass state exists yet, so density_value_binding
    cannot run. Pass those as explicit nulls. An omitted argument and a null one produced the
    same weakened gate with no record of which was intended, so omission is a schema error.

    Args:
        comprehensive_json: Path to check_equilibration_comprehensive's saved JSON output.
        regime:             "melt" (the melt hold -- rg and ct BIND there, see
                            enforce_gate.BINDING_MELT), "glassy", or "rubbery". The melt gate
                            passes "melt" outright rather than resolving it, because
                            resolve_regime answers "glassy" whenever Tg is unresolvable.
        dp:                 Degree of polymerization (drives the require_glassy DP≥30 carve-out).
        ct_gate_reliable:   False for aromatic-backbone classes (PSFO/PKTN) — C(t) is
                            structurally undefined there regardless of DP.
        tg_K:               (Class) Tg (K) — used only to split the cooling path into a glassy
                            and a melt segment, never as an experimental target.
        t_equil_K:          Melt/equilibration temperature (T_workflow_K).
        final_T_K:          Assessment temperature (K) — npt_final's own temperature, and the
                            cold endpoint of the cooling-contraction check. 300 is its default,
                            not its definition.
        glass_data:         npt_prod300_out.data (glass at 300K) — required only if
                            density_value_binding needs to run assess_cooling_contraction.
        melt_data:          npt_production_out.data (melt at T_equil) — same condition.
        out_dir:            Run's raw/ output directory — cooling_contraction.json is cached
                            here so repeat calls (e.g. after an EXTEND) don't re-run the probe.

    Returns:
        dict: regime, applicable_clause, binding_gates, advisory_gates,
        density_value_binding, failing_binding_gates, verdict (PASS | EXTEND |
        STRUCTURAL_FAIL | FAIL), remedy (set only for STRUCTURAL_FAIL — e.g.
        re_melt_slow_recool | a melt-mixing extension note).
    """
    repo_root = Path(__file__).resolve().parents[2]
    orchestration_dir = str(repo_root / "orchestration" / "scripts")
    if orchestration_dir not in sys.path:
        sys.path.insert(0, orchestration_dir)
    import enforce_gate

    class _LiveArgs:
        pass

    live_args = _LiveArgs()
    live_args.comprehensive_json = comprehensive_json
    live_args.regime = regime
    live_args.dp = dp
    live_args.ct_gate_reliable = ct_gate_reliable
    live_args.tg_k = tg_K
    live_args.t_equil_k = t_equil_K
    live_args.final_t_k = final_T_K
    live_args.glass_data = glass_data
    live_args.melt_data = melt_data
    live_args.out_dir = out_dir

    result = enforce_gate.enforce_live(live_args)

    if result.get("needs_probe"):
        cc_args = result["assess_cooling_contraction_args"]
        parts = [f"python {MDA_SCRIPTS_DIR}/assess_cooling_contraction.py",
                 f"--glass_data {cc_args['glass_data']}",
                 f"--tg_K {cc_args['tg_K']}",
                 f"--t_equil_K {cc_args['t_equil_K']}",
                 f"--final_T_K {cc_args.get('final_T_K', 300.0)}"]
        if cc_args.get("melt_data"):
            parts.append(f"--melt_data {cc_args['melt_data']}")
        if cc_args.get("melt_log"):
            parts.append(f"--melt_log {cc_args['melt_log']}")
        if cc_args.get("glass_log"):
            parts.append(f"--glass_log {cc_args['glass_log']}")
        command = " ".join(parts)
        logger.info(f"enforce_equilibration_gate: auto-running density_value_binding probe: {command}")
        stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=600)
        cooling_result = _parse_json_from_stdout(stdout, stderr)
        if cooling_result.get("status") == "failed":
            failure = {"status": "failed",
                       "error": "assess_cooling_contraction probe failed inside enforce_equilibration_gate",
                       "detail": cooling_result}
            return _save_gate_verdict(out_dir, failure, output_name)
        save_path = Path(result["save_result_to"])
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps(cooling_result, indent=2))
        result = enforce_gate.enforce_live(live_args)  # re-run now that the cache exists

    return _save_gate_verdict(out_dir, result, output_name)


@mcp.tool()
def extract_equilibrated_density(
    log_file: str,
    output_dir: str,
    target_temp: Optional[float],
    eq_fraction: float = 0.5,
    temp_tolerance: float = 50.0,
    plateau_shift_sigma: float = 1.0,
    density_col: str = "Density",
    temp_col: str = "Temp",
    output_name: str = "equilibration.json",
) -> dict:
    """
    Extract the equilibrated (plateau) density from a single LAMMPS log.

    Uses a reverse-cumulative-mean algorithm to find the longest stable
    tail of the density time series rather than a fixed burn-in fraction:

    1. Discard the first (1 - eq_fraction) of rows as initial burn-in.
    2. Starting from the last row, extend backwards one row at a time.
    3. Stop when adding the next row shifts the cumulative mean by more
       than plateau_shift_sigma * SEM of the current window.
    4. The identified plateau region gives the equilibrated density
       (mean +/- SEM).

    Also reports the naive mean (simple average of the full production
    window) for comparison — if the two agree, equilibration is clean.

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        log_file:            Full path to LAMMPS log file.
        output_dir:          Output directory.
        eq_fraction:         Fraction of rows used as production window
                             (0.5 = last 50 %).
        target_temp:         If set, only use rows where T is within
                             temp_tolerance of this value (K).  Useful
                             for multi-temperature logs.
        temp_tolerance:      Tolerance window for temperature filter (K).
        plateau_shift_sigma: Sensitivity of plateau detection.  Higher
                             values = more permissive (longer plateau).
                             Default 1.0 works well for typical NPT runs.
        density_col:         Density column name in thermo output.
        temp_col:            Temperature column name.

    Returns:
        dict with run_id.  When completed, result includes:
            plateau_density_mean     — equilibrated density (g/cm3)
            plateau_density_std      — standard deviation within plateau
            plateau_density_sem      — naive SEM (std/sqrt(n)); underestimates when autocorrelated
            block_sem_density        — tau_eff-aware block-SEM; preferred uncertainty estimate
            plateau_n_points         — number of thermo rows in plateau
            plateau_fraction         — fraction of production window identified as plateau
            production_n_points      — rows in production window
            total_n_points           — total rows in log
            tau_eff_frames           — integrated autocorrelation time / statistical inefficiency
            tau_eff_fraction         — tau_eff / n_plateau
            n_effective_samples      — n_plateau / tau_eff
            drift_slope              — linear regression slope over plateau (g/cm3 per frame)
            drift_pct                — |slope * n| / |mean| * 100
            drift_p_value            — p-value of drift slope
            plateau_equilibrated     — False if drift_pct > 1% AND p < 0.01
            rolling_mean_abs_deriv   — mean |d/dt(rolling mean)|; secondary stationarity check
            naive_mean / naive_std   — simple average of full production window
            plateau_step_range       — [start_step, end_step] of the plateau
            summary_json             — path to summary JSON
    """
    _require_output_dir(output_dir, "extract_equilibrated_density", "<log_file dir>/eq_analysis")

    run_id = run_manager.create("extract_equilibrated_density", {"log_file": log_file, "output_dir": output_dir})
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_extract_equilibrated_density, dict(
            log_file            = log_file,
            output_dir          = output_dir,
            eq_fraction         = eq_fraction,
            target_temp         = target_temp,
            temp_tolerance      = temp_tolerance,
            plateau_shift_sigma = plateau_shift_sigma,
            density_col         = density_col,
            temp_col            = temp_col,
            output_name         = output_name,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":     "submitted",
        "run_id":     run_id,
        "run_type":   "extract_equilibrated_density",
        "log_file":   log_file,
        "output_dir": output_dir,
        "message":    "Poll with get_run_status(run_id)",
    }


# ── Tool: extract_bulk_modulus ────────────────────────────────────────────────

def _run_extract_bulk_modulus(
    log_file: str,
    output_dir: str,
    eq_fraction: float,
    block_count: int,
    vol_col: str,
    temp_col: str,
    press_col: str,
    density_col: str,
    graphs_dir: Optional[str] = None,
) -> dict:
    """Background worker — runs extract_bulk_modulus.py via CLI."""

    parts = [f"python {MDA_SCRIPTS_DIR}/extract_bulk_modulus.py"]
    parts.append(f"--log_file {log_file}")
    parts.append(f"--output_dir {output_dir}")
    parts.append(f"--eq_fraction {eq_fraction}")
    parts.append(f"--block_count {block_count}")
    parts.append(f"--vol_col {vol_col}")
    parts.append(f"--temp_col {temp_col}")
    parts.append(f"--press_col {press_col}")
    parts.append(f"--density_col {density_col}")
    if graphs_dir:
        parts.append(f"--graphs_dir {graphs_dir}")

    command = " ".join(parts)
    logger.info(f"Running bulk modulus extraction via CLI: {command}")

    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=36000)

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def extract_bulk_modulus(
    log_file: str,
    output_dir: str,
    graphs_dir: str,
    eq_fraction: float = 0.5,
    block_count: int = 5,
    vol_col: str = "Volume",
    temp_col: str = "Temp",
    press_col: str = "Press",
    density_col: str = "Density",
) -> dict:
    """
    Extract isothermal bulk modulus from an NPT LAMMPS simulation log
    using the volume fluctuation method.

    Method:
        K_T = kB * T * <V> / Var(V)

    where kB is Boltzmann's constant, T is the mean temperature, <V> is
    the mean volume, and Var(V) is the sample variance of volume over the
    production window.  This is the standard statistical-mechanical route
    for isothermal bulk modulus from NPT ensembles (Allen & Tildesley, 2017).

    The simulation must be a constant-T, constant-P (NPT) run that is
    well-equilibrated.  The first (1 - eq_fraction) of thermo rows are
    discarded as burn-in.

    Uncertainty is estimated via block averaging: the production window is
    split into blocks, K is computed independently per block, and the SEM
    of the block values gives the uncertainty.

    A volume drift check is included — if volume drift exceeds 1% with
    p < 0.01, a warning is issued indicating incomplete equilibration.

    Output files written to output_dir:
        bulk_modulus.json        — full results and diagnostics
        volume_timeseries.csv    — step, volume, temperature, [pressure]

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        log_file:     Full path to the LAMMPS log file (NPT run).
        output_dir:   Output directory. Required — the run's raw/ dir.
        eq_fraction:  Fraction of rows used as production window
                      (0.5 = last 50%).
        block_count:  Number of blocks for block-average uncertainty.
        vol_col:      Volume column name (tries Volume, Vol, vol).
        temp_col:     Temperature column name.
        press_col:    Pressure column name.
        density_col:  Density column name.

    Returns:
        dict with run_id.  When completed, result includes:
            bulk_modulus_GPa       — K in GPa
            bulk_modulus_atm       — K in atm
            bulk_modulus_sem_GPa   — block-average SEM in GPa
            isothermal_compressibility_per_Pa — β_T = 1/K
            V_mean_A3, V_std_A3   — volume statistics
            block_averaging        — per-block K values and statistics
            diagnostics            — T, P, density means, drift check
            summary_json           — path to summary JSON
    """
    _require_output_dir(output_dir, "extract_bulk_modulus", "<log_file dir>/bulk_analysis")

    run_id = run_manager.create("extract_bulk_modulus", {"log_file": log_file, "output_dir": output_dir})
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_extract_bulk_modulus, dict(
            log_file    = log_file,
            output_dir  = output_dir,
            eq_fraction = eq_fraction,
            block_count = block_count,
            vol_col     = vol_col,
            temp_col    = temp_col,
            press_col   = press_col,
            density_col = density_col,
            graphs_dir  = graphs_dir,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":     "submitted",
        "run_id":     run_id,
        "run_type":   "extract_bulk_modulus",
        "log_file":   log_file,
        "output_dir": output_dir,
        "message":    "Poll with get_run_status(run_id)",
    }


# ── Tool: extract_bulk_modulus_deform ─────────────────────────────────────────

def _run_extract_bulk_modulus_deform(
    log_file: str,
    output_dir: str,
    strain_rate: float,
    strain_max: float,
    timestep: float,
    eq_steps: int,
    strain_start: float,
    avg_window: int = 2000,
    graphs_dir: Optional[str] = None,
    log_file_2: Optional[str] = None,
    strain_rate_2: Optional[float] = None,
    deform_direction: str = "x",
) -> dict:
    """Background worker — runs extract_bulk_modulus_deform.py via CLI."""
    parts = [f"python {MDA_SCRIPTS_DIR}/extract_bulk_modulus_deform.py"]
    parts.append(f"--log_file {log_file}")
    parts.append(f"--output_dir {output_dir}")
    parts.append(f"--strain_rate {strain_rate}")
    parts.append(f"--strain_max {strain_max}")
    parts.append(f"--timestep {timestep}")
    parts.append(f"--eq_steps {eq_steps}")
    parts.append(f"--strain_start {strain_start}")
    parts.append(f"--avg_window {avg_window}")
    if graphs_dir:
        parts.append(f"--graphs_dir {graphs_dir}")
    if log_file_2:
        parts.append(f"--log_file_2 {log_file_2}")
    if strain_rate_2 is not None:
        parts.append(f"--strain_rate_2 {strain_rate_2}")
    parts.append(f"--deform_direction {deform_direction}")

    command = " ".join(parts)
    logger.info(f"Running deformation bulk modulus extraction via CLI: {command}")

    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=36000)

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def extract_bulk_modulus_deform(
    log_file: str,
    output_dir: str,
    graphs_dir: str,
    strain_rate: float,
    strain_max: float,
    timestep: float,
    log_file_2: Optional[str],
    strain_rate_2: Optional[float],
    eq_steps: int = 200000,
    strain_start: float = 0.002,
    avg_window: int = 2000,
    deform_direction: str = "x",
) -> dict:
    """
    Extract elastic constants from a LAMMPS uniaxial deformation log
    (npt_deform template, Stage 5b).

    Method: Linear stress-strain fit in the elastic regime.

    Under uniaxial x-strain with fixed y/z (NVT, no barostat):
        C11 = -d(pxx)/d(ε_xx)    (axial stiffness)
        C12 = -d(pyy)/d(ε_xx)    (lateral coupling)

    Derived Voigt isotropic moduli:
        K = (C11 + 2·C12) / 3    (bulk modulus)
        G = (C11 - C12) / 2      (shear modulus)
        E = 9·K·G / (3·K + G)    (Young's modulus)
        ν = C12 / (C11 + C12)    (Poisson's ratio)

    Strain is reconstructed from step number:
        ε(step) = strain_rate × (step − step_0) × timestep

    Use alongside extract_bulk_modulus (volume fluctuation) for cross-checks.
    The deformation method is preferred for glassy polymers (Tg > 300 K)
    where volume fluctuations are too slow to converge.

    Output files written to output_dir:
        bulk_modulus_deform.json   — full results and diagnostics
        stress_strain.csv          — step, strain, σ_xx, σ_yy, σ_zz (GPa)

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        log_file:     Full path to the npt_deform LAMMPS log.
        output_dir:   Output directory. Required — the run's raw/ dir.
        strain_rate:  REQUIRED. Engineering strain rate in 1/fs (= K_deform_rate_inv_s × 1e-15).
        strain_max:   REQUIRED. Maximum strain for linear-regime fit (K_strain_max, ~0.03).
        timestep:     REQUIRED. MD timestep in fs — must match the deck. Strain is reconstructed
                      as eps(step) = strain_rate * (step - step_0) * timestep, so a dt=2 fs deck
                      analysed at 1.0 reports half the strain and twice the modulus.
        eq_steps:     NVT pre-equilibration steps (N_EQ_STEPS) — skipped in analysis.
        strain_start: Minimum strain to include in fit (skip initial transient). Default 0.002.
        avg_window:   Rolling-average window in thermo frames applied to stress before fitting.
                      Thermal noise (~0.2 GPa at THERMO_FREQ=100) swamps the elastic signal
                      (~0.09 GPa at 3% strain) on individual thermo rows. Default 2000 = 200 ps
                      at THERMO_FREQ=100. Set to 1 to disable. Scale with THERMO_FREQ if changed.
        log_file_2:   REQUIRED, may be null. Second deformation log (slow-rate run) for the
                      rate-sensitivity check; when non-null, K is extracted independently from
                      both logs and compared. Pass the null when there is no slow leg.
        strain_rate_2: REQUIRED, may be null. Strain rate for log_file_2 in 1/fs; non-null
                      whenever log_file_2 is.
        deform_direction: Axis the deck strained along ("x", "y", or "z"). Selects the loading
                       vs transverse stress components. Must match the deck — a y/z leg analysed
                       as "x" mislabels C11/C12 and can flip G/E negative (K is invariant).

    Returns:
        dict with run_id.  When completed, result includes:
            C11_GPa, C12_GPa        — elastic stiffness constants
            K_GPa                   — bulk modulus
            G_GPa                   — shear modulus
            E_GPa                   — Young's modulus
            nu_Poisson              — Poisson's ratio
            fit_r2_C11, fit_r2_C12_yy — R² of linear fits (quality check)
            isotropy_delta_pct      — % difference between C12_yy and C12_zz
            stress_strain_csv       — path to stress-strain CSV
            summary_json            — path to summary JSON
    """
    _require_output_dir(output_dir, "extract_bulk_modulus_deform", "<log_file dir>/deform_analysis")

    run_id = run_manager.create("extract_bulk_modulus_deform", {"log_file": log_file, "output_dir": output_dir})
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_extract_bulk_modulus_deform, dict(
            log_file      = log_file,
            output_dir    = output_dir,
            strain_rate   = strain_rate,
            strain_max    = strain_max,
            timestep      = timestep,
            eq_steps      = eq_steps,
            strain_start  = strain_start,
            avg_window    = avg_window,
            graphs_dir    = graphs_dir,
            log_file_2    = log_file_2,
            strain_rate_2 = strain_rate_2,
            deform_direction = deform_direction,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":     "submitted",
        "run_id":     run_id,
        "run_type":   "extract_bulk_modulus_deform",
        "log_file":   log_file,
        "output_dir": output_dir,
        "message":    "Poll with get_run_status(run_id)",
    }


# ── Tool: run_bulk_modulus_series ─────────────────────────────────────────────

@mcp.tool()
def run_bulk_modulus_series(
    data_file: str,
    work_dir: str,
    pressures_atm: list,
    temp_K: float,
    run_name: str,
    gpu_ids: str,
    mpi: int,
    velocity_seed: int,
    npt_steps: int,
    dt_fs: float,
    use_trappe: bool,
    use_pcff: bool,
    use_opls: bool,
    engine: str,
    thermo_freq: int = 100,
    thermostat_damp_fs: float = 100.0,
    barostat_damp_fs: float = 1000.0,
    use_long_range: bool = True,
    output_dir: Optional[str] = None,
) -> dict:
    """
    Run a series of constant-pressure NPT simulations to support Murnaghan
    EOS fitting (rubbery polymer bulk modulus).

    For each pressure in pressures_atm, generates an NPT script (constant T,
    constant P) from the standard npt template and submits all as a chain.
    After the chain completes, pass the resulting log files to
    extract_bulk_modulus_murnaghan to fit B0, B0', V0.

    Recommended pressures for soft melts: [1, 100, 300, 600, 1000] atm.
    Each NPT run equilibrates the box at that pressure; the mean volume is
    extracted from the production window (last 50%% by default).

    Args:
        data_file:      Equilibrated .data file (e.g. 07_npt_production_out.data).
        work_dir:       Base directory; subdirs bm_P{P}/ are created per pressure.
        pressures_atm:  One or more target pressures in atm. EOS analysis still requires
                        at least three; single-point calls support independently retried points.
        temp_K:         Simulation temperature (K). Use 300 K for property measurement.
        run_name:       NO-OP — accepted and required for backward compatibility, but never
                        read in the body. Do not treat it as a protocol knob.
        velocity_seed:  REQUIRED, non-null. The run's seed, forwarded to every pressure
                        point's generated script — see generate_script.
        npt_steps:      REQUIRED. MD steps per pressure point (500000 = 500 ps at dt=1 fs).
        dt_fs:          REQUIRED. Timestep in fs — must match the class's own dt.
        thermo_freq:    Thermo output frequency. Default 100.
        gpu_ids:        Comma-separated GPU IDs (e.g. "0" or "0,1"). Required —
                        no default; the engine no longer falls back to GPU 0,1.
        mpi:            MPI processes. Required — no default.
        output_dir:     Where to store the list of log file paths (JSON).
                        Defaults to work_dir.
        use_trappe:     REQUIRED. True for TraPPE-UA systems (PHYC, PDIE). Emits lj/cut +
                        neigh yes instead of PPPM/CHARMM defaults. Mirrors the same
                        flag in generate_equilibration_workflow and generate_script.
                        All three FF flags are required because all three defaulting to
                        False silently emits the wrong pair_style.
        use_pcff:       REQUIRED. True for PCFF (Class II) systems. Emits pppm + class2 pair.
        use_opls:       REQUIRED. True for OPLS-AA systems. Emits pppm + lj/cut/coul/long.
        engine:         REQUIRED. Launch engine forwarded to run_lammps_chain: "kokkos"
                        (full-offload; canonical for PCFF/OPLS PPPM cells, mpi=1),
                        "gpu" (GPU package), or "cpu". Must match the
                        per-FF hardware_policy default or the chain runs the wrong
                        binary (PCFF on the GPU package is CPU-bound).

    Returns:
        dict with chain_id, monitor_command, log_files (list of expected log paths),
        and pressures_atm. Pass log_files and pressures_atm to
        extract_bulk_modulus_murnaghan after the chain completes.
    """
    try:
        if len(pressures_atm) < 1:
            return {
                "status": "error",
                "error": "At least one pressure point is required."
            }
        if velocity_seed is None:
            return {
                "status": "error",
                "error": "velocity_seed is required and must not be null — the pressure points "
                         "would each draw their own random seed. Pass the run's seed.",
            }

        out_dir = Path(output_dir or work_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        stages = []
        log_files = []
        for p_atm in pressures_atm:
            tag = f"bm_P{int(p_atm)}"
            stage_dir = str(Path(work_dir) / tag)
            script_path = f"{stage_dir}/{tag}.in"
            log_path = f"{stage_dir}/{tag}.log"
            log_files.append(log_path)

            gen_result = generate_script(
                template_name="npt",
                data_file=data_file,
                output_script=script_path,
                velocity_seed=velocity_seed,
                params={
                    "T_START":     temp_K,
                    "T_FINAL":     temp_K,
                    "P_START":     float(p_atm),
                    "P_FINAL":     float(p_atm),
                    "T_DAMP":      thermostat_damp_fs,
                    "P_DAMP":      barostat_damp_fs,
                    "N_STEPS":     npt_steps,
                    "TIMESTEP":    dt_fs,
                    "THERMO_FREQ": thermo_freq,
                    "LOG_FILE":    log_path,
                    "use_gpu":     True,
                    "use_pppm":    use_long_range and not use_trappe,
                    "engine":      engine,
                    "use_trappe":  use_trappe,
                    "use_pcff":    use_pcff,
                    "use_opls":    use_opls,
                    "DUMP_FILE":   f"{stage_dir}/{tag}.dump",
                    "LAST_DUMP_FILE":  f"{stage_dir}/{tag}_last.dump",
                    "WRITE_DATA_FILE": f"{stage_dir}/{tag}_out.data",
                },
            )
            if gen_result.get("status") == "error":
                return {
                    "status": "error",
                    "error": f"generate_script failed for P={p_atm} atm: "
                             f"{gen_result.get('error')}"
                }
            stages.append({
                "name":     tag,
                "script":   script_path,
                "work_dir": stage_dir,
                "log_file": f"{tag}_stdout.log",  # basename only; chain prepends work_dir. LAMMPS writes thermo to log_path via the 'log' directive in the .in file.
            })

        # Save log file manifest alongside output
        manifest_path = str(out_dir / "bm_series_manifest.json")
        with open(manifest_path, "w") as mf:
            json.dump({"pressures_atm": pressures_atm, "log_files": log_files,
                       "temp_K": temp_K, "npt_steps": npt_steps}, mf, indent=2)

        chain_result = run_lammps_chain(
            stages=stages,
            mpi=mpi,
            gpu_ids=gpu_ids,
            data_file=data_file,
            engine=engine,
        )
        if chain_result.get("status") == "error":
            return chain_result

        chain_id = chain_result["chain_id"]
        return {
            "status":        "submitted",
            "chain_id":      chain_id,
            "run_name":      run_name,
            "pressures_atm": pressures_atm,
            "log_files":     log_files,
            "temp_K":        temp_K,
            "npt_steps":     npt_steps,
            "n_stages":      len(stages),
            "manifest_json": manifest_path,
            "monitor_command": f"watch_run('{chain_id}')",
            "next_step": (
                f"After chain completes: call extract_bulk_modulus_murnaghan("
                f"log_files={log_files}, pressures_atm={pressures_atm}, "
                f"output_dir='<raw_dir>', graphs_dir='<graphs_dir>')"
            ),
            **{k: v for k, v in chain_result.items() if k not in ("status", "chain_id")},
        }

    except Exception as e:
        logger.error(f"run_bulk_modulus_series failed: {e}")
        return {"status": "error", "error": str(e)}


# ── Tool: extract_bulk_modulus_murnaghan ─────────────────────────────────────

def _run_extract_bulk_modulus_murnaghan(
    log_files: list,
    pressures_atm: list,
    output_dir: str,
    eq_fraction: float,
    graphs_dir: Optional[str] = None,
    npt_prod_log: Optional[str] = None,
) -> dict:
    """Background worker — runs extract_bulk_modulus_murnaghan.py via CLI."""
    parts = [f"python {MDA_SCRIPTS_DIR}/extract_bulk_modulus_murnaghan.py"]
    parts.append("--log_files " + " ".join(str(f) for f in log_files))
    parts.append("--pressures_atm " + " ".join(str(p) for p in pressures_atm))
    parts.append(f"--output_dir {output_dir}")
    parts.append(f"--eq_fraction {eq_fraction}")
    if graphs_dir:
        parts.append(f"--graphs_dir {graphs_dir}")
    if npt_prod_log:
        parts.append(f"--npt_prod_log {npt_prod_log}")

    command = " ".join(parts)
    logger.info(f"Running Murnaghan bulk modulus extraction via CLI: {command}")

    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=36000)

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def extract_bulk_modulus_murnaghan(
    log_files: list,
    pressures_atm: list,
    output_dir: str,
    graphs_dir: str,
    npt_prod_log: Optional[str],
    eq_fraction: float = 0.5,
) -> dict:
    """
    Fit the Murnaghan equation of state to a multi-pressure NPT series and
    extract the isothermal bulk modulus B0.

    Input: N NPT log files (one per pressure) from run_bulk_modulus_series.
    Each log is parsed; the last eq_fraction of rows is used as production
    window to compute mean equilibrium volume at that pressure.

    Murnaghan EOS: P = (B0/B0') * [(V0/V)^B0' - 1]
    Free parameters: B0 (bulk modulus, GPa), B0' (pressure derivative), V0 (Å³).

    Advantages over volume-fluctuation B_dyn:
      - Barostat-independent (P_DAMP has no effect)
      - Captures EOS nonlinearity typical of soft polymer melts (B0' ~ 7-11)

    Falls back to linear P vs ln V fit if curve_fit fails to converge.

    When npt_prod_log is passed, also runs three credibility checks embedded
    in the same result (no separate tool call needed):
      - Fluctuation cross-check: an independent K estimate from npt_prod_log's
        volume fluctuations, flagged if it diverges >15% from B0.
      - Leave-one-out refit: drops each pressure point in turn and refits,
        flagged if any single point shifts B0 by >10%.
      - Volume monotonicity: flags a pressure point whose mean volume is out
        of sequence (likely inadequate equilibration at that point).

    Output files written to output_dir:
        mechanical.json      — B0_GPa, B0_prime, V0_A3, r_squared, …
                               Also contains bulk_modulus_GPa alias for
                               compatibility with generate_run_summary.
        murnaghan_eos.png    — P vs V scatter with fit curve

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        log_files:      List of LAMMPS log file paths, one per pressure point.
                        Same order as pressures_atm. From run_bulk_modulus_series.
        pressures_atm:  List of target pressures (atm), same order as log_files.
        output_dir:     Directory for mechanical.json output.
        graphs_dir:     Directory for PNG figures. Defaults to output_dir/figures.
        eq_fraction:    Fraction of each log used as production window. Default 0.5.
        npt_prod_log:   Optional separate NPT production log for the fluctuation
                        cross-check. Omit to skip it (result fields become null).

    Returns:
        dict with run_id.  When completed, result includes:
            B0_GPa          — isothermal bulk modulus (Murnaghan B0)
            B0_prime        — pressure derivative dB/dP
            V0_A3           — reference volume at P=0
            r_squared       — goodness of fit (goal > 0.999)
            bulk_modulus_GPa — alias for B0_GPa (used by generate_run_summary)
            fit_converged   — True if Murnaghan converged, False if linear fallback
            volume_monotonic — False flags an out-of-sequence pressure point
            loo_results     — per-point leave-one-out refit rows (null if not converged)
            fluctuation_bulk_modulus_GPa, fluctuation_divergence_pct — cross-check
            warnings        — list of any quality flags
    """
    _require_output_dir(output_dir, "extract_bulk_modulus_murnaghan", "<log_file dir>/bulk_analysis")

    run_id = run_manager.create(
        "extract_bulk_modulus_murnaghan",
        {"log_files": log_files, "output_dir": output_dir}
    )
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_extract_bulk_modulus_murnaghan, dict(
            log_files     = log_files,
            pressures_atm = pressures_atm,
            output_dir    = output_dir,
            eq_fraction   = eq_fraction,
            graphs_dir    = graphs_dir,
            npt_prod_log  = npt_prod_log,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":        "submitted",
        "run_id":        run_id,
        "run_type":      "extract_bulk_modulus_murnaghan",
        "n_pressure_points": len(log_files),
        "output_dir":    output_dir,
        "message":       "Poll with get_run_status(run_id)",
    }


# ── Tool: extract_solubility_parameter ────────────────────────────────────────

def _run_extract_solubility_parameter(
    bulk_log: str,
    vacuum_log: str,
    n_chains: int,
    output_dir: str,
    charge_method: Optional[str] = None,
    eq_fraction: float = 0.5,
    system_label: Optional[str] = None,
) -> dict:
    """Background worker — runs extract_solubility_parameter.py via CLI."""
    parts = [f"python {MDA_SCRIPTS_DIR}/extract_solubility_parameter.py"]
    parts.append(f"--bulk_log {bulk_log}")
    parts.append(f"--vacuum_log {vacuum_log}")
    parts.append(f"--n_chains {n_chains}")
    parts.append(f"--output_dir {output_dir}")
    parts.append(f"--eq_fraction {eq_fraction}")
    if charge_method:
        parts.append(f"--charge_method {charge_method}")
    if system_label:
        parts.append(f"--system_label {system_label}")

    command = " ".join(parts)
    logger.info(f"Running solubility parameter extraction via CLI: {command}")

    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=600)

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def extract_solubility_parameter(
    bulk_log: str,
    vacuum_log: str,
    n_chains: int,
    output_dir: str,
    charge_method: Optional[str] = None,
    eq_fraction: float = 0.5,
    system_label: Optional[str] = None,
) -> dict:
    """
    Cohesive energy density (CED) / Hildebrand solubility parameter (delta) via
    a vacuum single-chain intramolecular-energy reference.

    STANDALONE DIAGNOSTIC TOOL — not currently wired into any agent's mandatory
    workflow. Used to measure per-SYSTEM cohesion for cavitation-risk research
    (does measured CED predict whether a rubbery Murnaghan pressure series can
    safely include a tension point). Never cache/reuse the result across a
    nominal polymer class — different monomers in the same class can have
    meaningfully different cohesion; always measure the specific system.

    Method: a bulk NPT hold's log reports TOTAL nonbonded energy (E_vdwl+E_coul),
    which mixes intramolecular (chain-on-itself) and intermolecular (chain-to-
    chain, the part that resists tension) contributions — not separable from
    the bulk log alone. A separate short NVT hold of ONE isolated chain at low
    density (large box, no periodic-image contacts) gives a clean intramolecular
    reference (100% of its nonbonded energy is self-interaction by construction):

        E_inter_total = E_bulk_total - n_chains * E_intra_per_chain
        CED = -E_inter_total / V_bulk   (J/cm^3 == MPa);  delta = sqrt(CED)

    This is an approximation relative to RadonPy's true per-molecule tally
    decomposition (see the separate, currently-inactive
    extract_solubility_parameter_tally.py, gated on a TALLY-enabled LAMMPS
    binary that doesn't exist yet).

    Args:
        bulk_log:      The system's own bulk NPT hold log (npt_production.log /
                       npt_prod300.log) — must be the SAME system as vacuum_log.
        vacuum_log:    Log from a short NVT hold of one isolated chain of that
                       same system (same topology/force field/temperature),
                       built at low density so periodic images don't interact.
        n_chains:      Number of chains in the bulk cell (a known build parameter).
        output_dir:    Directory for solubility_parameter.json output.
        charge_method: e.g. none/Gasteiger/AM1-BCC/RESP — sets ced_confidence
                       ("degraded" for embedded/Gasteiger charges, per
                       docs/ROADMAP.md's 20%+ error-risk caveat for those systems).
        eq_fraction:   Fraction of each log used as production window. Default 0.5.
        system_label:  Traceability label (e.g. "PE4") — never a class name.

    Returns:
        dict with run_id. When completed, result includes:
            CED_MPa, solubility_parameter_MPa0p5, ced_confidence,
            e_bulk_total_nonbonded_kcal_mol, e_intra_per_chain_kcal_mol,
            e_inter_total_kcal_mol, v_bulk_A3, v_vacuum_chain_A3, warnings
    """
    run_id = run_manager.create(
        "extract_solubility_parameter",
        {"bulk_log": bulk_log, "vacuum_log": vacuum_log, "output_dir": output_dir}
    )
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_extract_solubility_parameter, dict(
            bulk_log      = bulk_log,
            vacuum_log    = vacuum_log,
            n_chains      = n_chains,
            output_dir    = output_dir,
            charge_method = charge_method,
            eq_fraction   = eq_fraction,
            system_label  = system_label,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":       "submitted",
        "run_id":       run_id,
        "run_type":     "extract_solubility_parameter",
        "system_label": system_label,
        "output_dir":   output_dir,
        "message":      "Poll with get_run_status(run_id)",
    }


# ── Tool: generate_run_summary ────────────────────────────────────────────────

def _run_generate_run_summary(
    output_dir: str,
    run_name: str,
    smiles: str,
    polymer_class: str,
    ff: str,
    simulation_dir: str,
    charge_method: str,
    dp: Optional[int],
    n_chains: Optional[int],
    n_atoms: Optional[int],
    date_start: str,
    date_end: str,
    d01: Optional[str],
    d02: Optional[str],
    d03: Optional[str],
    d04: Optional[str],
    d05: Optional[str],
    d06: Optional[str],
    graphs_dir: Optional[str] = None,
    n_replicates: Optional[int] = None,
    tg_path: Optional[str] = None,
    equilibration_path: Optional[str] = None,
    melt_equilibration_path: Optional[str] = None,
    mechanical_path: Optional[str] = None,
    bulk_modulus_deform_path: Optional[str] = None,
    byproducts_spec: Optional[str] = None,
) -> dict:
    """Background worker — runs generate_run_summary.py via CLI."""
    parts = [f"python {MDA_SCRIPTS_DIR}/generate_run_summary.py"]
    parts.append(f"--output_dir {output_dir}")
    parts.append(f"--run_name {run_name}")
    if smiles:         parts.append(f"--smiles '{smiles}'")
    if polymer_class:  parts.append(f"--polymer_class {polymer_class}")
    if ff:             parts.append(f"--ff '{ff}'")
    if charge_method:  parts.append(f"--charge_method '{charge_method}'")
    if simulation_dir: parts.append(f"--simulation_dir {simulation_dir}")
    if dp is not None:       parts.append(f"--dp {dp}")
    if n_chains is not None: parts.append(f"--n_chains {n_chains}")
    if n_atoms is not None:  parts.append(f"--n_atoms {n_atoms}")
    if date_start:     parts.append(f"--date_start {date_start}")
    if date_end:       parts.append(f"--date_end {date_end}")
    if d01 is not None: parts.append(f"--d01 '{d01}'")
    if d02 is not None: parts.append(f"--d02 '{d02}'")
    if d03 is not None: parts.append(f"--d03 '{d03}'")
    if d04 is not None: parts.append(f"--d04 '{d04}'")
    if d05 is not None: parts.append(f"--d05 '{d05}'")
    if d06 is not None: parts.append(f"--d06 '{d06}'")
    if graphs_dir:                  parts.append(f"--graphs_dir {graphs_dir}")
    if n_replicates is not None:    parts.append(f"--n_replicates {n_replicates}")
    if tg_path:                     parts.append(f"--tg_path {tg_path}")
    if equilibration_path:          parts.append(f"--equilibration_path {equilibration_path}")
    if melt_equilibration_path:     parts.append(f"--melt_equilibration_path {melt_equilibration_path}")
    if mechanical_path:             parts.append(f"--mechanical_path {mechanical_path}")
    if bulk_modulus_deform_path:    parts.append(f"--bulk_modulus_deform_path {bulk_modulus_deform_path}")
    if byproducts_spec:             parts.append(f"--byproducts_spec {byproducts_spec}")

    command = " ".join(parts)
    logger.info(f"Running generate_run_summary via CLI: {command}")
    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=300)
    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)



@mcp.tool()
def generate_run_summary(
    output_dir: str,
    run_name: str,
    graphs_dir: str,
    smiles: str = "",
    polymer_class: str = "",
    ff: str = "",
    simulation_dir: str = "",
    charge_method: str = "",
    dp: Optional[int] = None,
    n_chains: Optional[int] = None,
    n_atoms: Optional[int] = None,
    date_start: str = "",
    date_end: str = "",
    d01: Optional[str] = None,
    d02: Optional[str] = None,
    d03: Optional[str] = None,
    d04: Optional[str] = None,
    d05: Optional[str] = None,
    d06: Optional[str] = None,
    n_replicates: Optional[int] = None,
    tg_path: Optional[str] = None,
    equilibration_path: Optional[str] = None,
    melt_equilibration_path: Optional[str] = None,
    mechanical_path: Optional[str] = None,
    bulk_modulus_deform_path: Optional[str] = None,
    byproducts_spec: Optional[str] = None,
) -> dict:
    """
    Aggregate all Stage 4 analysis outputs into a single run_summary.json.

    Reads all JSON files written by the analysis tools in output_dir and
    assembles a canonical summary mirroring the run_log.md sections:
    run metadata, decisions (D-01 through D-06), results (Tg, density,
    bulk modulus), convergence, structural checks, artifact paths, and
    provenance (git commit, MDAnalysis version, timestamp).

    Reports measured values only — no experimental PASS/FAIL grading. Most runs are novel
    systems with no curated experimental reference, so compare results.tg/density/bulk_modulus
    against literature by hand (or via exp_lookup.json, written separately for provenance) when
    a reference happens to exist.

    Call as the final step of Stage 4, after all analysis tools have run.
    All artifact paths in the summary are relative to data/[RUN]/ in the
    PolyJarvis repo (e.g. "graphs/tg_fit.png").

    Args:
        output_dir:       Absolute path to data/[RUN]/raw/.
                          Every analysis JSON must already exist directly here —
                          only thermal.json is searched recursively. Anything an
                          extractor wrote into a subdirectory is reported in
                          artifacts_missing, not silently dropped.
        run_name:         Run directory name (e.g. "PS4").
        smiles:           SMILES string for the polymer.
        polymer_class:    Class ID (e.g. "PSTR").
        ff:               Force field name (e.g. "TraPPE-UA").
        simulation_dir:   Absolute path to the simulation base directory.
        charge_method:    Charge method used (e.g. "AM1-BCC", "embedded in FF").
        dp, n_chains, n_atoms: System size parameters.
        date_start, date_end: ISO date strings (e.g. "2026-06-04").
        d01–d06:          Decision strings (caller-resolved from the run plan).
        n_replicates:     Replicate count reported in results.tg.n_replicates
                          (single-run protocol: 1).
        tg_path:          Explicit path to the canonical thermal.json (e.g.
                          tg_r40/thermal.json — the slowest-rate folder). When
                          supplied, skips rglob discovery; prevents alphabetical-order
                          bugs when multiple rate folders coexist.
        byproducts_spec:    Path to a JSON list of free measurements to surface alongside the
                            requested results -- written by run_campaign.do_summary from
                            orchestration/scripts/track_registry.py. A path rather than an import
                            because track_registry lives in orchestration/ and these analysis
                            scripts deploy separately, the same reasoning as the explicit
                            cross-attempt paths below.
        equilibration_path, mechanical_path, bulk_modulus_deform_path:
                          Explicit paths to the accepted equilibration/mechanical
                          attempts' own equilibration.json/mechanical.json/
                          bulk_modulus_deform.json. Under the attempt-based run layout
                          these files live under a DIFFERENT stage's own attempt raw
                          dir, never under this call's own output_dir — the plain
                          same-dir lookup can never find them without these (mirrors
                          tg_path's existing precedent for exactly this reason).
                          Omit only for a flat (non-attempt-based) run where every
                          stage shares one output_dir.

    Returns:
        dict with status and summary_json path on success.
    """
    run_id = run_manager.create("generate_run_summary", {
        "output_dir": output_dir, "run_name": run_name,
    })
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_generate_run_summary, dict(
            output_dir=output_dir, run_name=run_name, smiles=smiles,
            polymer_class=polymer_class, ff=ff, simulation_dir=simulation_dir,
            charge_method=charge_method, dp=dp, n_chains=n_chains, n_atoms=n_atoms,
            date_start=date_start, date_end=date_end,
            d01=d01, d02=d02, d03=d03, d04=d04, d05=d05, d06=d06,
            graphs_dir=graphs_dir, n_replicates=n_replicates,
            tg_path=tg_path, equilibration_path=equilibration_path,
            melt_equilibration_path=melt_equilibration_path,
            mechanical_path=mechanical_path, bulk_modulus_deform_path=bulk_modulus_deform_path,
            byproducts_spec=byproducts_spec,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":     "submitted",
        "run_id":     run_id,
        "run_type":   "generate_run_summary",
        "output_dir": output_dir,
        "message":    "Poll with get_run_status(run_id)",
    }


# ─── Entry point ──────────────────────────────────────────────────────────────
def _recover_interrupted_chains():
    """
    On server startup, find any chains that were running/pending when the
    server last died and re-launch their threads, skipping stages whose
    output data file already exists locally.
    """
    recovered = 0
    for run in run_manager.all():
        if run["run_type"] != "lammps_chain":
            continue
        if run["status"] not in (JobStatus.RUNNING.value, JobStatus.PENDING.value):
            continue

        chain_id = run["run_id"]
        meta     = run["meta"]
        stages   = meta.get("stages", [])
        mpi      = meta.get("mpi", 2)
        gpu_ids  = meta.get("gpu_ids", "0")

        if not stages:
            run_manager.fail(chain_id, "Cannot recover: full stage list not persisted (pre-fix chain)")
            logger.warning(f"[{chain_id}] Cannot recover -- no stage list in meta")
            continue

        # Skip stages whose output data file already exists locally
        remaining = []
        for s in stages:
            out_data = (s.get("output_data") or
                        f"{s['work_dir']}/{s.get('name', 'stage')}_out.data")
            if Path(out_data).exists():
                logger.info(f"[{chain_id}] Recovery skip (done): {s.get('name')}")
                continue
            remaining.append(s)

        if not remaining:
            run_manager.complete(chain_id, {"recovered": True, "note": "All stages already complete on disk"})
            logger.info(f"[{chain_id}] Recovery: all stages already done")
            continue

        logger.info(f"[{chain_id}] Recovering: {len(remaining)} stages remaining")
        thread = threading.Thread(
            target=_lammps_chain_background,
            args=(chain_id, remaining, mpi, gpu_ids),
            daemon=True,
        )
        thread.start()
        recovered += 1

    if recovered:
        logger.info(f"Startup recovery: re-launched {recovered} interrupted chain(s)")


if __name__ == "__main__":
    logger.info("Starting PolyJarvis LAMMPS Engine MCP Server")
    _recover_interrupted_chains()
    mcp.run()
