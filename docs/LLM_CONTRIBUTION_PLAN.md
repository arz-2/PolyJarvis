# PolyJarvis — LLM Contribution: Benchmark & Enhancement Plan

**Status:** Draft for review · **Branch:** `claude/project-test-strategy-f28n48` · **Date:** 2026-06-14

This document has two parts:

- **Part A — Benchmark:** a fault-injection experiment that *quantifies* what the LLM
  actually contributes, so the value claim rests on measured numbers rather than assertion.
- **Part B — Enhancement:** a prioritized roadmap to make the LLM's contribution *greater
  and more effective*, derived directly from where Part A's metrics are expected to be weak.

Read Part A first — its metrics define the scoreboard that Part B is trying to move.

---

## 0. Premise (the value thesis being tested)

The LLM's defensible contribution is **not** the deterministic core (chained MD, convergence
gates, parameter lookup) — that is ordinary automation any workflow engine (AiiDA, Snakemake,
RadonPy, pyiron) provides. The LLM earns its keep in the **ambiguous and broken** parts of the
workflow:

1. **Open-ended failure recovery** — diagnosing failures it was never explicitly programmed for.
   CLAUDE.md already names the `RECOVERIES` log *"the primary evidence of agent value."*
2. **Routing arbitrary / novel chemistry** — SMILES → class → FF → parameters, *with rationale*.
3. **Literate, auditable provenance** — the `run_log.md` decision trail (D-01…D-06 + RECOVERIES).
4. **Cross-tool orchestration** — gluing heterogeneous MCP servers with stateful recovery.

Its characteristic **liability** is *confident error* (asserting plausible-but-unverified facts).
This is already documented in-repo: the PSTR `ff_note` in `guides/polymer_rules.json` carries a
self-correction retracting a paywalled, unverified "R²=0.40" figure. The benchmark must therefore
measure **both** the upside (recovery, time saved) **and** this cost (false confidence slipping
past gates).

> **Net claim under test:** PolyJarvis's value scales with *breadth and failure-density*, not
> with depth on any single known system, and it trades a slice of rigor for that breadth — repaid
> only if the guardrails hold. Part A measures whether that trade is favorable.

---

## Part A — Fault-Injection Benchmark

### A.1 Goal

Produce three headline numbers, per fault class and aggregate:

| Metric | Definition | What it proves |
|---|---|---|
| **Recovery rate** | fraction of injected failures resolved to a passing run **without human intervention** (≤ 2 recovery attempts, the CLAUDE.md cap) | the upside — autonomy |
| **Time-to-resolution / human-minutes saved** | wall-clock + estimated human-minutes the recovery would otherwise cost | the upside — efficiency |
| **Guardrail catch-rate** *(and its inverse, false-confidence rate)* | fraction of *deliberately unphysical* outputs correctly blocked by the experiment-free gates vs. reported as confident results | the cost — does breadth leak wrong answers? |

A fourth, diagnostic metric:

| **Recovery quality** | of resolved cases, fraction whose *diagnosis* was physically correct (not a lucky parameter nudge) | distinguishes reasoning from random search |

### A.2 Fault catalog

Each fault is drawn from a real failure mode already discussed or visible in the codebase. Injection
point in parentheses.

| ID | Fault | Injection | Correct LLM response |
|---|---|---|---|
| **F1** | Over-dense initial cell | set `density_initial_gcm3` near experimental RT density (e.g. PCBN 1.15 vs 0.60) — system traps over-densified (mirrors a real `RECOVERIES` example) | detect non-convergence at Stage 2 → lower density → re-build |
| **F2** | Tg sweep starts below glassy regime | set `tg_t_high_K` below MD Tg so the glassy slope is missing (mirrors the T_START=550 K recovery example) | detect missing high-T linear branch / poor fit → raise window → re-sweep |
| **F3** | Out-of-taxonomy chemistry | feed valid SMILES with exotic heteroatoms (Si/P/B/metal) outside the 21 classes | return `UNKNOWN` / low-confidence **gracefully**, not a confident misroute |
| **F4** | Missing-FF-increment chemistry | a monomer EMC cannot type (à la PSIL `{si,osi}`, PURA `{n,hn}`) | fail **loudly** at build with a clear missing-parameter error, or reroute to RadonPy |
| **F5** | Malformed connection points | `*` attachment missing / on the wrong atom | classify as fixable input error, not a pipeline crash |
| **F6** | Silent-wrong (hardest) | a SMILES that misclassifies into a **high-confidence** class with an FF that mistypes it | this is the dangerous case — measure whether *any* downstream gate (P2 order, C∞, density sanity) catches it |
| **F7** | Under-equilibrated handoff | truncate Stage 2 so the cell is not converged but the chain "succeeds" | `check_equilibration_comprehensive` must block before Tg sweep |

