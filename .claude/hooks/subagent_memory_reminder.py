#!/usr/bin/env python3
"""
SubagentStop hook — reminds a completed worker subagent to save agent-memory
feedback before it finishes. Self-gates on whether the agent has a memory dir
(.claude/agent-memory/<agent_type>/) so it silently no-ops for router/explore
agents that don't participate in this convention.

Fires only on the natural (first) stop attempt (stop_hook_active=False) — once
additionalContext has granted the subagent an extra turn, stop_hook_active is
True on every subsequent SubagentStop for the same turn, and re-injecting the
same reminder then loops indefinitely (confirmed empirically: an unguarded
version of this hook re-fired 11+ times on one subagent before it started
refusing).
"""
import sys
import json
import os

try:
    data = json.load(sys.stdin)
    agent_type = data.get("agent_type", "")
except Exception:
    sys.exit(0)

if not agent_type or data.get("stop_hook_active"):
    sys.exit(0)

project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
mem_dir = os.path.join(project_dir, ".claude", "agent-memory", agent_type)

if not os.path.isdir(mem_dir):
    sys.exit(0)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SubagentStop",
        "additionalContext": (
            f"MEMORY: before finishing, save a `feedback` memory for (1) any error encountered "
            f"this run, and (2) any codebase friction / room for improvement. Write to "
            f".claude/agent-memory/{agent_type}/ and add a one-line entry to that dir's "
            f"MEMORY.md. Skip only if the run was clean and nothing was awkward."
        ),
    }
}))
