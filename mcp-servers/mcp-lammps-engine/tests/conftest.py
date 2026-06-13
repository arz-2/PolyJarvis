"""Shared pytest configuration for the mcp-lammps-engine test suite.

Two source locations are placed on ``sys.path`` so their pure-logic functions
can be imported directly in unit tests:

* ``analysis_scripts/`` -- the analysis scripts import each other as top-level
  modules (e.g. ``from analysis_utils import compute_tau_eff``) and guard their
  CLI behaviour behind ``if __name__ == "__main__"``.
* the engine root -- ``script_generator.py`` (stdlib-only) holds the real
  ``ScriptGenerator.parse_data_file`` / ``validate_data_file`` logic that the
  ``fastmcp`` server in ``server.py`` merely wraps.
"""
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_SCRIPTS = ENGINE_ROOT / "analysis_scripts"
for _p in (ENGINE_ROOT, ANALYSIS_SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
