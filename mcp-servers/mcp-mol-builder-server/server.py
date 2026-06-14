#!/usr/bin/env python3
"""
RadonPy MCP Server - WITH JOB MANAGEMENT

This MCP server provides tools to build polymer structures and prepare LAMMPS simulations
using the RadonPy library. It enables LLMs to construct complete polymer systems from
SMILES strings with user-defined parameters. This version includes async job submission for long-running operations.
All expensive operations can run in background.
"""

import sys
import os
import threading
import queue
import uuid
import time
from datetime import datetime
from enum import Enum
from pathlib import Path as _Path

# Load root .env (PolyJarvis/.env) — single source of truth for all MCP servers
try:
    from dotenv import load_dotenv
    load_dotenv(_Path(__file__).parent.parent.parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on shell env vars

# Add RadonPy to path — set RADONPY_PATH in .env (see .env.example)
_radonpy_path = os.environ.get("RADONPY_PATH", "")
if _radonpy_path:
    sys.path.insert(0, _radonpy_path)

import tempfile
import json
from pathlib import Path
from typing import Optional, Literal
from mcp.server.fastmcp import FastMCP
import logging
import time as time_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [mol-builder] %(levelname)s %(message)s",
    stream=__import__("sys").stderr,
)
logger = logging.getLogger("mol_builder_mcp")
# Also log to file so we can confirm subprocess launch even from Claude Code
_fh = logging.FileHandler("/tmp/mol-builder-startup.log", mode='a')
_fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
logger.addHandler(_fh)
logger.info("Mol-Builder MCP Server starting...")

# Heavy libs loaded in a background thread so the MCP handshake completes fast
np = pd = optimize = stats = plt = Chem = utils = calc = poly = None
GAFF2_mod = GAFF2 = GAFF = qm = Analyze = None
_libs_ready = threading.Event()

def _load_heavy_libs():
    global np, pd, optimize, stats, plt, Chem, utils, calc, poly
    global GAFF2_mod, GAFF2, GAFF, qm, Analyze
    import numpy as _np
    import pandas as _pd
    from scipy import optimize as _opt, stats as _stats
    import matplotlib as _mpl; _mpl.use('Agg')
    import matplotlib.pyplot as _plt
    from rdkit import Chem as _Chem
    from radonpy.core import utils as _utils, calc as _calc, poly as _poly
    from radonpy.ff.gaff2_mod import GAFF2_mod as _GAFF2_mod
    from radonpy.ff.gaff2 import GAFF2 as _GAFF2
    from radonpy.ff.gaff import GAFF as _GAFF
    from radonpy.sim import qm as _qm
    from radonpy.sim.lammps import Analyze as _Analyze
    np = _np; pd = _pd; optimize = _opt; stats = _stats; plt = _plt; Chem = _Chem
    utils = _utils; calc = _calc; poly = _poly
    GAFF2_mod = _GAFF2_mod; GAFF2 = _GAFF2; GAFF = _GAFF; qm = _qm; Analyze = _Analyze
    _libs_ready.set()
    logger.info("Heavy libs loaded in background")

threading.Thread(target=_load_heavy_libs, daemon=True).start()

# ============================================================================
# JOB MANAGEMENT SYSTEM
# ============================================================================

