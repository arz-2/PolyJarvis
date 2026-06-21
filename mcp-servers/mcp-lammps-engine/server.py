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
  16b. extract_tg_multirate             - Multi-rate Tg: log-linear + VF fit across cooling rates
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


def _engine_launch(engine: str, n_gpu: int) -> tuple[str, str]:
    """Map an execution engine to (lmp binary, mpirun offload flags).

      gpu    → GPU package: pairwise forces on GPU, bonded/kspace/neigh on CPU (current default)
      cpu    → no offload flags (CPU-only; required by compute born/matrix numdiff)
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

# ─── Completion sentinels ─────────────────────────────────────────────────────
# Each completed (or failed) run writes a small JSON file here.
# Claude watches this directory via the Monitor tool so it is re-invoked
# automatically when a simulation finishes, without polling.
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
                logger.warning(f"Could not load run state: {e}")
                self.runs = {}

    def _save(self):
        """Persist run state to disk (call inside lock)."""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump(self.runs, f, indent=2)
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
        # use_gpu=False (e.g. compute born/matrix numdiff) forces the CPU engine regardless of the
        # engine arg; otherwise honor engine (gpu | kokkos). _engine_launch picks binary + flags.
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
            # Record our own PID first so watch_run can check liveness. $$ is the
            # long-lived wrapper; $! at launch is the short-lived setsid parent.
            f"mkdir -p {SENTINEL_DIR}\n"
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
    h_type_ids: Optional[list] = None,
    backbone_types: Optional[list] = None,
    atom_type_pairs: Optional[list] = None,
    lj_cutoff: float = 12.0,
    charge_tol: float = 0.01,
    params_file: str = "",
) -> dict:
    """
    Parse a LAMMPS .data file and run pre-simulation validation in one call.

    Returns system info (n_atoms, box, atom types, h_type_ids) together with
    validation results. Check validation.errors — if non-empty the file is not
    safe to submit.

    BLOCKING errors: charge non-neutrality, missing Coeffs sections,
    box smaller than 2×cutoff, type IDs out of range.
    ADVISORY warnings: unusual density, H-mass mismatch, bad bond/atom ratio.

    Args:
        data_file:       Path to the .data file.
        h_type_ids:      SHAKE H type IDs to validate.
        backbone_types:  Backbone atom type IDs to validate (end-to-end, P2).
        atom_type_pairs: RDF atom type pairs to validate.
        lj_cutoff:       LJ cutoff in Å (default 12.0 for GAFF2).
        charge_tol:      Maximum allowed |net charge| in e (default 0.01).
        params_file:     Optional path to an EMC-generated .params file. When
                         provided, "Coeffs section missing" errors are suppressed
                         — EMC TraPPE-UA and PCFF .data files store coefficients
                         in the params file, not in the .data file.

    Returns:
        dict with:
            info       — n_atoms, n_atom_types, box, atom type names, h_type_ids
            validation — {valid, errors, warnings, stats}
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
        return {
            "status":     "success",
            "data_file":  data_file,
            "info":       info,
            "validation": vr,
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

    Returns:
        dict with script content, output path, and params used.
    """
    try:
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
        )

        # For Tg staircases, compute and return the number of temperature steps so workers
        # can pass n_stages to run_lammps_script without re-implementing the list logic.
        n_tg_stages = 0
        if template_name == "npt_tg_step" and "T_END" in params and "T_STEP" in params:
            merged = {**TEMPLATE_DEFAULTS["npt_tg_step"], **params}
            _t = float(merged.get("T_START", 450.0))
            _end = float(params["T_END"])
            _step = float(params["T_STEP"])
            _temps: list = []
            while _t > _end + 1e-6:
                _temps.append(_t); _t -= _step
            if not _temps or abs(_temps[-1] - _end) > 1e-6:
                _temps.append(_end)
            n_tg_stages = len(_temps)

        return {
            "status":         "success",
            "template":       template_name,
            "output_script":  output_script,
            "params_used":    {**TEMPLATE_DEFAULTS[template_name], **params},
            "system_info":    gen.get_system_info(),
            "n_tg_stages":    n_tg_stages,
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
    log_file: str = "lammps_run.log",
    use_gpu: bool = True,
    engine: str = "gpu",
    progress_file: str = "",
    n_stages: int = 0,
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
                          via CUDA_VISIBLE_DEVICES=. Required for compute born/matrix
                          numdiff, which displaces atoms in CPU arrays and is
                          incompatible with GPU device-side neighbor lists.
                          (use_gpu=False forces engine="cpu" regardless of engine.)
        engine:           Execution engine: "gpu" (default; GPU package, pairwise on GPU),
                          "kokkos" (full-offload — pair+class2 bonded+pppm+neigh on GPU via
                          the KOKKOS binary, -sf kk), or "cpu". The KOKKOS path uses
                          LAMBDA_LAMMPS_KOKKOS and is ~7.9× faster on PCFF at mpi=1.

    Returns:
        dict with run_id for status polling via get_run_status().
    """
    try:
        # Ensure remote work directory exists
        Path(work_dir).mkdir(parents=True, exist_ok=True)

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
    data_file: Optional[str] = None,
    h_type_ids: Optional[list] = None,
    backbone_types: Optional[list] = None,
    params_file: str = "",
    engine: str = "gpu",
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

        # Start a background thread that polls the remote progress file and writes
        # a local sentinel when the nohup chain finishes — enabling Monitor-based
        # auto-continuation without Claude polling.
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
    Writes a sentinel file when the chain completes or fails so Claude can
    be notified via the Monitor tool without polling get_run_status().
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

        if chain_end:
            if chain_end["status"] == "completed":
                status = "completed"
            else:
                status = "failed"
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
            "progress_file":    progress_file,
            "pid":              run["meta"].get("pid"),
            "note":             "Status read live from progress file — survives MCP restarts.",
        }

    return run


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
    Return a shell command Claude can pass to the Monitor tool to be notified
    automatically when a run completes — no polling required.

    Call this immediately after run_lammps_chain(), run_lammps_script(), or
    any analysis tool. Then invoke the Monitor tool with the returned command.
    The Monitor will block until the sentinel file appears and print its
    contents; the harness re-invokes Claude at that point to continue the
    workflow.

    Args:
        run_id: The run_id or chain_id to watch.

    Returns:
        monitor_command:        pass to the Monitor tool with timeout_ms=3600000.
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



