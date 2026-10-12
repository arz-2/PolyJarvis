"""A validated SMILES replays its frozen protocol — and must not be re-planned on the way.

Skipping the critic and adjudicator on a cache hit is an optimisation. Skipping
materialize is a CORRECTNESS requirement, and the reason is easy to miss:
materialize_plan layers solve_system_size's recommended_params over decided_params, so
running it on a cache replay would re-solve the cell and overwrite the very protocol
make_plan_from_cache had just replayed verbatim. A "validated" run would then execute
something other than what was validated.

guides/system_characterization_cache.json is `{}` on this branch, so these use a fixture
cache rather than the live file -- the routing has to be correct before the first campaign
is ever accepted and write_characterization_cache populates it.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "langgraph"))
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

pytest.importorskip("langgraph")

import nodes  # noqa: E402
from graph import build_graph  # noqa: E402

CANONICAL = "*CC*"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "guides").mkdir()
    (tmp_path / "data" / "R" / "raw").mkdir(parents=True)
    monkeypatch.setattr(nodes, "_write_json", lambda p, d: None)
    return tmp_path


def _cache(repo, **entry):
    (repo / "guides" / "system_characterization_cache.json").write_text(
        json.dumps({CANONICAL: entry} if entry else {}))


def _stub_canon(monkeypatch):
    import rules_common
    monkeypatch.setattr(rules_common, "canonicalize", lambda s, **k: CANONICAL)


def _state(repo, **over):
    base = {"run_name": "R", "smiles": "*CC*", "goal": "g", "properties": ["density"],
            "repo_root": str(repo), "events": []}
    base.update(over)
    return base


def test_a_validated_smiles_is_a_cache_hit(repo, monkeypatch):
    _stub_canon(monkeypatch)
    _cache(repo, protocol_validated=True, polymer_class="PHYC")
    out = nodes.cache_probe(_state(repo))
    assert out["cache_hit"] is True
    assert out["polymer_class"] == "PHYC"
    assert out["class_source"] == "characterization_cache"


def test_an_unvalidated_entry_is_not_a_hit(repo, monkeypatch):
    """Present but not yet validated must still take the full planning path."""
    _stub_canon(monkeypatch)
    _cache(repo, protocol_validated=False, polymer_class="PHYC")
    assert nodes.cache_probe(_state(repo))["cache_hit"] is False


def test_an_empty_cache_is_not_a_hit(repo, monkeypatch):
    _stub_canon(monkeypatch)
    _cache(repo)
    assert nodes.cache_probe(_state(repo))["cache_hit"] is False


def test_a_missing_cache_file_is_not_a_hit(repo, monkeypatch):
    _stub_canon(monkeypatch)
    assert nodes.cache_probe(_state(repo))["cache_hit"] is False


def test_an_unreachable_conda_env_degrades_to_a_miss_rather_than_crashing(repo, monkeypatch):
    import rules_common

    def boom(*a, **k):
        raise RuntimeError("conda unavailable")
    monkeypatch.setattr(rules_common, "canonicalize", boom)
    out = nodes.cache_probe(_state(repo))
    assert out["cache_hit"] is False and out["canonical_smiles"] is None


def _record(visited, name, result):
    def node(_state):
        visited.append(name)
        return result
    return node


@pytest.fixture
def graph_harness(repo, monkeypatch):
    """Drive the graph from cache_probe with every side-effecting node replaced.

    entry_resolve MUST be stubbed. It reads data/<run>/ and, on finding any run_plan.json,
    routes to critique or materialize -- which in an unstubbed test means a real `claude -p`
    call and a real materialize subprocess. (conftest.py now turns the first into a failure
    rather than a spend; this keeps the graph on the path under test either way.)
    """
    visited: list[str] = []
    monkeypatch.setattr(nodes, "entry_resolve",
                        lambda s: {"entry_node": "cache_probe", "events": []})
    plan_file = repo / "data" / "R" / "raw" / "run_plan.json"

    def install(plan_doc, **overrides):
        defaults = {
            "classify": {"polymer_class": "PHYC", "events": []},
            "critique": {"critic_verdict": "agrees", "events": []},
            "adjudicate": {"confidence": "medium", "events": []},
            "materialize": {"plan_mode": "reasoned", "events": []},
            "execute": {"status": "accepted", "events": []},
        }
        defaults.update(overrides)
        for name, result in defaults.items():
            monkeypatch.setattr(nodes, name, _record(visited, name, result))

        def plan_node(_state):
            visited.append("plan")
            plan_file.write_text(json.dumps(plan_doc))
            return {"plan_path": str(plan_file), "events": []}

        monkeypatch.setattr(nodes, "plan", plan_node)
        return visited

    return install


def test_a_cache_hit_skips_classify_critique_adjudicate_and_materialize(repo, monkeypatch, graph_harness):
    """The whole point. materialize in particular would re-solve the cell and overwrite the
    frozen protocol make_plan_from_cache just replayed."""
    _stub_canon(monkeypatch)
    _cache(repo, protocol_validated=True, polymer_class="PHYC")
    visited = graph_harness({"plan_mode": "deterministic",
                             "cost_estimate": {"total_gpu_hours": 3.0}})

    build_graph().invoke(_state(repo, max_gpu_hours=40))

    assert visited == ["plan", "execute"], f"cache hit took the wrong path: {visited}"


def test_a_cache_miss_takes_the_full_planning_path(repo, monkeypatch, graph_harness):
    _stub_canon(monkeypatch)
    _cache(repo)
    visited = graph_harness({"cost_estimate": {"total_gpu_hours": 3.0},
                             "decisions": [{"admissible": ["pcff"]}]})

    build_graph().invoke(_state(repo, max_gpu_hours=40))

    assert visited == ["classify", "plan", "critique", "adjudicate", "materialize", "execute"]


def test_a_cache_hit_still_clears_the_cost_ceiling(repo, monkeypatch, graph_harness):
    """A frozen protocol is not a licence to ignore --max-gpu-hours."""
    _stub_canon(monkeypatch)
    _cache(repo, protocol_validated=True, polymer_class="PHYC")

    def explode(_state):
        raise AssertionError("execute must not run when the ceiling is exceeded")
    graph_harness({"plan_mode": "deterministic", "cost_estimate": {"total_gpu_hours": 99.0}})
    monkeypatch.setattr(nodes, "execute", explode)

    final = build_graph().invoke(_state(repo, max_gpu_hours=1))
    assert final["status"] == "cost_exceeded"
