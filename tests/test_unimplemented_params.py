"""Planning parameters must be executable, never provenance-only decoration."""

import ast
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from make_deterministic_plan import SNAPSHOT_KEYS  # noqa: E402
from scientific_control import ALLOWED_OVERRIDES, planning_parameter_contract  # noqa: E402
from validate_run_plan import UNIMPLEMENTED_PARAMS, _unimplemented_param_findings  # noqa: E402


def test_every_advertised_parameter_has_an_executable_route():
    assert UNIMPLEMENTED_PARAMS == {}
    assert _unimplemented_param_findings({"decided_params": {"eq_annealing_cycles": 10}}) == []


def test_annealing_cycles_are_snapshotted_and_agent_adjustable():
    assert "eq_annealing_cycles" in SNAPSHOT_KEYS
    assert "eq_annealing_cycles" in ALLOWED_OVERRIDES
    spec = planning_parameter_contract()["eq_annealing_cycles"]
    assert spec == {"type": "integer", "minimum": 0, "maximum": 50}


def test_executor_forwards_resolved_annealing_controls():
    tree = ast.parse((REPO_ROOT / "orchestration" / "scripts" / "run_campaign.py").read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr == "generate_equilibration_workflow"]
    assert len(calls) == 3
    full = next(call for call in calls
                if any(kw.arg == "anneal_cycles" and isinstance(kw.value, ast.Subscript)
                       for kw in call.keywords))
    passed = {kw.arg for kw in full.keywords}
    assert {"anneal_cycles", "anneal_cycle_steps"} <= passed


def test_server_materializes_heat_and_cool_stage_per_cycle():
    source = (REPO_ROOT / "mcp-servers" / "mcp-lammps-engine" / "server.py").read_text()
    assert 'range(1, anneal_cycles + 1)' in source
    assert 'anneal_{cycle_index:02d}_heat' in source
    assert 'anneal_{cycle_index:02d}_cool' in source