@mcp.tool()
def generate_equilibration_workflow(
    data_file: str,
    work_dir_base: str,
    polymer_name: str = "polymer",
    temp: float = 300.0,
    max_temp: float = 600.0,
    press: float = 1.0,
    max_press: float = 50000.0,
    n_chains: int = 6,
    n_atoms: Optional[int] = None,
    use_pcff: bool = False,
    use_trappe: bool = False,
    use_opls: bool = False,
    params_file: str = "",
    npt_prod_steps: Optional[int] = None,
    add_melt_npt: bool = False,
    t_equil_K: Optional[float] = None,
    melt_npt_steps: Optional[int] = None,
    add_300k_production: bool = True,
    engine: str = "gpu",
) -> dict:
    """
    Auto-generate a complete equilibration workflow as a sequence of
    LAMMPS scripts. Mirrors the Larsen 21-step logic but with full
    parameter control.

    Protocol (7-run chain, rubbery: temp ≤ 300 K):
      minimize         - energy minimization in amorphous cell
      nvt_softheat     - NVT heat from 300 K to max_temp
      npt_compress     - NPT compress to max_press at max_temp
      npt_pppm         - NPT decompress from max_press to 1 atm
      npt_cool         - NPT cool from max_temp to target temp
      nvt_production   - NVT production at target temp (GPU on; MSD/C(t) analysis)
      npt_production   - NPT constant-T/P at target conditions (GPU on; bulk modulus)

    Protocol (9-run chain, glassy: temp > 300 K, add_300k_production=True [default]):
      Runs 1–7: same as above (at melt temperature)
      npt_cool300      - NPT cool temp → 300 K (~1 ns)
      npt_prod300      - NPT constant-T at 300 K (~2 ns) — density and deform source

    Protocol (9-run chain, add_melt_npt=True, rubbery only: temp < t_equil_K):
      Runs 1–4: unchanged
      npt_cool_melt    - NPT cool max_temp → t_equil_K
      npt_melt         - NPT isothermal at t_equil_K (melt density extraction)
      npt_cool         - NPT cool t_equil_K → temp  (replaces standard npt_cool)
      Runs 6–7: unchanged

    Args:
        data_file:      Path to the .data file.
        work_dir_base:  Base directory for all stage subdirectories.
        polymer_name:   Label used in filenames and log comments.
        temp:           Target simulation temperature (K).
        max_temp:       Peak annealing temperature (K). Typically 2x Tg.
        press:          Target pressure (atm), typically 1.
        max_press:      Compression pressure (atm), typically 50000.
        n_chains:       Number of polymer chains (informational).
        n_atoms:        Total atom count. Auto-detected if not provided.
        npt_prod_steps: Explicit step count for npt_production run. When None
                        (default), uses steps_npt // 2 from the atom-count tier.
                        Convert from ns: int(t_ns * 1e6 / dt_fs).
        engine:         Execution engine stamped into every GPU stage deck: "gpu"
                        (default; renders `package gpu`) or "kokkos" (renders no GPU
                        package — `-sf kk` rewrites styles to /kk at launch). Submit
                        the chain with the matching engine= in run_lammps_chain().
        use_pcff:       Set True for EMC/PCFF class2 systems (PCBN, PAMD, PKTN,
                        PSFO, PIMD, POXI, PEST, PSUL, PURT, PANH, PPHS, PACR,
                        PIMN, PVNL, PPNL). Switches all templates to class2
                        styles, sixthpower mixing, and full 1-4 interactions.
                        SHAKE is disabled (PCFF runs cleanly at 1 fs without it).
        use_trappe:     Set True for EMC/TraPPE-UA systems (PHYC, PDIE, PSTR).
                        Switches all templates to pair_style lj/cut 14.0 (no
                        kspace), multi/harmonic dihedrals, and SHAKE on all
                        C-C bond types (enables dt=2 fs for npt_pppm through npt_production).
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
        add_melt_npt:        If True and temp < t_equil_K, replace npt_cool with three
                             runs: npt_cool_melt (max_temp→t_equil_K), npt_melt
                             (isothermal at t_equil_K), npt_cool (t_equil_K→temp).
                             npt_melt is the melt density extraction target.
                             Default False (standard 7-run workflow).
        t_equil_K:           Melt equilibration temperature (K). Required when
                             add_melt_npt=True. Must satisfy temp < t_equil_K < max_temp.
        melt_npt_steps:      Step count for npt_melt isothermal run. Defaults to
                             int(1.0e6 / dt_prod) (≈1 ns at the production timestep).
        add_300k_production: When True (default) and temp > 300.0, append npt_cool300
                             (T→300 K, ~1 ns) and npt_prod300 (300 K constant-T, ~2 ns).
                             These provide density and deformation input for glassy polymers.
                             npt_production_log/dir in the return dict point to npt_prod300
                             when present. Set False only for diagnostic or rubbery-at-high-T runs.

    Returns:
        dict with:
            stages       - list of stage dicts (script_path, work_dir, params)
            run_order    - ordered list of stage names
            instructions - how to execute this workflow
    """
    try:
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

        # PCFF class2 cells from EMC start at ~0.5× experimental density — no
        # separate soft-heat or cutoff-only compression phase needed.
        # SHAKE is off: PCFF runs stably at 1 fs all-atom without constraints.
        # TraPPE-UA: united-atom (no H), pure lj/cut, no kspace.
        # SHAKE is disabled — UA removes fast C-H stretch modes, so 2 fs is stable
        # WITHOUT bond constraints. fix shake on a continuous backbone would fail in
        # LAMMPS anyway (interior atoms have 2 bonds; cluster-build requires terminal atoms).
        # The 2 fs speedup comes from timestep increase alone (dt_prod below).
        if use_pcff:
            ff_base = {"use_pcff": True, "use_shake": False}
        elif use_trappe:
            ff_base = {
                "use_trappe": True,
                "use_shake":  False,
                "use_pppm":   False,
                "LJ_CUTOFF":  14.0,
            }
        elif use_opls:
            ff_base = {"use_opls": True, "use_shake": False}
        else:
            ff_base = {}
        if params_file:
            ff_base["params_file"] = params_file
        # Carry the execution engine into every stage deck. GPU-enabled stages render the matching
        # accelerator package (gpu → `package gpu`; kokkos → none, -sf kk handles it); use_gpu=False
        # stages ignore it and stay CPU. Submit the chain with the SAME engine (run_lammps_chain).
        ff_base["engine"] = engine

        # TraPPE-UA with SHAKE enables 2 fs timestep for npt_pppm through npt_production.
        # Stages 02-03 keep 0.5 fs (chain overlap risk at startup is too high for large dt).
        dt_prod = 2.0 if use_trappe else 1.0

        stages = []

        def _stage(name, template, p, prev_data):
            stage_dir = f"{work_dir_base}/{name}"
            script    = f"{stage_dir}/{name}.in"
            out_data  = f"{stage_dir}/{name}_out.data"
            p = {
                "LOG_FILE":        f"{name}.log",
                "DUMP_FILE":       f"{name}.dump",
                "LAST_DUMP_FILE":  f"{name}_last.dump",
                "WRITE_DATA_FILE": out_data,
                **p,        # stage params first (lower priority for FF keys)
                **ff_base,  # ff_base last — ensures use_shake/use_pcff/params_file always win
            }
            Path(stage_dir).mkdir(parents=True, exist_ok=True)
            gen.generate(
                template_name=template,
                output_path=script,
                params=p,
                data_file_override=prev_data,
            )
            return {
                "name":            name,
                "template":        template,
                "script":   script,
                "work_dir": stage_dir,
                "input_data":      prev_data,
                "output_data":     out_data,
                "params":          p,
            }

        # minimize
        s1 = _stage("minimize", "minimize", {
            "use_pppm":  True,
            "use_gpu":   True,
            "MIN_STYLE": "cg",
            "MAXITER":   50000,
        }, data_file)
        stages.append(s1)

        # nvt_softheat — GPU + PPPM throughout
        s2 = _stage("nvt_softheat", "nvt", {
            "T_START":    300.0,
            "T_FINAL":    max_temp,
            "T_DAMP":     50.0,
            "TIMESTEP":   0.5,
            "N_STEPS":    steps_comp,
            "use_pppm":   True,
            "use_gpu":    True,
            "use_shake":  False,
            "init_velocity": 300.0,
        }, s1["output_data"])
        stages.append(s2)

        # npt_compress — NPT compression to target density.
        # OPLS-AA: use short-range Coulomb (use_pppm=False → lj/cut/coul/cut) during compression
        # to prevent PPPM "out of range atoms" crash when the box shrinks rapidly at high pressure.
        # Full PPPM resumes at npt_pppm. ff_base temporarily overridden so use_pppm=False wins.
        saved_ff_base = ff_base
        ff_base = {**ff_base, "use_pppm": False} if use_opls else ff_base
        s3 = _stage("npt_compress", "npt_compress", {
            "T_START":   max_temp,
            "T_FINAL":   max_temp,
            "T_DAMP":    100.0,
            "P_START":   1.0,
            "P_FINAL":   max_press,
            "P_DAMP":    1000.0,
            "TIMESTEP":  0.5,
            "N_STEPS":   steps_comp,
            "use_pppm":  False,
            "use_gpu":   True,
        }, s2["output_data"])
        stages.append(s3)
        ff_base = saved_ff_base  # restore PPPM for all subsequent stages

        # npt_pppm — NPT decompress, GPU + PPPM
        s4 = _stage("npt_pppm", "npt", {
            "T_START":   max_temp,
            "T_FINAL":   max_temp,
            "T_DAMP":    100.0,
            "P_START":   max_press,
            "P_FINAL":   press,
            "P_DAMP":    1000.0,
            "TIMESTEP":  dt_prod,
            "N_STEPS":   steps_comp,
            "use_pppm":  True,
            "use_gpu":   True,
            "write_restart": True,
        }, s3["output_data"])
        stages.append(s4)

        # npt_cool — NPT cool to target temp.
        # With add_melt_npt=True (rubbery validation runs): split into npt_cool_melt/npt_melt/npt_cool
        # to capture an isothermal NPT run at t_equil_K for melt density extraction.
        _use_melt_npt = (
            add_melt_npt
            and t_equil_K is not None
            and temp < t_equil_K
        )
        if _use_melt_npt:
            _melt_steps = melt_npt_steps or int(1.0e6 / dt_prod)
            s5a = _stage("npt_cool_melt", "npt", {
                "T_START":   max_temp,
                "T_FINAL":   t_equil_K,
                "T_DAMP":    100.0,
                "P_START":   press,
                "P_FINAL":   press,
                "P_DAMP":    1000.0,
                "TIMESTEP":  dt_prod,
                "N_STEPS":   steps_npt // 2,
                "use_pppm":  True,
                "use_gpu":   True,
                "write_restart": True,
            }, s4["output_data"])
            stages.append(s5a)
            s5b = _stage("npt_melt", "npt", {
                "T_START":   t_equil_K,
                "T_FINAL":   t_equil_K,
                "T_DAMP":    100.0,
                "P_START":   press,
                "P_FINAL":   press,
                "P_DAMP":    1000.0,
                "TIMESTEP":  dt_prod,
                "N_STEPS":   _melt_steps,
                "use_pppm":  True,
                "use_gpu":   True,
                "write_restart": True,
            }, s5a["output_data"])
            stages.append(s5b)
            s5 = _stage("npt_cool", "npt", {
                "T_START":   t_equil_K,
                "T_FINAL":   temp,
                "T_DAMP":    100.0,
                "P_START":   press,
                "P_FINAL":   press,
                "P_DAMP":    1000.0,
                "TIMESTEP":  dt_prod,
                "N_STEPS":   steps_npt,
                "use_pppm":  True,
                "use_gpu":   True,
                "write_restart": True,
            }, s5b["output_data"])
            stages.append(s5)
        else:
            s5 = _stage("npt_cool", "npt", {
                "T_START":   max_temp,
                "T_FINAL":   temp,
                "T_DAMP":    100.0,
                "P_START":   press,
                "P_FINAL":   press,
                "P_DAMP":    1000.0,
                "TIMESTEP":  dt_prod,
                "N_STEPS":   steps_npt,
                "use_pppm":  True,
                "use_gpu":   True,
                "write_restart": True,
            }, s4["output_data"])
            stages.append(s5)

        # nvt_production — NVT production, GPU + PPPM
        s6 = _stage("nvt_production", "nvt", {
            "T_START":   temp,
            "T_FINAL":   temp,
            "T_DAMP":    100.0,
            "TIMESTEP":  dt_prod,
            "N_STEPS":   steps_nvt,
            "use_pppm":  True,
            "use_gpu":   True,
            "write_restart": False,
        }, s5["output_data"])
        stages.append(s6)

        # npt_production — NPT production at target conditions, dedicated for K_T measurement.
        # Must be constant-T/P; the npt_cool ramp is invalid for volume fluctuation method.
        # Reads from nvt_production output (best-equilibrated config).
        steps_npt_prod = npt_prod_steps if npt_prod_steps is not None else steps_npt // 2
        s7 = _stage("npt_production", "npt", {
            "T_START":       temp,
            "T_FINAL":       temp,
            "T_DAMP":        100.0,
            "P_START":       press,
            "P_FINAL":       press,
            "P_DAMP":        1000.0,
            "TIMESTEP":      dt_prod,
            "N_STEPS":       steps_npt_prod,
            "use_pppm":      True,
            "use_gpu":       True,
            "write_restart": False,
        }, s6["output_data"])
        stages.append(s7)

        # npt_cool300 + npt_prod300 (glassy only): cool and produce at 300 K.
        # temp > 300 means the chain runs at melt T; density and deform inputs
        # must come from a constant-T 300 K run, not the cooling-ramp tail.
        _add_300k = add_300k_production and temp > 300.0
        s8 = s9 = None
        if _add_300k:
            steps_cool300 = int(1.0e6 / dt_prod)   # ~1 ns
            steps_prod300 = int(2.0e6 / dt_prod)   # ~2 ns
            s8 = _stage("npt_cool300", "npt", {
                "T_START":       temp,
                "T_FINAL":       300.0,
                "T_DAMP":        100.0,
                "P_START":       press,
                "P_FINAL":       press,
                "P_DAMP":        1000.0,
                "TIMESTEP":      dt_prod,
                "N_STEPS":       steps_cool300,
                "use_pppm":      not use_trappe,
                "use_gpu":       True,
                "write_restart": False,
            }, s7["output_data"])
            stages.append(s8)
            s9 = _stage("npt_prod300", "npt", {
                "T_START":       300.0,
                "T_FINAL":       300.0,
                "T_DAMP":        100.0,
                "P_START":       press,
                "P_FINAL":       press,
                "P_DAMP":        1000.0,
                "TIMESTEP":      dt_prod,
                "N_STEPS":       steps_prod300,
                "use_pppm":      not use_trappe,
                "use_gpu":       True,
                "write_restart": False,
            }, s8["output_data"])
            stages.append(s9)

        # npt_production_log/dir point to npt_prod300 (glassy) or npt_production (rubbery)
        _npt_final = s9 if _add_300k else s7
        ret = {
            "status":     "success",
            "polymer":    polymer_name,
            "n_atoms":    n_atoms,
            "temp":       temp,
            "max_temp":   max_temp,
            "n_stages":   len(stages),
            "engine":     engine,
            "stages":     stages,
            "run_order":  [s["name"] for s in stages],
            "npt_production_log": f"{_npt_final['work_dir']}/{_npt_final['params']['LOG_FILE']}",
            "npt_production_dir": _npt_final["work_dir"],
            "preflight_warnings": vr["warnings"],
            "preflight_stats":    vr["stats"],
            "instructions": (
                f"Generated {len(stages)} staged scripts for {polymer_name} (engine={engine}).\n"
                "Execute in order using run_lammps_script().\n"
                "GPU is ON for all stages.\n"
                f"Pass engine='{engine}' to run_lammps_chain() so the launch flags match the decks.\n"
                + (
                    "npt_cool300 + npt_prod300 cool to 300 K and produce at 300 K — use npt_prod300 for density and deformation.\n"
                    if _add_300k else
                    "npt_production is a constant-T/P NPT run for bulk modulus (volume fluctuation method).\n"
                )
                + "Submit stages as a chain using run_lammps_chain()."
            ),
        }
        if _add_300k:
            ret["npt_prod300_log"]  = f"{s9['work_dir']}/{s9['params']['LOG_FILE']}"
            ret["npt_prod300_data"] = s9["output_data"]
            ret["npt_prod300_dump"] = f"{s9['work_dir']}/{s9['params']['DUMP_FILE']}"
        if _use_melt_npt:
            ret["melt_npt_log"] = f"{s5b['work_dir']}/{s5b['params']['LOG_FILE']}"
            ret["melt_npt_dir"] = s5b["work_dir"]
        return ret

    except Exception as e:
        logger.error(f"generate_equilibration_workflow failed: {e}")
        return {"status": "error", "error": str(e)}


