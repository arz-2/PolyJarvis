"""runlog_miner — parse and summarize the PolyJarvis run_log.md corpus.

P0a (this package): read-only parsing + a markdown summary report. See
``docs/specs/B4_runlog_miner_spec.md`` for the full B.4 learning-loop design.
"""
from .parse import (
    Decision,
    Recovery,
    ResultRow,
    RunRecord,
    load_corpus,
    parse_run_log,
    parse_text,
)
from .report import summarize

__all__ = [
    "Decision",
    "Recovery",
    "ResultRow",
    "RunRecord",
    "load_corpus",
    "parse_run_log",
    "parse_text",
    "summarize",
]
