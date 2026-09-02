"""Extracts the LLM-reasoning-contribution axis for the PolyJarvis arm.

Reads two files, verified field-by-field against real PE1/PP/PEG1 run data in this
checkout (schemas do drift across runs made with different code versions -- always
prefer the freshest example, PEG1, over older ones like PE1 when the two disagree):

- data/<run>/raw/run_plan.json: top-level `plan_mode` in {"reasoned","deterministic","scaffold"}.
  Only "reasoned" reflects live LLM reasoning; "deterministic" is a frozen cache replay
  (zero new reasoning) and "scaffold" is an unreviewed placeholder. A benchmark run that
  isn't "reasoned" has nothing for this axis to measure -- flagged via `note`, not silently
  scored as zero contribution.

- data/<run>/raw/decision.json: `decision_evaluations` is a dict keyed by decision id
  (currently D-01_ff, D-02_charges, D-03_electrostatics, D-04_system_size, D-08_hardware
  on this checkout -- confirmed live via make_decision_scaffold.py's PEG1 output; D-05/D-06/D-07
  are NOT keys here, they are mechanized runtime gate verdicts folded into run_summary.json's
  `decisions` dict instead, e.g. "D-05_convergence": "PASS"). Each decision_evaluations row has
  `evidence`: a list of dicts. A row counts as "with evidence" only if at least one entry carries
  a real citation (`source_doi` or `citation` key) -- a bare `{"claim": ..., "source": "polymer_rules.json:..."}`
  placeholder (seeded by the scaffold generator, never replaced) does not count.
"""
from __future__ import annotations

import json
from pathlib import Path

from .schema import LLMContributionBlock

MECHANIZED_DECISION_PREFIXES = ("D-05", "D-06", "D-07")


def _has_real_citation(evidence_entry: dict) -> bool:
    return bool(evidence_entry.get("source_doi") or evidence_entry.get("citation"))


def extract_llm_contribution(run_dir: Path) -> LLMContributionBlock:
    run_plan_path = run_dir / "raw" / "run_plan.json"
    decision_path = run_dir / "raw" / "decision.json"

    block = LLMContributionBlock()

    if not run_plan_path.is_file():
        block.applicable = False
        block.note = f"no run_plan.json at {run_plan_path}"
        return block

    run_plan = json.loads(run_plan_path.read_text())
    block.plan_mode = run_plan.get("plan_mode")
    block.confidence = run_plan.get("confidence")

    if block.plan_mode != "reasoned":
        block.note = (
            f"plan_mode={block.plan_mode!r}, not 'reasoned' -- this run reflects a cached "
            "replay or unreviewed scaffold, not live LLM reasoning; exclude from this axis "
            "or treat its contribution as zero-by-construction, not measured."
        )

    if not decision_path.is_file():
        block.note += f" (no decision.json at {decision_path})"
        return block

    decision = json.loads(decision_path.read_text())
    evaluations = decision.get("decision_evaluations", {})
    block.llm_authored_decisions_total = len(evaluations)
    block.llm_authored_decisions_with_evidence = sum(
        1 for row in evaluations.values()
        if any(_has_real_citation(e) for e in row.get("evidence", []))
    )

    run_summary_glob = list((run_dir / "attempts" / "summary").glob("attempt-*/raw/run_summary.json"))
    if run_summary_glob:
        summary = json.loads(sorted(run_summary_glob)[-1].read_text())
        decisions = summary.get("decisions", {})
        block.mechanized_gate_decisions_total = sum(
            1 for k in decisions if any(k.startswith(p) for p in MECHANIZED_DECISION_PREFIXES)
        )

    lit_files = [
        run_dir / "raw" / "literature_grounding_ff_protocol.json",
        run_dir / "raw" / "literature_grounding_system_size.json",
    ]
    lit_count = 0
    for lit_path in lit_files:
        if lit_path.is_file():
            try:
                lit_data = json.loads(lit_path.read_text())
            except json.JSONDecodeError:
                continue
            sources = lit_data.get("sources") or lit_data.get("evidence") or []
            if isinstance(sources, list):
                lit_count += sum(1 for s in sources if isinstance(s, dict) and s.get("verified"))
    block.literature_grounding_evidence_count = lit_count

    return block
