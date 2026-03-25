#!/usr/bin/env python3
"""
PolyJarvis LAMMPS Engine MCP Server
=====================================
Provides AI-driven, template-based LAMMPS script generation and remote execution.

Architecture:
  - RadonPy (existing) handles: SMILES -> polymer chain -> amorphous cell -> .data file
  - This server handles: .data file -> filled LAMMPS .in script -> execute on Lambda

Tools exposed:
  ── Simulation ────────────────────────────────────────────────────────────────
  1.  list_templates                  - Show all available simulation templates
  2.  get_template_defaults           - Tunable parameters and defaults for a template
  3.  parse_data_file                 - Extract system info from a .data file
  4.  generate_script                 - Fill a template and write a .in file
  5.  run_lammps_script               - Execute a .in script on the remote server
  6.  run_lammps_chain                - Submit ordered chain of scripts (nohup, crash-safe)
  7.  generate_equilibration_workflow - Auto-generate full 6-stage equilibration protocol
  ── Monitoring ────────────────────────────────────────────────────────────────
  8.  get_run_status                  - Check status of any run or analysis job
  9.  get_run_output                  - Results + log tail from a completed job
  10. list_runs                       - List all submitted runs and analysis jobs
  11. read_remote_log                 - Live-tail a LAMMPS log during a running job
  ── Analysis ──────────────────────────────────────────────────────────────────
  12. unwrap_coordinates              - Write new dump with image-flag-unwrapped coords
  13. extract_end_to_end_vectors      - End-to-end R vectors via MDAnalysis sort_backbone
  14. calculate_rdf                   - g(r) via MDAnalysis InterRDF
  15. check_equilibration             - Drift + block-average convergence check
  16. extract_equilibrated_density    - Plateau density via reverse-cumulative-mean
  17. extract_tg                      - Tg via exhaustive F-stat bilinear fit
  18. extract_bulk_modulus            - Isothermal K via NPT volume fluctuations
  ── Remote Utilities (utilities.py) ──────────────────────────────────────────
  19. list_remote_files               - List files in a remote directory
  20. list_remote_files_detailed      - List files with size + mtime
  21. upload_file_to_remote           - Upload a local file to the remote server
  22. download_file_from_remote       - Download a remote file locally
  23. check_remote_status             - Server status and GPU availability
  24. read_remote_file                - Read full content of a remote file
  25. read_remote_file_tail           - Read last N lines of a remote file
  26. write_remote_file               - Write content to a remote file
  27. execute_remote_shell_command    - Run an arbitrary shell command remotely
  28. check_remote_file_exists        - Check whether a remote path exists
"""

import os
import sys
import json
import uuid
import logging
import threading
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

# Add server directory to path so we can import script_generator
sys.path.insert(0, str(Path(__file__).parent))
from script_generator import ScriptGenerator, TEMPLATE_DOCS, TEMPLATE_DEFAULTS
import utilities

from mcp.server.fastmcp import FastMCP

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [LAMMPS-ENGINE] %(levelname)s %(message)s",
)
logger = logging.getLogger("lammps_engine")

# ─── Remote executor ─────────────────────────────────────────────────────────
from remote_executor import RemoteExecutor

# Connection config — loaded from environment variables.
# Copy .env.example → .env and fill in real values. Never commit .env.
LAMBDA_HOST     = os.environ.get("LAMBDA_HOST",     "YOUR_SERVER_IP")
LAMBDA_USER     = os.environ.get("LAMBDA_USER",     "YOUR_USERNAME")
LAMBDA_KEY      = os.environ.get("LAMBDA_KEY",      "~/.ssh/your_key")
LAMBDA_WORKDIR  = os.environ.get("LAMBDA_WORKDIR",  "/home/YOUR_USERNAME/simulations")
LAMBDA_LAMMPS   = os.environ.get("LAMBDA_LAMMPS",   "/home/YOUR_USERNAME/lammps-install/bin/lmp")
CONDA_ENV       = os.environ.get("CONDA_ENV",       "radonpy")
MDA_SCRIPTS_DIR = os.environ.get("MDA_SCRIPTS_DIR", "/home/YOUR_USERNAME/simulations/analysis_scripts")

executor = RemoteExecutor(
    host=LAMBDA_HOST,
    username=LAMBDA_USER,
    key_path=LAMBDA_KEY,
    remote_workdir=LAMBDA_WORKDIR,
    conda_env=CONDA_ENV,
)
executor.connect()

# ─── Local working directory ──────────────────────────────────────────────────
LOCAL_WORKDIR = Path.home() / "Desktop" / "Research" / "sims"
LOCAL_WORKDIR.mkdir(parents=True, exist_ok=True)

# ─── MCP Server ───────────────────────────────────────────────────────────────
mcp = FastMCP("PolyJarvis LAMMPS Engine")

# Register remote utility tools (file I/O, shell, status)
utilities.register(mcp, executor)

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
# Helper: execute LAMMPS on Lambda in a background thread
# ─────────────────────────────────────────────────────────────────────────────

