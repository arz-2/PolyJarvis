#!/usr/bin/env python3
"""
EMC MCP Server
==============
Builds amorphous polymer cells via EMC for Track C (PCFF including PSTR), PHAL+PSIL (OPLS-AA),
and PHYC/PDIE (TraPPE-UA) classes using EMC v9.4.4.

Wraps mcp-servers/mcp-emc-server/smiles_to_emc.py's build_cell() pipeline:
    SMILES → .esh → emc_setup.pl → EMC binary → LAMMPS .data

Force field auto-selection by polymer_class:
    PCBN, PAMD, PKTN, PSFO, PIMD, PSTR  →  pcff               (use_pcff=True downstream)
    PHAL, PSIL                           →  opls/2024/opls-aa  (use_opls=True downstream)
    PHYC, PDIE                           →  trappe-ua          (use_opls=False downstream)

Tools
-----
submit_emc_cell_job   async  Build amorphous cell; returns job_id immediately
get_emc_job_status    sync   Poll a running job
get_emc_job_output    sync   Retrieve result (data_path + lammps_flags) when complete
list_emc_jobs         sync   Show all jobs with status
"""

import json
import logging
import os
import random
import sys
import threading
import time
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from smiles_to_emc import build_cell, strip_bond_stereo

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EMC-SERVER] %(levelname)s %(message)s",
)
logger = logging.getLogger("emc_server")

# ---------------------------------------------------------------------------
# Job storage root
# ---------------------------------------------------------------------------

JOBS_ROOT = Path(os.environ.get("EMC_JOBS_DIR", Path.home() / "polyjarvis_emc_jobs"))
JOBS_ROOT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Job manager (same pattern as RadonPy server)
# ---------------------------------------------------------------------------

