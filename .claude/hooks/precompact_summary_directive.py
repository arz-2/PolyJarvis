#!/usr/bin/env python3
"""
PreCompact hook — supplies the compaction summarizer with PolyJarvis-specific instructions.

Hook stdout is consumed raw as the compaction custom instructions, so this prints plain text,
never JSON. Always exits 0: blocking auto-compaction would leave the session over its context
limit with no way forward.

Orchestrator sessions (no agent_id) additionally get an authoritative state block read from disk
— run_log.md and the GPU claim table — so the identifiers a restarting orchestrator needs survive
compaction as facts, not as whatever the summarizer chose to keep. The run is resolved from this
session's own transcript, never from mtime: several campaigns run concurrently on this host, and
a state block naming the wrong run is worse than none.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MAX_CHARS = 3000
TRANSCRIPT_TAIL_BYTES = 2_000_000
RUN_REF_RE = re.compile(r"data/([A-Za-z0-9][A-Za-z0-9._-]*)/")

AMBIGUOUS_NOTE = (
    "This host runs several campaigns at once and this session's run could not be resolved: "
    "re-Read your own data/[RUN]/run_log.md after compaction, and do not assume the run named "
    "anywhere in the summary."
)

ORCHESTRATOR_DIRECTIVE = """\
PolyJarvis campaign session. Summarize as an operator handoff, not a narrative.

Preserve verbatim, as a labeled list:
- run_name, canonical SMILES, IS_NOVEL, VALIDATED, properties_requested
- plan_mode and PLAN_PATH
- current phase (SETUP / A / B-thermal / B-mechanical / C) and the stage in flight
- every live chain_id and run_id with its monitor_command and BgTask id
- claimed gpu_ids and the run holding each claim
- every gate verdict in the order it was returned (equil-check, critic, RECOVERY)
- the RECOVERY attempt count so far
- the absolute path to run_log.md
- any outstanding user instruction, in the user's original wording
- the instruction to re-Read orchestration/ORCHESTRATOR.md and the current phase guide first

Drop entirely: tool-call transcripts, worker reasoning, thermo/log excerpts, superseded plan
drafts, and the text of any guide already read — name the guide path instead of summarizing it,
it will be re-read on demand.
"""

WORKER_DIRECTIVE = """\
PolyJarvis worker subagent. Keep only the tool results, absolute paths, and numeric values needed
to emit the RESULT: block, plus any error text and the step that failed. Drop all narration.
"""


def resolve_run(transcript_path: str):
    """The one run this session is driving, from its own transcript. None if not exactly one."""
    if not transcript_path:
        return None
    try:
        with open(transcript_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - TRANSCRIPT_TAIL_BYTES))
            tail = fh.read().decode("utf-8", "replace")
    except OSError:
        return None

    names = {
        n for n in RUN_REF_RE.findall(tail)
        if n != "TEMPLATE" and (REPO_ROOT / "data" / n / "run_log.md").is_file()
    }
    return names.pop() if len(names) == 1 else None


def read_run_log_state(run_name: str) -> str:
    """Header lines + SIMULATION STATE table of this session's run_log.md."""
    log = REPO_ROOT / "data" / run_name / "run_log.md"
    try:
        text = log.read_text()
    except OSError:
        return ""

    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    header = text.split("\n---", 1)[0].strip()
    sim = ""
    m = re.search(r"^## SIMULATION STATE$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if m:
        sim = "\n".join(
            ln for ln in m.group(1).splitlines()
            if ln.strip() and ln.strip() != "---"
        ).strip()

    parts = [f"run_log: {log}"]
    if header:
        parts.append(header)
    if sim:
        parts.append("SIMULATION STATE\n" + sim)
    return "\n\n".join(parts)


def read_gpu_claims() -> str:
    script = REPO_ROOT / "orchestration" / "scripts" / "pick_gpu.py"
    if not script.exists():
        return ""
    try:
        out = subprocess.run(
            [sys.executable, str(script), "--json", "status"],
            capture_output=True, text=True, timeout=15, cwd=str(REPO_ROOT),
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if out.returncode != 0 or not out.stdout.strip():
        return ""
    try:
        status = json.loads(out.stdout)
    except ValueError:
        return ""
    claims = [f"GPU {g.get('index')}: {g.get('claim') or 'free'}" for g in status.get("gpus", [])]
    return "GPU claims — " + ", ".join(claims) if claims else ""


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    if data.get("agent_id"):
        sys.stdout.write(WORKER_DIRECTIVE)
        return

    run_name = resolve_run(data.get("transcript_path") or "")
    out = ORCHESTRATOR_DIRECTIVE
    if run_name is None:
        sys.stdout.write(out + "\n" + AMBIGUOUS_NOTE)
        return

    blocks = [b for b in (read_run_log_state(run_name), read_gpu_claims()) if b]
    if blocks:
        state = "\n\n".join(blocks)
        budget = MAX_CHARS - len(out) - len("\nAUTHORITATIVE STATE (from disk) — restate verbatim:\n")
        if budget > 200:
            if len(state) > budget:
                state = state[:budget].rstrip() + "\n…(truncated)"
            out += "\nAUTHORITATIVE STATE (from disk) — restate verbatim:\n" + state

    sys.stdout.write(out[:MAX_CHARS])


if __name__ == "__main__":
    main()