def _build_chain_script(chain_id: str, stages: list, mpi: int, gpu_ids: str) -> str:
    """
    Generate a self-contained bash script that runs LAMMPS stages sequentially
    on Lambda. Designed to run under nohup so it is fully independent of the
    MCP server process.

    Each completed stage appends a JSON line to chain_progress.jsonl:
        {"stage": "name", "status": "done"|"failed", "ts": "ISO timestamp"}
    A final line with stage=__chain__ marks overall completion or failure.
    """
    n_gpu = len(gpu_ids.split(","))
    lines = [
        "#!/bin/bash",
        f"# PolyJarvis chain {chain_id} — auto-generated, do not edit",
        "set -euo pipefail",
        "",
        f"CHAIN_ID={chain_id}",
        f"LMP={LAMBDA_LAMMPS}",
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
        f"export CUDA_VISIBLE_DEVICES={gpu_ids}",
        "",
    ]

    for i, stage in enumerate(stages):
        name  = stage.get("name", f"stage_{i+1}")
        script = stage["remote_script"]
        wdir  = stage["remote_work_dir"]
        log   = stage.get("log_file", f"{name}_run.log")

        lines += [
            f"# --- Stage {i+1}/{len(stages)}: {name} ---",
            f"mkdir -p {wdir}",
            f"cd {wdir}",  # FIX: cd into stage workdir so relative paths in .in files resolve correctly
            f"log_start {name}",
            f"mpirun -np $MPI $LMP -sf gpu -pk gpu $N_GPU "
            f"-in {script} > {wdir}/{log} 2>&1 \\",
            f"  && log_done {name} \\",
            f"  || {{ log_fail {name}; "
            f"echo \"{{\\\"stage\\\":\\\"__chain__\\\",\\\"status\\\":\\\"failed\\\","
            f"\\\"failed_at\\\":\\\"{name}\\\",\\\"ts\\\":\\\"$(date -Iseconds)\\\"}}\" >> \"$PROGRESS\"; exit 1; }}",
            "",
        ]

    lines += [
        f"echo \"{{\\\"stage\\\":\\\"__chain__\\\",\\\"status\\\":\\\"completed\\\","
        f"\\\"n_stages\\\":{len(stages)},\\\"ts\\\":\\\"$(date -Iseconds)\\\"}}\" >> \"$PROGRESS\"",
    ]

    return "\n".join(lines) + "\n"


