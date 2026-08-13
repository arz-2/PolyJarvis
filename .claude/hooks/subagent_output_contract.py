#!/usr/bin/env python3
"""
SubagentStart hook — injects the output contract a spawned agent's own definition doesn't carry.

Per-worker output style stays in .claude/agents/<type>.md and is deliberately not restated here.
This hook covers only the two gaps: the RESULT-block invariant that workers keep violating on the
extra turn SubagentStop grants them, and a report budget for built-in agents, which have no .md
and default to long prose.
"""
import json
import os
import sys

BUILTIN_AGENTS = {"Explore", "Plan", "general-purpose", "claude"}

WORKER_CONTRACT = (
    "OUTPUT CONTRACT: your final message is the RESULT: block and nothing else — no lead "
    "sentence, no recap, no 'done'/'clean run' line, and no memory-save confirmation. A memory "
    "save is never the last action; if you save one, emit the RESULT: block again after it."
)

BUILTIN_CONTRACT = (
    "OUTPUT CONTRACT: report findings only, 15 lines max. Cite file:line instead of pasting file "
    "contents. Do not restate the prompt, narrate your process, or list what you searched."
)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    agent_type = data.get("agent_type") or ""
    if not agent_type:
        sys.exit(0)

    if agent_type in BUILTIN_AGENTS:
        context = BUILTIN_CONTRACT
    else:
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        agent_md = os.path.join(project_dir, ".claude", "agents", f"{agent_type}.md")
        if not os.path.isfile(agent_md):
            sys.exit(0)
        context = WORKER_CONTRACT

    print(json.dumps({
        "suppressOutput": True,
        "hookSpecificOutput": {
            "hookEventName": "SubagentStart",
            "additionalContext": context,
        },
    }))


if __name__ == "__main__":
    main()
