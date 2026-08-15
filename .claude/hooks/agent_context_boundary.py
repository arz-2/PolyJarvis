#!/usr/bin/env python3
"""
PreToolUse hook — per-subagent file-access boundary.

Enforces a default-deny allowlist for Read/Grep/Glob and a deny-list scan for Bash, scoped only
to subagent calls (agent_id present in hook input). Main-thread/orchestrator calls have no
agent_id and are never restricted here.

Cooperative-agent guardrail, not an adversarial sandbox: a Bash command can evade the path scan
via base64, shell variable indirection, or a symlink. It keeps a well-behaved worker from
wandering into out-of-scope context — it is not a security boundary against a worker actively
trying to defeat it.
"""
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = REPO_ROOT / ".claude" / "agent-context-boundaries.json"


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def allow_silent() -> None:
    sys.exit(0)


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        print(f"agent_context_boundary: could not load {CONFIG_PATH}, skipping enforcement",
              file=sys.stderr)
        sys.exit(0)


def resolve(path_str: str, cwd: str) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        p = Path(cwd or REPO_ROOT) / p
    try:
        return Path(os.path.normpath(str(p)))
    except Exception:
        return p


def glob_to_check(entry: str):
    is_abs = entry.startswith("abs:")
    raw = entry[4:] if is_abs else entry
    is_prefix = raw.endswith("/**")
    base = raw[:-3] if is_prefix else raw
    base_path = Path(base) if is_abs else (REPO_ROOT / base)
    return Path(os.path.normpath(str(base_path))), is_prefix


def path_matches(abs_path: Path, entries: list) -> bool:
    for entry in entries:
        base, is_prefix = glob_to_check(entry)
        if is_prefix:
            try:
                abs_path.relative_to(base)
                return True
            except ValueError:
                continue
        else:
            if abs_path == base:
                return True
    return False


def check_read_like(tool_name: str, tool_input: dict, cwd: str, allow_entries: list):
    if tool_name == "Read":
        raw = tool_input.get("file_path")
        if not raw:
            allow_silent()
        abs_path = resolve(raw, cwd)
        if path_matches(abs_path, allow_entries):
            allow_silent()
        deny(f"Read denied: '{raw}' is outside your allowed context (guide + relevant "
             f"rules JSON + your own data/** workspace + agent-memory).")

    if tool_name == "Glob":
        raw = tool_input.get("path") or tool_input.get("pattern") or "."
        base = re.split(r"[*?\[]", raw, maxsplit=1)[0].rstrip("/") or "."
        abs_path = resolve(base, cwd)
        if path_matches(abs_path, allow_entries):
            allow_silent()
        deny(f"Glob denied: pattern/base '{raw}' resolves outside your allowed context.")

    if tool_name == "Grep":
        raw = tool_input.get("path")
        if not raw:
            deny("Grep denied: no explicit 'path' given — a path-less Grep defaults to a "
                 "repo-wide search, which would reach directories outside your allowed context.")
        abs_path = resolve(raw, cwd)
        if path_matches(abs_path, allow_entries):
            allow_silent()
        deny(f"Grep denied: path '{raw}' is outside your allowed context.")

    allow_silent()


_PATH_TOKEN_RE = re.compile(
    r"(?:/home/arz2/PolyJarvis/\S+)"
    r"|(?:/home/arz2/(?:simulations|polyjarvis_emc_jobs)/\S+)"
    # (?<![\w./-]) not \b: a leading "." is not a word character, so \b never matched at the
    # start of ".claude/..." or ".git/..." and those deny entries were dead on the Bash path
    # (a plain `cat .claude/settings.json` passed). The lookbehind anchors on "start of token"
    # instead, and still refuses to fire mid-path (foo/data/x) or mid-word.
    r"|(?<![\w./-])(?:\.claude|mcp-servers|orchestration|guides|db|manuscript|manuscript_v2|docs|"
    r"hardware|tools|tests|literature|\.understand-anything|\.git|\.github|data)/\S+"
    r"|\bCLAUDE\.md\b|\bAGENTS\.md\b|\bREADME\.md\b|\bTask_TEMPLATE\.txt\b|\bLICENSE\b"
    r"|\.env\b|\.mcp\.json\S*|\bpytest\.ini\b|\brequirements-test\.txt\b"
)


def check_bash(tool_input: dict, cwd: str, deny_entries: list, bash_allow_entries: list):
    cmd = tool_input.get("command", "")
    if not cmd:
        allow_silent()

    for raw_tok in _PATH_TOKEN_RE.findall(cmd):
        tok = raw_tok.rstrip(",;)'\"")
        abs_path = resolve(tok, cwd)
        if not path_matches(abs_path, deny_entries):
            continue
        if path_matches(abs_path, bash_allow_entries):
            continue
        deny(f"Bash denied: command references '{tok}', which is outside your allowed Bash "
             f"scope (own data/** workspace + your specific allowlisted scripts).")

    allow_silent()


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    agent_id = data.get("agent_id")
    if not agent_id:
        sys.exit(0)

    agent_type = data.get("agent_type") or ""
    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input", {}) or {}
    cwd = data.get("cwd") or str(REPO_ROOT)

    if tool_name not in ("Read", "Grep", "Glob", "Bash"):
        allow_silent()

    config = load_config()
    agents = config.get("agents", {})
    rules = agents.get(agent_type) or config.get("default_unknown_agent", {})

    baseline_allow = [e.replace("{agent}", agent_type) for e in config.get("baseline_allow", [])]
    allow_entries = baseline_allow + rules.get("extra_read_allow", [])
    deny_entries = config.get("deny_dirs", [])
    bash_allow_entries = baseline_allow + rules.get("bash_allow", [])

    if tool_name == "Bash":
        check_bash(tool_input, cwd, deny_entries, bash_allow_entries)
    else:
        check_read_like(tool_name, tool_input, cwd, allow_entries)


if __name__ == "__main__":
    main()