class JobStatus(Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


class JobManager:
    def __init__(self):
        self._jobs: dict = {}
        self._lock = threading.Lock()

    def submit(self, func, kwargs: dict, job_type: str = "emc_cell") -> str:
        job_id = str(uuid.uuid4())[:8]
        record = {
            "job_id":       job_id,
            "job_type":     job_type,
            "status":       JobStatus.PENDING.value,
            "result":       None,
            "error":        None,
            "submitted_at": datetime.now().isoformat(),
            "started_at":   None,
            "completed_at": None,
            "kwargs":       kwargs,
        }
        with self._lock:
            self._jobs[job_id] = record

        thread = threading.Thread(
            target=self._run, args=(job_id, func, kwargs), daemon=True
        )
        thread.start()
        logger.info(f"Job {job_id} ({job_type}) submitted")
        return job_id

    def _run(self, job_id: str, func, kwargs: dict):
        with self._lock:
            self._jobs[job_id]["status"]     = JobStatus.RUNNING.value
            self._jobs[job_id]["started_at"] = datetime.now().isoformat()
        t0 = time.time()
        try:
            result = func(**kwargs)
            elapsed = time.time() - t0
            with self._lock:
                self._jobs[job_id]["status"]       = JobStatus.COMPLETED.value
                self._jobs[job_id]["result"]        = result
                self._jobs[job_id]["completed_at"]  = datetime.now().isoformat()
            logger.info(f"Job {job_id} completed in {elapsed:.1f}s")
        except Exception as exc:
            elapsed = time.time() - t0
            with self._lock:
                self._jobs[job_id]["status"]       = JobStatus.FAILED.value
                self._jobs[job_id]["error"]         = str(exc)
                self._jobs[job_id]["completed_at"]  = datetime.now().isoformat()
            logger.error(f"Job {job_id} failed after {elapsed:.1f}s: {exc}")

    # _resolve_sentinel REMOVED 2026-09-02. It flipped a job from "running" to "completed"
    # whenever ANY *.data existed in output_dir, which is true from the moment EMC writes
    # the file -- before run_emc_build() has stripped pair_style/kspace_style out of the
    # emitted .params. A 30 s poll landing in that window handed the campaign a .params that
    # then overrode the equilibration template's own coul/long-vs-coul/cut choice, and a
    # result dict with no resolved_seed. It existed to recover a job whose MCP server had
    # restarted under it; run_campaign.py imports this module in-process (see
    # _load_server_module), so the worker thread and the poller live or die together and
    # there is nothing to recover. A job is complete when its thread says so.

    def status(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                return {"error": f"Job {job_id} not found"}
            j = self._jobs[job_id]
            return {
                "job_id":       j["job_id"],
                "job_type":     j["job_type"],
                "status":       j["status"],
                "submitted_at": j["submitted_at"],
                "started_at":   j["started_at"],
                "completed_at": j["completed_at"],
                "has_result":   j["result"] is not None,
                "has_error":    j["error"]  is not None,
            }

    def output(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                return {"error": f"Job {job_id} not found"}
            j = self._jobs[job_id]
        if j["status"] in (JobStatus.PENDING.value, JobStatus.RUNNING.value):
            return {"job_id": job_id, "status": j["status"],
                    "message": "Job not yet complete"}
        if j["status"] == JobStatus.FAILED.value:
            return {"job_id": job_id, "status": j["status"],
                    "error": j["error"], "completed_at": j["completed_at"]}
        return {"job_id": job_id, "status": j["status"],
                "result": j["result"], "completed_at": j["completed_at"]}

    def list_jobs(self, status_filter: Optional[str] = None) -> list:
        with self._lock:
            rows = []
            for j in self._jobs.values():
                if status_filter is None or j["status"] == status_filter:
                    rows.append({
                        "job_id":       j["job_id"],
                        "job_type":     j["job_type"],
                        "status":       j["status"],
                        "submitted_at": j["submitted_at"],
                        "completed_at": j["completed_at"],
                    })
        return rows


job_manager = JobManager()

# ---------------------------------------------------------------------------
# Field selection
# ---------------------------------------------------------------------------

_PCFF_CLASSES   = {
    # Original engineering thermoplastics
    "PCBN", "PAMD", "PKTN", "PSFO", "PIMD",
    # Expanded: build-tested 2026-05-31 — pcff.frc has explicit types for all
    "POXI",  # polyethers/polyoxides (PEO, PPO)
    "PEST",  # polyesters (PLA, PET, PCL)
    "PSUL",  # polythioethers/polysulfides (PPS)
    "PURT",  # polyurethanes — aliphatic only; aromatic MDI-type SMILES fail {o, c_2}
    "PANH",  # polyanhydrides
    "PPHS",  # polyphosphazenes — ethoxy/alkoxy substituents tested; Cl-substituted untested
    "PACR",  # polyacrylics (PMMA, PMA) — pcff preferred over opls-aa (Class II vs I)
    "PIMN",  # polyamines/polyetherimides (PEI, linear amines)
    "PVNL",  # polyvinyls (PVC, PVAc, PVA) — tested with PVC+PVAc+PVA
    "PPNL",  # conjugated/polyphenylene (PPV, MEH-PPV)
    "PSTR",  # polystyrenics (PS, P2VP, SAN) — PCFF preferred; TraPPE-UA lacks aromatic ring charges/π-dihedrals and has no direct PS Tg validation
}
_OPLS_CLASSES   = {
    "PHAL",  # polyhalogenated (PTFE, PVDF, PCTFE)
    "PSIL",  # polysiloxanes (PDMS) — opls/2024/opls-aa has si4/o2 Si-O params; pcff missing {si,osi}
}
_TRAPPE_CLASSES = {"PHYC", "PDIE"}  # PSTR moved to _PCFF_CLASSES — PCFF preferred (see PSTR entry above)
# PURA (polyurea): EMC build fails on pcff (missing {na,c_2} amide-N increment) — remains on RadonPy

# Fields reachable by explicit field_override for force-field comparison. Class
# defaults above are unchanged; these are candidates, not routes.
#   compass   — Class II, parameterized for condensed-phase density/cohesive energy.
#               Published/LAMMPS subset only: H,C,N,O,Si,P,S (no F, no Cl) and 96
#               typing templates against pcff's 422. Fails to type many chemistries.
#   pcff_ore  — same pcff base (#define cff91), larger .frc, full-size templates.
_COMPARISON_FIELDS = {"compass", "pcff_ore", "trappe-eh", "opls/2012/opls-aa"}

_ALL_FIELDS = {"pcff", "opls/2024/opls-aa", "trappe-ua"} | _COMPARISON_FIELDS


def _select_field(polymer_class: str) -> str:
    if polymer_class in _PCFF_CLASSES:
        return "pcff"
    if polymer_class in _OPLS_CLASSES:
        return "opls/2024/opls-aa"
    if polymer_class in _TRAPPE_CLASSES:
        return "trappe-ua"
    raise ValueError(
        f"Unsupported polymer_class '{polymer_class}' for EMC. "
        f"Supported: {sorted(_PCFF_CLASSES | _OPLS_CLASSES | _TRAPPE_CLASSES)}"
    )


def _resolve_field(polymer_class: str, field_override: str = "") -> str:
    """Class default, or a validated override for a comparison run."""
    if not field_override:
        return _select_field(polymer_class)
    if field_override not in _ALL_FIELDS:
        raise ValueError(
            f"Unknown field_override '{field_override}'. Known: {sorted(_ALL_FIELDS)}"
        )
    return field_override


def _lammps_flags(field: str) -> dict:
    # pcff_ore IS pcff, and compass shares the Class II functional form (9-6 LJ,
    # quartic bonds, cross terms), so both take the class2 deck.
    if field in ("pcff", "pcff_ore", "compass"):
        return {"use_pcff": True,  "use_opls": False}
    if field in ("trappe-ua", "trappe-eh"):
        return {"use_pcff": False, "use_opls": False, "use_trappe": True}
    return {"use_pcff": False, "use_opls": True}


# ---------------------------------------------------------------------------
# Worker function
# ---------------------------------------------------------------------------

def _build_emc_cell(
    smiles: str,
    output_dir: str,
    field: str,
    density: float,
    dp: int,
    nchains: int,
    temperature: float,
    seed: int,
) -> dict:
    # EMC discards SMILES double-bond stereo, and "/" additionally breaks the .esh parser.
    # Record the drop here so the run's provenance says the cell is cis/trans-mixed by
    # construction rather than leaving it to be inferred from a silent success.
    _, stereo_stripped = strip_bond_stereo(smiles)
    if stereo_stripped:
        logger.warning("cis/trans bond stereo stripped from %s: EMC packs a mixed cell", smiles)

    # Resolve seed before calling EMC so the cell is reproducible.
    if seed == -1:
        seed = random.randint(1, 2**31 - 1)
        logger.info("EMC seed resolved: %d", seed)

    data_path = build_cell(
        smiles=smiles,
        output_dir=output_dir,
        field=field,
        density=density,
        dp=dp,
        nchains=nchains,
        temperature=temperature,
        seed=seed,
    )
    data_path = str(data_path)

    # Write reproducibility metadata so the seed survives run_log.md references.
    try:
        meta = {
            "resolved_seed": seed,
            "field": field,
            "dp": dp,
            "density": density,
            "smiles": smiles,
            "stereo_stripped": stereo_stripped,
        }
        (Path(output_dir) / "emc_metadata.json").write_text(
            json.dumps(meta, indent=2)
        )
    except Exception:
        pass

    # Quick sanity: count atoms from the .data header
    natoms = None
    try:
        with open(data_path) as fh:
            for line in fh:
                if "atoms" in line and not line.strip().startswith("#"):
                    natoms = int(line.split()[0])
                    break
    except Exception:
        pass

    return {
        "status":        "success",
        "data_path":     data_path,
        "output_dir":    output_dir,
        "smiles":        smiles,
        "field":         field,
        "dp":            dp,
        "density":       density,
        "natoms":        natoms,
        "resolved_seed": seed,
        "stereo_stripped": stereo_stripped,
        "lammps_flags":  _lammps_flags(field),
        "message":       f"LAMMPS .data file written: {data_path}",
    }


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "EMC",
    instructions="""
    EMC MCP Server — amorphous cell builder for 20 polymer classes.
    Uses PCFF (Class II), OPLS-AA, or TraPPE-UA depending on class.
    One class remains on RadonPy: PURA (urea N-H, EMC fails).

    SUPPORTED CLASSES → pcff (Class II, best thermomechanical accuracy):
      PCBN  Polycarbonates       (e.g. BPA-PC)
      PAMD  Polyamides           (e.g. Nylon-6, Nylon-6,6)
      PKTN  Polyketones/PEEK     (e.g. PEEK, PEK)
      PSFO  Polysulfones         (e.g. PSU/Udel, PES)
      PIMD  Polyimides           (e.g. PMDA-ODA/Kapton)
      POXI  Polyethers/oxides    (e.g. PEO, PPO, POM)
      PEST  Polyesters           (e.g. PLA, PET, PCL)
      PSUL  Polythioethers       (e.g. PPS)
      PURT  Polyurethanes        (e.g. TPU) ⚠ aliphatic segments only; aromatic MDI fails
      PANH  Polyanhydrides       (e.g. poly(sebacic anhydride))
      PPHS  Polyphosphazenes     (e.g. poly(ethoxyphosphazene)) ⚠ alkoxy substituents tested
      PACR  Polyacrylics         (e.g. PMMA, PMA, PAA)
      PIMN  Polyamines/etherimides (e.g. PEI, linear poly(ethylenimine))
      PVNL  Polyvinyls           (e.g. PVC, PVAc, PVA)
      PPNL  Conjugated/PPV       (e.g. PPV, MEH-PPV)
      PSTR  Polystyrenics        (e.g. PS, P2VP, SAN) — PCFF preferred over TraPPE-UA (aromatic ring charges)

    SUPPORTED CLASSES → opls/2024/opls-aa:
      PHAL  Polyhalogenated      (e.g. PTFE, PVDF, PCTFE)
      PSIL  Polysiloxanes        (e.g. PDMS) — opls-aa si4/o2 params; pcff missing {si,osi}

    SUPPORTED CLASSES → trappe-ua:
      PHYC  Polyhydrocarbons     (e.g. PE, PP, PIB)
      PDIE  Polydienes           (e.g. PBD, PI)

    RadonPy only (EMC build fails):
      PURA  Polyureas            — pcff missing {na,c_2} amide-N increment

    The field is selected automatically from polymer_class — do not override it.

    SMILES CONVENTION:
      Use exactly two * atoms as chain-end connection points (same as RadonPy).
      For polycarbonates the full -O-C(=O)-O- carbonate group must be within
      the repeat unit — put * on the aromatic carbon, not on the carbonyl oxygen.
      Example BPA-PC: *OC(=O)Oc1ccc(C(C)(C)c2ccc(*)cc2)cc1

    TYPICAL WORKFLOW:
      1. submit_emc_cell_job(smiles, polymer_class, ...) → job_id
      2. get_emc_job_status(job_id)       → poll until "completed"
      3. get_emc_job_output(job_id)       → result["data_path"], result["lammps_flags"]
      4. Pass data_path to upload_file_to_remote() (LAMMPS engine server).
         Pass lammps_flags (use_pcff / use_opls) to generate_script() and
         generate_equilibration_workflow().
    """
)


@mcp.tool()
def submit_emc_cell_job(
    smiles: str,
    polymer_class: str,
    dp: int,
    nchains: int,
    density_initial: float,
    seed: int,
    temperature: float = 300.0,
    field_override: str = "",
) -> dict:
    """
    Build an amorphous polymer cell with EMC and return a LAMMPS .data file.

    The force field is selected automatically from polymer_class:
        PCBN/PAMD/PKTN/PSFO/PIMD/POXI/PEST/PSUL/PURT/PANH/PPHS/PACR/PIMN/PVNL/PPNL/PSTR  →  pcff
        PHAL/PSIL                                                                            →  opls/2024/opls-aa
        PHYC/PDIE                                                                            →  trappe-ua

    Runs emc_setup.pl + EMC binary in a background thread; returns job_id
    immediately. Poll get_emc_job_status() then call get_emc_job_output() for
    data_path and lammps_flags when status == "completed".

    Args:
        smiles:          Repeat-unit SMILES with exactly two * connection points.
                         For polycarbonates include the full -O-C(=O)-O- carbonate
                         in the repeat unit and put * on aromatic carbons.
        polymer_class:   PolyInfo class name — determines force field; required.
                         PCFF: PCBN/PAMD/PKTN/PSFO/PIMD/POXI/PEST/PSUL/PURT/PANH/PPHS/PACR/PIMN/PVNL/PPNL/PSTR
                         OPLS-AA: PHAL/PSIL.  TraPPE-UA: PHYC/PDIE.
        dp:              REQUIRED. Degree of polymerization (repeat units per chain) —
                         the class's own dp_typical, commonly 50.
        nchains:         REQUIRED. Exact number of polymer chains to build (EMC "number"
                         mode), >= 1. The chain count is always explicit: the
                         atom-count-driven sizing path was removed 2026-09-02 so that
                         D-04_system_size is the only thing that decides a cell.
        density_initial: REQUIRED. Target packing density in g/cm³. Use ~0.5× experimental
                         to avoid steric clashes during initial build; LAMMPS
                         equilibration will compress to target density.
        temperature:     Build temperature in K. Feeds EMC's `build.system.temperature`,
                         which its `grow -> {method -> energetic}` chain growth accepts
                         moves against, so it shapes the packed configuration — not only
                         the velocities of the run script EMC generates (that script is
                         unused; PolyJarvis generates its own decks). [300.0]
        seed:            REQUIRED. Random seed pinning the packing RNG. Pass -1 only when
                         you deliberately want a fresh cell: EMC then draws one and reports
                         it, and that drawn value is what must reach the run log's Seeds
                         line. Omitting the argument used to do the same draw silently,
                         which produced an unreproducible cell under a run log claiming a
                         pinned seed.
        field_override:  FOR FORCE-FIELD COMPARISON RUNS ONLY — leave empty for
                         normal builds, which must use the class default above.
                         Accepts compass / pcff_ore / trappe-eh / opls/2012/opls-aa
                         plus the three defaults. `compass` is the published subset:
                         no F, no Cl, and 96 typing templates against pcff's 422, so
                         it silently fails to type many chemistries — always check
                         the build log rather than assuming a fallback. [""]

    Returns:
        {"status": "submitted", "job_id": ..., "output_dir": ..., "field": ...}
    """
    try:
        field = _resolve_field(polymer_class, field_override)
    except ValueError as exc:
        return {"error": str(exc)}

    job_id = str(uuid.uuid4())[:8]
    output_dir = str(JOBS_ROOT / job_id)

    kwargs = dict(
        smiles=smiles,
        output_dir=output_dir,
        field=field,
        density=density_initial,
        dp=dp,
        nchains=nchains,
        temperature=temperature,
        seed=seed,
    )

    # Pre-register the job_id so the directory is predictable
    import threading as _t
    record = {
        "job_id":       job_id,
        "job_type":     "emc_cell",
        "status":       JobStatus.PENDING.value,
        "result":       None,
        "error":        None,
        "submitted_at": datetime.now().isoformat(),
        "started_at":   None,
        "completed_at": None,
        "kwargs":       kwargs,
    }
    with job_manager._lock:
        job_manager._jobs[job_id] = record

    thread = _t.Thread(
        target=job_manager._run,
        args=(job_id, _build_emc_cell, kwargs),
        daemon=True,
    )
    thread.start()
    logger.info(f"EMC cell job {job_id} submitted — class={polymer_class} dp={dp}")

    return {
        "status":        "submitted",
        "job_id":        job_id,
        "job_type":      "emc_cell",
        "output_dir":    output_dir,
        "polymer_class": polymer_class,
        "field":         field,
        "smiles":        smiles,
        "dp":            dp,
        "density":       density_initial,
        "message":       (
            f"EMC cell job {job_id} submitted. "
            f"Class={polymer_class}, field={field}, dp={dp}, density={density_initial}. "
            "Poll get_emc_job_status() then get_emc_job_output() for data_path + lammps_flags."
        ),
    }


@mcp.tool()
def get_emc_job_status(job_id: str) -> dict:
    """
    Poll the status of a submitted EMC cell build job.

    Args:
        job_id: Job ID returned by submit_emc_cell_job.

    Returns:
        {"job_id": ..., "status": "pending|running|completed|failed", ...}
    """
    return job_manager.status(job_id)


@mcp.tool()
def get_emc_job_output(job_id: str) -> dict:
    """
    Retrieve the result of a completed EMC cell build job.

    When status == "completed", result contains:
      data_path  — absolute path to the LAMMPS .data file
      natoms     — total atom count
      output_dir — directory containing all intermediate files (.esh, build.emc, …)

    Args:
        job_id: Job ID returned by submit_emc_cell_job.

    Returns:
        Full result dict; "error" key is set on failure.
    """
    return job_manager.output(job_id)


@mcp.tool()
def list_emc_jobs(
    status_filter: Optional[str] = None,
) -> dict:
    """
    List all EMC cell build jobs.

    Args:
        status_filter: Optional filter — one of "pending", "running",
                       "completed", "failed". Omit to list all.

    Returns:
        {"total": N, "jobs": [...]}
    """
    jobs = job_manager.list_jobs(status_filter)
    return {"total": len(jobs), "jobs": jobs, "filter": status_filter}


if __name__ == "__main__":
    mcp.run()
