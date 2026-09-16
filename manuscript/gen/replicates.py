"""Which run directory reports each (system, replicate), and how each system's K is taken.

The single place the manuscript's run set is defined. Every generator imports it.

Decisions (2026-09-15):
  - aPS and sPVC replicate 1 are the locked-protocol reruns (one continuous melt hold). The
    original replicate-1 workspaces were deleted on 2026-09-16 and the reruns renamed from
    aPS_1_rerun / sPVC_1_rerun to aPS_1 / sPVC_1 (see input_hash_restamp in each workflow_state).
  - sPVC K uses all simulated pressure points: benchmarks/bm_diagnostics_r2 shows the -1000 atm
    point the fit script flags as discontinuous is reproducible (1M-step repeat within 0.4 sigma,
    no in-run drift), and every fit that keeps it gives 2.7-3.1 GPa.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SYSTEMS = ["PE", "PEG", "PLLA", "aPS", "sPVC", "PEEK", "PSU"]


# System -> K basis: "production" (fit script's selected window) or "all_points".
# 2026-09-15: all systems use every simulated pressure point (extends the sPVC decision; the only
# other point the fit script had dropped is aPS_2's 5000 atm).
K_BASIS = {s: "all_points" for s in SYSTEMS}


def run_for(system: str, replicate: int) -> str:
    return f"{system}_{replicate}"


def reported_runs() -> list[tuple[str, int, str]]:
    """[(system, replicate, run_dir)] in system order."""
    return [(s, i, run_for(s, i)) for s in SYSTEMS for i in (1, 2, 3)]


def k_basis(system: str) -> str:
    return K_BASIS.get(system, "production")
