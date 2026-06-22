# Autonomy evidence package — run design (R1M1 / M7 / M11)

Load-bearing evidence for the autonomy cluster. The delineation table and provenance
audit concede that routine decisions are deterministic lookups; **these two runs are the
only evidence a script cannot reproduce.** Both hold the backend fixed (EMC builder +
LAMMPS engine + `polymer_rules.json` + `decision_policy.json`) and vary only the
orchestrator.

Pre-scripted vs. inferred is decided by one artifact: **`.claude/commands/recover.md`**
(14 documented error→recovery rows). A recovery already in that table = pre-scripted
(Tier 1). A recovery not in it = inferred (Tier 3). Same discriminator as the manuscript
("could the if-then have been written in advance?").

---

## A. Scripted-baseline ablation (R1M1 + R1M7)

**Goal:** isolate the LLM. Same EMC+LAMMPS backend; toggle the orchestrator only.

**Two arms**
- **SCRIPT** — deterministic Python driver: reads `polymer_rules.json`, runs the fixed
  stage chain (build → equil → equil-check → property) with no LLM. On any non-zero exit
  or failed gate it halts (no recovery beyond any pre-coded retry).
- **AGENT** — full PolyJarvis orchestrator (LLM + workers + `recover.md`).

**Systems (3; spans happy-path → failure → off-table)**
| System | Class | Role | Expected outcome |
|---|---|---|---|
| PMMA | PACR | high-confidence happy path | SCRIPT ≈ AGENT (routine decisions are not LLM-dependent — concession) |
| PE | PHYC | the +25% density failure | AGENT detects/diagnoses over-densification; SCRIPT emits the bad density undetected |
| off-table probe | class absent from `polymer_rules.json` (or PE with a perturbed input: corrupted `.data` / wrong `density_initial`) | SCRIPT stalls (no encoded path); AGENT composes a recovery |

**Seeds:** one fixed seed per system, identical across arms (the ablation measures
orchestration behavior, not a property distribution — keep cost low). Log the seed at
submit time per cross-track rule 2.

**Metrics (process, not accuracy)**
- human interventions required (count)
- wall-clock to first valid result
- recovery events: failures encountered / auto-resolved
- terminal state: completed | stalled | wrong-but-undetected

**Narrative it must support:** happy path identical (honest concession) → failure /
off-table diverge (localized LLM value). Do **not** claim improved accuracy.

---

## B. Error-recovery benchmark (R1M1 + R1M11)

**Goal:** reproducible, pre-registered failure-injection suite; report success rate,
failed attempts, and pre-scripted vs. inferred — exactly what M11 asks.

**Fault catalog** — the four categories the paper already cites, plus a generalization
probe of faults absent from `recover.md`:

| # | Injected fault | In `recover.md`? | Label |
|---|---|---|---|
| 1 | PPPM out-of-range atoms (npt_compress) | yes | pre-scripted |
| 2 | pair/dihedral-style mismatch (missing FF flag) | yes | pre-scripted |
| 3 | velocity re-initialization bug | partial | pre-scripted |
| 4 | Tg fit R² < 0.80 / <4 bins | yes | pre-scripted |
| 5 | **EMC build failure on an unsupported increment** | no | **inferred (generalization probe)** |
| 6 | **data-file atom-count / topology mismatch** | no | **inferred (generalization probe)** |

**Protocol:** run each fault through the AGENT N≥3 times. Record #attempts (incl.
failures — M11 asks explicitly), human guidance needed, final outcome, and the
pre-scripted/inferred label. Report an overall recovery success rate and a per-category
breakdown.

**Honesty hook:** faults 1–4 demonstrate reliable execution of *encoded* recovery (Tier
1 — not novelty); faults 5–6 are the *inferred* recoveries that substantiate Tier 3.
Keep the two visibly separate in the table.

---

## Deliverables → manuscript

- Ablation table → SI (cited from main R1M7 baseline subsection).
- Recovery benchmark table → SI §S10 (replaces the current "13 errors" prose; cited from
  main R1M11).
- Both feed the M1 Decision Architecture subsection as the Tier-3 evidence.
- Until both complete, M1/M7/M11 remain **Partially** in the response letter.

---

## Implementation status (built + smoke-tested; full runs pending)

Code: `benchmarks/autonomy/` (reuses `make_deterministic_plan.py`, `ScriptGenerator`,
`build_cell`, `recover.md`; `pytest benchmarks/autonomy/tests/` = 15 green).
- `error_classifier.py` — 15 recover.md rows as a regex table; the unsupported-increment
  case is deliberately kept inferred (discriminator). Benchmark-only, not wired live.
- `scripted_baseline.py` — SCRIPT arm; deterministic plan + halt-on-failure; foundation
  track (build→equil→equil-check, where PE density surfaces) wired; `--smoke` dry-runs it.
- `fault_catalog.py` + `run_recovery_benchmark.py` — 6 faults (4 prescripted, 2 inferred);
  smoke run: 6/6 triggered, classifier 6/6, prescripted recovery rate 1.0, 2 inferred
  left for the AGENT. **Caveat:** F2 is scored on the real ScriptGenerator exception text;
  F1/F3/F4/F6 on real validator/arithmetic surfaces; **F5 (and the F1 PPPM runtime string)
  are still representative strings, not captured logs** — so "recovery 1.0" is a
  wiring result, NOT validation.
- Production change: `ScriptGenerator.generate(velocity_seed=...)` (default unset =
  unchanged) for reproducible benchmark runs; engine suite regression-free (53 passed).
- Halt-on-failure (the SCRIPT control) is unit-tested: forced failure → classify → record
  unrecovered → `terminal_state=stalled`.

### Hard gates before any number here is citable (launch step)
1. **Capture real error logs as fixtures** and re-score the classifier on them — especially
   F5: actually run the PURA EMC build, capture EMC's real error, confirm it matches NO
   recover.md regex (that non-match is the entire "inferred" claim). Same for the F1 PPPM
   runtime error from a real low-density run.
2. **AGENT-arm instrumentation parity** — the AGENT arm must emit the *same* `metrics.py`
   schema (interventions / wall-clock / recovery) by the same mechanism as SCRIPT, not
   hand-counted, or the SCRIPT-vs-AGENT comparison is not apples-to-apples.
3. Full ablation (PMMA/PE/off-table) + AGENT-arm inferred recoveries + property-stage
   wiring (tg/bm).
Until 1–3 land, M1/M7/M11 stay **Partially** and the recovery rate is reported as a
harness check, not evidence.