def _lammps_run_background(
    run_id: str,
    remote_work_dir: str,
    remote_script: str,
    mpi: int,
    gpu_ids: str,
    log_file: str,
):
    """Background thread: executes LAMMPS on Lambda and updates run_manager."""
    try:
        run_manager.start(run_id)

        n_gpu = len(gpu_ids.split(","))
        cmd = (
            f"export CUDA_VISIBLE_DEVICES={gpu_ids} && "
            f"mpirun -np {mpi} {LAMBDA_LAMMPS} "
            f"-sf gpu -pk gpu {n_gpu} "
            f"-in {remote_script} "
            f"> {remote_work_dir}/{log_file} 2>&1"
        )

        logger.info(f"[{run_id}] Launching LAMMPS: {cmd}")
        stdout, stderr, exit_code = executor.execute_command(
            cmd,
            workdir=remote_work_dir,
            timeout=86400,  # 24h max
        )

        if exit_code == 0:
            run_manager.complete(run_id, {
                "work_dir":   remote_work_dir,
                "log_file":   f"{remote_work_dir}/{log_file}",
                "exit_code":  exit_code,
                "stdout_tail": stdout[-2000:] if stdout else "",
            })
            logger.info(f"[{run_id}] LAMMPS completed successfully")
        else:
            err = stderr[-2000:] if stderr else "no stderr"
            run_manager.fail(run_id, f"LAMMPS exited {exit_code}: {err}")
            logger.error(f"[{run_id}] LAMMPS failed: {err}")

    except Exception as e:
        run_manager.fail(run_id, str(e))
        logger.error(f"[{run_id}] Exception: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tools
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_templates() -> dict:
    """
    List all available LAMMPS simulation templates with their descriptions.

    Returns:
        dict mapping template_name -> description
    """
    return {
        "templates": TEMPLATE_DOCS,
        "usage_tip": (
            "Call get_template_defaults(template_name) to see all tunable "
            "parameters and their default values before generating a script."
        ),
    }


@mcp.tool()
def get_template_defaults(template_name: str) -> dict:
    """
    Get all tunable parameters and their defaults for a given template.

    Args:
        template_name: One of: minimize, nvt, npt, npt_compress,
                       npt_tg_step, nemd_thermal

    Returns:
        dict with parameter names, defaults, and brief explanations
    """
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
def parse_data_file(data_file: str, remote: bool = True) -> dict:
    """
    Parse a RadonPy LAMMPS .data file and extract system information.
    Use this to understand your system before generating scripts.

    Args:
        data_file: Path to the .data file. If remote=True, path on Lambda.
        remote:    If True, reads file from Lambda Labs via SSH.

    Returns:
        dict with n_atoms, n_atom_types, box dimensions, atom type names,
        h_type_ids (for SHAKE), and force field info.
    """
    try:
        if remote:
            content = executor.read_file(data_file)
        else:
            with open(data_file, "r") as f:
                content = f.read()

        gen = ScriptGenerator(data_file=data_file)
        info = gen.parse_data_file(content=content)

        info["gaff2_styles"] = {
            "pair_style":     "lj/charmm/coul/long 8.0 12.0",
            "kspace_style":   "pppm 1e-6",
            "bond_style":     "harmonic",
            "angle_style":    "harmonic",
            "dihedral_style": "fourier",
            "improper_style": "cvff",
        }
        info["note"] = (
            "RadonPy always uses GAFF2/GAFF2_mod. Force field styles are "
            "fixed. Only pair coefficients vary between systems."
        )
        return {"status": "success", "data_file": data_file, "info": info}

    except Exception as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
def generate_script(
    template_name: str,
    data_file: str,
    output_script: str,
    params: dict,
    upload_to_lambda: bool = True,
    remote_output_dir: Optional[str] = None,
) -> dict:
    """
    Generate a filled LAMMPS .in script from a template and optionally
    upload it to Lambda Labs ready to run.

    Args:
        template_name:     Template to use (minimize/nvt/npt/npt_compress/
                           npt_tg_step/nemd_thermal)
        data_file:         Path to RadonPy .data file ON LAMBDA (used as DATA_FILE
                           in the script). This is the remote path.
        output_script:     Local path to write the generated .in file.
        params:            Parameter overrides (see get_template_defaults for options).
                           Common params: T_START, T_FINAL, N_STEPS, T_DAMP,
                           P_START, P_FINAL, P_DAMP, use_gpu, LOG_FILE, DUMP_FILE.
        upload_to_lambda:  If True, upload the generated script to Lambda.
        remote_output_dir: Directory on Lambda to upload the script to.
                           Defaults to dirname of data_file.

    Returns:
        dict with script content, local path, and remote path (if uploaded).
    """
    try:
        gen = ScriptGenerator(data_file=data_file)

        # Try to parse the data file to enrich system info
        try:
            content = executor.read_file(data_file)
            gen.parse_data_file(content=content)
        except Exception:
            logger.warning("Could not parse data file from Lambda; using defaults")

        script = gen.generate(
            template_name=template_name,
            output_path=output_script,
            params=params,
            data_file_override=data_file,  # always use remote path in script
        )

        result = {
            "status":        "success",
            "template":      template_name,
            "local_script":  output_script,
            "remote_script": None,
            "params_used":   {**TEMPLATE_DEFAULTS[template_name], **params},
            "system_info":   gen.get_system_info(),
            "script_preview": script[:1500] + "\n..." if len(script) > 1500 else script,
        }

        if upload_to_lambda:
            remote_dir = remote_output_dir or os.path.dirname(data_file)
            remote_path = os.path.join(remote_dir, os.path.basename(output_script))
            executor.upload_file(output_script, remote_path)
            result["remote_script"] = remote_path
            result["upload_status"] = "uploaded"

        return result

    except Exception as e:
        logger.error(f"generate_script failed: {e}")
        return {"status": "error", "error": str(e)}


@mcp.tool()
def run_lammps_script(
    remote_script: str,
    remote_work_dir: str,
    log_file: str = "lammps_run.log",
    mpi: int = 2,
    gpu_ids: str = "0,1",
) -> dict:
    """
    Execute a LAMMPS .in script on Lambda Labs GPU server in the background.

    Args:
        remote_script:    Full path to .in file on Lambda Labs.
        remote_work_dir:  Working directory on Lambda where outputs will be written.
        log_file:         Name of the stdout/stderr capture log (in remote_work_dir).
        mpi:              Number of MPI processes (= number of GPUs used).
                          Use 1 for small systems (<5k atoms), 2 for medium (5-10k),
                          4 for large (>10k) or Tg sweeps.
        gpu_ids:          Comma-separated GPU IDs to use (e.g. "0,1" or "0,1,2,3").

    Returns:
        dict with run_id for status polling via get_run_status().
    """
    try:
        # Ensure remote work directory exists
        executor.execute_command(f"mkdir -p {remote_work_dir}")

        meta = {
            "remote_script":   remote_script,
            "remote_work_dir": remote_work_dir,
            "log_file":        log_file,
            "mpi":             mpi,
            "gpu_ids":         gpu_ids,
        }
        run_id = run_manager.create("lammps_run", meta)

        thread = threading.Thread(
            target=_lammps_run_background,
            args=(run_id, remote_work_dir, remote_script, mpi, gpu_ids, log_file),
            daemon=True,
        )
        thread.start()

        return {
            "status":          "submitted",
            "run_id":          run_id,
            "remote_work_dir": remote_work_dir,
            "remote_script":   remote_script,
            "log_file":        f"{remote_work_dir}/{log_file}",
            "mpi":             mpi,
            "gpu_ids":         gpu_ids,
            "poll_tip":        "Use get_run_status(run_id) to check progress. "
                               "Use read_remote_log(run_id) to monitor LAMMPS output.",
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
def run_lammps_chain(
    stages: list,
    mpi: int = 2,
    gpu_ids: str = "0,1",
) -> dict:
    """
    Execute a sequence of LAMMPS scripts on Lambda Labs as a fully chained
    pipeline. Each stage runs to completion before the next begins.

    Implementation: generates a bash script on Lambda and launches it under
    nohup. The chain process is fully independent of the MCP server — it
    survives server restarts, disconnections, and conversation resets.

    Progress is written to chain_progress.jsonl (one JSON line per event)
    in the same directory as the chain script. Poll with get_run_status().

    Args:
        stages:   Ordered list of stage dicts, each with:
                    - name            (str)  human-readable label
                    - remote_script   (str)  full path to .in file on Lambda
                    - remote_work_dir (str)  working directory on Lambda
                    - log_file        (str)  run log filename (optional)
        mpi:      MPI processes (same for all stages).
        gpu_ids:  Comma-separated GPU IDs (same for all stages).

    Returns:
        dict with chain_id, remote paths, and poll instructions.
    """
    try:
        if not stages:
            return {"status": "error", "error": "stages list is empty"}

        for i, s in enumerate(stages):
            for field in ("remote_script", "remote_work_dir"):
                if field not in s:
                    return {"status": "error",
                            "error": f"Stage {i} missing required field '{field}'"}
        for s in stages:
            if "log_file" not in s:
                s["log_file"] = f"{s.get('name', 'stage')}_run.log"

        chain_id = str(uuid.uuid4())[:8]

        # Place the chain script and its progress log next to the first stage
        chain_dir  = stages[0]["remote_work_dir"].rsplit("/", 1)[0]  # parent dir
        chain_script  = f"{chain_dir}/chain_{chain_id}.sh"
        progress_file = f"{chain_dir}/chain_{chain_id}_progress.jsonl"

        # Build and upload the bash script
        script_body = _build_chain_script(chain_id, stages, mpi, gpu_ids)
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
            f"nohup bash {chain_script} > {chain_dir}/chain_{chain_id}.log 2>&1 & echo $!"
        )
        stdout, _, _ = executor.execute_command(one_shot)
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
            "lambda_pid":    pid,
        }
        run_manager.create_with_id(chain_id, "lammps_nohup_chain", meta)
        run_manager.start(chain_id)

        return {
            "status":        "submitted",
            "chain_id":      chain_id,
            "n_stages":      len(stages),
            "stage_names":   meta["stage_names"],
            "lambda_pid":    pid,
            "chain_script":  chain_script,
            "progress_file": progress_file,
            "poll_tip":      "Use get_run_status(chain_id) to check progress. "
                             "Status is read live from Lambda's progress file — "
                             "survives MCP server restarts.",
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
def get_run_status(run_id: str) -> dict:
    """
    Get the current status of a submitted LAMMPS run or chain.

    For nohup chains, status is read live from Lambda's progress file so it
    always reflects reality regardless of server restarts.

    Args:
        run_id: Run ID returned by run_lammps_script() or run_lammps_chain().

    Returns:
        dict with status, completed_stages, current_stage, timing, etc.
    """
    run = run_manager.get(run_id)
    if not run:
        return {"error": f"Run '{run_id}' not found"}

    # For nohup chains, derive live status from Lambda's progress file
    if run.get("run_type") == "lammps_nohup_chain":
        progress_file = run["meta"].get("progress_file", "")
        try:
            stdout, _, rc = executor.execute_command(
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
            "lambda_pid":       run["meta"].get("lambda_pid"),
            "note":             "Status read live from Lambda — survives MCP restarts.",
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
    work_dir = run["meta"].get("remote_work_dir", "")

    # Tail the LAMMPS log
    try:
        lammps_log = os.path.join(work_dir, "log.lammps")
        stdout, _, _ = executor.execute_command(f"tail -100 {lammps_log}")
        result["lammps_log_tail"] = stdout
    except Exception:
        result["lammps_log_tail"] = "(could not read log.lammps)"

    # List output files
    try:
        files = executor.list_directory(work_dir)
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
            "run_id":       r["run_id"],
            "status":       r["status"],
            "run_type":     r["run_type"],
            "submitted_at": r["submitted_at"],
            "completed_at": r["completed_at"],
            "script":       r["meta"].get("remote_script", ""),
        })

    return {"runs": summaries, "total": len(summaries)}