# ─── Analysis tools (Tg, density, convergence, bulk modulus) ─────────────────
#
# These tools run Python analysis scripts locally and track their
# progress through run_manager — poll with get_run_status() / get_run_output().

def _parse_json_from_stdout(stdout: str, stderr: str) -> dict:
    """Scan stdout bottom-up for the first valid JSON line. Returns error dict on failure."""
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"status": "failed", "error": "No JSON found in stdout",
            "stdout": stdout, "stderr": stderr}


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
        output_dir:     Output directory. Defaults to <dump_dir>/analysis.
        atom_style:     LAMMPS atom_style column order for the data file.

    Returns:
        dict with run_id.  Completed result includes per_chain stats and csv_file path.
    """
    if output_dir is None:
        output_dir = str(Path(dump_file).parent / "analysis")

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
        output_dir:       Output directory. Defaults to <dump_dir>/analysis.
        atom_style:       LAMMPS atom_style column order for the data file.

    Returns:
        dict with run_id.  Completed result includes rdf_files paths and
        pairs_computed list.
    """
    if output_dir is None:
        output_dir = str(Path(dump_file).parent / "analysis")

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
            "re-spawn tg-sweep-worker with --tg_t_high_K +50 and --tg_t_low_K −50."
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
    output_dir: Optional[str] = None,
    graphs_dir: Optional[str] = None,
    initial_tg_guess: Optional[float] = None,
    equilibration_fraction: float = 0.5,
    temp_col: str = "Temp",
    density_col: str = "Density",
    enthalpy_col: str = "Enthalpy",
    per_t_dump_file: Optional[str] = None,
    tg_data_file: Optional[str] = None,
    backbone_types: Optional[List[str]] = None,
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
        per_t_dump_file:        Path to per-T structural dump written by the
                                Tg staircase (one frame per T step, cooling order).
                                Enables dump-based structural analysis.
        tg_data_file:           LAMMPS .data file used as input to the Tg sweep
                                (topology/masses). Required for ΔCp mass
                                normalisation and MDAnalysis structural analysis.
        backbone_types:         Backbone atom type IDs (list of strings/ints).
                                Used for P2 nematic order computation.

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
    if output_dir is None:
        output_dir = str(Path(log_file).parent / "tg_analysis")

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


