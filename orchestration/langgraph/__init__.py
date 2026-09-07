"""LangGraph driver: a PolyJarvis campaign start-to-finish with no live Claude Code session.

The deterministic control plane was always headless-ready -- agent_api exposes the whole
flow and recovery_agent_cli already drives a headless `claude -p` -- but PLANNING was still
done interactively by a human running the novel-run-plan skill. This package is the missing
half, and nothing more: it decides WHEN to call the existing scripts, never what they do.

Ownership is unchanged from AGENTS.md. Code owns simulation files, parameter resolution,
job submission, validation, recovery limits and provenance; the graph owns none of them and
holds no durable state of its own (see nodes.entry_resolve -- the resume point is derived
from data/<run>/, so there is no checkpointer and nothing to keep in sync).
"""
