#!/usr/bin/env python3
"""
RadonPy MCP Server - COMPLETE REMOTE TEST SERVER

This server provides GPU-accelerated execution on Lambda Labs.
Supports job submissions for lammps-engine simulation job submission and monitoring, with all computations performed remotely on Lambda's GPU servers.

All operations execute on Lambda Labs GPU server (4x Quadro RTX 6000).
"""

import sys
import os
import json
import logging
import uuid
import threading
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

# Remote execution is always enabled for this test server
REMOTE_MODE = True

from mcp.server.fastmcp import FastMCP
from remote_executor import RemoteExecutor

# Initialize remote executor
executor = RemoteExecutor(
    host="128.2.112.31",
    username="arz2",
    key_path="~/.ssh/lambda_radonpy",
    remote_workdir="/home/arz2/simulations"
)
executor.connect()

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("radonpy_remote_test")
logger.info("=" * 60)
logger.info("RadonPy REMOTE TEST Server Starting")
logger.info(f"Lambda Host: {executor.host}")
logger.info(f"Remote Workdir: {executor.remote_workdir}")
logger.info("=" * 60)

# Initialize MCP server
mcp = FastMCP("RadonPy Remote Test Server")

# ============================================================================
# JOB MANAGEMENT (Simplified)
# ============================================================================

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class SimpleJobManager:
    """Simplified job manager for remote execution testing"""
    
    def __init__(self):
        self.jobs = {}
        self.lock = threading.Lock()
        logger.info("SimpleJobManager initialized")
    
    def submit_job(self, func, args, kwargs, job_type="test"):
        job_id = str(uuid.uuid4())[:8]
        
        job_info = {
            "job_id": job_id,
            "job_type": job_type,
            "status": JobStatus.PENDING.value,
            "result": None,
            "error": None,
            "submitted_at": datetime.now().isoformat(),
            "completed_at": None
        }
        
        with self.lock:
            self.jobs[job_id] = job_info
        
        logger.info(f"Job {job_id} submitted: {job_type}")
        
        # Start background thread
        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, func, args, kwargs),
            daemon=True
        )
        thread.start()
        
        return job_id
    
    def _run_job(self, job_id, func, args, kwargs):
        start_time = time.time()
        
        try:
            with self.lock:
                self.jobs[job_id]["status"] = JobStatus.RUNNING.value
            
            logger.info(f"Job {job_id} execution started")
            result = func(*args, **kwargs)
            
            elapsed = time.time() - start_time
            
            with self.lock:
                self.jobs[job_id]["status"] = JobStatus.COMPLETED.value
                self.jobs[job_id]["result"] = result
                self.jobs[job_id]["completed_at"] = datetime.now().isoformat()
            
            logger.info(f"Job {job_id} completed in {elapsed:.2f}s")
                
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Job {job_id} failed after {elapsed:.2f}s: {str(e)}")
            
            with self.lock:
                self.jobs[job_id]["status"] = JobStatus.FAILED.value
                self.jobs[job_id]["error"] = str(e)
                self.jobs[job_id]["completed_at"] = datetime.now().isoformat()
    
    def get_status(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                return {"error": f"Job {job_id} not found"}
            
            job = self.jobs[job_id]
            return {
                "job_id": job_id,
                "job_type": job["job_type"],
                "status": job["status"],
                "submitted_at": job["submitted_at"],
                "completed_at": job["completed_at"],
                "has_result": job["result"] is not None,
                "has_error": job["error"] is not None
            }
    
    def get_output(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                return {"error": f"Job {job_id} not found"}
            
            job = self.jobs[job_id]
            
            if job["status"] == JobStatus.PENDING.value:
                return {"job_id": job_id, "status": job["status"], "message": "Job pending"}
            
            if job["status"] == JobStatus.RUNNING.value:
                return {"job_id": job_id, "status": job["status"], "message": "Job running"}
            
            if job["status"] == JobStatus.FAILED.value:
                return {"job_id": job_id, "status": job["status"], "error": job["error"]}
            
            # Completed
            return {
                "job_id": job_id,
                "status": job["status"],
                "result": job["result"],
                "completed_at": job["completed_at"]
            }
    
    def list_jobs(self):
        with self.lock:
            jobs_list = [{
                "job_id": jid,
                "job_type": info["job_type"],
                "status": info["status"],
                "submitted_at": info["submitted_at"]
            } for jid, info in self.jobs.items()]
            
            return {"jobs": jobs_list, "count": len(jobs_list)}

job_manager = SimpleJobManager()

# ============================================================================
# REMOTE EXECUTION HELPERS
# ============================================================================

def execute_script(script: str, description: str = "script", gpu_ids: str = "0,1,2,3") -> dict:
    """
    Execute a Python script on Lambda.
    
    Args:
        script: Python code to execute
        description: Description for logging
        gpu_ids: GPU IDs to use (default: "0,1,2,3")
        
    Returns:
        dict with stdout, stderr, exit_code, success
    """
    logger.info(f"Executing on Lambda: {description} (GPUs: {gpu_ids})")
    
    # Set environment variables for execution
    env_vars = {
        'CUDA_VISIBLE_DEVICES': gpu_ids,
        'DISPLAY': ''
    }
    
    stdout, stderr, exit_code = executor.execute_python_script(
        script,
        workdir=executor.remote_workdir,
        env_vars=env_vars  # Pass GPU assignment
    )
    
    success = exit_code == 0
    
    if not success:
        logger.error(f"Lambda execution failed: {stderr}")
    else:
        logger.info(f"Lambda execution succeeded: {description}")
    
    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "success": success
    }

# ============================================================================
# MCP TOOLS - Job Management
# ============================================================================

@mcp.tool()
def remote_get_job_status(job_id: str) -> dict:
    """
    Get the status of a submitted job.
    
    Args:
        job_id: Job ID returned from submit_*_job functions
        
    Returns:
        Dict with job status info
    """
    return job_manager.get_status(job_id)


@mcp.tool()
def remote_get_job_output(job_id: str) -> dict:
    """
    Get the output/results from a completed job.
    
    Args:
        job_id: Job ID returned from submit_*_job functions
        
    Returns:
        Dict with job results (only available when status=completed)
    """
    return job_manager.get_output(job_id)


@mcp.tool()
def remote_list_all_jobs() -> dict:
    """
    List all submitted jobs and their statuses.
    
    Returns:
        Dict with list of all jobs
    """
    return job_manager.list_jobs()


# ============================================================================
# MCP TOOLS - File Operations
# ============================================================================

@mcp.tool()
def list_remote_files(remote_dir: str = "/home/arz2/simulations") -> dict:
    """
    List files in a directory on Lambda server.
    
    Args:
        remote_dir: Directory path on Lambda
        
    Returns:
        Dict with list of files
    """
    try:
        files = executor.list_directory(remote_dir)
        return {
            "status": "success",
            "directory": remote_dir,
            "files": files,
            "count": len(files)
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@mcp.tool()
def upload_file_to_lambda(local_path: str, remote_path: str = None) -> dict:
    """
    Upload a file from local machine to Lambda server.
    
    Args:
        local_path: Local file path to upload
        remote_path: Remote destination (auto-generated if None)
        
    Returns:
        Dict with upload status and remote file path
    """
    if remote_path is None:
        filename = Path(local_path).name
        remote_path = f"/home/arz2/simulations/{filename}"
    
    try:
        executor.upload_file(local_path, remote_path)
        return {
            "status": "success",
            "local_path": local_path,
            "remote_path": remote_path,
            "message": f"File uploaded to Lambda: {remote_path}"
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@mcp.tool()
def download_file_from_lambda(remote_path: str, local_path: str = None) -> dict:
    """
    Download a file from Lambda to local machine.
    
    Args:
        remote_path: File path on Lambda
        local_path: Local destination (auto-generated if None)
        
    Returns:
        Dict with local file path
    """
    if local_path is None:
        local_path = f"/tmp/lambda_download_{Path(remote_path).name}"
    
    try:
        executor.download_file(remote_path, local_path)
        return {
            "status": "success",
            "remote_path": remote_path,
            "local_path": local_path
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@mcp.tool()
def check_lambda_status() -> dict:
    """
    Check Lambda server status and GPU availability.
    
    Returns:
        Dict with Lambda server info
    """
    # Check hostname
    stdout, stderr, exit_code = executor.execute_command("hostname")
    hostname = stdout.strip() if exit_code == 0 else "unknown"
    
    # Check GPUs
    stdout, stderr, exit_code = executor.execute_command(
        "nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader"
    )
    
    gpus = []
    if exit_code == 0:
        for i, line in enumerate(stdout.strip().split('\n')):
            parts = line.split(',')
            if len(parts) == 3:
                gpus.append({
                    "gpu_id": i,
                    "name": parts[0].strip(),
                    "memory_total": parts[1].strip(),
                    "memory_used": parts[2].strip()
                })
    
    # Check RadonPy
    stdout, stderr, exit_code = executor.execute_python_script(
        "import radonpy; print(radonpy.__version__)"
    )
    radonpy_version = stdout.strip() if exit_code == 0 else "unknown"
    
    return {
        "status": "connected",
        "lambda_host": executor.host,
        "hostname": hostname,
        "remote_workdir": executor.remote_workdir,
        "radonpy_version": radonpy_version,
        "gpu_count": len(gpus),
        "gpus": gpus
    }

@mcp.tool()
def read_remote_file(remote_path: str) -> dict:
    """
    Read content of a file on Lambda server.
    
    Args:
        remote_path: Full path to file on Lambda (e.g., '/home/arz2/simulations/test/log.lammps')
    
    Returns:
        dict with file content and metadata
    """
    try:
        content = executor.read_file(remote_path)
        
        # Get file size
        try:
            import stat
            file_stat = executor.sftp_client.stat(remote_path)
            size_bytes = file_stat.st_size
        except:
            size_bytes = len(content)
        
        return {
            "status": "success",
            "file": remote_path,
            "content": content,
            "size_bytes": size_bytes,
            "lines": len(content.split('\n'))
        }
    except Exception as e:
        logger.error(f"Failed to read {remote_path}: {e}")
        return {
            "status": "error",
            "file": remote_path,
            "error": str(e)
        }


@mcp.tool()
def read_remote_file_tail(remote_path: str, n_lines: int = 50) -> dict:
    """
    Read the last N lines of a file on Lambda server (useful for monitoring logs).
    
    Args:
        remote_path: Full path to file on Lambda
        n_lines: Number of lines from end to read (default: 50)
    
    Returns:
        dict with last N lines and metadata
    """
    try:
        content = executor.read_file(remote_path)
        lines = content.split('\n')
        tail_lines = lines[-n_lines:] if len(lines) > n_lines else lines
        
        return {
            "status": "success",
            "file": remote_path,
            "content": '\n'.join(tail_lines),
            "lines_returned": len(tail_lines),
            "total_lines": len(lines)
        }
    except Exception as e:
        logger.error(f"Failed to read tail of {remote_path}: {e}")
        return {
            "status": "error",
            "file": remote_path,
            "error": str(e)
        }


@mcp.tool()
def write_remote_file(remote_path: str, content: str) -> dict:
    """
    Write content to a file on Lambda server.
    
    Args:
        remote_path: Full path to file on Lambda
        content: Content to write
    
    Returns:
        dict with write status
    """
    try:
        executor.write_file(content, remote_path)
        
        return {
            "status": "success",
            "file": remote_path,
            "bytes_written": len(content.encode('utf-8'))
        }
    except Exception as e:
        logger.error(f"Failed to write {remote_path}: {e}")
        return {
            "status": "error",
            "file": remote_path,
            "error": str(e)
        }


@mcp.tool()
def execute_remote_shell_command(command: str, workdir: str = None, timeout: int = 60) -> dict:
    """
    Execute a shell command on Lambda server.
    
    Args:
        command: Shell command to execute
        workdir: Working directory (default: /home/arz2/simulations)
        timeout: Command timeout in seconds (default: 60)
    
    Returns:
        dict with command output
    """
    try:
        stdout, stderr, exit_code = executor.execute_command(
            command, 
            workdir=workdir,
            timeout=timeout
        )
        
        return {
            "status": "success" if exit_code == 0 else "failed",
            "command": command,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code
        }
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        return {
            "status": "error",
            "command": command,
            "error": str(e)
        }


@mcp.tool()
def list_remote_files_detailed(remote_dir: str) -> dict:
    """
    List files in a directory on Lambda with detailed information (size, modified time).
    
    Args:
        remote_dir: Directory path on Lambda
    
    Returns:
        dict with detailed file listing
    """
    try:
        files = executor.sftp_client.listdir_attr(remote_dir)
        
        file_list = []
        for file_attr in files:
            import stat
            is_dir = stat.S_ISDIR(file_attr.st_mode)
            
            file_list.append({
                "name": file_attr.filename,
                "type": "directory" if is_dir else "file",
                "size_bytes": file_attr.st_size,
                "modified": file_attr.st_mtime
            })
        
        return {
            "status": "success",
            "directory": remote_dir,
            "files": file_list,
            "count": len(file_list)
        }
    except Exception as e:
        logger.error(f"Failed to list {remote_dir}: {e}")
        return {
            "status": "error",
            "directory": remote_dir,
            "error": str(e)
        }


@mcp.tool()
def check_remote_file_exists(remote_path: str) -> dict:
    """
    Check if a file exists on Lambda server.
    
    Args:
        remote_path: Full path to check
    
    Returns:
        dict with existence status
    """
    exists = executor.file_exists(remote_path)
    
    return {
        "status": "success",
        "path": remote_path,
        "exists": exists
    }

@mcp.tool()
async def save_molecule_remote(
    mol_file: str,
    output_path: str,
    format: str = "json"
) -> dict:
    """
    Save molecule to file on Lambda server.
    
    Args:
        mol_file: Path to input molecule JSON file on Lambda
        output_path: Output file path on Lambda (with extension)
        format: Output format ('json', 'pickle', 'pdb', 'xyz', 'mol')
    
    Returns:
        dict with save status and file path
    
    Example:
        # Save equilibrated cell for next stage
        save_molecule_remote(
            mol_file="/path/to/work_dir/radon_md_lmp_last.json",
            output_path="/path/to/phase1a_output.json",
            format="json"
        )
    """
    
    logger.info(f"Saving molecule: {mol_file} -> {output_path}")
    
    script = f"""
import sys
import os
sys.path.insert(0, '/home/arz2/RadonPy')

from radonpy.core import utils

# Load molecule
mol = utils.JSONToMol("{mol_file}")
print(f"Loaded molecule: {{mol.GetNumAtoms()}} atoms")

# Save in requested format
format = "{format}"
if format == "json":
    utils.MolToJSON(mol, "{output_path}")
elif format == "pickle":
    utils.pickle_dump(mol, "{output_path}")
elif format == "pdb":
    utils.MolToPDBFile(mol, "{output_path}")
elif format == "xyz":
    utils.MolToXYZFile(mol, "{output_path}")
elif format == "mol":
    utils.MolToMolFile(mol, "{output_path}")
else:
    raise ValueError(f"Unsupported format: {{format}}")

print(f"SUCCESS: Saved to {output_path}")
"""
    
    result = execute_script(script, "save_molecule")
    
    if not result["success"]:
        return {
            "status": "failed",
            "error": result["stderr"],
            "stdout": result["stdout"]
        }
    
    return {
        "status": "success",
        "output_path": output_path,
        "format": format,
        "stdout": result["stdout"]
    }



# ============================================================================
# MCP TOOLS - Trajectory Analysis
# ============================================================================

# ---------------------------------------------------------------------------
# Shared remote helper code
# ---------------------------------------------------------------------------
# _DUMP_HELPERS is prepended verbatim to every remote analysis script so that
# parse_lammps_dump_frame and unwrap_frame are available without re-importing
# a separate file on Lambda. Keeping it here in one place means any fix
# propagates to all three tools automatically.
# Note: this is NOT an f-string, so single braces are literal Python braces
# in the remote code.  Inside the per-tool f-strings below, braces that
# belong to the remote Python code are escaped as {{ }}.

_DUMP_HELPERS = """
import numpy as np
import pandas as pd
import json
import os
from pathlib import Path


def parse_lammps_dump_frame(fh):
    \"\"\"
    Read one frame from an already-open LAMMPS dump file.
    Returns a dict with keys: timestep, natoms, box (np array), df (DataFrame).
    Returns None at EOF or on a malformed header.
    \"\"\"
    line = fh.readline()
    if not line:
        return None
    if "ITEM: TIMESTEP" not in line:
        return None
    timestep = int(fh.readline().strip())

    fh.readline()  # ITEM: NUMBER OF ATOMS
    natoms = int(fh.readline().strip())

    fh.readline()  # ITEM: BOX BOUNDS …
    box = np.array([
        list(map(float, fh.readline().split()[:2])) for _ in range(3)
    ])

    header = fh.readline()  # ITEM: ATOMS col1 col2 …
    columns = header.strip().split()[2:]

    rows = [fh.readline().split() for _ in range(natoms)]
    df = pd.DataFrame(rows, columns=columns)
    for col in columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass

    return {"timestep": timestep, "natoms": natoms, "box": box, "df": df}


def unwrap_frame(df, box):
    \"\"\"
    Return an (N, 3) array of unwrapped coordinates.
    Requires columns x, y, z, ix, iy, iz in df.
    Formula: x_unwrap = x + ix * Lx  (and same for y, z).
    \"\"\"
    coords = df[["x", "y", "z"]].values.astype(float)
    images = df[["ix", "iy", "iz"]].values.astype(float)
    lengths = (box[:, 1] - box[:, 0]).reshape(1, 3)
    return coords + images * lengths
"""


# ---------------------------------------------------------------------------
# Helper: parse JSON result line from remote stdout
# ---------------------------------------------------------------------------

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


# ============================================================================
# Tool 1: unwrap_coordinates
# ============================================================================

def _run_unwrap_coordinates(dump_file: str, output_file: str) -> dict:
    """Background worker — runs on Lambda via execute_script."""

    script = _DUMP_HELPERS + f"""
dump_file   = "{dump_file}"
output_file = "{output_file}"

# Ensure parent directory exists
Path(output_file).parent.mkdir(parents=True, exist_ok=True)

frames_written = 0
natoms_last    = 0

with open(dump_file, "r") as fin, open(output_file, "w") as fout:
    while True:
        frame = parse_lammps_dump_frame(fin)
        if frame is None:
            break

        df  = frame["df"]
        box = frame["box"]
        cols = list(df.columns)

        # Validate image flags are present
        for flag in ("ix", "iy", "iz"):
            if flag not in cols:
                raise ValueError(
                    f"Column '{{flag}}' missing from dump. "
                    "Dump must be written with 'dump … id mol type x y z ix iy iz' "
                    "(or similar including image flags)."
                )

        # Compute unwrapped positions, zero out image flags
        unwrapped = unwrap_frame(df, box)
        df = df.copy()
        df["x"]  = unwrapped[:, 0]
        df["y"]  = unwrapped[:, 1]
        df["z"]  = unwrapped[:, 2]
        df["ix"] = 0
        df["iy"] = 0
        df["iz"] = 0

        # Write LAMMPS dump header
        fout.write("ITEM: TIMESTEP\n")
        fout.write(f"{{frame['timestep']}}\n")
        fout.write("ITEM: NUMBER OF ATOMS\n")
        fout.write(f"{{frame['natoms']}}\n")
        fout.write("ITEM: BOX BOUNDS pp pp pp\n")
        for lo, hi in frame["box"]:
            fout.write(f"{{lo:.10f}} {{hi:.10f}}\n")
        fout.write("ITEM: ATOMS " + " ".join(cols) + "\n")

        # Determine per-column format: integer for id/mol/type/image flags, float otherwise
        int_cols = {{"id", "mol", "type", "ix", "iy", "iz"}}
        fmt = " ".join("%d" if c in int_cols else "%.6f" for c in cols)
        np.savetxt(fout, df.values.astype(float), fmt=fmt)

        frames_written += 1
        natoms_last = frame["natoms"]

        if frames_written % 500 == 0:
            print(f"  unwrap: {{frames_written}} frames written...", flush=True)

size_bytes = os.path.getsize(output_file)
print(json.dumps({{
    "status":         "success",
    "output_file":    output_file,
    "frames_written": frames_written,
    "natoms":         natoms_last,
    "size_bytes":     size_bytes,
}}))
"""

    result = execute_script(script, description="unwrap_coordinates")
    if not result["success"]:
        return {"status": "failed", "error": result["stderr"], "stdout": result["stdout"]}
    return _parse_json_from_stdout(result["stdout"], result["stderr"])


@mcp.tool()
def unwrap_coordinates(
    dump_file: str,
    output_file: Optional[str] = None,
) -> dict:
    """
    Write a new LAMMPS dump file with fully unwrapped coordinates.

    Reads every frame of `dump_file` on Lambda, applies the standard
    image-flag unwrapping formula (x_unwrap = x + ix*Lx, same for y/z),
    and writes a new dump file where x/y/z hold the unwrapped Cartesian
    positions and ix/iy/iz are zeroed out.  All other columns (id, mol,
    type, …) are preserved exactly as-is.  The output is a valid LAMMPS
    dump that can be loaded by OVITO, VMD, or fed directly into the other
    analysis tools.

    Requirements:
        - dump_file must contain columns: x y z ix iy iz
        - Any additional columns (mol, type, vx, vy, vz, …) are written through unchanged

    The job runs in the background — poll with remote_get_job_status(job_id).

    Args:
        dump_file:   Full path to the wrapped LAMMPS dump file on Lambda.
        output_file: Destination path on Lambda for the unwrapped dump.
                     Defaults to <original_stem>_unwrapped.dump in the
                     same directory.

    Returns:
        dict with job_id.  Use remote_get_job_output(job_id) when complete
        to retrieve output_file, frames_written, natoms, size_bytes.
    """
    if output_file is None:
        stem = dump_file.replace(".dump", "").rstrip(".")
        output_file = stem + "_unwrapped.dump"

    job_id = job_manager.submit_job(
        func     = _run_unwrap_coordinates,
        args     = [],
        kwargs   = dict(dump_file=dump_file, output_file=output_file),
        job_type = "unwrap_coordinates",
    )
    return {
        "status":      "submitted",
        "job_id":      job_id,
        "job_type":    "unwrap_coordinates",
        "dump_file":   dump_file,
        "output_file": output_file,
        "message":     "Poll with remote_get_job_status(job_id)",
    }


# ============================================================================
# Tool 2: extract_end_to_end_vectors
# ============================================================================

def _run_extract_end_to_end(
    dump_file: str,
    data_file: Optional[str],
    num_chains: Optional[int],
    chain_ids: Optional[list],
    skip_frames: int,
    max_frames: Optional[int],
    output_dir: str,
) -> dict:
    """Background worker — runs on Lambda via execute_script."""

    # Serialise Python-None-able values for safe f-string injection
    data_file_py  = "None" if data_file  is None else f'"{data_file}"'
    num_chains_py = "None" if num_chains is None else str(num_chains)
    max_frames_py = "None" if max_frames is None else str(max_frames)
    chain_ids_py  = "None" if chain_ids is None else json.dumps(chain_ids)  # "None" or "[1,2,3]"

    script = _DUMP_HELPERS + f"""
dump_file   = "{dump_file}"
data_file   = {data_file_py}
output_dir  = Path("{output_dir}")
output_dir.mkdir(parents=True, exist_ok=True)

skip_frames = {skip_frames}
max_frames  = {max_frames_py}
num_chains  = {num_chains_py}
chain_ids   = {chain_ids_py}   # list of ints or None


def parse_terminal_atoms(data_file):
    \"\"\"
    Return a dict {{atom_id: bond_count}} by scanning the Bonds section
    of a LAMMPS data file.  Atoms with bond_count == 1 are chain termini.
    \"\"\"
    bond_counts = {{}}
    in_bonds = False
    with open(data_file) as f:
        for line in f:
            if "Bonds" in line and not line.strip().startswith("#"):
                in_bonds = True
                continue
            if in_bonds:
                if not line.strip() or line.strip().startswith("#"):
                    continue
                if any(kw in line for kw in ("Angles", "Dihedrals", "Impropers", "Pair Coeffs")):
                    break
                parts = line.split()
                if len(parts) >= 4:
                    a, b = int(parts[2]), int(parts[3])
                    bond_counts[a] = bond_counts.get(a, 0) + 1
                    bond_counts[b] = bond_counts.get(b, 0) + 1
    return bond_counts


bond_counts = parse_terminal_atoms(data_file) if data_file else {{}}
all_rows    = []
frames_done = 0

with open(dump_file) as f:
    while True:
        frame = parse_lammps_dump_frame(f)
        if frame is None:
            break
        if frames_done < skip_frames:
            frames_done += 1
            continue
        if max_frames is not None and (frames_done - skip_frames) >= max_frames:
            break

        df  = frame["df"]
        box = frame["box"]

        # Auto-detect chain count on first analysed frame
        if num_chains is None and "mol" in df.columns:
            num_chains = int(df["mol"].max())

        # Unwrap if image flags present; otherwise use wrapped (still useful for Rg)
        has_images = all(c in df.columns for c in ("ix", "iy", "iz"))
        coords = unwrap_frame(df, box) if has_images else df[["x","y","z"]].values.astype(float)

        # Fast id -> coordinate lookup as numpy index array
        ids = df["id"].values.astype(int)
        id_to_idx = {{int(aid): i for i, aid in enumerate(ids)}}

        chains_todo = chain_ids if chain_ids is not None else range(1, num_chains + 1)

        for cid in chains_todo:
            mask     = (df["mol"] == cid).values
            chain_ids_arr = ids[mask]
            if len(chain_ids_arr) < 2:
                continue
            chain_ids_sorted = sorted(chain_ids_arr.tolist())

            # Prefer bond-topology termini; fall back to first/last by atom ID
            if bond_counts:
                termini = [aid for aid in chain_ids_sorted
                           if bond_counts.get(aid, 99) == 1]
                a_id, b_id = (termini[0], termini[-1]) if len(termini) >= 2 \
                              else (chain_ids_sorted[0], chain_ids_sorted[-1])
            else:
                a_id, b_id = chain_ids_sorted[0], chain_ids_sorted[-1]

            if a_id not in id_to_idx or b_id not in id_to_idx:
                continue

            r_a = coords[id_to_idx[a_id]]
            r_b = coords[id_to_idx[b_id]]
            r_vec  = r_b - r_a
            r_dist = float(np.linalg.norm(r_vec))

            all_rows.append({{
                "frame":    frames_done,
                "timestep": int(frame["timestep"]),
                "chain":    int(cid),
                "rx":       float(r_vec[0]),
                "ry":       float(r_vec[1]),
                "rz":       float(r_vec[2]),
                "distance": r_dist,
            }})

        frames_done += 1
        if frames_done % 200 == 0:
            print(f"  e2e: frame {{frames_done}}", flush=True)


df_out   = pd.DataFrame(all_rows)
csv_path = str(output_dir / "end_to_end_vectors.csv")
df_out.to_csv(csv_path, index=False)

# Per-chain statistics
per_chain = []
for cid, grp in df_out.groupby("chain"):
    d  = grp["distance"]
    r2 = grp["rx"]**2 + grp["ry"]**2 + grp["rz"]**2
    per_chain.append({{
        "chain":    int(cid),
        "mean_R":   float(d.mean()),
        "std_R":    float(d.std()),
        "mean_R2":  float(r2.mean()),
        "std_R2":   float(r2.std()),
        "n_frames": int(len(d)),
    }})

summary = {{
    "status":           "success",
    "dump_file":        dump_file,
    "output_dir":       str(output_dir),
    "csv_file":         csv_path,
    "num_chains":       num_chains,
    "frames_analysed":  frames_done - skip_frames,
    "per_chain":        per_chain,
    "overall_mean_R":   float(df_out["distance"].mean()),
    "overall_mean_R2":  float((df_out["rx"]**2 + df_out["ry"]**2 + df_out["rz"]**2).mean()),
}}

json_path = str(output_dir / "end_to_end_summary.json")
with open(json_path, "w") as jf:
    json.dump(summary, jf, indent=2)

print(json.dumps(summary))
"""

    result = execute_script(script, description="extract_end_to_end_vectors")
    if not result["success"]:
        return {"status": "failed", "error": result["stderr"], "stdout": result["stdout"]}
    return _parse_json_from_stdout(result["stdout"], result["stderr"])


@mcp.tool()
def extract_end_to_end_vectors(
    dump_file: str,
    data_file: Optional[str] = None,
    num_chains: Optional[int] = None,
    chain_ids: Optional[list] = None,
    skip_frames: int = 0,
    max_frames: Optional[int] = None,
    output_dir: Optional[str] = None,
) -> dict:
    """
    Extract end-to-end vectors and distances from polymer simulation.

    Analyses a LAMMPS dump trajectory on Lambda to calculate per-chain
    end-to-end distance R and vector (rx, ry, rz) for every frame.
    Coordinates are automatically unwrapped when image flags (ix, iy, iz)
    are present in the dump.

    Terminal atom identification:
        - If data_file is provided, reads the Bonds section and finds atoms
          with exactly one bond (true chain ends).
        - Otherwise uses the first and last atom IDs within each molecule
          as a fallback.

    Output files written to output_dir on Lambda:
        end_to_end_vectors.csv   — columns: frame, timestep, chain, rx, ry, rz, distance
        end_to_end_summary.json  — per-chain mean/std R and R², overall averages

    The job runs in the background — poll with remote_get_job_status(job_id).

    Args:
        dump_file:   Full path to LAMMPS dump on Lambda.
                     Must include columns: id mol x y z (ix iy iz recommended).
        data_file:   Optional path to LAMMPS .data file on Lambda for
                     bond-based terminal atom detection.
        num_chains:  Chain count; auto-detected from mol column if None.
        chain_ids:   Subset of chain IDs to analyse, e.g. [1, 2, 3].
                     All chains analysed if None.
        skip_frames: Initial frames to skip (burn-in).
        max_frames:  Cap on frames to analyse after skip.
        output_dir:  Output directory on Lambda.
                     Defaults to <dump_dir>/analysis.

    Returns:
        dict with job_id.  Completed output includes per_chain stats and csv_file path.
    """
    if output_dir is None:
        output_dir = str(Path(dump_file).parent / "analysis")

    job_id = job_manager.submit_job(
        func     = _run_extract_end_to_end,
        args     = [],
        kwargs   = dict(
            dump_file   = dump_file,
            data_file   = data_file,
            num_chains  = num_chains,
            chain_ids   = chain_ids,
            skip_frames = skip_frames,
            max_frames  = max_frames,
            output_dir  = output_dir,
        ),
        job_type = "extract_end_to_end_vectors",
    )
    return {
        "status":     "submitted",
        "job_id":     job_id,
        "job_type":   "extract_end_to_end_vectors",
        "dump_file":  dump_file,
        "output_dir": output_dir,
        "message":    "Poll with remote_get_job_status(job_id)",
    }


# ============================================================================
# Tool 3: calculate_rdf
# ============================================================================

def _run_calculate_rdf(
    dump_file: str,
    atom_type_pairs: Optional[list],
    rmax: float,
    nbins: int,
    skip_frames: int,
    max_frames: Optional[int],
    output_dir: str,
) -> dict:
    """Background worker — runs on Lambda via execute_script."""

    max_frames_py = "None" if max_frames is None else str(max_frames)
    pairs_py      = json.dumps(atom_type_pairs)  # "null" or "[[1,2],[2,2]]"

    script = _DUMP_HELPERS + f"""
dump_file  = "{dump_file}"
output_dir = Path("{output_dir}")
output_dir.mkdir(parents=True, exist_ok=True)

rmax        = {rmax}
nbins       = {nbins}
skip_frames = {skip_frames}
max_frames  = {max_frames_py}
pairs_req   = {pairs_py}   # list of [t1,t2] or None

bin_edges   = np.linspace(0.0, rmax, nbins + 1)
bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
dr          = bin_edges[1] - bin_edges[0]

# accumulators[(t1,t2)] = running histogram counts (float64)
accumulators = {{}}
frame_counts = {{}}
last_n_atoms = {{}}
last_volume  = 1.0

frames_done = 0

with open(dump_file) as f:
    while True:
        frame = parse_lammps_dump_frame(f)
        if frame is None:
            break
        if frames_done < skip_frames:
            frames_done += 1
            continue
        if max_frames is not None and (frames_done - skip_frames) >= max_frames:
            break

        df   = frame["df"]
        box  = frame["box"]
        Lxyz = box[:, 1] - box[:, 0]      # (3,)
        vol  = float(np.prod(Lxyz))
        last_volume = vol

        coords = df[["x", "y", "z"]].values.astype(float)  # (N, 3)
        types  = df["type"].values.astype(int)              # (N,)

        # Determine which type-pairs to compute
        if pairs_req is None:
            ut = sorted(set(types.tolist()))
            pairs = [(t1, t2) for t1 in ut for t2 in ut if t1 <= t2]
        else:
            pairs = [tuple(p) for p in pairs_req]

        for t1, t2 in pairs:
            key = (int(t1), int(t2))
            if key not in accumulators:
                accumulators[key] = np.zeros(nbins, dtype=np.float64)
                frame_counts[key] = 0

            idx1 = np.where(types == t1)[0]
            idx2 = np.where(types == t2)[0]
            if idx1.size == 0 or idx2.size == 0:
                continue

            last_n_atoms[t1] = int(idx1.size)
            last_n_atoms[t2] = int(idx2.size)

            pos1 = coords[idx1]  # (N1, 3)
            pos2 = coords[idx2]  # (N2, 3)

            # --- vectorised pairwise distances (numpy broadcasting) ---
            # diff shape: (N1, N2, 3)
            diff = pos1[:, np.newaxis, :] - pos2[np.newaxis, :, :]

            # Minimum image convention applied component-wise
            diff -= np.round(diff / Lxyz) * Lxyz

            # Euclidean distances: (N1, N2)
            dists = np.sqrt(np.einsum("ijk,ijk->ij", diff, diff))

            if t1 == t2:
                # Same-type: extract upper triangle to count each pair once
                rows, cols = np.triu_indices(idx1.size, k=1)
                d_valid = dists[rows, cols]
            else:
                d_valid = dists.ravel()

            within = d_valid[d_valid < rmax]
            hist, _ = np.histogram(within, bins=bin_edges)
            accumulators[key] += hist.astype(np.float64)
            frame_counts[key] += 1

        frames_done += 1
        if frames_done % 100 == 0:
            print(f"  rdf: frame {{frames_done}}", flush=True)


# --- Normalise and write output files ---
rdf_files = {{}}

for key, histogram in accumulators.items():
    t1, t2    = key
    n_frames  = frame_counts[key]
    if n_frames == 0:
        continue

    n1  = last_n_atoms.get(t1, 1)
    n2  = last_n_atoms.get(t2, 1)

    r_lo      = bin_edges[:-1]
    r_hi      = bin_edges[1:]
    shell_vol = (4.0 / 3.0) * np.pi * (r_hi**3 - r_lo**3)

    # Expected counts in an ideal (uncorrelated) gas
    if t1 == t2:
        # n1*(n1-1)/2 unique pairs, factor of 2 absorbed into normalisation
        ideal = (n1 * (n1 - 1) / 2.0 / last_volume) * shell_vol * n_frames
    else:
        ideal = (n1 * n2 / last_volume) * shell_vol * n_frames

    gr = np.where(ideal > 0.0, histogram / ideal, 0.0)

    fname = str(output_dir / f"rdf_t{{t1}}-t{{t2}}.csv")
    pd.DataFrame({{"r": bin_centers, "g_r": gr}}).to_csv(fname, index=False)
    rdf_files[f"{{t1}}-{{t2}}"] = fname
    print(f"  Wrote {{fname}}", flush=True)

summary = {{
    "status":          "success",
    "dump_file":       dump_file,
    "output_dir":      str(output_dir),
    "rmax":            rmax,
    "nbins":           nbins,
    "frames_analysed": frames_done - skip_frames,
    "pairs_computed":  [f"{{k[0]}}-{{k[1]}}" for k in accumulators],
    "rdf_files":       rdf_files,
}}

with open(str(output_dir / "rdf_summary.json"), "w") as jf:
    json.dump(summary, jf, indent=2)

print(json.dumps(summary))
"""

    result = execute_script(script, description="calculate_rdf")
    if not result["success"]:
        return {"status": "failed", "error": result["stderr"], "stdout": result["stdout"]}
    return _parse_json_from_stdout(result["stdout"], result["stderr"])


@mcp.tool()
def calculate_rdf(
    dump_file: str,
    atom_type_pairs: Optional[list] = None,
    rmax: float = 15.0,
    nbins: int = 150,
    skip_frames: int = 0,
    max_frames: Optional[int] = None,
    output_dir: Optional[str] = None,
) -> dict:
    """
    Calculate radial distribution function g(r) from simulation trajectory.

    Computes pair correlation functions using a fully vectorised numpy
    implementation.  For each frame, pairwise distance matrices are built
    with array broadcasting ((N1,N2,3) diff tensor) and the minimum-image
    convention is applied in one vectorised step — no Python loops over
    individual atom pairs.  This is ~100× faster than the scalar loop in
    radonpy_analysis_tools.py.

    Normalisation follows the standard RDF definition:
        g(r) = histogram(r) / [rho_ideal * shell_volume * n_frames]
    where rho_ideal is the number density of the reference species.
    Same-type pairs use the n*(n-1)/2 unique-pair counting.

    Output files written to output_dir on Lambda:
        rdf_t<T1>-t<T2>.csv   — columns: r, g_r   (one file per pair)
        rdf_summary.json       — metadata and file paths

    The job runs in the background — poll with remote_get_job_status(job_id).

    Args:
        dump_file:        Full path to LAMMPS dump on Lambda.
                          Must include columns: type x y z.
        atom_type_pairs:  List of [type1, type2] pairs, e.g. [[1,1],[2,2],[1,2]].
                          All type pairs computed if None.
        rmax:             Maximum distance in Å (default 15.0).
        nbins:            Histogram bin count (default 150).
        skip_frames:      Frames to skip at start.
        max_frames:       Cap on frames after skip.
        output_dir:       Output directory on Lambda.
                          Defaults to <dump_dir>/analysis.

    Returns:
        dict with job_id.  Completed output includes rdf_files paths and
        pairs_computed list.

    Memory note:
        Per frame, peak RAM = O(N1 * N2 * 24 bytes).  For a 10k-atom system
        analysing all-atom pairs (~10k x 10k) this reaches ~2 GB.  Specify
        atom_type_pairs to limit computation to the pairs you actually need.
    """
    if output_dir is None:
        output_dir = str(Path(dump_file).parent / "analysis")

    job_id = job_manager.submit_job(
        func     = _run_calculate_rdf,
        args     = [],
        kwargs   = dict(
            dump_file        = dump_file,
            atom_type_pairs  = atom_type_pairs,
            rmax             = rmax,
            nbins            = nbins,
            skip_frames      = skip_frames,
            max_frames       = max_frames,
            output_dir       = output_dir,
        ),
        job_type = "calculate_rdf",
    )
    return {
        "status":     "submitted",
        "job_id":     job_id,
        "job_type":   "calculate_rdf",
        "dump_file":  dump_file,
        "output_dir": output_dir,
        "message":    "Poll with remote_get_job_status(job_id)",
    }


# ============================================================================
# Tool 4: extract_tg
# ============================================================================

def _run_extract_tg(
    log_file: str,
    output_dir: str,
    initial_tg_guess: Optional[float],
    equilibration_fraction: float,
    temp_col: str,
    density_col: str,
) -> dict:
    """Background worker — runs on Lambda via execute_script."""

    initial_tg_py = "None" if initial_tg_guess is None else str(initial_tg_guess)

    script = f"""
import numpy as np
import pandas as pd
import json
import os
import re
from pathlib import Path
from scipy import optimize, stats

log_file   = "{log_file}"
output_dir = Path("{output_dir}")
output_dir.mkdir(parents=True, exist_ok=True)

initial_tg_guess      = {initial_tg_py}
equilibration_fraction = {equilibration_fraction}
temp_col              = "{temp_col}"
density_col           = "{density_col}"

# -----------------------------------------------------------------------
# 1. Parse LAMMPS log file — collect thermo data from every Run block
# -----------------------------------------------------------------------

def parse_lammps_log(path):
    \"\"\"
    Parse all thermo-output tables from a LAMMPS log file.
    Returns a single DataFrame with all rows concatenated.
    \"\"\"
    all_dfs = []
    header  = None
    rows    = []

    with open(path) as f:
        for raw in f:
            line = raw.strip()

            # A header line looks like: Step Temp Press Density …
            # Detect it by checking the first token is a known keyword
            if re.match(r'^Step\\s', line) or re.match(r'^(Step|TotEng|Temp)', line):
                # Save any in-progress block
                if rows:
                    all_dfs.append(pd.DataFrame(rows, columns=header))
                    rows = []
                header = line.split()
                continue

            # Data rows: all tokens must be numeric
            if header is not None:
                tokens = line.split()
                if len(tokens) == len(header):
                    try:
                        rows.append([float(t) for t in tokens])
                        continue
                    except ValueError:
                        pass
                # Non-numeric or wrong length → end of block
                if rows:
                    all_dfs.append(pd.DataFrame(rows, columns=header))
                    rows   = []
                    header = None

    if rows and header is not None:
        all_dfs.append(pd.DataFrame(rows, columns=header))

    if not all_dfs:
        raise ValueError(f"No thermo data found in {{path}}")

    return pd.concat(all_dfs, ignore_index=True)


df_all = parse_lammps_log(log_file)

if temp_col not in df_all.columns:
    raise ValueError(
        f"Column '{{temp_col}}' not found.  "
        f"Available columns: {{list(df_all.columns)}}"
    )
if density_col not in df_all.columns:
    raise ValueError(
        f"Column '{{density_col}}' not found.  "
        f"Available columns: {{list(df_all.columns)}}"
    )

# -----------------------------------------------------------------------
# 2. Bin temperatures → mean density per temperature window
#    (Tg-sweep logs contain many steps at each temperature; we want
#    equilibrated averages, so we take the last `equilibration_fraction`
#    of steps at each temperature.)
# -----------------------------------------------------------------------

# Identify unique temperatures by rounding to nearest 5 K
df_all["_T_bin"] = (df_all[temp_col] / 5.0).round() * 5.0

records = []
for T_bin, grp in df_all.groupby("_T_bin", sort=True):
    n_eq = max(1, int(len(grp) * equilibration_fraction))
    eq_grp = grp.tail(n_eq)
    records.append({{
        "temperature": float(T_bin),
        "mean_density": float(eq_grp[density_col].mean()),
        "std_density":  float(eq_grp[density_col].std(ddof=1) if len(eq_grp) > 1 else 0.0),
        "n_points":     int(n_eq),
    }})

df_bins = pd.DataFrame(records).sort_values("temperature").reset_index(drop=True)

if len(df_bins) < 4:
    raise ValueError(
        f"Only {{len(df_bins)}} temperature bins found — need at least 4 for a "
        "bilinear fit.  Check that the log contains a temperature sweep."
    )

temps     = df_bins["temperature"].values
densities = df_bins["mean_density"].values

# -----------------------------------------------------------------------
# 3. Bilinear fit to extract Tg
# -----------------------------------------------------------------------

def bilinear_model(T, Tg, a1, b1, a2, b2):
    # Piecewise linear: below Tg (glassy) = a2+b2*T; above (rubbery) = a1+b1*T
    return np.where(T < Tg, a2 + b2 * T, a1 + b1 * T)


def fit_bilinear(temps, densities, tg_guess=None):
    if tg_guess is None:
        tg_guess = float(np.median(temps))

    p0 = [
        tg_guess,   # Tg
        1.2,        # a1 (rubbery intercept)
        -0.0005,    # b1 (rubbery slope, neg)
        1.0,        # a2 (glassy intercept)
        -0.0003,    # b2 (glassy slope, neg, shallower)
    ]

    try:
        popt, _ = optimize.curve_fit(
            bilinear_model, temps, densities,
            p0=p0, maxfev=20000,
        )
    except RuntimeError as e:
        return {{"error": f"curve_fit failed: {{e}}"}}

    Tg, a1, b1, a2, b2 = popt
    predicted = bilinear_model(temps, *popt)
    ss_res = np.sum((densities - predicted) ** 2)
    ss_tot = np.sum((densities - densities.mean()) ** 2)
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")

    # Robustness cross-check: two independent linear regressions
    lo_mask = temps < Tg
    hi_mask = temps >= Tg
    alt_Tg  = None
    if lo_mask.sum() >= 2 and hi_mask.sum() >= 2:
        sl_lo, ic_lo, _, _, _ = stats.linregress(temps[lo_mask], densities[lo_mask])
        sl_hi, ic_hi, _, _, _ = stats.linregress(temps[hi_mask], densities[hi_mask])
        denom = sl_hi - sl_lo
        if abs(denom) > 1e-12:
            alt_Tg = float((ic_lo - ic_hi) / denom)

    return {{
        "Tg":              float(Tg),
        "Tg_alternative":  alt_Tg,
        "params":          {{"a1": float(a1), "b1": float(b1),
                            "a2": float(a2), "b2": float(b2)}},
        "r_squared":       r2,
        "n_temperature_bins": int(len(temps)),
        "temp_range":      [float(temps.min()), float(temps.max())],
    }}


fit_result = fit_bilinear(temps, densities, tg_guess=initial_tg_guess)

if "error" in fit_result:
    print(json.dumps({{"status": "failed", "error": fit_result["error"]}}))
else:
    # -----------------------------------------------------------------------
    # 4. Validation tiers  (|ΔTg| vs experimental not known here, but
    #    we still report quality based on R²)
    # -----------------------------------------------------------------------
    r2 = fit_result["r_squared"]
    fit_quality = (
        "EXCELLENT" if r2 >= 0.99 else
        "GOOD"      if r2 >= 0.97 else
        "ACCEPTABLE" if r2 >= 0.90 else
        "POOR — check data"
    )

    # -----------------------------------------------------------------------
    # 5. Save outputs
    # -----------------------------------------------------------------------
    bins_csv = str(output_dir / "tg_density_bins.csv")
    df_bins.to_csv(bins_csv, index=False)

    result = {{
        "status":             "success",
        "log_file":          log_file,
        "output_dir":        str(output_dir),
        "Tg_K":              fit_result["Tg"],
        "Tg_alternative_K":  fit_result["Tg_alternative"],
        "r_squared":         fit_result["r_squared"],
        "fit_quality":       fit_quality,
        "fit_params":        fit_result["params"],
        "n_temperature_bins": fit_result["n_temperature_bins"],
        "temp_range_K":      fit_result["temp_range"],
        "bins_csv":          bins_csv,
        "equilibration_fraction": equilibration_fraction,
        "temp_col":          temp_col,
        "density_col":       density_col,
    }}

    summary_json = str(output_dir / "tg_summary.json")
    with open(summary_json, "w") as jf:
        json.dump(result, jf, indent=2)
    result["summary_json"] = summary_json

    print(json.dumps(result))
"""

    exec_result = execute_script(script, description="extract_tg")
    if not exec_result["success"]:
        return {"status": "failed", "error": exec_result["stderr"],
                "stdout": exec_result["stdout"]}
    return _parse_json_from_stdout(exec_result["stdout"], exec_result["stderr"])


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

    Workflow
    --------
    1. Parse every thermo block in the LAMMPS log file into a single DataFrame.
    2. Group rows by temperature (binned to nearest 5 K) and compute the mean
       density over the last `equilibration_fraction` of steps at each temperature.
       This gives one (T, ρ) data point per temperature window — identical to the
       procedure used by Larsen et al. and RadonPy.
    3. Fit a bilinear (piecewise-linear) model to ρ(T) using scipy.optimize.curve_fit.
       The breakpoint of the two lines is Tg.
    4. Cross-check with two independent linear regressions (glassy vs. rubbery
       regions) to compute an alternative Tg estimate from the line intersection.
    5. Write outputs to output_dir on Lambda:
           tg_density_bins.csv  — (temperature, mean_density, std_density, n_points)
           tg_summary.json      — all results including Tg, R², fit params

    The job runs in the background — poll with remote_get_job_status(job_id).

    Args:
        log_file:               Full path to the LAMMPS log file on Lambda.
                                Must contain thermo output with Temp and Density columns.
        output_dir:             Output directory on Lambda.
                                Defaults to <log_dir>/tg_analysis.
        initial_tg_guess:       Initial guess for Tg in K (helps curve_fit converge).
                                Defaults to the median temperature in the sweep.
        equilibration_fraction: Fraction of steps at each T used for the mean density
                                (0.5 = last 50 %, default).  Increase if the system
                                equilibrates slowly.
        temp_col:               Name of the temperature column in the LAMMPS log
                                (default: 'Temp').
        density_col:            Name of the density column in the LAMMPS log
                                (default: 'Density').

    Returns:
        dict with job_id.  When completed, result includes:
            Tg_K                — bilinear-fit Tg in Kelvin
            Tg_alternative_K    — cross-check Tg from line intersection
            r_squared           — goodness-of-fit R²
            fit_quality         — EXCELLENT / GOOD / ACCEPTABLE / POOR
            fit_params          — {{a1, b1, a2, b2}}
            n_temperature_bins  — number of (T, ρ) data points used
            temp_range_K        — [T_min, T_max] of the sweep
            bins_csv            — path to tg_density_bins.csv on Lambda
            summary_json        — path to tg_summary.json on Lambda
    """
    if output_dir is None:
        output_dir = str(Path(log_file).parent / "tg_analysis")

    job_id = job_manager.submit_job(
        func     = _run_extract_tg,
        args     = [],
        kwargs   = dict(
            log_file               = log_file,
            output_dir             = output_dir,
            initial_tg_guess       = initial_tg_guess,
            equilibration_fraction = equilibration_fraction,
            temp_col               = temp_col,
            density_col            = density_col,
        ),
        job_type = "extract_tg",
    )
    return {
        "status":   "submitted",
        "job_id":   job_id,
        "job_type": "extract_tg",
        "log_file": log_file,
        "output_dir": output_dir,
        "message":  "Poll with remote_get_job_status(job_id)",
    }


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Remote Test Server Ready!")
    logger.info("Available tools:")
    logger.info("  Equilibration (GPU-accelerated):")
    logger.info("    - submit_equilibration_job (21-step Larsen)")
    logger.info("    - submit_quick_nvt_job")
    logger.info("    - submit_quick_npt_job")
    logger.info("    - submit_additional_equilibration_job")
    logger.info("    - submit_annealing_job")
    logger.info("  Job Management:")
    logger.info("    - get_job_status")
    logger.info("    - get_job_output")
    logger.info("    - list_all_jobs")
    logger.info("  File Operations:")
    logger.info("    - list_remote_files")
    logger.info("    - upload_file_to_lambda")
    logger.info("    - download_file_from_lambda")
    logger.info("    - read_remote_file")
    logger.info("    - read_remote_file_tail")
    logger.info("    - write_remote_file")
    logger.info("    - execute_remote_command")
    logger.info("    - list_remote_files_detailed")
    logger.info("    - check_remote_file_exists")
    logger.info("    - save_molecule_remote")
    logger.info("    - convert_lammps_data_to_json")
    logger.info("  Trajectory Analysis:")
    logger.info("    - unwrap_coordinates")
    logger.info("    - extract_end_to_end_vectors")
    logger.info("    - calculate_rdf")
    logger.info("    - extract_tg")
    logger.info("  System Status:")
    logger.info("    - check_lambda_status")
    logger.info("=" * 60)
    mcp.run()
