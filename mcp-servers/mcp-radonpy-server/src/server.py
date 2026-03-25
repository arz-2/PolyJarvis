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

# Add RadonPy to path — set RADONPY_PATH in .env (see .env.example)
_radonpy_path = os.environ.get("RADONPY_PATH", "")
if _radonpy_path:
    sys.path.insert(0, _radonpy_path)

import tempfile
import json
from pathlib import Path
from typing import Optional, Literal
import numpy as np
import pandas as pd
from scipy import optimize, stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


from mcp.server.fastmcp import FastMCP
from rdkit import Chem

# Import RadonPy modules
from radonpy.core import utils, calc, poly
from radonpy.ff.gaff2_mod import GAFF2_mod
from radonpy.ff.gaff2 import GAFF2
from radonpy.ff.gaff import GAFF
from radonpy.sim import qm
from radonpy.sim.lammps import Analyze
import mcp_logging
import logging
import time as time_module


# Initialize logging
logger = mcp_logging.setup_logging(
    log_level=logging.INFO,
    enable_console=True,
    session_name=datetime.now().strftime("%Y%m%d_%H%M%S")
)
logger.info("RadonPy MCP Server starting...")

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
        self.logger = logging.getLogger("radonpy_mcp.JobManager")
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
        
        job_logger = mcp_logging.get_job_logger(job_id, job_type)
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
        job_logger = logging.getLogger(f"radonpy_mcp.job.{job_id}")
        start_time = time_module.time()
        
        try:
            with self.lock:
                self.jobs[job_id]["status"] = JobStatus.RUNNING.value
                self.jobs[job_id]["started_at"] = datetime.now().isoformat()
            
            job_logger.info("Job execution started")
            self.logger.info(f"Job {job_id} execution started")
            
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

def _run_assign_charges(mol_file, charge_method, optimize_geometry, omp_psi4, memory, work_dir):
    """Internal function to assign charges"""
    os.makedirs(work_dir, exist_ok=True)
    mol = utils.JSONToMol(mol_file)
    
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

def _run_calculate_sp_properties(mol_file, method, basis, omp_psi4, mem, work_dir):
    """Internal function to calculate SP properties"""
    os.makedirs(work_dir, exist_ok=True)
    mol = utils.JSONToMol(mol_file)
    
    qm_data = qm.sp_prop(mol, opt=False, work_dir=work_dir, omp=omp_psi4, memory=mem, log_name='monomer1')
    polar_data = qm.polarizability(mol, opt=False, work_dir=work_dir, omp=omp_psi4, memory=mem, log_name='monomer1')
    
    tot_energy = qm_data['qm_total_energy']
    homo = qm_data['qm_homo']
    lumo = qm_data['qm_lumo']
    dipole = qm_data['qm_dipole']
    dipole_polarizability = polar_data['Dipole polarizability']
    polarizability_tensor = polar_data['Polarizability tensor']
    
    utils.MolToJSON(mol, mol_file)
    
    return {
        "status": "success",
        "total_energy": float(tot_energy),
        "homo": float(homo),
        "lumo": float(lumo),
        "dipole (x,y,z)": [float(d) for d in dipole],
        "dipole_polarizability": float(dipole_polarizability) if dipole_polarizability else None,
        "polarizability_tensor (xx,yy,zz,xy,xz,yz)": [float(p) for p in polarizability_tensor] if polarizability_tensor else None,
        "method": method,
        "basis": basis,
        "output_file": mol_file,
        "message": "Properties calculated successfully"
    }