@mcp.tool()
def read_remote_log(
    run_id: Optional[str] = None,
    remote_log_path: Optional[str] = None,
    n_lines: int = 50,
) -> dict:
    """
    Read the tail of a LAMMPS log file for live monitoring.
    Provide either run_id (auto-resolves path) or a direct remote_log_path.

    Args:
        run_id:          Run ID (optional, resolves to log path automatically).
        remote_log_path: Direct remote path to log file (optional).
        n_lines:         Number of lines from end to return (default 50).

    Returns:
        dict with last N lines and basic convergence hints.
    """
    try:
        if run_id:
            run = run_manager.get(run_id)
            if not run:
                return {"error": f"Run '{run_id}' not found"}
            work_dir = run["meta"].get("remote_work_dir", "")
            log_path = os.path.join(work_dir, "log.lammps")
        elif remote_log_path:
            log_path = remote_log_path
        else:
            return {"error": "Provide either run_id or remote_log_path"}

        stdout, _, exit_code = executor.execute_command(f"tail -{n_lines} {log_path}")

        if exit_code != 0:
            return {"error": f"Could not read log at {log_path}"}

        # Quick convergence hints
        lines = stdout.strip().splitlines()
        last_density = None
        last_temp    = None
        last_step    = None
        for line in lines:
            parts = line.split()
            if len(parts) > 3 and parts[0].isdigit():
                last_step = parts[0]
                # Try to extract density (last column often)
                try:
                    last_density = float(parts[-1])
                except ValueError:
                    pass

        hints = {}
        if last_step:
            hints["last_step"] = last_step
        if last_density:
            hints["last_density_col"] = last_density

        return {
            "log_path":  log_path,
            "n_lines":   n_lines,
            "content":   stdout,
            "hints":     hints,
        }

    except Exception as e:
        return {"error": str(e)}


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
) -> dict:
    """
    Auto-generate a complete equilibration workflow as a sequence of
    LAMMPS scripts. Mirrors the Larsen 21-step logic but with full
    parameter control.

    Protocol:
      Stage 1: minimize       - relax contacts in amorphous cell
      Stage 2: npt_compress   - NVT heat to max_temp + NPT compress to target density
      Stage 3: nvt            - NVT equilibration at max_temp (full PPPM)
      Stage 4: npt            - NPT cool to target temp, density equilibration
      Stage 5: nvt            - NVT production run at target temp

    Args:
        data_file:      Remote path to RadonPy .data file on Lambda.
        work_dir_base:  Remote base directory for all stages.
        polymer_name:   Label used in filenames and log comments.
        temp:           Target simulation temperature (K).
        max_temp:       Peak annealing temperature (K). Typically 2x Tg.
        press:          Target pressure (atm), typically 1.
        max_press:      Compression pressure (atm), typically 50000.
        n_chains:       Number of polymer chains (informational).
        n_atoms:        Total atom count. Auto-detected if not provided.

    Returns:
        dict with:
            stages       - list of stage dicts (script_path, work_dir, params)
            run_order    - ordered list of stage names
            instructions - how to execute this workflow
    """
    try:
        # Parse data file to get system info
        content = executor.read_file(data_file)
        gen = ScriptGenerator(data_file=data_file)
        info = gen.parse_data_file(content=content)
        n_atoms = n_atoms or info.get("n_atoms", 0)

        # Select step counts based on system size
        # Larger systems need fewer steps per stage (GPU is faster)
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

        stages = []
        local_base = LOCAL_WORKDIR / "generated_scripts" / polymer_name
        local_base.mkdir(parents=True, exist_ok=True)

        def _stage(name, template, p, prev_data):
            local_script = str(local_base / f"{name}.in")
            remote_dir   = f"{work_dir_base}/{name}"
            remote_script = f"{remote_dir}/{name}.in"
            out_data     = f"{remote_dir}/{name}_out.data"
            p = {
                "LOG_FILE":        f"{name}.log",
                "DUMP_FILE":       f"{name}.dump",
                "LAST_DUMP_FILE":  f"{name}_last.dump",
                "WRITE_DATA_FILE": out_data,
                **p,
            }
            script = gen.generate(
                template_name=template,
                output_path=local_script,
                params=p,
                data_file_override=prev_data,
            )
            executor.execute_command(f"mkdir -p {remote_dir}")
            executor.upload_file(local_script, remote_script)
            return {
                "name":          name,
                "template":      template,
                "local_script":  local_script,
                "remote_script": remote_script,
                "remote_work_dir": remote_dir,
                "input_data":    prev_data,
                "output_data":   out_data,
                "params":        p,
            }

        # Stage 1: Minimize
        s1 = _stage("01_minimize", "minimize", {
            "use_pppm":  True,
            "use_gpu":   False,
            "MIN_STYLE": "cg",
            "MAXITER":   50000,
        }, data_file)
        stages.append(s1)

        # Stage 2: NVT soft heat (no PPPM, low timestep to avoid blowup)
        s2 = _stage("02_nvt_softheat", "nvt", {
            "T_START":    300.0,
            "T_FINAL":    max_temp,
            "T_DAMP":     50.0,
            "TIMESTEP":   0.5,
            "N_STEPS":    steps_comp,
            "use_pppm":   False,   # lj/cut during initial heating
            "use_gpu":    False,
            "use_shake":  False,   # off for first heat to avoid constraint failures
            "init_velocity": 300.0,
        }, s1["output_data"])
        stages.append(s2)

        # Stage 3: NPT compression to target density
        s3 = _stage("03_npt_compress", "npt_compress", {
            "T_START":   max_temp,
            "T_FINAL":   max_temp,
            "T_DAMP":    100.0,
            "P_START":   1.0,
            "P_FINAL":   max_press,
            "P_DAMP":    1000.0,
            "TIMESTEP":  1.0,
            "N_STEPS":   steps_comp,
            "use_pppm":  False,   # still lj/cut during compression
            "use_gpu":   False,
            "use_shake": True,
        }, s2["output_data"])
        stages.append(s3)

        # Stage 4: NPT decompress + switch to PPPM
        s4 = _stage("04_npt_pppm", "npt", {
            "T_START":   max_temp,
            "T_FINAL":   max_temp,
            "T_DAMP":    100.0,
            "P_START":   max_press,
            "P_FINAL":   press,
            "P_DAMP":    1000.0,
            "TIMESTEP":  1.0,
            "N_STEPS":   steps_comp,
            "use_pppm":  True,
            "use_gpu":   False,  # CPU for NPT + restart
            "use_shake": True,
            "write_restart": True,
        }, s3["output_data"])
        stages.append(s4)

        # Stage 5: NPT cool to target temp
        s5 = _stage("05_npt_cool", "npt", {
            "T_START":   max_temp,
            "T_FINAL":   temp,
            "T_DAMP":    100.0,
            "P_START":   press,
            "P_FINAL":   press,
            "P_DAMP":    1000.0,
            "TIMESTEP":  1.0,
            "N_STEPS":   steps_npt,
            "use_pppm":  True,
            "use_gpu":   False,
            "use_shake": True,
            "write_restart": True,
        }, s4["output_data"])
        stages.append(s5)

        # Stage 6: NVT production at target temp (GPU safe)
        s6 = _stage("06_nvt_production", "nvt", {
            "T_START":   temp,
            "T_FINAL":   temp,
            "T_DAMP":    100.0,
            "TIMESTEP":  1.0,
            "N_STEPS":   steps_nvt,
            "use_pppm":  True,
            "use_gpu":   True,   # GPU safe: NVT + no restarts
            "use_shake": True,
            "write_restart": False,
        }, s5["output_data"])
        stages.append(s6)

        return {
            "status":     "success",
            "polymer":    polymer_name,
            "n_atoms":    n_atoms,
            "temp":       temp,
            "max_temp":   max_temp,
            "n_stages":   len(stages),
            "stages":     stages,
            "run_order":  [s["name"] for s in stages],
            "instructions": (
                f"Generated {len(stages)} staged scripts for {polymer_name}.\n"
                "Execute in order using run_lammps_script().\n"
                "GPU is OFF for NPT stages (restart safety).\n"
                "GPU is ON for NVT production stage.\n"
                "Monitor each stage with read_remote_log() before proceeding."
            ),
        }

    except Exception as e:
        logger.error(f"generate_equilibration_workflow failed: {e}")
        return {"status": "error", "error": str(e)}


