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
from .suggest import aggregate, build_suggestions, extract_signals, propose_diff
from .cluster import build_playbook, cluster_recoveries
from .calibrate import build_calibration, calibrate

__all__ = [
    "Decision",
    "Recovery",
    "ResultRow",
    "RunRecord",
    "load_corpus",
    "parse_run_log",
    "parse_text",
    "summarize",
    "aggregate",
    "build_suggestions",
    "extract_signals",
    "propose_diff",
    "build_playbook",
    "cluster_recoveries",
    "build_calibration",
    "calibrate",
]