class JobStatus(Enum):
    """Job status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class JobManager:
    """
    Manage long-running background jobs for RadonPy operations.
    Thread-safe job submission and status tracking.
    """
    
    def __init__(self):
        self.jobs = {}
        self.lock = threading.Lock()
        self.logger = logging.getLogger("mol_builder_mcp.JobManager")
        self.logger.info("JobManager initialized")
    
    def submit_job(self, func, args, kwargs, job_type="generic"):
        """Submit a job and return job_id immediately"""
        job_id = str(uuid.uuid4())[:8]  # Short ID
        
        job_info = {
            "job_id": job_id,
            "job_type": job_type,
            "status": JobStatus.PENDING.value,
            "progress": 0,
            "result": None,
            "error": None,
            "output_files": [],
            "submitted_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "args": args,
            "kwargs": kwargs
        }
        
        with self.lock:
            self.jobs[job_id] = job_info
        
        job_logger = logging.getLogger(f"mol_builder_mcp.job.{job_id}")
        job_logger.info(f"Job submitted: {job_type}")

        # Start background thread
        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, func, args, kwargs),
            daemon=True
        )
        thread.start()
        
        self.logger.info(f"Job {job_id} thread started")
        return job_id
    
    def _run_job(self, job_id, func, args, kwargs):
        job_logger = logging.getLogger(f"mol_builder_mcp.job.{job_id}")
        start_time = time_module.time()
        
        try:
            with self.lock:
                self.jobs[job_id]["status"] = JobStatus.RUNNING.value
                self.jobs[job_id]["started_at"] = datetime.now().isoformat()
            
            job_logger.info("Job execution started")
            self.logger.info(f"Job {job_id} execution started")
            _libs_ready.wait()
            result = func(*args, **kwargs)
            
            elapsed = time_module.time() - start_time
            job_logger.info(f"Function completed in {elapsed:.2f}s")
            
            with self.lock:
                self.jobs[job_id]["status"] = JobStatus.COMPLETED.value
                self.jobs[job_id]["result"] = result
                self.jobs[job_id]["progress"] = 100
                self.jobs[job_id]["completed_at"] = datetime.now().isoformat()
                
                if isinstance(result, dict):
                    if "output_file" in result:
                        self.jobs[job_id]["output_files"].append(result["output_file"])
                        job_logger.info(f"Output file: {result['output_file']}")
                    if "temp_file" in result:
                        self.jobs[job_id]["output_files"].append(result["temp_file"])
            
            job_logger.info(f"Job completed successfully [time: {elapsed:.2f}s]")
            self.logger.info(f"Job {job_id} completed in {elapsed:.2f}s")
                
        except Exception as e:
            elapsed = time_module.time() - start_time
            job_logger.error(f"Job failed after {elapsed:.2f}s: {str(e)}", exc_info=True)
            self.logger.error(f"Job {job_id} failed: {str(e)}")
            
            with self.lock:
                self.jobs[job_id]["status"] = JobStatus.FAILED.value
                self.jobs[job_id]["error"] = str(e)
                self.jobs[job_id]["completed_at"] = datetime.now().isoformat()
    
    def get_status(self, job_id):
        """Get job status"""
        with self.lock:
            if job_id not in self.jobs:
                return {"error": f"Job {job_id} not found"}
            return {
                "job_id": job_id,
                "job_type": self.jobs[job_id]["job_type"],
                "status": self.jobs[job_id]["status"],
                "progress": self.jobs[job_id]["progress"],
                "submitted_at": self.jobs[job_id]["submitted_at"],
                "started_at": self.jobs[job_id]["started_at"],
                "completed_at": self.jobs[job_id]["completed_at"],
                "has_result": self.jobs[job_id]["result"] is not None,
                "has_error": self.jobs[job_id]["error"] is not None
            }
    
    def get_output(self, job_id):
        """Get job output/results"""
        with self.lock:
            if job_id not in self.jobs:
                return {"error": f"Job {job_id} not found"}
            
            job = self.jobs[job_id]
            
            if job["status"] == JobStatus.PENDING.value:
                return {
                    "job_id": job_id,
                    "status": job["status"],
                    "message": "Job is pending, not started yet"
                }
            
            if job["status"] == JobStatus.RUNNING.value:
                return {
                    "job_id": job_id,
                    "status": job["status"],
                    "progress": job["progress"],
                    "message": "Job is still running"
                }
            
            if job["status"] == JobStatus.FAILED.value:
                return {
                    "job_id": job_id,
                    "status": job["status"],
                    "error": job["error"],
                    "completed_at": job["completed_at"]
                }
            
            # Completed
            return {
                "job_id": job_id,
                "status": job["status"],
                "result": job["result"],
                "output_files": job["output_files"],
                "completed_at": job["completed_at"]
            }
    
    def list_jobs(self, status_filter=None):
        """List all jobs, optionally filtered by status"""
        with self.lock:
            jobs_list = []
            for jid, info in self.jobs.items():
                if status_filter is None or info["status"] == status_filter:
                    jobs_list.append({
                        "job_id": jid,
                        "job_type": info["job_type"],
                        "status": info["status"],
                        "progress": info["progress"],
                        "submitted_at": info["submitted_at"],
                        "started_at": info["started_at"],
                        "completed_at": info["completed_at"]
                    })
            return jobs_list
    
    def cancel_job(self, job_id):
        """Mark job for cancellation (note: actual cancellation depends on implementation)"""
        with self.lock:
            if job_id not in self.jobs:
                return {"error": f"Job {job_id} not found"}
            
            if self.jobs[job_id]["status"] in [JobStatus.COMPLETED.value, JobStatus.FAILED.value]:
                return {"error": f"Job {job_id} already finished"}
            
            # Note: This doesn't actually stop the thread, just marks it
            # For true cancellation, would need cooperative thread cancellation
            self.jobs[job_id]["status"] = JobStatus.FAILED.value
            self.jobs[job_id]["error"] = "Cancelled by user"
            self.jobs[job_id]["completed_at"] = datetime.now().isoformat()
            
            return {
                "job_id": job_id,
                "message": "Job marked as cancelled"
            }

# Create global job manager instance
job_manager = JobManager()

# ============================================================================
# HELPER FUNCTIONS FOR BACKGROUND EXECUTION
# ============================================================================

def _run_conformer_search(mol_file, ff, psi4_omp, mpi, omp, memory, log_name, work_dir):
    """Internal function to run conformer search"""
    os.makedirs(work_dir, exist_ok=True)
    mol = utils.JSONToMol(mol_file)
    mol_opt, energies = qm.conformation_search(
        mol,
        ff=ff,
        psi4_omp=psi4_omp,
        mpi=mpi,
        omp=omp,
        memory=memory,
        log_name=log_name,
        work_dir=work_dir
    )
    
    utils.MolToJSON(mol_opt, mol_file)
    
    return {
        "status": "success",
        "num_conformers": mol_opt.GetNumConformers(),
        "energies_kcal": energies.tolist() if isinstance(energies, np.ndarray) else [energies],
        "lowest_energy": float(np.min(energies)),
        "energy_range": float(np.max(energies) - np.min(energies)),
        "output_file": mol_file,
        "message": f"Generated {mol_opt.GetNumConformers()} conformers, lowest energy {np.min(energies):.4f} kcal/mol"
    }

def _assign_charges_am1bcc(mol):
    """Assign GFN2-xTB Mulliken charges as AM1-BCC surrogate (fast, no antechamber needed).

    Quality is comparable to AM1-BCC for GAFF2-typed organic monomers.
    Use when RESP/ESP Psi4 jobs exceed ~2h (large fused aromatics, polyimides).
    """
    from xtb.interface import Calculator, Param
    from xtb.libxtb import VERBOSITY_MUTED
    from rdkit.Chem import AllChem
    import numpy as np

    BOHR = 0.529177249  # Å per bohr

    if mol.GetNumConformers() == 0:
        AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())

    conf = mol.GetConformer()
    numbers = np.array([atom.GetAtomicNum() for atom in mol.GetAtoms()])
    positions = np.array([conf.GetAtomPosition(i) for i in range(mol.GetNumAtoms())]) / BOHR

    calc = Calculator(Param.GFN2xTB, numbers, positions)
    calc.set_verbosity(VERBOSITY_MUTED)
    res = calc.singlepoint()
    charges = res.get_charges().tolist()

    for i, atom in enumerate(mol.GetAtoms()):
        atom.SetDoubleProp('AtomicCharge', charges[i])
    return charges


def _run_assign_charges(mol_file, charge_method, optimize_geometry, omp_psi4, memory, work_dir):
    """Internal function to assign charges"""
    os.makedirs(work_dir, exist_ok=True)
    mol = utils.JSONToMol(mol_file)

    if charge_method == "am1bcc":
        charges = _assign_charges_am1bcc(mol)
    else:
        result = qm.assign_charges(
            mol,
            charge=charge_method,
            opt=optimize_geometry,
            omp=omp_psi4,
            memory=memory,
            log_name='monomer1',
            work_dir=work_dir
        )
        if not result:
            raise Exception(f"Charge assignment failed with method {charge_method}")
        charges = [atom.GetDoubleProp('AtomicCharge') for atom in mol.GetAtoms()]

    total_charge = sum(charges)
    utils.MolToJSON(mol, mol_file)

    return {
        "status": "success",
        "method": charge_method,
        "total_charge": float(total_charge),
        "charge_range": [float(min(charges)), float(max(charges))],
        "num_atoms": len(charges),
        "output_file": mol_file,
        "message": f"Charges assigned using {charge_method} method"
    }

def _run_polymerize(mol_file, degree_of_polymerization, tacticity, headhead):
    """Internal function to polymerize"""
    mol = utils.JSONToMol(mol_file)
    
    polymer = poly.polymerize_rw(
        mol,
        n=degree_of_polymerization,
        tacticity=tacticity,
        headhead=headhead,
    )
    
    stats = poly.polymer_stats(polymer, df=False)
    utils.MolToJSON(polymer, mol_file)
    
    return {
        "status": "success",
        "degree_of_polymerization": degree_of_polymerization,
        "tacticity": tacticity,
        "num_atoms": polymer.GetNumAtoms(),
        "num_bonds": polymer.GetNumBonds(),
        "molecular_weight": stats['Mn'],
        "output_file": mol_file,
        "message": f"Polymer generated with {degree_of_polymerization} repeat units"
    }

def _run_generate_cell(mol_file, num_chains, density, temperature):
    """Internal function to generate amorphous cell"""
    mol = utils.JSONToMol(mol_file)

    cell = poly.amorphous_cell(mol, n=num_chains, density=density)
    cell = calc.set_velocity(cell, temp=temperature)

    output_file = mol_file.replace('.json', '_cell.json')
    utils.MolToJSON(cell, output_file)

    stats = poly.polymer_stats(cell, df=False)

    return {
        "status": "success",
        "num_chains": num_chains,
        "num_atoms": cell.GetNumAtoms(),
        "density_target": density,
        "density_actual": calc.mol_density(cell),
        "cell_volume": cell.cell.volume,
        "cell_dimensions": {"x": cell.cell.dx, "y": cell.cell.dy, "z": cell.cell.dz},
        "molecular_weight_avg": stats['Mn'],
        "output_file": output_file,
        "message": f"Amorphous cell generated with {num_chains} chains"
    }


def _run_copolymerize(mol_files, copoly_type, n, ratios, tacticity, nchain, work_dir, forcefield):
    """Internal function to build random, alternating, or block copolymer chains."""
    os.makedirs(work_dir, exist_ok=True)

    mols = [utils.JSONToMol(f) for f in mol_files]

    if copoly_type == "alternating":
        # n = repeat units per monomer block; total DP ≈ n * len(mols)
        chains = poly.copolymerize_rw_mp(mols, n, tacticity=tacticity, nchain=nchain)
    elif copoly_type == "random":
        if ratios is None:
            ratios = [1.0 / len(mols)] * len(mols)
        chains = poly.random_copolymerize_rw_mp(mols, n, ratio=ratios, tacticity=tacticity, nchain=nchain)
    elif copoly_type == "block":
        if ratios is None:
            ratios = [1.0 / len(mols)] * len(mols)
        n_list = [max(1, round(n * r / sum(ratios))) for r in ratios]
        chains = poly.block_copolymerize_rw_mp(mols, n_list, tacticity=tacticity, nchain=nchain)
    else:
        raise ValueError(f"Unknown copoly_type: {copoly_type}")

    ff_obj = None
    if forcefield == "GAFF":
        ff_obj = GAFF()
    elif forcefield == "GAFF2":
        ff_obj = GAFF2()
    elif forcefield == "GAFF2_mod":
        ff_obj = GAFF2_mod()

    chain_files = []
    ff_failed = []
    for i, chain in enumerate(chains):
        if ff_obj is not None:
            ok = ff_obj.ff_assign(chain)
            if not ok:
                ff_failed.append(i)
        chain_file = os.path.join(work_dir, f"chain_{i}.json")
        utils.MolToJSON(chain, chain_file)
        chain_files.append(chain_file)

    stats = poly.polymer_stats(chains[0], df=False)

    result = {
        "status": "success",
        "copoly_type": copoly_type,
        "n_chains": len(chains),
        "ratios": ratios,
        "chain_files": chain_files,
        "num_atoms_per_chain": chains[0].GetNumAtoms(),
        "molecular_weight": float(stats['Mn']),
        "forcefield_assigned": forcefield is not None,
        "message": f"{copoly_type} copolymer: {nchain} chains generated",
    }
    if copoly_type == "block":
        result["block_lengths"] = n_list
    if ff_failed:
        result["ff_assignment_warnings"] = f"FF assignment failed for chains: {ff_failed}"
    return result


def _run_generate_copolymer_cell(chain_files, density, temperature):
    """Pack pre-built copolymer chains (one JSON per chain) into an amorphous cell."""
    chains = [utils.JSONToMol(f) for f in chain_files]

    # amorphous_mixture_cell: mols = list of mol objects, n = list of counts (1 each)
    cell = poly.amorphous_mixture_cell(chains, [1] * len(chains), density=density)
    cell = calc.set_velocity(cell, temp=temperature)

    work_dir = os.path.dirname(chain_files[0])
    output_file = os.path.join(work_dir, "copolymer_cell.json")
    utils.MolToJSON(cell, output_file)

    return {
        "status": "success",
        "num_chains": len(chains),
        "num_atoms": cell.GetNumAtoms(),
        "density_target": density,
        "density_actual": float(calc.mol_density(cell)),
        "cell_volume": float(cell.cell.volume),
        "cell_dimensions": {"x": float(cell.cell.dx), "y": float(cell.cell.dy), "z": float(cell.cell.dz)},
        "output_file": output_file,
        "message": f"Copolymer cell packed: {len(chains)} chains, {cell.GetNumAtoms()} atoms",
    }


# ============================================================================
# MCP SERVER
# ============================================================================

# Create MCP server
mcp = FastMCP(
    "RadonPy",
    instructions="""
    RadonPy MCP Server with Job Management for polymer simulation preparation.
    
    ASYNC OPERATIONS (return job_id immediately):
    - submit_conformer_search_job() - QM conformer search
    - submit_assign_charges_job() - QM charge calculations
    - submit_polymerize_job() - Homopolymer generation
    - submit_copolymerize_job() - Random/alternating/block copolymer generation
    - submit_generate_cell_job() - Amorphous cell packing (homopolymer)
    - submit_generate_copolymer_cell_job() - Amorphous cell packing (copolymer chains)
    
    JOB MANAGEMENT:
    - get_job_status(job_id) - Check job progress
    - get_job_output(job_id) - Get results when complete
    - list_all_jobs() - See all submitted jobs
    - cancel_job(job_id) - Cancel a running job
    
    SYNC OPERATIONS (for quick tasks):
    - build_molecule_from_smiles() - Fast
    - assign_forcefield() - Fast
    - save_molecule() - Fast
    - get_molecule_info() - Fast
    
    Typical homopolymer workflow:
    1. build_molecule_from_smiles() → submit_assign_charges_job()
    2. submit_polymerize_job() → submit_generate_cell_job() → save_lammps_data()

    Typical copolymer workflow:
    1. build_molecule_from_smiles() x N monomers → submit_assign_charges_job() x N
    2. submit_copolymerize_job(mol_files=[...], copoly_type, ratios, forcefield=FF)
    3. submit_generate_copolymer_cell_job(chain_files from step 2) → save_lammps_data()
    """
)

# ============================================================================
# JOB MANAGEMENT TOOLS
# ============================================================================

@mcp.tool()
def submit_conformer_search_job(
    mol_file: str,
    ff: str = None, # Force field instance. If None, MMFF94 optimization is carried out by RDKit
    psi4_omp: int = 1, # OpenMP threads
    mpi: int = 1, # Number of MPI processes for parallel execution
    omp: int = 1, # OpenMP threads for RadonPy LAMMPS simulations
    memory: int = 2000, # Memory for Psi4 calculations in MB
    log_name: str = 'monomer1', # Name of output log files for this step
    work_dir: str = 'conformer_search' # Working directory
) -> dict:
    """
    Submit conformer search job (runs in background).
    
    Returns immediately with job_id. Use get_job_status() to check progress.
    """
    try:
        job_id = job_manager.submit_job(
            func=_run_conformer_search,
            args=(),
            kwargs={
                "mol_file": mol_file,
                "ff": ff,
                "psi4_omp": psi4_omp,
                "mpi": mpi,
                "omp": omp,
                "memory": memory,
                "log_name": log_name,
                "work_dir": work_dir
            },
            job_type="conformer_search"
        )
        
        return {
            "status": "submitted",
            "job_id": job_id,
            "job_type": "conformer_search",
            "message": f"Conformer search job {job_id} submitted. This may take 30-60 minutes."
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def submit_assign_charges_job(
    mol_file: str, # Path to molecule JSON file
    charge_method: Literal["gasteiger", "RESP", "ESP", "Mulliken", "Lowdin", "am1bcc"] = "RESP",
    optimize_geometry: bool = False, # Whether to optimize geometry before charge calculation
    omp_psi4: int = 1, # OpenMP threads for Psi4
    memory: int = 2000, # Memory for Psi4 calculations in MB
    work_dir: str = 'assign_charges' # Working directory
) -> dict:
    """
    Submit charge assignment job (runs in background).

    charge_method options:
      RESP/ESP/Mulliken/Lowdin — Psi4 QM (slow, ~30-120 min for large monomers)
      am1bcc                   — GFN2-xTB Mulliken charges (AM1-BCC surrogate,
                                 <1s, no antechamber needed; use for large/fused
                                 aromatics where RESP takes >2h)
      gasteiger                — RDKit Gasteiger (fastest, lowest accuracy)

    Returns immediately with job_id. Use get_job_status() to check progress.
    """
    try:
        job_id = job_manager.submit_job(
            func=_run_assign_charges,
            args=(),
            kwargs={
                "mol_file": mol_file,
                "charge_method": charge_method,
                "optimize_geometry": optimize_geometry,
                "omp_psi4": omp_psi4,
                "memory": memory,
                "work_dir": work_dir
            },
            job_type="assign_charges"
        )
        
        return {
            "status": "submitted",
            "job_id": job_id,
            "job_type": "assign_charges",
            "message": f"Charge assignment job {job_id} submitted. Method: {charge_method}"
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def submit_polymerize_job(
    mol_file: str,
    degree_of_polymerization: int,
    tacticity: Literal["isotactic", "syndiotactic", "atactic"] = "atactic",
    headhead: bool = False
) -> dict:
    """
    Submit polymerization job (runs in background).
    
    Args:
        mol_file: Path to monomer molecule JSON file
        degree_of_polymerization: Number of repeat units (n)
        tacticity: Polymer tacticity
        headhead: Use head-to-head polymerization if True

    Returns immediately with job_id. Useful for large polymers (n>50).
    """
    try:
        job_id = job_manager.submit_job(
            func=_run_polymerize,
            args=(),
            kwargs={
                "mol_file": mol_file,
                "degree_of_polymerization": degree_of_polymerization,
                "tacticity": tacticity,
                "headhead": headhead
            },
            job_type="polymerize"
        )
        
        return {
            "status": "submitted",
            "job_id": job_id,
            "job_type": "polymerize",
            "message": f"Polymerization job {job_id} submitted. DP={degree_of_polymerization}"
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def submit_generate_cell_job(
    mol_file: str,
    num_chains: int,
    density: float = 0.05,
    temperature: float = 300.0
) -> dict:
    """
    Submit amorphous cell generation job (runs in background).
    
    Args:
        mol_file: Path to polymer molecule JSON file
        num_chains: Number of polymer chains in the cell
        density: Initial density in g/cm³
        temperature: Temperature in Kelvin

    Returns immediately with job_id. Useful for large systems (>6 chains).
    """
    try:
        job_id = job_manager.submit_job(
            func=_run_generate_cell,
            args=(),
            kwargs={
                "mol_file": mol_file,
                "num_chains": num_chains,
                "density": density,
                "temperature": temperature
            },
            job_type="generate_cell"
        )
        
        return {
            "status": "submitted",
            "job_id": job_id,
            "job_type": "generate_cell",
            "message": f"Cell generation job {job_id} submitted. {num_chains} chains"
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def submit_copolymerize_job(
    mol_files: list[str],
    copoly_type: Literal["random", "alternating", "block"] = "random",
    n: int = 20,
    ratios: Optional[list[float]] = None,
    tacticity: Literal["isotactic", "syndiotactic", "atactic"] = "atactic",
    nchain: int = 10,
    forcefield: Optional[Literal["GAFF", "GAFF2", "GAFF2_mod"]] = None,
    work_dir: str = "copolymerize"
) -> dict:
    """
    Build random, alternating, or block copolymer chains from two or more charged monomers.

    Prereq: each monomer in mol_files must already have charges assigned
    (run submit_assign_charges_job first for each monomer).

    Args:
        mol_files:   Ordered list of monomer JSON file paths (one per monomer type).
        copoly_type: Architecture — "random", "alternating", or "block".
        n:           Degree of polymerization.
                       random/alternating: total repeat units per chain.
                       block: total repeat units split by ratios (e.g. n=20, ratios=[0.7,0.3]
                              → block_A=14 units, block_B=6 units).
        ratios:      Mole fractions for each monomer (must sum to 1.0).
                       random: target composition (e.g. [0.7, 0.3] for 70:30).
                       block:  controls block length split.
                       alternating: ignored (sequence is strictly alternating).
                       Defaults to equal fractions if None.
        tacticity:   Stereoregularity of each chain.
        nchain:      Number of independent chains to generate.
        forcefield:  If provided, assigns FF parameters to every chain immediately.
                     Pass the same FF you would use for the homopolymer components.
                     Skipping here means you must call assign_forcefield() per chain later.
        work_dir:    Directory where chain_0.json … chain_N.json are written.

    Returns job_id. Use get_job_output() for chain_files list once complete.
    Pass chain_files to submit_generate_copolymer_cell_job() to pack the cell.
    """
    try:
        job_id = job_manager.submit_job(
            func=_run_copolymerize,
            args=(),
            kwargs={
                "mol_files": mol_files,
                "copoly_type": copoly_type,
                "n": n,
                "ratios": ratios,
                "tacticity": tacticity,
                "nchain": nchain,
                "work_dir": work_dir,
                "forcefield": forcefield,
            },
            job_type="copolymerize"
        )
        return {
            "status": "submitted",
            "job_id": job_id,
            "job_type": "copolymerize",
            "message": (
                f"{copoly_type} copolymerization job {job_id} submitted. "
                f"{nchain} chains, DP={n}, {len(mol_files)} monomers."
            ),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def submit_generate_copolymer_cell_job(
    chain_files: list[str],
    density: float = 0.05,
    temperature: float = 300.0
) -> dict:
    """
    Pack pre-built copolymer chains into an amorphous simulation cell.

    Use this after submit_copolymerize_job completes. Pass the chain_files
    list from that job's output directly here.

    Prereq: every chain in chain_files must have FF parameters assigned
    (either via forcefield= in submit_copolymerize_job, or assign_forcefield()
    called per chain afterward).

    Args:
        chain_files: List of chain JSON file paths (chain_0.json … chain_N.json)
                     returned by submit_copolymerize_job.
        density:     Initial packing density in g/cm³ (default 0.05 — low density
                     lets LAMMPS compress during equilibration Stage 2).
        temperature: Temperature (K) for initial velocity assignment.

    Returns job_id. Output includes output_file path for the packed cell JSON,
    ready for save_lammps_data().
    """
    try:
        job_id = job_manager.submit_job(
            func=_run_generate_copolymer_cell,
            args=(),
            kwargs={
                "chain_files": chain_files,
                "density": density,
                "temperature": temperature,
            },
            job_type="generate_copolymer_cell"
        )
        return {
            "status": "submitted",
            "job_id": job_id,
            "job_type": "generate_copolymer_cell",
            "message": f"Copolymer cell packing job {job_id} submitted. {len(chain_files)} chains.",
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_job_status(job_id: str) -> dict:
    """
    Get the status of a submitted job.
    
    Args:
        job_id: Job ID returned from submit_*_job
    
    Returns:
        Status: pending/running/completed/failed with progress info
    """
    return job_manager.get_status(job_id)

@mcp.tool()
def get_job_output(job_id: str) -> dict:
    """
    Get the output/results from a completed job.
    
    Args:
        job_id: Job ID returned from submit_*_job
    
    Returns:
        Job results, output files, and data (only available when status=completed)
    """
    return job_manager.get_output(job_id)

@mcp.tool()
def list_all_jobs(status_filter: Optional[Literal["pending", "running", "completed", "failed"]] = None) -> dict:
    """
    List all submitted jobs and their statuses.
    
    Args:
        status_filter: Optional filter by status
    
    Returns:
        List of all jobs with their current status
    """
    jobs = job_manager.list_jobs(status_filter)
    return {
        "total_jobs": len(jobs),
        "jobs": jobs,
        "filter": status_filter
    }

@mcp.tool()
def cancel_job(job_id: str) -> dict:
    """
    Cancel a pending or running job.
    
    Args:
        job_id: Job ID to cancel
    
    Returns:
        Cancellation status
    """
    return job_manager.cancel_job(job_id)

# ============================================================================
# ORIGINAL SYNC TOOLS (keep for fast operations)
# ============================================================================

# PoLyInfo class ID → name/description lookup
def _get_preferred_ff(smiles: str, class_name: str) -> dict:
    """Return preferred FF, builder, and justification based on SMILES chemistry and class.

    Decision rule (E1):
      PCBN/PAMD/PKTN/PSFO/PIMD → pcff / emc  (Track C, already implemented)
      All-aliphatic C/H only   → trappe-ua / emc  (Ramos 2015 PE benchmark)
      Polar / halogen / aromatic → opls-aa/2024 / emc  (Afzal 2021, 315 polymers)
    """
    PCFF_CLASSES = {"PCBN", "PAMD", "PKTN", "PSFO", "PIMD"}
    if class_name in PCFF_CLASSES:
        return {
            "preferred_ff": "pcff",
            "preferred_builder": "emc",
            "ff_confidence": "high",
            "ff_justification": "Track C engineering thermoplastic — PCFF via EMC",
            "ff_justification_doi": None,
        }

    smiles_clean = smiles.replace("[*]", "[H]").replace("*", "[H]")
    try:
        from rdkit import Chem  # available in radonpy env
        mol = Chem.MolFromSmiles(smiles_clean)
        if mol is None:
            raise ValueError("unparseable SMILES")
        has_aromatic = any(a.GetIsAromatic() for a in mol.GetAtoms())
        has_heteroatom = any(a.GetAtomicNum() not in (1, 6) for a in mol.GetAtoms())
    except Exception:
        import re
        lc = set(re.findall(r'[a-z]', smiles_clean))
        has_aromatic = bool(lc & {'c', 'n', 'o', 's', 'p'})
        up = smiles_clean.upper()
        has_heteroatom = any(x in up for x in ['O', 'N', 'S', 'F', 'CL', 'BR', 'I', 'P', 'SI'])

    if not has_aromatic and not has_heteroatom:
        return {
            "preferred_ff": "trappe-ua",
            "preferred_builder": "emc",
            "ff_confidence": "high" if class_name == "PHYC" else "medium",
            "ff_justification": (
                "All-aliphatic C/H backbone — TraPPE-UA via EMC. "
                "Ramos et al. Macromolecules 2015: PE Tg=187K vs exp 185-195K, density ±7%. "
                "Branched types (PP, PIB): parameters exist but polymer-Tg validation pending."
            ),
            "ff_justification_doi": "10.1021/acs.macromol.5b00823",
        }

    caveat = (
        " CAUTION: OPLS3e R²=0.40 for styrene-class polymers (Afzal 2021) — "
        "rank-ordering within PS class unreliable; advisor input pending."
        if class_name == "PSTR" else ""
    )
    return {
        "preferred_ff": "opls-aa/2024",
        "preferred_builder": "emc",
        "ff_confidence": "medium" if class_name == "PSTR" else "high",
        "ff_justification": (
            "Polar/halogen/aromatic backbone — OPLS-AA 2024 via EMC. "
            f"Afzal 2021 (OPLS3e, 315 polymers): density R²=0.95, MAE=3.5%.{caveat}"
        ),
        "ff_justification_doi": "10.1021/acsapm.0c00524",
    }


POLYINFO_CLASS_NAMES = {
    0: ("UNKNOWN", "Unclassified"),
    1: ("PHYC", "Polyhydrocarbon"),
    2: ("PSTR", "Polystyrenic"),
    3: ("PVNL", "Polyvinyl"),
    4: ("PACR", "Polyacrylic"),
    5: ("PHAL", "Polyhalogenated"),
    6: ("PDIE", "Polydiene"),
    7: ("POXI", "Polyoxide/Polyether"),
    8: ("PSUL", "Polythioether"),
    9: ("PEST", "Polyester"),
    10: ("PAMD", "Polyamide"),
    11: ("PURT", "Polyurethane"),
    12: ("PURA", "Polyurea"),
    13: ("PIMD", "Polyimide"),
    14: ("PANH", "Polyanhydride"),
    15: ("PCBN", "Polycarbonate"),
    16: ("PIMN", "Polyamine"),
    17: ("PSIL", "Polysiloxane"),
    18: ("PPHS", "Polyphosphazene"),
    19: ("PKTN", "Polyketone/PEEK"),
    20: ("PSFO", "Polysulfone"),
    21: ("PPNL", "Polyphenylenevinylene"),
}


@mcp.tool()
def classify_polymer(smiles: str) -> dict:
    """
    Classify a polymer repeat unit into one of 21 PoLyInfo backbone classes.

    Delegates to RadonPy's poly.polyinfo_classifier which:
      - Extracts the mainchain from the repeat-unit SMILES
      - Builds a cyclic tetramer for robust SMARTS matching
      - Uses isotope-tagged [14C] for mainchain-aware patterns (styrene, acrylic)
      - Falls back to element counting for vinyl/diene/hydrocarbon/halogenated

    Returns ONLY the polymer class — force field, charge method, and
    electrostatics selections are handled downstream.

    Args:
        smiles: Polymer SMILES with * or [*] attachment points
                (e.g. "*CC*", "*CCO*", "*CC(C)(C(=O)OC)*")

    Returns:
        dict with class_id, class_name, description, flags (all 21 groups),
        co_occurring_groups, and any warnings
    """
    _libs_ready.wait()
    try:
        class_id, flags = poly.polyinfo_classifier(smiles, return_flag=True)

        class_name, description = POLYINFO_CLASS_NAMES.get(
            class_id, ("UNKNOWN", "Unclassified")
        )

        # Identify co-occurring functional groups (matched but not the winner)
        co_occurring = []
        for flag_name, matched in flags.items():
            if matched and flag_name != class_name:
                fid = next(
                    (k for k, v in POLYINFO_CLASS_NAMES.items() if v[0] == flag_name),
                    None,
                )
                if fid is not None:
                    co_occurring.append({
                        "class_id": fid,
                        "class_name": flag_name,
                        "description": POLYINFO_CLASS_NAMES[fid][1],
                    })

        # Warnings for known force-field problem cases
        warning = None
        if class_name == "PHYC":
            warning = (
                "Pure hydrocarbon (PHYC): GAFF2_mod overestimates PE density "
                "~24% and Tg ~80K. Use GAFF2 instead of GAFF2_mod."
            )
        elif class_name == "PDIE":
            warning = (
                "Diene polymer: verify cis/trans geometry in SMILES — "
                "cis vs trans isomers can differ by ~60K in Tg."
            )

        ff_routing = _get_preferred_ff(smiles, class_name)

        return {
            "status": "success",
            "class_id": class_id,
            "class_name": class_name,
            "description": description,
            "flags": flags,
            "co_occurring_groups": co_occurring,
            "warning": warning,
            "preferred_ff": ff_routing["preferred_ff"],
            "preferred_builder": ff_routing["preferred_builder"],
            "ff_confidence": ff_routing["ff_confidence"],
            "ff_justification": ff_routing["ff_justification"],
            "ff_justification_doi": ff_routing["ff_justification_doi"],
            "message": f"Class {class_id} ({class_name}): {description}",
        }

    except Exception as e:
        return {
            "status": "error",
            "class_id": 0,
            "class_name": "UNKNOWN",
            "message": f"Classification failed: {str(e)}",
        }


@mcp.tool()
def build_molecule_from_smiles(smiles: str, add_hydrogens: bool = True) -> dict:
    """
    Build a molecule from a SMILES string (fast, synchronous).
    
    Args:
        smiles: SMILES string representation of the molecule
        add_hydrogens: Whether to add explicit hydrogens
    
    Returns:
        dict with status, num_atoms, num_bonds, and temp_file path
    """
    _libs_ready.wait()
    try:
        mol = utils.mol_from_smiles(smiles)
        if mol is None:
            return {"error": "Invalid SMILES string", "smiles": smiles}
        
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, f"radonpy_mol_{os.getpid()}.json")
        utils.MolToJSON(mol, temp_file)
        
        return {
            "status": "success",
            "smiles": smiles,
            "num_atoms": mol.GetNumAtoms(),
            "num_bonds": mol.GetNumBonds(),
            "has_3d": mol.GetNumConformers() > 0,
            "temp_file": temp_file,
            "message": f"Molecule built with {mol.GetNumAtoms()} atoms"
        }
    except Exception as e:
        return {"error": str(e), "smiles": smiles}

@mcp.tool()
def assign_forcefield(
    mol_file: str,
    forcefield: Literal["GAFF", "GAFF2", "GAFF2_mod"] = "GAFF2_mod"
) -> dict:
    """
    Assign force field parameters (fast, synchronous).
    
    Args:
        mol_file: Path to molecule JSON file
        forcefield: Force field to use
    
    Returns:
        dict with force field assignment status
    """
    _libs_ready.wait()
    try:
        mol = utils.JSONToMol(mol_file)
        
        if forcefield == "GAFF":
            ff = GAFF()
        elif forcefield == "GAFF2":
            ff = GAFF2()
        elif forcefield == "GAFF2_mod":
            ff = GAFF2_mod()
        else:
            return {"error": f"Unknown force field: {forcefield}"}
        
        result = ff.ff_assign(mol)
        
        if not result:
            return {"error": "Force field assignment failed", "forcefield": forcefield}
        
        utils.MolToJSON(mol, mol_file)
        
        atom_types = set()
        for atom in mol.GetAtoms():
            if atom.HasProp('ff_type'):
                atom_types.add(atom.GetProp('ff_type'))
        
        return {
            "status": "success",
            "forcefield": forcefield,
            "num_atom_types": len(atom_types),
            "atom_types": list(atom_types),
            "num_atoms": mol.GetNumAtoms(),
            "num_bonds": mol.GetNumBonds(),
            "message": f"Force field {forcefield} assigned successfully"
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def save_molecule(
    mol_file: str,
    output_path: str,
    format: Literal["json", "mol", "pdb", "xyz", "lammps"] = "json"
) -> dict:
    """
    Save molecule to file (fast, synchronous).
    
    Args:
        mol_file: Path to molecule JSON file
        output_path: Output file path
        format: Output format
    
    Returns:
        dict with save status
    """
    _libs_ready.wait()
    try:
        mol = utils.JSONToMol(mol_file)
        
        if format == "json":
            utils.MolToJSON(mol, output_path)
        elif format == "mol":
            Chem.MolToMolFile(mol, output_path)
        elif format == "pdb":
            Chem.MolToPDBFile(mol, output_path)
        elif format == "xyz":
            Chem.MolToXYZFile(mol, output_path)
        elif format == "lammps":
            from radonpy.sim import lammps as lmp_module
            result = lmp_module.MolToLAMMPSdata(mol, output_path)
            if not result:
                return {"error": "MolToLAMMPSdata returned False — check that force field parameters are assigned (run assign_forcefield first)"}
        
        return {
            "status": "success",
            "output_path": output_path,
            "format": format,
            "message": f"Molecule saved to {output_path}"
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def save_lammps_data(
    mol_file: str,
    output_path: str,
    temp: float = 300.0,
    include_velocities: bool = True,
) -> dict:
    """
    Save a RadonPy molecule/cell to a LAMMPS .data file.

    This is the primary bridge between RadonPy's JSON format and
    the LAMMPS Engine's template-based simulation pipeline.

    Prerequisites:
        - Force field must be assigned (run assign_forcefield first)
        - For amorphous cells, cell geometry must be present

    Args:
        mol_file:            Path to RadonPy JSON molecule/cell file
        output_path:         Output .data file path (should end in .data)
        temp:                Temperature (K) used for initial velocity generation
        include_velocities:  If True, write initial velocities to the data file

    Returns:
        dict with output path, atom count, atom types, and box dimensions
    """
    _libs_ready.wait()
    try:
        from radonpy.sim import lammps as lmp_module
        from radonpy.core import utils, calc

        mol = utils.JSONToMol(mol_file)

        # Check force field is assigned
        if not mol.GetAtomWithIdx(0).HasProp('ff_type'):
            return {
                "error": "No force field parameters found on molecule. "
                         "Run assign_forcefield() before saving as LAMMPS data."
            }

        ok = lmp_module.MolToLAMMPSdata(
            mol,
            output_path,
            velocity=include_velocities,
            temp=temp,
        )

        if not ok:
            return {"error": "MolToLAMMPSdata failed — check force field assignment"}

        # Collect summary info
        atom_types = sorted({a.GetProp('ff_type') for a in mol.GetAtoms()
                             if a.HasProp('ff_type')})

        info = {
            "status": "success",
            "output_path": output_path,
            "num_atoms": mol.GetNumAtoms(),
            "num_bonds": mol.GetNumBonds(),
            "num_atom_types": len(atom_types),
            "atom_types": atom_types,
            "message": f"LAMMPS data file written to {output_path}",
        }

        if hasattr(mol, 'cell'):
            info["is_cell"] = True
            info["box"] = {
                "x": round(mol.cell.dx, 4),
                "y": round(mol.cell.dy, 4),
                "z": round(mol.cell.dz, 4),
            }
            info["density_g_cm3"] = round(calc.mol_density(mol), 4)
        else:
            info["is_cell"] = False

        return info

    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


@mcp.tool()
def get_molecule_info(mol_file: str) -> dict:
    """
    Get information about a molecule (fast, synchronous).
    
    Args:
        mol_file: Path to molecule JSON file
    
    Returns:
        dict with molecule information
    """
    _libs_ready.wait()
    try:
        mol = utils.JSONToMol(mol_file)
        
        info = {
            "num_atoms": mol.GetNumAtoms(),
            "num_bonds": mol.GetNumBonds(),
            "num_conformers": mol.GetNumConformers(),
            "has_3d": mol.GetNumConformers() > 0,
            "has_charges": mol.GetAtomWithIdx(0).HasProp('AtomicCharge'),
            "has_forcefield": mol.GetAtomWithIdx(0).HasProp('ff_type'),
            "molecular_weight": calc.molecular_weight(mol)
        }
        
        try:
            info["smiles"] = Chem.MolToSmiles(mol)
        except:
            info["smiles"] = None
        
        if hasattr(mol, 'cell'):
            info["is_cell"] = True
            info["cell_volume"] = mol.cell.volume
            info["density"] = calc.mol_density(mol)
        else:
            info["is_cell"] = False
        
        return info
    except Exception as e:
        return {"error": str(e)}




if __name__ == "__main__":
    mcp.run()
