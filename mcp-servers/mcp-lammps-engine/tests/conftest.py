"""Shared pytest configuration for the mcp-lammps-engine test suite.

The analysis scripts live in ``analysis_scripts/`` and import each other as
top-level modules (e.g. ``from analysis_utils import compute_tau_eff``). Put
that directory on ``sys.path`` so the deterministic functions can be imported
directly in unit tests without running the scripts' ``__main__`` blocks.
"""
import sys
from pathlib import Path

ANALYSIS_SCRIPTS = Path(__file__).resolve().parent.parent / "analysis_scripts"
if str(ANALYSIS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_SCRIPTS))