F6 and F7 are the **false-confidence** probes — they are designed to *not* throw an error, so the
only defense is the experiment-free gate stack.

### A.3 Polymer test set

A small matrix that spans the credibility spectrum (keep it to ~6–8 to stay tractable):

| Tier | Examples | Purpose |
|---|---|---|
| **Known / literature-anchored** | BPA-PC (PCBN), PS (PSTR), PE (PHYC) | baseline; faults injected against a known-good target |
| **Analog-transfer** | a polymer whose nearest analog *is* in `db/` | tests the analog-validation path (Part B item 3) |
| **Novel-but-typeable** | an unusual but EMC/PCFF-typeable monomer | breadth without a ground truth |
| **Out-of-taxonomy** | Si/P/metal-containing, F3/F4 targets | classifier/build failure-mode probes |

### A.4 Experimental design

- **Control arm:** each (polymer × fault) run with recovery **disabled** (orchestrator stops on
  first failure) → establishes the failure is real and what "no LLM" looks like.
- **Treatment arm:** same, recovery **enabled** (normal orchestrator behavior).
- **Replicates:** ≥ 3 seeds per cell where stochastic packing matters (F1, F6, F7), to separate
  signal from initial-condition noise.
- **Blind-ish scoring:** recovery-quality (diagnosis correctness) scored against a pre-written
  expected-diagnosis key per fault, not post-hoc rationalized.

### A.5 Harness architecture

A thin layer **around** the existing orchestrator — it must not change pipeline physics:

```
benchmark/
  faults.yaml            # the F1–F7 catalog: param overrides + expected diagnosis key
  polymers.yaml          # the test-set matrix
  inject.py              # applies a fault to a run_params dict / data file
  run_matrix.py          # drives (polymer × fault × arm × seed); spawns orchestrator runs
  score.py               # reads run_log.md + gate JSON → the 4 metrics
  report.md (generated)  # the scoreboard
```

- **Source of truth for outcomes:** the `run_log.md` itself (DECISIONS, RECOVERIES,
  D-05/D-06) plus `check_equilibration_comprehensive` JSON. The harness *parses what the
  agent already records* — no new instrumentation inside workers.
- **No-network / compute budget:** faults F3–F6 are cheap (fail fast); F1/F2/F7 require real
  (short) MD. Use the smallest DP/nchain that still reproduces the failure to keep cost down.

### A.6 Scoring rubric (per fault, then aggregate)

- Recovery rate = resolved / injected (treatment arm).
- False-confidence rate = (unphysical outputs reported as results) / (unphysical outputs total).
  **Target: 0.** Any non-zero value is the headline risk to report.
- Time-to-resolution = Σ recovery wall-clock; human-minutes-saved estimated from a per-fault
  "manual baseline" (how long an expert would take to diagnose+fix).
- Recovery quality = correct-diagnosis / resolved.

### A.7 Deliverable

`docs/benchmarks/llm_value_report.md`: a table per fault class + an executive summary of the
three headline numbers, plus a **"leak log"** enumerating every F6/F7 case that slipped a gate
(the most important artifact — it directly sizes the trust cost).

### A.8 Risks & honesty guards

- **Don't grade your own homework:** the expected-diagnosis key is written *before* runs.
- **Small-N caveat:** 6–8 polymers × 7 faults is illustrative, not statistically powerful; report
  it as a *demonstration*, not a proof.
- **Recovery cap discipline:** enforce the 2-attempt cap so "recovery rate" can't be inflated by
  unbounded retries.

---

## Part B — Making LLM Contributions Greater & More Effective

Principle: **amplify where the LLM is strong, harden where it is weak.** Each lever is mapped to
the Part A metric it should move.

### B.1 Recovery: turn one-off fixes into a reusable, growing playbook
*Moves: recovery rate ↑, recovery quality ↑, time-to-resolution ↓*

- **Failure taxonomy + playbook** (`guides/RECOVERY_PLAYBOOK.md`): each known failure signature →
  diagnosis → adjustment. The orchestrator consults it first, and **appends** new patterns after
  any novel recovery. This converts the scattered `RECOVERIES` blocks into institutional memory.
- **Structured RECOVERIES schema** so recoveries are machine-readable (signature, cause, action,
  outcome) and can be mined — see B.4.