# ── Tool: extract_tg_multirate ───────────────────────────────────────────────

def _run_extract_tg_multirate(
    rates: list,
    tg_values: list,
    output_dir: str,
    polymer_name: str,
    slow_rate_ref: float,
) -> dict:
    """Background worker — runs extract_tg_multirate.py via CLI."""
    rate_args = " ".join(str(r) for r in rates)
    tg_args   = " ".join(str(t) for t in tg_values)
    parts = [
        f"python {MDA_SCRIPTS_DIR}/extract_tg_multirate.py",
        f"--rates {rate_args}",
        f"--tg_values {tg_args}",
        f"--output_dir {output_dir}",
        f"--polymer_name {polymer_name}",
        f"--slow_rate_ref {slow_rate_ref}",
        "--no_plot",
    ]
    command = " ".join(parts)
    logger.info(f"Running multi-rate Tg analysis: {command}")
    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=120)
    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def extract_tg_multirate(
    rates_K_per_ns: list,
    tg_values_K: list,
    output_dir: str,
    polymer_name: str = "polymer",
    slow_rate_ref_K_per_ns: float = 5.0,
) -> dict:
    """
    Fit a log-linear trend and attempt a Vogel-Fulcher (VF) extrapolation
    across multiple cooling-rate Tg_MD values.

    Primary output: log-linear slope (K per ln(K/ns)) and Tg at the
    reference slow rate — this is the reliable deliverable for comparing
    trend vs. Ramos 2015 Fig. 3.

    Secondary output: VF extrapolated Tg0 (at Γ → 0).  Note that < 2 decades
    of rate coverage gives a poorly-constrained VF fit; CI > 100 K is flagged
    POORLY_CONSTRAINED.

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        rates_K_per_ns:          List of cooling rates in K/ns (same order as tg_values_K).
        tg_values_K:             Tg_MD values in K from extract_thermal runs at each rate.
        output_dir:              Directory for JSON, markdown, and plot outputs.
        polymer_name:            Label for outputs and plot title.
        slow_rate_ref_K_per_ns:  Reference rate for log-linear Tg reporting (default 5.0).

    Returns:
        dict with run_id.  Result includes loglinear_slope_K, loglinear_r_squared,
        tg_at_slow_rate_K, vf_fit_quality, tg0_K (if VF converged), d06_markdown.
    """
    run_id = run_manager.create(
        "extract_tg_multirate",
        {"output_dir": output_dir, "n_rates": len(rates_K_per_ns)},
    )
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_extract_tg_multirate, dict(
            rates       = rates_K_per_ns,
            tg_values   = tg_values_K,
            output_dir  = output_dir,
            polymer_name = polymer_name,
            slow_rate_ref = slow_rate_ref_K_per_ns,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":     "submitted",
        "run_id":     run_id,
        "run_type":   "extract_tg_multirate",
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
    ]
    if n_backbone_bonds is not None:
        parts.append(f"--n_backbone_bonds {n_backbone_bonds}")
    if graphs_dir:
        parts.append(f"--graphs_dir {graphs_dir}")
    if ct_min_decay is not None:
        parts.append(f"--ct_min_decay {ct_min_decay}")

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
    output_dir: Optional[str] = None,
    graphs_dir: Optional[str] = None,
    skip_frames: int = 50,
    timestep_fs: float = 1.0,
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
    ct_min_decay: Optional[float] = None,
) -> dict:
    """
    Comprehensive polymer equilibration validator — thermo + structural checks in
    a single call, single overall_pass verdict, auto-generated D-05 markdown block.

    Hard gates (block overall_pass=True):
      A. Density drift (regression p-value + magnitude)
      B. Energy drift
      C. Density block-SEM < 1% of mean (Flyvbjerg-Petersen)
      D. Energy block-SEM < 1% of mean
      E. Rg CV across chains < 30%  (unequal conformation flag)
      F. P2 nematic order < 0.10    (residual backbone alignment)
      G. Density homogeneity voxel CV < 25%  (adaptive grid; corrects 10³ false positives)

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
        dump_file:           LAMMPS dump trajectory (e.g. 06_nvt_production.dump).
        data_file:           LAMMPS .data topology file.
        backbone_types:      List of LAMMPS atom type IDs that form the backbone.
                             Determine from inspect_data_file() — do not guess.
        output_dir:          Output directory (default: <dump_dir>/eq_comprehensive).
        skip_frames:         Frames to skip at start of dump (production window start).
        timestep_fs:         MD timestep in femtoseconds.
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
    if output_dir is None:
        output_dir = str(Path(dump_file).parent / "eq_comprehensive")

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

    command = " ".join(parts)
    logger.info(f"Running equilibrated density extraction via CLI: {command}")

    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=36000)

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def extract_equilibrated_density(
    log_file: str,
    output_dir: Optional[str] = None,
    eq_fraction: float = 0.5,
    target_temp: Optional[float] = None,
    temp_tolerance: float = 50.0,
    plateau_shift_sigma: float = 1.0,
    density_col: str = "Density",
    temp_col: str = "Temp",
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
            tau_eff_frames           — autocorrelation time (batch-means plateau, F&P 1989)
            tau_eff_fraction         — tau_eff / n_plateau
            n_effective_samples      — n_plateau / (2 * tau_eff)
            drift_slope              — linear regression slope over plateau (g/cm3 per frame)
            drift_pct                — |slope * n| / |mean| * 100
            drift_p_value            — p-value of drift slope
            plateau_equilibrated     — False if drift_pct > 1% AND p < 0.01
            rolling_mean_abs_deriv   — mean |d/dt(rolling mean)|; secondary stationarity check
            naive_mean / naive_std   — simple average of full production window
            plateau_step_range       — [start_step, end_step] of the plateau
            summary_json             — path to summary JSON
    """
    if output_dir is None:
        output_dir = str(Path(log_file).parent / "eq_analysis")

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
    output_dir: Optional[str] = None,
    graphs_dir: Optional[str] = None,
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
        output_dir:   Output directory. Defaults to <log_dir>/bulk_analysis.
                      Defaults to <log_dir>/bulk_analysis.
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
    if output_dir is None:
        output_dir = str(Path(log_file).parent / "bulk_analysis")

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

    command = " ".join(parts)
    logger.info(f"Running deformation bulk modulus extraction via CLI: {command}")

    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=36000)

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def extract_bulk_modulus_deform(
    log_file: str,
    output_dir: Optional[str] = None,
    graphs_dir: Optional[str] = None,
    strain_rate: float = 1e-7,
    strain_max: float = 0.03,
    timestep: float = 1.0,
    eq_steps: int = 200000,
    strain_start: float = 0.002,
    avg_window: int = 2000,
    log_file_2: Optional[str] = None,
    strain_rate_2: Optional[float] = None,
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
        output_dir:   Output directory. Defaults to <log_dir>/deform_analysis.
        strain_rate:  Engineering strain rate in 1/fs (= K_deform_rate_inv_s × 1e-15).
                      Default 1e-7 corresponds to 1e8 s⁻¹ from polymer_rules.json.
        strain_max:   Maximum strain for linear-regime fit (K_strain_max). Default 0.03.
        timestep:     MD timestep in fs (must match simulation). Default 1.0.
        eq_steps:     NVT pre-equilibration steps (N_EQ_STEPS) — skipped in analysis.
        strain_start: Minimum strain to include in fit (skip initial transient). Default 0.002.
        avg_window:   Rolling-average window in thermo frames applied to stress before fitting.
                      Thermal noise (~0.2 GPa at THERMO_FREQ=100) swamps the elastic signal
                      (~0.09 GPa at 3% strain) on individual thermo rows. Default 2000 = 200 ps
                      at THERMO_FREQ=100. Set to 1 to disable. Scale with THERMO_FREQ if changed.
        log_file_2:   Optional second deformation log (slow-rate run) for rate-sensitivity check.
                      When provided, K is extracted independently from both logs and compared.
        strain_rate_2: Strain rate for log_file_2 in 1/fs. Required if log_file_2 is set.

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
    if output_dir is None:
        output_dir = str(Path(log_file).parent / "deform_analysis")

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
    npt_steps: int = 500000,
    dt_fs: float = 1.0,
    thermo_freq: int = 100,
    output_dir: Optional[str] = None,
    use_trappe: bool = False,
    use_pcff: bool = False,
    use_opls: bool = False,
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
        pressures_atm:  List of target pressures in atm (at least 3).
        temp_K:         Simulation temperature (K). Use 300 K for property measurement.
        run_name:       Human-readable label for logging.
        npt_steps:      MD steps per pressure point. Default 500000 (500 ps at dt=1 fs).
        dt_fs:          Timestep in fs. Default 1.0.
        thermo_freq:    Thermo output frequency. Default 100.
        gpu_ids:        Comma-separated GPU IDs (e.g. "0" or "0,1"). Required —
                        no default; the engine no longer falls back to GPU 0,1.
        mpi:            MPI processes. Required — no default.
        output_dir:     Where to store the list of log file paths (JSON).
                        Defaults to work_dir.
        use_trappe:     Set True for TraPPE-UA systems (PHYC, PDIE). Emits lj/cut +
                        neigh yes instead of PPPM/CHARMM defaults. Mirrors the same
                        flag in generate_equilibration_workflow and generate_script.
        use_pcff:       Set True for PCFF (Class II) systems. Emits pppm + class2 pair.
        use_opls:       Set True for OPLS-AA systems. Emits pppm + lj/cut/coul/long.

    Returns:
        dict with chain_id, monitor_command, log_files (list of expected log paths),
        and pressures_atm. Pass log_files and pressures_atm to
        extract_bulk_modulus_murnaghan after the chain completes.
    """
    try:
        if len(pressures_atm) < 3:
            return {
                "status": "error",
                "error": f"At least 3 pressure points required for Murnaghan fit "
                         f"(got {len(pressures_atm)})."
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
                params={
                    "T_START":     temp_K,
                    "T_FINAL":     temp_K,
                    "P_START":     float(p_atm),
                    "P_FINAL":     float(p_atm),
                    "N_STEPS":     npt_steps,
                    "TIMESTEP":    dt_fs,
                    "THERMO_FREQ": thermo_freq,
                    "LOG_FILE":    log_path,
                    "use_gpu":     True,
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
                "log_file": log_path,
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
) -> dict:
    """Background worker — runs extract_bulk_modulus_murnaghan.py via CLI."""
    parts = [f"python {MDA_SCRIPTS_DIR}/extract_bulk_modulus_murnaghan.py"]
    parts.append("--log_files " + " ".join(str(f) for f in log_files))
    parts.append("--pressures_atm " + " ".join(str(p) for p in pressures_atm))
    parts.append(f"--output_dir {output_dir}")
    parts.append(f"--eq_fraction {eq_fraction}")
    if graphs_dir:
        parts.append(f"--graphs_dir {graphs_dir}")

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
    graphs_dir: Optional[str] = None,
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

    Output files written to output_dir:
        bulk_modulus_murnaghan.json  — B0_GPa, B0_prime, V0_A3, r_squared, …
                                       Also contains bulk_modulus_GPa alias for
                                       compatibility with generate_run_summary.
        murnaghan_eos.png            — P vs V scatter with fit curve

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        log_files:      List of LAMMPS log file paths, one per pressure point.
                        Same order as pressures_atm. From run_bulk_modulus_series.
        pressures_atm:  List of target pressures (atm), same order as log_files.
        output_dir:     Directory for bulk_modulus_murnaghan.json output.
        graphs_dir:     Directory for PNG figures. Defaults to output_dir/figures.
        eq_fraction:    Fraction of each log used as production window. Default 0.5.

    Returns:
        dict with run_id.  When completed, result includes:
            B0_GPa          — isothermal bulk modulus (Murnaghan B0)
            B0_prime        — pressure derivative dB/dP
            V0_A3           — reference volume at P=0
            r_squared       — goodness of fit (goal > 0.999)
            bulk_modulus_GPa — alias for B0_GPa (used by generate_run_summary)
            fit_converged   — True if Murnaghan converged, False if linear fallback
            warnings        — list of any quality flags
    """
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
    exp_tg_min: Optional[float],
    exp_tg_max: Optional[float],
    exp_density_min: Optional[float],
    exp_density_max: Optional[float],
    exp_K_min: Optional[float],
    exp_K_max: Optional[float],
    graphs_dir: Optional[str] = None,
    n_replicates: Optional[int] = None,
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
    if exp_tg_min is not None:      parts.append(f"--exp_tg_min {exp_tg_min}")
    if exp_tg_max is not None:      parts.append(f"--exp_tg_max {exp_tg_max}")
    if exp_density_min is not None: parts.append(f"--exp_density_min {exp_density_min}")
    if exp_density_max is not None: parts.append(f"--exp_density_max {exp_density_max}")
    if exp_K_min is not None:       parts.append(f"--exp_K_min {exp_K_min}")
    if exp_K_max is not None:       parts.append(f"--exp_K_max {exp_K_max}")
    if graphs_dir:                  parts.append(f"--graphs_dir {graphs_dir}")
    if n_replicates is not None:    parts.append(f"--n_replicates {n_replicates}")

    command = " ".join(parts)
    logger.info(f"Running generate_run_summary via CLI: {command}")
    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=60)
    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


