#!/usr/bin/env python3
"""The graph: a DAG, with `execute` appearing exactly once.

That is the single most important structural fact here, so it is worth stating plainly.
It is tempting to loop execute -> recover -> execute, and it would be wrong.
`agent_escalations` is a RUN-GLOBAL list in workflow_state.json, and
WorkflowEngine._escalate returns early the moment it reaches MAX_AGENT_DECISIONS. So by
the time WorkflowEngine.run() hands back `escalation_required`, both agent calls are
already spent and recorded. Re-entering resume_campaign would re-execute the failing stage
-- real GPU hours -- and then escalate-fail again against the same exhausted cap. The
engine's own `while True` IS the retry/remedy loop; a second loop around it buys nothing
and costs hardware. `escalation_required` and `failed` are terminal, and a run that reaches
them needs a human.

Every node is wrapped by @_node, which short-circuits once a terminal status is set and
checks the deadline first. That means each conditional edge is the same one-liner rather
than each carrying its own copy of the stop logic.
"""
from __future__ import annotations

import functools
import json
import sys
from pathlib import Path
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

sys.path.insert(0, str(Path(__file__).resolve().parent))

import guards  # noqa: E402
import nodes  # noqa: E402
from state import RunState  # noqa: E402


def _emit(payload: dict) -> None:
    """One NDJSON line per event, flushed.

    Goes to stdout, where it interleaves with agent_api's and the MCP server modules' own
    output -- consumers filter on the presence of an "event" key. Documented rather than
    worked around: routing these to stderr would defeat the point of streaming node events
    on stdout.
    """
    print(json.dumps(payload, default=str), flush=True)


def _node(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
    @functools.wraps(fn)
    def wrapper(state: dict) -> dict:
        if state.get("status"):
            return {}                       # a terminal status was already set upstream
        if guards.deadline_expired(state):
            out = {"status": "deadline_exceeded",
                   "detail": (f"--deadline-hours elapsed before {fn.__name__}. Nothing was "
                              "killed; the campaign is resumable with --resume."),
                   "events": [nodes.event("deadline", before=fn.__name__)]}
            for item in out["events"]:
                _emit(item)
            return out
        result = fn(state)
        for item in result.get("events", ()):
            _emit({**item, "node": fn.__name__})
        return result
    return wrapper


def _route(*, when_stopped: str = END) -> Callable[[dict], str]:
    """Every conditional edge starts the same way, so it is written once."""
    def decide(state: dict, _next: str) -> str:
        return when_stopped if state.get("status") else _next
    return decide


def _after_entry(state: dict) -> str:
    return state.get("entry_node", "cache_probe")


def _after_cache(state: dict) -> str:
    if state.get("status"):
        return END
    return "plan" if state.get("cache_hit") else "classify"


def _after_cost_pre(state: dict) -> str:
    if state.get("status"):
        return END
    # A cache hit replays a frozen, already-validated protocol: no critique to run, and
    # crucially no materialize either (it would re-solve the cell and overwrite the
    # replayed protocol -- see nodes.cache_probe). It still goes through the priced cost
    # guard, because EVERY path into execute must clear the ceiling; the pre-gate ran with
    # priced=False and cannot have applied it.
    return "cost_guard_post" if state.get("cache_hit") else "critique"


def _stop_or(next_node: str) -> Callable[[dict], str]:
    def decide(state: dict) -> str:
        return END if state.get("status") else next_node
    return decide


def build_graph():
    g = StateGraph(RunState)

    for name, fn in (
        ("entry_resolve", nodes.entry_resolve),
        ("cache_probe", nodes.cache_probe),
        ("classify", nodes.classify),
        ("plan", nodes.plan),
        ("cost_guard_pre", nodes.cost_guard_pre),
        ("critique", nodes.critique),
        ("adjudicate", nodes.adjudicate),
        ("materialize", nodes.materialize),
        ("cost_guard_post", nodes.cost_guard_post),
        ("execute", nodes.execute),
    ):
        g.add_node(name, _node(fn))

    g.add_edge(START, "entry_resolve")
    # entry_resolve is the only fan-out: a resumed run re-enters wherever data/<run>/ says
    # it left off, rather than replaying steps that already wrote their artifacts.
    g.add_conditional_edges("entry_resolve", _after_entry, {
        "cache_probe": "cache_probe", "classify": "classify", "critique": "critique",
        "adjudicate": "adjudicate", "materialize": "materialize",
        # NOT straight to execute: a resumed run must still clear the cost ceiling. Routing
        # it through the guard is what keeps --max-gpu-hours from silently disarming itself
        # on every invocation after the first.
        "execute": "cost_guard_post",
    })
    g.add_conditional_edges("cache_probe", _after_cache,
                            {"classify": "classify", "plan": "plan", END: END})
    g.add_conditional_edges("classify", _stop_or("plan"), {"plan": "plan", END: END})
    g.add_conditional_edges("plan", _stop_or("cost_guard_pre"),
                            {"cost_guard_pre": "cost_guard_pre", END: END})
    g.add_conditional_edges("cost_guard_pre", _after_cost_pre,
                            {"critique": "critique", "cost_guard_post": "cost_guard_post",
                             END: END})
    g.add_conditional_edges("critique", _stop_or("adjudicate"),
                            {"adjudicate": "adjudicate", END: END})
    g.add_conditional_edges("adjudicate", _stop_or("materialize"),
                            {"materialize": "materialize", END: END})
    g.add_conditional_edges("materialize", _stop_or("cost_guard_post"),
                            {"cost_guard_post": "cost_guard_post", END: END})
    g.add_conditional_edges("cost_guard_post", _stop_or("execute"),
                            {"execute": "execute", END: END})
    g.add_edge("execute", END)
    return g.compile()
