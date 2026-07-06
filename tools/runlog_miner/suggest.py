"""Suggestion engine for the run_log learning loop (P0b).

Turns parsed :class:`~tools.runlog_miner.parse.RunRecord`s into *proposed*
``polymer_rules.json`` default changes. Read-only and advisory:

  * suggestions are gated by **agreement** — at least ``min_support`` distinct
    runs of a class must show the same signal before anything is proposed;
  * numeric proposals are emitted as a **unified diff** against
    ``guides/polymer_rules.json`` — this module never writes that file;
  * qualitative signals (finite-size, added annealing cycles) become
    ``suggested: null`` *review flags*, never auto-numbers.
"""
from __future__ import annotations

import difflib
import json
import re
import statistics
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ─── signal extraction ──────────────────────────────────────────────────────
_DENSITY_IN_FIX = re.compile(r"density_initial\s*[=:]\s*(\d+\.?\d*)", re.I)
_TSTART_IN_FIX = re.compile(r"T_START\s*[=:]\s*(\d+\.?\d*)", re.I)
_FINITE_SIZE_TERMS = ("longer dp", "finite-size", "finite size", "more chains", "longer chain")

_RULE_DESC = {
    "density_initial_gcm3": "density-recovery-consensus",
    "tg_t_high_K": "sweep-ceiling-consensus",
    "eq_annealing_cycles": "review-flag: annealing cycles added to converge",
    "dp_typical": "review-flag: finite-size noted in decisions",
}


@dataclass
class Signal:
    field: str
    kind: str            # "numeric" | "review"
    value: Optional[float]
    evidence: str


def _succeeded(outcome: str) -> bool:
    o = outcome.lower()
    return ("converged" in o) or ("pass" in o)


def extract_signals(record) -> list:
    """Pull structured signals from one RunRecord's recoveries + decisions."""
    signals: list = []
    for rec in record.recoveries:
        if not _succeeded(rec.outcome):
            continue
        m = _DENSITY_IN_FIX.search(rec.fix)
        if m:
            signals.append(Signal(
                "density_initial_gcm3", "numeric", float(m.group(1)),
                f"Stage {rec.stage}: density_initial→{m.group(1)} ({rec.outcome[:50]})",
            ))
        m = _TSTART_IN_FIX.search(rec.fix)
        if m:
            signals.append(Signal(
                "tg_t_high_K", "numeric", float(m.group(1)),
                f"Stage {rec.stage}: sweep ceiling→{m.group(1)} ({rec.outcome[:50]})",
            ))
        if "annealing cycle" in rec.fix.lower():
            signals.append(Signal(
                "eq_annealing_cycles", "review", None,
                f"Stage {rec.stage}: added annealing cycle(s) to converge",
            ))
    for key, d in record.decisions.items():
        if any(t in d.rationale.lower() for t in _FINITE_SIZE_TERMS):
            signals.append(Signal("dp_typical", "review", None, f"{key}: {d.rationale[:70]}"))
    return signals


# ─── aggregation ────────────────────────────────────────────────────────────
def _maybe_int(median_val: float, values: list):
    if median_val == int(median_val) and all(v == int(v) for v in values):
        return int(median_val)
    return round(median_val, 4)


def aggregate(records: list, rules_classes: dict, min_support: int = 2) -> dict:
    """Return {class_id: {field: suggestion_dict}} for fields with ≥min_support runs."""
    numeric: dict = defaultdict(lambda: defaultdict(list))   # cid -> field -> [(run, value, evidence)]
    review: dict = defaultdict(lambda: defaultdict(list))    # cid -> field -> [(run, evidence)]

    for r in records:
        cid = r.polymer_class
        if not cid:
            continue
        for s in extract_signals(r):
            if s.kind == "numeric":
                numeric[cid][s.field].append((r.run_name, s.value, s.evidence))
            else:
                review[cid][s.field].append((r.run_name, s.evidence))

    suggestions: dict = {}

    for cid, fields in numeric.items():
        for field, items in fields.items():
            runs = sorted({run for run, _, _ in items})
            if len(runs) < min_support:
                continue
            values = [v for _, v, _ in items]
            suggested = _maybe_int(statistics.median(values), values)
            current = rules_classes.get(cid, {}).get(field)
            if current is not None and float(current) == float(suggested):
                continue  # no-op
            suggestions.setdefault(cid, {})[field] = {
                "current": current,
                "suggested": suggested,
                "support_runs": runs,
                "evidence": [e for _, _, e in items],
                "rule": _RULE_DESC.get(field, "numeric-consensus"),
            }

    for cid, fields in review.items():
        for field, items in fields.items():
            runs = sorted({run for run, _ in items})
            if len(runs) < min_support:
                continue
            suggestions.setdefault(cid, {}).setdefault(field, {
                "current": rules_classes.get(cid, {}).get(field),
                "suggested": None,                       # review only
                "support_runs": runs,
                "evidence": [e for _, e in items],
                "rule": _RULE_DESC.get(field, "review-flag"),
            })

    return suggestions


# ─── proposed diff (never written) ──────────────────────────────────────────
def propose_diff(rules_path, suggestions: dict) -> str:
    """Unified diff applying only the *numeric* suggestions to a copy of
    polymer_rules.json. Canonical-JSON formatting; the file is not modified."""
    rules = json.loads(Path(rules_path).read_text(encoding="utf-8"))
    modified = deepcopy(rules)
    changed = False
    for cid, fields in suggestions.items():
        if cid not in modified.get("classes", {}):
            continue
        for field, info in fields.items():
            if info["suggested"] is None:
                continue
            modified["classes"][cid][field] = info["suggested"]
            changed = True
    if not changed:
        return ""
    a = json.dumps(rules, indent=2, ensure_ascii=False).splitlines(keepends=True)
    b = json.dumps(modified, indent=2, ensure_ascii=False).splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        a, b,
        fromfile="guides/polymer_rules.json (current)",
        tofile="guides/polymer_rules.json (proposed — canonical JSON, review before applying)",
    ))


def build_suggestions(records: list, rules_path, min_support: int = 2):
    rules = json.loads(Path(rules_path).read_text(encoding="utf-8"))
    suggestions = aggregate(records, rules.get("classes", {}), min_support)
    return suggestions, propose_diff(rules_path, suggestions)
