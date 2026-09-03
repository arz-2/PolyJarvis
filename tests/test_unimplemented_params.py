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


def test_anneal_cap_steps_is_snapshotted_and_agent_adjustable():
    """The direct successor to eq_annealing_cycles: annealing is one continuously-extendable
    NVT hold, bounded by a TIME cap (anneal_cap_steps), not a cycle count."""
    assert "anneal_cap_steps" in SNAPSHOT_KEYS
    assert "anneal_cap_steps" in ALLOWED_OVERRIDES
    spec = planning_parameter_contract()["anneal_cap_steps"]
    assert spec == {"type": "integer", "minimum": 1, "maximum": 2_000_000_000}


def test_executor_forwards_resolved_anneal_hold_controls():
    """Every resolved anneal control reaches the generator from _submit_equil_chain.

    The three call sites (fresh / resume_from / extend_only) share a `common` kwargs dict now,
    so the controls appear as dict KEYS rather than as keyword args on each call -- assert
    against the function body as a whole rather than against one call's keywords, which is what
    this checked before the shared dict existed."""
    tree = ast.parse((REPO_ROOT / "orchestration" / "scripts" / "run_campaign.py").read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr == "generate_equilibration_workflow"]
    assert len(calls) == 3

    submit = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "_submit_equil_chain")
    forwarded = {kw.arg for call in ast.walk(submit) if isinstance(call, ast.Call)
                 for kw in call.keywords if kw.arg}
    forwarded |= {k.value for d in ast.walk(submit) if isinstance(d, ast.Dict)
                  for k in d.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert {"anneal_heat_steps", "anneal_check_every_steps", "anneal_cap_steps"} <= forwarded
    # The melt tail must be forwarded on the same footing -- it is the half that is new.
    assert {"melt_ramp_steps", "melt_hold_min_steps", "nvt_melt_min_steps"} <= forwarded


def test_server_materializes_anneal_heat_then_a_single_extendable_hold():
    source = (REPO_ROOT / "mcp-servers" / "mcp-lammps-engine" / "server.py").read_text()
    assert '"anneal_heat"' in source
    assert '"anneal_hold"' in source
    # No more per-cycle heat/cool stage naming -- annealing is one continuous hold at max_temp.
    assert 'anneal_{cycle_index:02d}_heat' not in source
    assert 'anneal_{cycle_index:02d}_cool' not in source
