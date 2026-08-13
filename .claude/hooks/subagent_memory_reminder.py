#!/usr/bin/env python3
"""
SubagentStop hook — reminds a completed worker subagent to save agent-memory
feedback before it finishes. Self-gates on whether the agent has a memory dir
(.claude/agent-memory/<agent_type>/) so it silently no-ops for router/explore
agents that don't participate in this convention.

Gated further on the worker's turn actually hitting friction — a tool error, a
permission denial, or a coordinator correction — so clean runs don't spend an
extra turn. A repeated identical tool call is deliberately NOT a signal:
molecule-builder polls get_job_status in a loop and watch_run repeats by design.

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


def had_friction(transcript_path: str) -> bool:
    """An errored tool result (this is also how a permission denial surfaces), or a second real
    user message — i.e. the coordinator had to send a correction.

    Tool results are themselves recorded as type="user" entries, so a real message is one whose
    content is a plain string or carries no tool_result block.
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return False

    real_user_messages = 0
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("type") != "user" or entry.get("isMeta"):
                    continue
                content = (entry.get("message") or {}).get("content")
                if isinstance(content, str):
                    real_user_messages += 1
                    continue
                if not isinstance(content, list):
                    continue
                results = [b for b in content
                           if isinstance(b, dict) and b.get("type") == "tool_result"]
                if not results:
                    real_user_messages += 1
                elif any(b.get("is_error") for b in results):
                    return True
    except OSError:
        return False

    return real_user_messages > 1


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

if not had_friction(data.get("agent_transcript_path", "")):
    sys.exit(0)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SubagentStop",
        "additionalContext": (
            f"MEMORY: this run hit friction (a tool error, a denial, or a correction from the "
            f"coordinator). Save a `feedback` memory covering it, plus any codebase friction / "
            f"room for improvement. Write to .claude/agent-memory/{agent_type}/ and add a "
            f"one-line entry to that dir's MEMORY.md. Then emit the RESULT: block again as the "
            f"true final message of the turn — a memory save is never the last action."
        ),
    }
}))
