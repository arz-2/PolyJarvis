"""Which run directory reports each (system, replicate), and how each system's K is taken.

The single place the manuscript's run set is defined. Every generator imports it.

Decisions (2026-09-15):
  - sPVC replicate 1 is sPVC_1_rerun (locked replicate protocol, one continuous melt hold).
  - aPS replicate 1 becomes aPS_1_rerun automatically once its summary stage is accepted.
  - sPVC K uses all simulated pressure points: benchmarks/bm_diagnostics_r2 shows the -1000 atm
    point the fit script flags as discontinuous is reproducible (1M-step repeat within 0.4 sigma,
    no in-run drift), and every fit that keeps it gives 2.7-3.1 GPa.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SYSTEMS = ["PE", "PEG", "PLLA", "aPS", "sPVC", "PEEK", "PSU"]

# (system, replicate) -> run directory. Anything not listed is f"{system}_{replicate}".
REPLICATE_RUNS = {
    ("sPVC", 1): "sPVC_1_rerun",
}
# Swapped in only when the rerun has completed (summary accepted); otherwise the original is used.
CONDITIONAL_RUNS = {
    ("aPS", 1): "aPS_1_rerun",
}

# System -> K basis: "production" (fit script's selected window) or "all_points".
# 2026-09-15: all systems use every simulated pressure point (extends the sPVC decision; the only
# other point the fit script had dropped is aPS_2's 5000 atm).
K_BASIS = {s: "all_points" for s in SYSTEMS}


def _accepted(run: str) -> bool:
    try:
        ws = json.loads((REPO / "data" / run / "workflow_state.json").read_text())
    except OSError:
        return False
    return (ws.get("stages", {}).get("summary", {}) or {}).get("status") == "accepted"


def run_for(system: str, replicate: int) -> str:
    key = (system, replicate)
    if key in REPLICATE_RUNS:
        return REPLICATE_RUNS[key]
    if key in CONDITIONAL_RUNS and _accepted(CONDITIONAL_RUNS[key]):
        return CONDITIONAL_RUNS[key]
    return f"{system}_{replicate}"


def reported_runs() -> list[tuple[str, int, str]]:
    """[(system, replicate, run_dir)] in system order."""
    return [(s, i, run_for(s, i)) for s in SYSTEMS for i in (1, 2, 3)]


def k_basis(system: str) -> str:
    return K_BASIS.get(system, "production")