- **Tighter escalation criteria:** today it's "max 2 attempts → UNRESOLVED." Add *typed* escalation
  (input-fixable vs FF-limitation vs genuine non-convergence) so the right ones stop early and the
  recoverable ones get the full budget.

### B.2 Confidence calibration & anti-hallucination
*Moves: false-confidence rate ↓ (the headline cost)*

- **Mandatory claim verification:** any literature number entering a `run_log`/`polymer_rules`
  must pass a verification step (cf. the existing `verify` skill) — DOI resolves, figure
  corroborated by ≥1 source — or be labelled `UNVERIFIED`. Directly prevents the PSTR-style leak.
- **Confidence propagation:** ensure `ff_routing` `ff_confidence` and classifier warnings flow all
  the way into the final RESULTS block, not just D-01. A low-confidence prediction must *look*
  low-confidence at the end.
- **Refuse-to-fabricate default:** for unstudied systems the required output shape is
  *"Tg = X ± Y, low confidence, no experimental anchor, FF unvalidated for this chemistry"* —
  never a bare confident number. Encode this as a RESULTS gate.

### B.3 Active novelty handling (built-in robustness battery)
*Moves: provides an honest ± where literature gives none; lowers false-confidence*

Promote the robustness battery (from the earlier robustness discussion) to a **standard optional
worker**:

- **Analog-transfer validation:** auto-find nearest literature analog in `db/`, validate the
  pipeline on it first, and *inherit its error bar* for the novel target.
- **Replica spread → uncertainty:** N seeds = the real error bar when no experiment exists.
- **Force-field cross-check:** if two supported FFs can type the monomer, run both; agreement =
  robust, divergence = flag.
- **Cooling-rate / size convergence as first-class outputs**, not afterthoughts (ties to the
  PCBN protocol critique: cooling rate 4×10¹⁰ K/s, system below the cited 20×100-mer minimum).

### B.4 Provenance → learning loop (close the loop)
*Moves: every run makes the next better; recovery rate ↑ over time*

- **Mine `run_log.md` corpus** across runs to (a) auto-suggest improved `polymer_rules.json`
  defaults (e.g. better `density_initial`, sweep windows) and (b) surface recurring failure
  signatures into B.1's playbook. This is the single biggest force-multiplier: it makes the LLM's
  past judgment compound instead of evaporating per session.

### B.5 Orchestration efficiency
*Moves: time-to-resolution ↓, throughput ↑*

- **Parallel fan-out** of independent polymers/replicas (the multi-agent pattern already supports
  it).
- **Recovery-budget allocation** informed by fault type (don't spend 2 attempts on an
  input-fixable error).

### B.6 Guardrail hardening
*Moves: false-confidence rate ↓*

- Make the **experiment-free gates hard blocks** *before* any literature comparison, so a result
  can never be reported as trustworthy on the basis of a lucky match to experiment while failing
  convergence/structure checks.

### B.7 Prioritization (impact × effort)

| Lever | Impact | Effort | Priority |
|---|---|---|---|
| B.2 Anti-hallucination / confidence propagation | High (bounds the core risk) | Low–Med | **P0** |
| B.4 run_log mining → learning loop | High (compounding) | Med | **P0** |
| B.1 Recovery playbook | High | Low–Med | **P1** |
| B.3 Robustness-battery worker | Med–High | Med | **P1** |
| B.6 Guardrail-ordering | Med | Low | **P1** |
| B.5 Orchestration | Med | Low | **P2** |

### B.8 Suggested phasing

1. **Phase 0 — measure:** build Part A harness; get baseline numbers. *Nothing is justified until
   the scoreboard exists.*
2. **Phase 1 — bound the cost:** B.2 + B.6 (drive false-confidence toward 0).
3. **Phase 2 — compound the upside:** B.4 + B.1 (learning loop + playbook), re-run Part A to show
   recovery-rate lift.
4. **Phase 3 — breadth with honesty:** B.3 robustness worker for novel systems; B.5 for scale.

---

## Open questions for you

1. **Scope of Part A:** the full 7-fault × ~8-polymer matrix, or a minimal 3-fault smoke test first?
2. **Compute budget:** is real (short) MD for F1/F2/F7 acceptable, or keep the first cut to the
   fail-fast faults (F3–F6) that need no simulation?
3. **Build vs design-only:** do you want the harness implemented, or this plan refined further first?
4. **Part B sequencing:** agree with P0 = {anti-hallucination, run_log mining}, or prioritize the
   recovery playbook first (most visible "agent value" demo)?