def _run_polymerize(mol_file, degree_of_polymerization, tacticity, headhead):
    """Internal function to polymerize"""
    mol = utils.JSONToMol(mol_file)
    
    polymer = poly.polymerize_rw(
        mol,
        n=degree_of_polymerization,
        tacticity=tacticity,
        headhead=headhead,
        opt='rdkit'
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
    - submit_sp_properties_job() - QM single-point properties
    - submit_polymerize_job() - Polymer generation
    - submit_generate_cell_job() - Amorphous cell packing
    
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
    
    Typical workflow:
    1. build_molecule_from_smiles() - Instant
    2. submit_conformer_search_job() - Returns job_id
    3. get_job_status(job_id) - Poll until complete
    4. get_job_output(job_id) - Get optimized structure
    5. submit_assign_charges_job() - Returns job_id
    ... continue workflow ...
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
    charge_method: Literal["gasteiger", "RESP", "ESP", "Mulliken", "Lowdin"] = "RESP",
    optimize_geometry: bool = False, # Whether to optimize geometry before charge calculation
    omp_psi4: int = 1, # OpenMP threads for Psi4
    memory: int = 2000, # Memory for Psi4 calculations in MB
    work_dir: str = 'assign_charges' # Working directory
) -> dict:
    """
    Submit charge assignment job (runs in background).
    
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
def submit_sp_properties_job(
    mol_file: str,
    method: str = "HF",
    basis: str = "6-31G(d)",
    omp_psi4: int = 1,
    mem: int = 2000,
    work_dir: str = "sp_properties"
) -> dict:
    """
    Submit single-point properties calculation job (runs in background).

    Args:
        mol_file: Path to molecule JSON file
        method: QM method (e.g., 'HF', 'B3LYP')
        basis: Basis set
        omp_psi4: OpenMP threads for Psi4 DFT calculations
        mem: Memory for Psi4 calculations in MB
        work_dir: Working directory
    
    Returns immediately with job_id. Use get_job_status() to check progress.
    """
    try:
        job_id = job_manager.submit_job(
            func=_run_calculate_sp_properties,
            args=(),
            kwargs={
                "mol_file": mol_file,
                "method": method,
                "basis": basis,
                "omp_psi4": omp_psi4,
                "mem": mem,
                "work_dir": work_dir
            },
            job_type="sp_properties"
        )
        
        return {
            "status": "submitted",
            "job_id": job_id,
            "job_type": "sp_properties",
            "message": f"SP properties job {job_id} submitted. Method: {method}/{basis}"
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

        return {
            "status": "success",
            "class_id": class_id,
            "class_name": class_name,
            "description": description,
            "flags": flags,
            "co_occurring_groups": co_occurring,
            "warning": warning,
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




@mcp.tool()
def get_job_logs(job_id: str) -> dict:
    """Get complete log for a specific job."""
    logger.info(f"Job log retrieval: {job_id}")
    
    from pathlib import Path
    job_log_dir = Path(mcp_logging.JOB_LOG_DIR) / job_id
    
    if not job_log_dir.exists():
        return {"error": f"No logs for job {job_id}"}
    
    log_files = list(job_log_dir.glob("*.log"))
    if not log_files:
        return {"error": f"No log files for job {job_id}"}
    
    try:
        with open(log_files[0], 'r') as f:
            lines = f.readlines()
        
        return {
            "job_id": job_id,
            "log_file": str(log_files[0]),
            "line_count": len(lines),
            "log_content": [line.strip() for line in lines]
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_logging_info() -> dict:
    """Get logging system info and statistics."""
    logger.info("Logging info requested")
    
    debug_info = mcp_logging.get_debug_info()
    
    with job_manager.lock:
        debug_info["job_manager"] = {
            "total_jobs": len(job_manager.jobs),
            "pending": sum(1 for j in job_manager.jobs.values() if j["status"] == "pending"),
            "running": sum(1 for j in job_manager.jobs.values() if j["status"] == "running"),
            "completed": sum(1 for j in job_manager.jobs.values() if j["status"] == "completed"),
            "failed": sum(1 for j in job_manager.jobs.values() if j["status"] == "failed")
        }
    
    return debug_info


@mcp.tool()
def list_job_logs() -> dict:
    """List all jobs with log files."""
    from pathlib import Path
    
    job_log_dir = Path(mcp_logging.JOB_LOG_DIR)
    if not job_log_dir.exists():
        return {"error": "Job log directory doesn't exist"}
    
    jobs_with_logs = []
    for job_dir in job_log_dir.iterdir():
        if job_dir.is_dir():
            job_id = job_dir.name
            log_files = list(job_dir.glob("*.log"))
            
            if log_files:
                log_file = log_files[0]
                log_size = log_file.stat().st_size
                
                job_status = job_manager.get_status(job_id)
                status = job_status.get("status", "unknown") if "error" not in job_status else "unknown"
                
                jobs_with_logs.append({
                    "job_id": job_id,
                    "log_file": str(log_file),
                    "log_size_kb": round(log_size / 1024, 2),
                    "status": status
                })
    
    return {
        "job_count": len(jobs_with_logs),
        "jobs": sorted(jobs_with_logs, key=lambda x: x["job_id"])
    }


if __name__ == "__main__":
    mcp.run()