# ── Tool: extract_bulk_modulus_born ──────────────────────────────────────────

def _run_extract_bulk_modulus_born(
    born_matrix_file: str,
    log_file: str,
    n_atoms: int,
    output_dir: str,
    eq_fraction: float,
    block_count: int,
    graphs_dir: Optional[str] = None,
) -> dict:
    """Background worker — runs extract_bulk_modulus_born.py via CLI."""
    parts = [f"python {MDA_SCRIPTS_DIR}/extract_bulk_modulus_born.py"]
    parts.append(f"--born_matrix_file {born_matrix_file}")
    parts.append(f"--log_file {log_file}")
    parts.append(f"--n_atoms {n_atoms}")
    parts.append(f"--output_dir {output_dir}")
    parts.append(f"--eq_fraction {eq_fraction}")
    parts.append(f"--block_count {block_count}")
    if graphs_dir:
        parts.append(f"--graphs_dir {graphs_dir}")

    command = " ".join(parts)
    logger.info(f"Running Born bulk modulus extraction via CLI: {command}")
    stdout, stderr, exit_code = _conda_run(command, workdir=LAMBDA_WORKDIR, timeout=36000)
    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def extract_bulk_modulus_born(
    born_matrix_file: str,
    log_file: str,
    n_atoms: int,
    output_dir: Optional[str] = None,
    graphs_dir: Optional[str] = None,
    eq_fraction: float = 0.5,
    block_count: int = 5,
) -> dict:
    """
    Extract isothermal bulk modulus via the Born + NVT stress-fluctuation
    method from an nvt_born simulation (Stage 8, glassy polymers only).

    Method:
        K_T = K_Born + NkT/V − (V/kT)·Var(P)_NVT

    where K_Born is the Born elastic constant bulk average from
    compute born/matrix numdiff (time-averaged over the NVT trajectory),
    NkT/V is the kinetic (ideal-gas) contribution, and Var(P) is the
    variance of isotropic pressure P = (pxx+pyy+pzz)/3 in the NVT ensemble.

    This gives the unrelaxed (high-frequency) isothermal bulk modulus,
    appropriate for comparison with ultrasonic or Brillouin scattering data.
    Rate-free: no NEMD strain-rate artifacts.

    Requires:
      - born_matrix_file: fix ave/time output from nvt_born template
        (columns: TimeStep b11 b22 b33 b12 b13 b23 in atm)
      - log_file: NVT log with pxx, pyy, pzz, vol, temp columns
      - n_atoms: total atom count (from inspect_data_file or born-worker RESULT)

    Output files written to output_dir:
        bulk_modulus_born.json   — full results and diagnostics
        born_matrix_timeseries.png — Born elements + pressure time series

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        born_matrix_file: Path to fix ave/time Born matrix output.
        log_file:         Path to nvt_born LAMMPS log.
        n_atoms:          Number of atoms in simulation cell.
        output_dir:       Output directory (defaults to <log_dir>/born_analysis).
        eq_fraction:      Fraction of rows used as production window (last eq_fraction).
        block_count:      Number of blocks for block-average uncertainty.

    Returns:
        dict with run_id. When completed, result includes:
            bulk_modulus_GPa         — K_T in GPa
            bulk_modulus_sem_GPa     — block-average SEM in GPa
            K_Born_GPa               — Born contribution alone
            kinetic_term_GPa         — NkT/V contribution
            fluctuation_correction_GPa — (V/kT)·Var(P) correction
            V_mean_A3, T_mean_K      — thermodynamic averages
            Var_P_atm2               — pressure variance
            n_effective_samples      — τ_eff-corrected sample count
            block_averaging          — per-block K values and SEM
            diagnostics              — full term breakdown and statistics
            summary_json             — path to bulk_modulus_born.json
    """
    if output_dir is None:
        output_dir = str(Path(log_file).parent / "born_analysis")

    run_id = run_manager.create("extract_bulk_modulus_born",
                                {"born_matrix_file": born_matrix_file, "output_dir": output_dir})
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_extract_bulk_modulus_born, dict(
            born_matrix_file = born_matrix_file,
            log_file         = log_file,
            n_atoms          = n_atoms,
            output_dir       = output_dir,
            eq_fraction      = eq_fraction,
            block_count      = block_count,
            graphs_dir       = graphs_dir,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":            "submitted",
        "run_id":            run_id,
        "run_type":          "extract_bulk_modulus_born",
        "born_matrix_file":  born_matrix_file,
        "log_file":          log_file,
        "output_dir":        output_dir,
        "message":           "Poll with get_run_status(run_id)",
    }


