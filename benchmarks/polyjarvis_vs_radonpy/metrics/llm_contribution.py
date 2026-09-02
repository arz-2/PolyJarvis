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
  on this checkout -- confirmed live via make_deterministic_plan.py decision's PEG1 output; D-05/D-06/D-07
  are NOT keys here, they are mechanized runtime gate verdicts folded into run_summary.json's
  `decisions` dict instead, e.g. "D-05_convergence": "PASS"). Each decision_evaluations row has
  `evidence`: a list of dicts. A row counts as "with evidence" only if at least one entry carries
  a real citation (`source_doi` or `citation` key) AND is not tagged `origin: "autofill"`.
  Since 2026-09-02 make_deterministic_plan.py's `decision` subcommand pre-populates every row
  with genuinely cited evidence resolved from polymer_rules.json's _metadata.primary_sources --
  that is the deterministic baseline, not LLM reasoning, and it is tagged `origin: "autofill"`
  so this axis excludes it. Evidence the calling session transcribes from the literature critic
  is tagged `origin: "critic"` and does count. (A legacy bare
  `{"claim": ..., "source": "polymer_rules.json:..."}` placeholder still fails the citation test
  on its own.)
"""
from __future__ import annotations

import json
from pathlib import Path

from .schema import LLMContributionBlock

MECHANIZED_DECISION_PREFIXES = ("D-05", "D-06", "D-07")


def _has_real_citation(evidence_entry: dict) -> bool:
    """True only for a cited entry that live LLM reasoning actually produced.

    `origin: "autofill"` marks an entry the deterministic decision tool wrote from
    polymer_rules.json's own primary_sources -- well cited, but zero LLM contribution. Counting
    it would collapse the deterministic baseline into the treatment arm, which is the exact
    separation this axis exists to measure. Tested with `!= "autofill"` rather than
    `== "critic"` so historical run dirs, whose entries predate the tag entirely, still count.
    """
    return bool((evidence_entry.get("source_doi") or evidence_entry.get("citation"))
                and evidence_entry.get("origin") != "autofill")


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
    block.autofilled_decisions_with_evidence = sum(
        1 for row in evaluations.values()
        if any(e.get("origin") == "autofill"
               and (e.get("source_doi") or e.get("citation"))
               for e in row.get("evidence", []))
    )

    run_summary_glob = list((run_dir / "attempts" / "summary").glob("attempt-*/raw/run_summary.json"))
    if run_summary_glob:
        summary = json.loads(sorted(run_summary_glob)[-1].read_text())
        decisions = summary.get("decisions", {})
        block.mechanized_gate_decisions_total = sum(
            1 for k in decisions if any(k.startswith(p) for p in MECHANIZED_DECISION_PREFIXES)
        )

    # literature_grounding_ff_protocol.json / _system_size.json were merged into one
    # literature_grounding.json on 2026-09-02; the old names stay listed so historical
    # benchmark run dirs still score.
    lit_files = [
        run_dir / "raw" / "literature_grounding.json",
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