# ─── Analysis tools (Tg, density, convergence, bulk modulus) ─────────────────
#
# These tools run Python analysis scripts on Lambda via SSH and track their
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
    except Exception as e:
        logger.error(f"Analysis run {run_id} failed: {e}")
        run_manager.fail(run_id, str(e))


# ── Tool: unwrap_coordinates ─────────────────────────────────────────────────

def _run_unwrap_coordinates(dump_file: str, output_file: str) -> dict:
    """Background worker — runs unwrap_dump.py on Lambda via CLI."""

    parts = [f"python {MDA_SCRIPTS_DIR}/unwrap_dump.py"]
    parts.append(f"--dump_file {dump_file}")
    parts.append(f"--output_file {output_file}")

    command = " ".join(parts)
    logger.info(f"Running unwrap via CLI: {command}")

    stdout, stderr, exit_code = executor.execute_command(
        command,
        workdir=executor.remote_workdir,
        timeout=36000,
    )

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

    Reads every frame of dump_file on the remote server, applies the
    standard image-flag unwrapping formula (x_unwrap = x + ix*Lx, same
    for y/z), and writes a new dump file where x/y/z hold the unwrapped
    Cartesian positions and ix/iy/iz are zeroed out.  All other columns
    (id, mol, type, …) are preserved exactly as-is.  The output is a
    valid LAMMPS dump loadable by OVITO, VMD, or the other analysis tools.

    Requirements:
        - dump_file must contain columns: x y z ix iy iz
        - Any additional columns (mol, type, vx, vy, vz, …) are passed through

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        dump_file:   Full path to the wrapped LAMMPS dump file on the remote server.
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
    atom_style: str = "id resid type charge x y z",
) -> dict:
    """Background worker — runs mda_end_to_end.py on the remote server via CLI."""

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
    parts.append(f'--atom_style "{atom_style}"')

    command = " ".join(parts)
    logger.info(f"Running E2E via MDAnalysis: {command}")

    stdout, stderr, exit_code = executor.execute_command(
        command,
        workdir=executor.remote_workdir,
        timeout=36000,
    )

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

    Output files written to output_dir on the remote server:
        end_to_end_vectors.csv   — frame, timestep, chain, rx, ry, rz, distance
        end_to_end_summary.json  — per-chain mean/std R and R², overall averages,
                                   backbone_types used, and terminal atom IDs

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        dump_file:      Full path to LAMMPS dump on the remote server.
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
    atom_style: str = "id resid type charge x y z",
) -> dict:
    """Background worker — runs mda_rdf.py on the remote server via CLI."""

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
    parts.append(f'--atom_style "{atom_style}"')

    command = " ".join(parts)
    logger.info(f"Running RDF via MDAnalysis: {command}")

    stdout, stderr, exit_code = executor.execute_command(
        command,
        workdir=executor.remote_workdir,
        timeout=36000,
    )

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
    atom_style: str = "id resid type charge x y z",
) -> dict:
    """
    Calculate radial distribution function g(r) from a simulation trajectory.

    Uses MDAnalysis InterRDF for well-tested, standard RDF computation.
    Requires a LAMMPS data file (topology) and dump file (trajectory).

    Normalisation follows the standard RDF definition:
        g(r) = histogram(r) / [rho_ideal * shell_volume * n_frames]

    Output files written to output_dir on the remote server:
        rdf_t<T1>-t<T2>.csv   — columns: r, g_r  (one file per pair)
        rdf_summary.json       — metadata and file paths

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        dump_file:        Full path to LAMMPS dump on the remote server.
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


# ── Tool: extract_tg ──────────────────────────────────────────────────────────

def _run_extract_tg(
    log_file: str,
    output_dir: str,
    initial_tg_guess: Optional[float],
    equilibration_fraction: float,
    temp_col: str,
    density_col: str,
) -> dict:
    """Background worker — runs extract_tg.py on Lambda via CLI."""

    parts = [f"python {MDA_SCRIPTS_DIR}/extract_tg.py"]
    parts.append(f"--log_file {log_file}")
    parts.append(f"--output_dir {output_dir}")
    if initial_tg_guess is not None:
        parts.append(f"--initial_tg_guess {initial_tg_guess}")
    parts.append(f"--equilibration_fraction {equilibration_fraction}")
    parts.append(f"--temp_col {temp_col}")
    parts.append(f"--density_col {density_col}")

    command = " ".join(parts)
    logger.info(f"Running Tg extraction via CLI: {command}")

    stdout, stderr, exit_code = executor.execute_command(
        command,
        workdir=executor.remote_workdir,
        timeout=36000,
    )

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def extract_tg(
    log_file: str,
    output_dir: Optional[str] = None,
    initial_tg_guess: Optional[float] = None,
    equilibration_fraction: float = 0.5,
    temp_col: str = "Temp",
    density_col: str = "Density",
) -> dict:
    """
    Extract glass transition temperature (Tg) from a LAMMPS MD temperature-sweep log.

    Methodology (v3 — March 2026):
      Data: Plateau detection (|ΔT|>15 K jump = new set-point) with
      equilibration burn-in, producing one clean (T, ρ) point per plateau.
      Plateaus with density drift > 1% (p < 0.01) are excluded from fitting
      to ensure only equilibrated data contributes to the Tg estimate.
      Fitting: Exhaustive F-stat split — tries every split point, fits two
      independent OLS lines, selects the split maximising the F-statistic
      of the two-line model vs a single line.  Physics constraints enforced
      (both slopes negative, rubbery steeper).  Tg = line intersection.
      Cross-validated by scipy curve_fit bilinear.
      Quality: Rated by both R² and F-stat p-value; overall quality is the
      stricter of the two.

    References:
      Patrone et al., Polymer 87 (2016) 246–259
      Suter et al., JCTC 21 (2025) 1405–1421

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        log_file:               Full path to the LAMMPS log file on Lambda.
        output_dir:             Output directory on Lambda.
        initial_tg_guess:       Hint for secondary curve_fit method (primary
                                F-stat method is guess-free).
        equilibration_fraction: Fraction of steps at each T used for density
                                averaging (0.5 = last 50 %).
        temp_col:               Temperature column name (default: 'Temp').
        density_col:            Density column name (default: 'Density').

    Returns:
        dict with run_id.  Result includes Tg_K, Tg_alternative_K,
        r_squared, f_statistic, f_statistic_pvalue, fit_quality,
        fit_quality_r2, fit_quality_fstat, fit_method, binning_method,
        n_plateaus_skipped_drift, fit_params, n_temperature_bins,
        temp_range_K, bins_csv, summary_json.
    """
    if output_dir is None:
        output_dir = str(Path(log_file).parent / "tg_analysis")

    run_id = run_manager.create("extract_tg", {"log_file": log_file, "output_dir": output_dir})
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_extract_tg, dict(
            log_file               = log_file,
            output_dir             = output_dir,
            initial_tg_guess       = initial_tg_guess,
            equilibration_fraction = equilibration_fraction,
            temp_col               = temp_col,
            density_col            = density_col,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":     "submitted",
        "run_id":     run_id,
        "run_type":   "extract_tg",
        "log_file":   log_file,
        "output_dir": output_dir,
        "message":    "Poll with get_run_status(run_id)",
    }


# ── Tool: check_equilibration ─────────────────────────────────────────────────

def _run_check_equilibration(
    log_file: str,
    output_dir: str,
    eq_fraction: float,
    drift_threshold_pct: float,
    drift_pvalue: float,
    block_count: int,
    temp_col: str,
    press_col: str,
    density_col: str,
    energy_col: str,
) -> dict:
    """Background worker — runs check_equilibration.py on Lambda via CLI."""

    parts = [f"python {MDA_SCRIPTS_DIR}/check_equilibration.py"]
    parts.append(f"--log_file {log_file}")
    parts.append(f"--output_dir {output_dir}")
    parts.append(f"--eq_fraction {eq_fraction}")
    parts.append(f"--drift_threshold_pct {drift_threshold_pct}")
    parts.append(f"--drift_pvalue {drift_pvalue}")
    parts.append(f"--block_count {block_count}")
    parts.append(f"--temp_col {temp_col}")
    parts.append(f"--press_col {press_col}")
    parts.append(f"--density_col {density_col}")
    parts.append(f"--energy_col {energy_col}")

    command = " ".join(parts)
    logger.info(f"Running equilibration check via CLI: {command}")

    stdout, stderr, exit_code = executor.execute_command(
        command,
        workdir=executor.remote_workdir,
        timeout=36000,
    )

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def check_equilibration(
    log_file: str,
    output_dir: Optional[str] = None,
    eq_fraction: float = 0.5,
    drift_threshold_pct: float = 1.0,
    drift_pvalue: float = 0.01,
    block_count: int = 5,
    temp_col: str = "Temp",
    press_col: str = "Press",
    density_col: str = "Density",
    energy_col: str = "TotEng",
) -> dict:
    """
    Check whether a LAMMPS simulation is equilibrated based on density
    and energy convergence.

    Analyses the production window (last ``eq_fraction`` of the thermo
    rows) from a single LAMMPS log file and applies two convergence
    tests on both density and total energy:

    1. **Drift test** — linear regression on property vs row index.
       FAIL if drift > ``drift_threshold_pct`` % AND p < ``drift_pvalue``.
    2. **Block-average test** — split into ``block_count`` blocks
       (Flyvbjerg & Petersen, JCP 1989); FAIL if the SEM of block
       means exceeds 1 % of the overall mean.

    System is "equilibrated" only if BOTH density and energy pass both
    tests.

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        log_file:            Full path to LAMMPS log file on Lambda.
        output_dir:          Output directory on Lambda (default: <log_dir>/eq_analysis).
        eq_fraction:         Fraction of rows to use as production window (0.5 = last 50 %).
        drift_threshold_pct: Max allowed drift as % of mean.
        drift_pvalue:        p-value threshold for drift regression significance.
        block_count:         Number of blocks for block averaging.
        temp_col:            Temperature column name in thermo output.
        press_col:           Pressure column name.
        density_col:         Density column name.
        energy_col:          Energy column name.

    Returns:
        dict with run_id.  When completed, result includes:
            equilibrated        — overall bool
            density_equilibrated — bool
            energy_equilibrated  — bool
            density / energy     — per-test details (drift, block_avg
                                   sub-dicts each with a 'pass' field
                                   and diagnostics)
            meta                 — T_mean, P_mean, row counts
            summary_json         — path on Lambda
    """
    if output_dir is None:
        output_dir = str(Path(log_file).parent / "eq_analysis")

    run_id = run_manager.create("check_equilibration", {"log_file": log_file, "output_dir": output_dir})
    t = threading.Thread(
        target=_analysis_run_background,
        args=(run_id, _run_check_equilibration, dict(
            log_file            = log_file,
            output_dir          = output_dir,
            eq_fraction         = eq_fraction,
            drift_threshold_pct = drift_threshold_pct,
            drift_pvalue        = drift_pvalue,
            block_count         = block_count,
            temp_col            = temp_col,
            press_col           = press_col,
            density_col         = density_col,
            energy_col          = energy_col,
        )),
        daemon=True,
    )
    t.start()
    return {
        "status":     "submitted",
        "run_id":     run_id,
        "run_type":   "check_equilibration",
        "log_file":   log_file,
        "output_dir": output_dir,
        "message":    "Poll with get_run_status(run_id)",
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
    """Background worker — runs extract_equilibrated_density.py on Lambda via CLI."""

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

    stdout, stderr, exit_code = executor.execute_command(
        command,
        workdir=executor.remote_workdir,
        timeout=36000,
    )

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
        log_file:            Full path to LAMMPS log file on Lambda.
        output_dir:          Output directory on Lambda.
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
            plateau_density_mean  — equilibrated density (g/cm3)
            plateau_density_std   — standard deviation within plateau
            plateau_density_sem   — standard error of the mean
            plateau_n_points      — number of thermo rows in plateau
            plateau_fraction      — fraction of production window identified as plateau
            naive_mean / naive_std — simple average of full production window
            plateau_step_range    — [start_step, end_step] of the plateau
            summary_json          — path to JSON on Lambda
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
) -> dict:
    """Background worker — runs extract_bulk_modulus.py on Lambda via CLI."""

    parts = [f"python {MDA_SCRIPTS_DIR}/extract_bulk_modulus.py"]
    parts.append(f"--log_file {log_file}")
    parts.append(f"--output_dir {output_dir}")
    parts.append(f"--eq_fraction {eq_fraction}")
    parts.append(f"--block_count {block_count}")
    parts.append(f"--vol_col {vol_col}")
    parts.append(f"--temp_col {temp_col}")
    parts.append(f"--press_col {press_col}")
    parts.append(f"--density_col {density_col}")

    command = " ".join(parts)
    logger.info(f"Running bulk modulus extraction via CLI: {command}")

    stdout, stderr, exit_code = executor.execute_command(
        command,
        workdir=executor.remote_workdir,
        timeout=36000,
    )

    if exit_code != 0:
        return {"status": "failed", "error": stderr, "stdout": stdout}
    return _parse_json_from_stdout(stdout, stderr)


@mcp.tool()
def extract_bulk_modulus(
    log_file: str,
    output_dir: Optional[str] = None,
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

    Output files written to output_dir on Lambda:
        bulk_modulus.json        — full results and diagnostics
        volume_timeseries.csv    — step, volume, temperature, [pressure]

    The job runs in the background — poll with get_run_status(run_id).

    Args:
        log_file:     Full path to the LAMMPS log file on Lambda (NPT run).
        output_dir:   Output directory on Lambda.
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
            summary_json           — path on Lambda
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


# ─── Entry point ──────────────────────────────────────────────────────────────
def _recover_interrupted_chains():
    """
    On server startup, find any chains that were running/pending when the
    server last died and re-launch their threads, skipping stages whose
    output data file already exists on Lambda.
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

        # Skip stages whose output data file already exists on Lambda
        remaining = []
        for s in stages:
            out_data = (s.get("output_data") or
                        f"{s['remote_work_dir']}/{s.get('name', 'stage')}_out.data")
            try:
                _, _, rc = executor.execute_command(f"test -f {out_data}")
                if rc == 0:
                    logger.info(f"[{chain_id}] Recovery skip (done): {s.get('name')}")
                    continue
            except Exception:
                pass
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