@mcp.tool()
def generate_run_summary(
    output_dir: str,
    run_name: str,
    graphs_dir: Optional[str] = None,
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
    exp_tg_min: Optional[float] = None,
    exp_tg_max: Optional[float] = None,
    exp_density_min: Optional[float] = None,
    exp_density_max: Optional[float] = None,
    exp_K_min: Optional[float] = None,
    exp_K_max: Optional[float] = None,
    n_replicates: Optional[int] = None,
) -> dict:
    """
    Aggregate all Stage 4 analysis outputs into a single run_summary.json.

    Reads all JSON files written by the analysis tools in output_dir and
    assembles a canonical summary mirroring the run_log.md sections:
    run metadata, decisions (D-01 through D-06), results (Tg, density,
    bulk modulus), convergence, structural checks, artifact paths, and
    provenance (git commit, MDAnalysis version, timestamp).

    Call as the final step of Stage 4, after all analysis tools have run.
    All artifact paths in the summary are relative to data/[RUN]/ in the
    PolyJarvis repo (e.g. "outputs/figures/tg_fit.png").

    Args:
        output_dir:       Absolute path to data/[RUN]/outputs/.
                          All analysis JSON files must already exist here.
        run_name:         Run directory name (e.g. "PS4").
        smiles:           SMILES string for the polymer.
        polymer_class:    Class ID (e.g. "PSTR").
        ff:               Force field name (e.g. "TraPPE-UA").
        simulation_dir:   Absolute path to the simulation base directory.
        charge_method:    Charge method used (e.g. "AM1-BCC", "embedded in FF").
        dp, n_chains, n_atoms: System size parameters.
        date_start, date_end: ISO date strings (e.g. "2026-06-04").
        d01–d06:          Decision strings from run_log.md.
        exp_tg_min/max:   Experimental Tg range (K) for PASS/FAIL status.
        exp_density_min/max: Experimental density range (g/cm³).
        exp_K_min/max:    Experimental bulk modulus range (GPa).
        n_replicates:     Distinct replicates in the multi-rate Tg registry (for the
                          DSC-equivalent extrapolation reported in results.tg).

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
            exp_tg_min=exp_tg_min, exp_tg_max=exp_tg_max,
            exp_density_min=exp_density_min, exp_density_max=exp_density_max,
            exp_K_min=exp_K_min, exp_K_max=exp_K_max,
            graphs_dir=graphs_dir, n_replicates=n_replicates,
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
