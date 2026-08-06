# Revision Plan — PolyJarvis Round 2 (ct-2026-00736q, post-revision review)

Action tracker only. Source: `manuscript_v2/reviewer_comment.txt` (single reviewer, 6 major
points + reproducibility; quality 7/10, importance 8/10). Round-1 tracker for reference:
`manuscript/revision.md`. Legend: `[ ]` not started · `[~]` in progress · `[x]` done.

Every item below was cross-checked against the actual repo state (not just the round-1 tracker's
claims) before being scoped — see "Evidence" lines.

---

## Priority 0 — blocks grading of everything else

### B. Convergence-gate enforcement (reviewer comment 2)
Reviewer: trajectories exceeding stated hard thresholds (energy drift, Rg variability, density
homogeneity) remain in the property ensembles; wants a per-run pass/fail table, the action taken,
and the final disposition, under a predeclared rerun/exclude rule.

**Audit superseded 2026-08-04 by the mechanized gate** (`orchestration/enforce_gate.py`, built and
validated this session — see the "Mechanized enforcement" subsection below). The manual audit below
was the first pass; it missed an entire class of violation because it never checked
`decision_policy.json`'s `density_value_binding` clause (a run can have `overall_pass=True` — i.e.
clear every drift/SEM stability check — while its glassy density sits >5% below experiment, because
`overall_pass` only tests that the value *stopped moving*, never that it stopped at the *right*
value). Running the mechanized gate — which does check it — against all 36 runs gives:

**10 PASS_CLEAN | 8 PASS_CARVEOUT | 17 VIOLATION | 1 UNADJUDICATED**, not the original 18/9/9. The
8 new violations are entirely in **PS (4/4) and PEEK (4/4)** — both families I had already finalized
as clean canonical protocol sources in task #17 below, based on the manual audit alone. That
conclusion is wrong for PS and PEEK specifically; superseded here.

- 10/36 runs pass the mechanized gate cleanly.
- 8/36 fail *only* a metric their regime's policy clause already declares advisory (PE4,
  cis-PBD4, PEG2, PEG3 → rubbery C(t); PLA1–4 → glassy C(t), DP=50) — legitimate, but currently
  undisclosed (buried in `run_log.md` prose, not surfaced in the manuscript).
- **17/36 are genuine, mechanized-gate-confirmed violations** — the original 9 (below), plus 8 more
  surfaced only once `density_value_binding` was actually checked:

  | Run | New finding (2026-08-04) |
  |---|---|
  | PMMA1 | Also `UNDER_ANNEALED_COOLING` (−6.24% density gap) — matches PMMA2/3/4 exactly. **All 4** PMMA replicates share the identical root cause, not 3 of 4 as originally scoped; PMMA1 was never actually a clean pass |
  | PS1, PS2, PS3, PS4 | `MELT_STAGE_DEFICIT` (all 4) — density deficit is in the equilibrated melt itself, not the cooling ramp. Re-cooling slower will **not** fix this, unlike PMMA/PEEK. `run_summary.json` already narrates these as "MARGINAL FAIL... documented aromatic-PCFF underdensity" — an honest FAIL, but the specific diagnostic the policy requires before accepting that explanation was never run. Root cause (FF underbinding vs. melt under-annealing) is genuinely undetermined without a heavy-melt-anneal probe |
  | PEEK1, PEEK2, PEEK3, PEEK4 | `UNDER_ANNEALED_COOLING` (all 4, −5.2 to −5.7%) — same mechanism as PMMA, though `extrapolation_reliable=False` (470 K cooling span exceeds the tool's reliable range) — lean on the absolute density gate, treat the melt/cooling split as indicative only |

  The **original 9** (unchanged from the first pass):

  | Run | Failing gate(s) | What was recorded | Why it's a real violation |
  |---|---|---|---|
  | PMMA2, PMMA3, PMMA4 | density-homogeneity CV (27.7–28.7%) | "require_glassy carve-out → PASS" | density-homogeneity is explicitly **binding** under require_glassy, not advisory |
  | PSU2, PSU3, PSU4 | density-homogeneity CV (25.1–26.2%) | "finite-size Poisson noise" carve-out | same — no finite-size exception exists in the policy text |
  | PE2 | energy drift | run_log claims "all hard gates pass" | its own JSON shows energy drift fails, binding under require_rubbery |
  | PVC1 | — | D-05 row is the **unfilled template placeholder** | never actually adjudicated |
  | PVC4 | energy drift/SEM | extended once, drift worsened 5.55%→9.56% ("physical aging"), accepted with caveat | no carve-out applies; explicitly admitted unfixable by extension, kept anyway. `tau_V_ps=41.9` vs ~3–8 ps for PVC1–3 — a real, measurable non-equilibrium signature, not noise |

- [x] Predeclared hard-gate rule already exists (`decision_policy.json` `require_glassy` /
      `require_rubbery`) — the fix is enforcement, not writing a new rule.
- [x] Rule applied retroactively to all 36 runs (table above); per-run pass/fail/action/disposition
      data already sits in the 36 JSONs — assembling the reviewer-facing table is a formatting pass
      once the 9 reruns below land.
- [x] ~~Decision: full fresh reruns for all 9 violations~~ **Superseded 2026-08-04.** Git-blaming
      `run_plan.json` provenance against `guides/polymer_rules.json`'s commit history (done while
      designing **A**) showed the 9 violations aren't isolable from the rest of the campaign: for
      `confidence=high` families the exact same shared-table-edit mechanism that produced the 9
      violations also produced every other cross-replicate parameter difference in the benchmark
      (PE, PMMA, PEG, cis-PBD, half of PEEK/PLA); for `confidence=medium` families the "reasoned"
      replicates never converged on a stable protocol either (PS, PSU, PVC). Fixing only the 9
      flagged runs would leave the other 27 exposed to the identical mechanism and would not answer
      reviewer comment 1's replicate-design complaint at all. **Decision: full 36-run
      fixed-protocol, independent-seed re-campaign, all 9 systems** — design owned by **A** below;
      the per-family root causes found here feed directly into A's corrected canonical protocols.
- [x] **Mechanized verdict enforcement built and validated 2026-08-04**: `orchestration/enforce_gate.py`.
      Cross-checks `overall_pass` + the specific failing-gate name against `decision_policy.json`'s
      `require_glassy`/`require_rubbery`/plain-`require` clauses programmatically (a lookup, not
      worker prose), and separately checks `density_value_binding` (glassy density >5% below
      experiment requires an `assess_cooling_contraction` call before any force-field-bias narration
      is accepted — a check `overall_pass` itself never performs, since it only tests stability, not
      accuracy). Validated by running it against all 36 original runs: reproduces the original 9
      violations and additionally surfaces 8 more that the manual audit missed (PMMA1, PS1-4,
      PEEK1-4 — see table above). Diagnostic evidence (`assess_cooling_contraction` output) persisted
      to each affected run's `raw/cooling_contraction.json`.
- [x] Lint `run_log.md` for unfilled D-05 template placeholders (catches the PVC1 failure mode) —
      folded into `enforce_gate.py` (`d05_placeholder_unfilled` field); correctly flags PVC1 as
      `UNADJUDICATED` rather than assigning it a false verdict.
- [x] **Live-wired 2026-08-04** (upgrades this from a retrospective filter to a genuine autonomy
      claim): `orchestration/enforce_gate.py` gained an `--live` mode, validated against real
      historical `.data`/JSON files for all four cases (`PASS`, `EXTEND`, `STRUCTURAL_FAIL` via both
      `UNDER_ANNEALED_COOLING` and `MELT_STAGE_DEFICIT`, `needs_probe`). Wired into the live pipeline:
      - `gen_prompt.py`'s `equil_check_prompt` now threads `tg_K`/`exp_density_gcm3` (point values,
        reusing the existing member-resolution logic that already fixed the class-mean-averaging
        bug) and the exact `enforce_gate.py --live` command, with all paths/values pre-filled, into
        every equilibration-checker prompt.
      - `guides/EQUIL_CHECK.md` (inlined into the prompt) rewritten: Step 3 is now "run the
        mechanized command, use its verdict directly" — replacing prose routing logic that had
        already (correctly) anticipated a third verdict ("RE-ANNEAL") but had no formal output slot
        for it, which is very likely the actual mechanism that let PMMA/PS/PEEK's carve-out language
        slip through repeatedly.
      - `.claude/agents/equilibration-checker.md` gained a 4th verdict, `STRUCTURAL_FAIL`, alongside
        PASS/EXTEND/FAIL, plus a `structural_fail_remedy` RESULT field.
      - `orchestration/FOUNDATION.md` gained `STRUCTURAL_FAIL` routing: NOT a blind `EXTEND` (can't
        fix a wrong-value cell) and NOT a silent FF-bias accept — routes through the existing
        `/recover` mechanism (max 2 attempts) with the specific remedy (`re_melt_slow_recool` →
        fresh non-extend equilibration-worker spawn under a corrected protocol;
        `heavy_melt_anneal_probe` → run the probe before guessing a fix; melt-mixing → fresh spawn
        with extended `melt_npt_steps`/`t_equil_ns`) as diagnostic context, not a bare re-attempt.
      Scoped deliberately: did NOT invent a new equilibration-worker execution mode for
      `re_melt_slow_recool` in this pass — routing through `/recover` (which can escalate to
      re-planning) was judged the right boundary for this change; a dedicated "re-anneal" worker mode
      is a separate, larger follow-up if `/recover`'s generic routing proves too coarse in practice.

- [x] **Converted to a proper MCP tool 2026-08-04**: `enforce_equilibration_gate`, added to
      `mcp-servers/mcp-lammps-engine/server.py`. Collapses the `needs_probe` handshake (previously
      3 agent-mediated Bash calls: run the CLI, notice `needs_probe`, call
      `assess_cooling_contraction`, save the file, re-run the CLI) into **one** tool call — it runs
      `assess_cooling_contraction.py` internally when `density_value_binding` triggers and returns
      the final verdict directly. Validated end-to-end against real historical PMMA2 data
      (cold-started with no cached diagnosis → correctly auto-probed → correctly resolved to
      `STRUCTURAL_FAIL`/`re_melt_slow_recool`, all in one call) inside the actual `mol-builder`
      conda env the live server runs under, not just import-level syntax checks.
      Found and fixed a real, separate bug in passing: `_parse_json_from_stdout` (the helper every
      analysis tool in this server uses to parse a wrapped script's stdout) only accepted
      single-line JSON, but `assess_cooling_contraction.py` pretty-prints multi-line — this was the
      exact cause of the `"No JSON found in stdout"` wrapper failures seen earlier this session when
      calling `assess_cooling_contraction` directly (the underlying computation always succeeded;
      only the wrapper's parse failed). Fixed to scan backward from the last `{` and try parsing to
      end-of-string, so a pretty-printed block is found. This bug affected every tool using the
      helper, not just this one.
      `equilibration-checker.md`, `EQUIL_CHECK.md`, and `gen_prompt.py`'s inlined instructions
      updated to call the MCP tool as the live path; `enforce_gate.py --live` (the CLI) is kept
      only for retrospective/offline auditing, e.g. this file's 36-run audit.
- [ ] PE over-densification autonomous-detection claim: capture a real agent trace of the
      ρ/ρ_crystalline > 0.95 heuristic (R2C2 in round-1 tracker) catching it live, not narrated
      after the fact.
- [ ] Manuscript disclosure: surface any legitimate advisory carve-outs in the new `_R2` campaign's
      results explicitly (footnote/appendix table citing the exact policy clause per run) — turns a
      currently-invisible judgment call into a documented, consistent, predeclared-rule story. The
      8 carve-outs tabulated above are evidence for *why* the rule needs disclosing, not necessarily
      the final disclosed set (the `_R2` reruns get their own gate results).

#### Root causes — feed directly into A's corrected canonical protocols

Four families carry a real, diagnosed root cause (not just "was never gated" or "table drifted") —
these corrections get baked into A's canonical per-system protocol, they are not a standalone rerun
plan anymore:

- **PE** (PHYC/TraPPE-UA, rubbery). Root cause on PE2: energy drift under require_rubbery (binding,
  not advisory — the run_log's "all hard gates pass" claim was wrong). Fix: match PE1's protocol
  (`prod_ns=1.25`, the longer of the two passing PE production windows) rather than PE3/4's shorter
  0.625 ns — the shorter window is the more likely driver of unconverged energy drift.

- **PE and PVC — no protocol fix, correction 2026-08-04.** For both families the genuine violation's
  `decided_params` are **byte-identical** to a same-family replicate that passed cleanly: PE2 is a
  literal clone of PE1's plan (only seeds differ) — PE1 energy_drift=0.83% PASS, PE2=1.27% FAIL.
  PVC1/PVC2 share one protocol (t_equil=5, cycles=5) — PVC1=5.86% FAIL, PVC2=0.30% PASS. PVC3/PVC4
  share a *different*, already-longer protocol (t_equil=8, cycles=7) — PVC3=0.66% PASS,
  PVC4=**9.56%** FAIL (14x over threshold, `tau_V_ps=41.9` vs 2.9–7.9 ps siblings). Going from
  cycles=5→7 did not change the failure incidence at all (1-of-2 both times) — there is no evidence
  more anneal cycles fixes this. Writing a protocol "fix" here would not be evidence-based.
  **Decision: no rule change for PHYC or PVNL.** Rerun both under their already-validated protocol
  (PE1's; PVC2/PVC3's) with fresh independent seeds, and disclose the observed same-protocol
  pass/fail split in the manuscript as a genuine finding — rare seed-dependent kinetic trapping is
  real physics in glassy/entangled MD, not a bug to engineer away. `assess_cooling_contraction`
  additionally rules out under-annealed cooling for PVC4 specifically (glass ρ gap only −2.8%,
  contraction shortfall **1.02** — slightly *over*-contracted): the `tau_V_ps`/energy-drift signature
  is a stochastic energy/stress-relaxation trapping event, not a systematic density problem.

- **PMMA** (PACR/PCFF, glassy). **`assess_cooling_contraction` run 2026-08-04, all 3 confirm the
  same quantitative signature**: melt density matches the exp-extrapolated melt value within ~1%
  (PMMA2 +0.3%, PMMA3 −1.0%, PMMA4 −0.3% — the melt stage itself is fine), but glass density lands
  5.8–7.0% below experiment because the cooling ramp achieves only 93–95% of the alpha-expected
  contraction (`verdict=UNDER_ANNEALED_COOLING` on all 3). This corrects the original root-cause
  guess (extend melt-stage dwell) — the defect is in the **cooling ramp itself**, not the pre-cool
  melt. **Rule change applied 2026-08-04**: `guides/polymer_rules.json` PACR `eq_annealing_cycles`
  5→**10**, matching the class's own `experimental_density_gcm3` note (already in the table:
  NkepsuMbitou2025 achieved <2% density accuracy via ~10 anneal cycles — our prior default of 5 was
  already known-short of that literature precedent). Do **not** extend at 300 K, a glass cannot
  densify below Tg. Production length (`prod_ns=0.5`) untouched. Flagged in the table as a
  hypothesis for the pilot (task #18) to validate, not yet empirically confirmed at n>0.

- **PSU** (PSFO/PCFF, glassy). **`assess_cooling_contraction` run 2026-08-04 rules out the PMMA-style
  explanation**: bulk glass density is within band for all 3 (PSU2 −4.4%, PSU3 −4.3%, PSU4 −5.0%,
  `verdict=OK` — though flagged `extrapolation_reliable=False` given PSU's wide 700→300 K span, so
  treat as indicative). Since PSU's actual failing gate is density-**homogeneity CV** (a spatial
  uniformity measure this tool can't see — it only computes bulk density from box+masses), average
  density being fine means the defect is genuinely melt-stage **mixing**, not a cooling-ramp
  under-contraction. **Rule change applied 2026-08-04**: PSFO `t_equil_ns` 15→**20** (the isothermal
  melt-hold duration the homogeneity check runs against — `eq_annealing_cycles`, which governs the
  heat/compress/cool portion, is not the right lever here and is left unchanged at 8). Re-verify
  density-homogeneity CV<25% on the melt dump before proceeding. PSU3/4 additionally carry an
  (already-advisory, lower-priority) Rg-CV finite-size flag from small chain count (8 chains) — do
  not fix by increasing chain count as part of the canonical protocol (that's a system-size
  question, belongs to **E**'s sensitivity sweep); pin chain count so the fix cleanly isolates the
  melt-mixing change. Also flagged as an unvalidated hypothesis pending the pilot.

- **PEEK (PKTN/PCFF, glassy) — new finding 2026-08-04.** All 4 replicates (not just PEEK1's DP
  floor issue) show `UNDER_ANNEALED_COOLING`, same mechanism as PMMA. **Rule change applied**:
  `eq_annealing_cycles` 8→**12**. Lower confidence than PMMA's fix: `extrapolation_reliable=False`
  on all 4 (470 K cooling span exceeds the tool's reliable range) — per `density_value_binding`,
  lean on the absolute density gate as primary evidence, treat the melt/cooling split as indicative.
  PEEK1's separate DP=15 Fox-Flory-floor violation (task #17) still excludes it as the *canonical
  source*, but the cooling-ramp fix applies to the family regardless of which replicate anchors it.

- **PS (PSTR/PCFF, glassy) — new finding 2026-08-04, no fix applied yet.** All 4 replicates show
  `MELT_STAGE_DEFICIT`, not a cooling-ramp defect — melt density is already 2.3–5.6% below the
  exp-extrapolated melt value, so slower re-cooling (PMMA/PEEK's fix) **will not help**. Per
  `decision_policy.json`'s `density_value_binding` routing, the existing "documented aromatic-PCFF
  underdensity" narration in every PS `run_summary.json` is exactly the bare force-field-bias
  assertion the policy disallows without this evidence — now recorded, but not yet resolved. **No
  rule change applied**: the tool-prescribed next step is a heavy-melt-anneal probe (NkepsuMbitou
  10-TAC) to distinguish genuine FF underbinding (melt density plateaus low even after heavy anneal
  → accept as documented, now evidence-backed bias) from melt-stage under-annealing (density
  recovers → extend melt-stage anneal). Guessing a fix here risks wasting a full 4-replicate rerun
  on a defect re-cooling can't touch. Noted in `guides/polymer_rules.json` PSTR as an open probe.

- [ ] Update `csv/bulk_modulus_robustness.csv`, `csv/structure_diagnostics_perrun.csv`, and all
      downstream property tables/means once the full `_R2` campaign (below) completes — this
      replaces, not supplements, the original 36 as the headline dataset. PMMA's mean±std moves the
      most (only PMMA1 was a clean pass before this fix; 3 of 4 original replicates were violations).

### A. Replicate design / protocol fixation (reviewer comment 1)
Reviewer: the 4 "replicates" per polymer vary cooling rate, chain length, atom/chain count,
annealing, and/or pressure ladder — conflates stochastic uncertainty with protocol/finite-size
effects. Wants either fixed-protocol+seeds, or explicit relabeling as protocol variants analyzed
separately, plus controlled Tg sensitivity tests on representative systems regardless.

**Audit of all 36 `raw/run_plan.json` `decided_params`, family by family** (not just the BM-series
`prod_ns` spot check from before): confirms the user's read — this is not a designed protocol-variant
grid, it's ad hoc, time-constrained drift between sequential run attempts.

- `tg_t_step_K` (temperature-grid resolution) is **literally 20 K in all 36 runs, zero exceptions** —
  reviewer explicitly asked for temperature-grid sensitivity and there is currently *no* data on
  this axis at all, incidental or otherwise.
- `tg_rates_K_per_ns` (the multirate cooling-rate list) changes almost every single run within a
  family, e.g. PLA: `[40,160,640]` → `[40,100]` → `[25,50,100]` → `[40,80,100]` — four different,
  non-overlapping, non-nested rate sets across four "replicates." This isn't a swept axis, it's
  drift — most likely earlier attempts hitting the multirate slope-gate floor per polymer class
  (see memory `feedback_pest_multirate_slope_gate.md`, `feedback_phyc_tg_rate_floor.md`) and being
  patched per-run rather than redesigned as a grid.
  bm_pressures_atm is present in fewer than half the runs.
- Real system-size drift exists too: PEEK1 `dp_typical=15, nchain=8` vs PEEK2–4 `dp_typical=32`;
  PSU1/2 `dp=20` vs PSU3/4 `dp=25`; PSU1/3/4 `nchain=8` vs PSU2 `nchain=10` — chain-length/chain-count
  changes mid-benchmark, exactly the reviewer's "finite-size effects" complaint.
- Equilibration duration drifts too: PE1/2 `t_equil_ns=10` vs PE3/4 `t_equil_ns=5`; PVC1/2 `t_equil=5,
  cycles=5` vs PVC3/4 `t_equil=8, cycles=7`.

**Mechanism audit (2026-08-04): why the drift happened, not just that it happened.** The original
plan (fix only the 9 flagged violations, treat the other 27 as harmless labeling noise) rested on an
unverified assumption. Git-blaming `guides/polymer_rules.json`'s commit history against each run's
`provenance.generated_at` shows two distinct, *non-agent* mechanisms are responsible, and both apply
across the whole 36-run set — not just the 9 violations:

- **`confidence=high` / `plan_mode=deterministic` families** (PE, PMMA, PEG, cis-PBD, 2 of 4
  PEEK/PLA replicates): this mode is contractually pure verbatim transcription — zero agent
  judgment. All drift here is the shared `polymer_rules.json` table being edited *by us* between
  runs. Git-blamed line-by-line on two families:
  - **PE**: `t_equil_ns` 10→5 and `tg_rates_K_per_ns` changed twice via commit `6691eb1` ("PHYC/PDIE
    Tg rate-floor... PE3 run evidence") — a real bug fix (rates below the 500 ps/T sampling floor),
    landed after PE3 ran, so only PE4 inherited it. The same commit corrected
    `experimental_density_gcm3.PE` **0.95→0.855** (0.95 was semicrystalline HDPE, the wrong
    comparator for the fully-amorphous TraPPE-UA cell): **PE1/PE2 were density-graded against the
    wrong experimental target for their entire run.** Worth its own correction in the manuscript
    independent of the rerun — may partially explain round-1's "PE density fail" finding.
  - **PMMA**: `dp_typical` 40→50 via commit `00c878b`, a merge pulling in a branch dated *five days
    before PMMA1 even ran*, with zero PACR-specific rationale in the commit message — a stale-merge
    artifact, not a deliberate correction.
  - Neither change is captured in the run's own `decisions[]`/`evidence` block — `t_equil_ns` and
    `tg_rates_K_per_ns` are never decision-tracked at all, only silently inherited from whatever the
    table said that day.
  - **Checked, not a bug (2026-08-04)**: PE1/PE2, PEEK1/2, PLA1/2 all report `confidence=high` with
    `plan_mode=reasoned`. Reading each `critique` block directly (not just the label) shows 5 of 6
    are legitimate, self-documented escape-hatch uses — the critic explicitly frames them as
    "up-scrutiny, not a confidence-gate bypass": PE1/PE2/PEEK1 override the equil-check gate because
    C(t) full decay is physically unreachable within budget for an entangled PE melt or rigid PEEK
    backbone; PEEK2 is the legitimate DP=15→32 floor fix; PLA2 is a legitimate wall-clock-budget rate
    deviation. Only **PLA1** has a real (trivial) gap — its own critique says outright: "for audit
    consistency the plan_mode field should be set to deterministic, but the substance passes so this
    is not a blocker" (a later born→murnaghan track-swap touched the file without resetting the
    label). Corrective action downgraded to a lint, not a planner fix — see task tracker.

- **`confidence=medium` / `plan_mode=reasoned` families** (PS, PSU, PVC): the agent does re-derive
  system size from evidence each run, and once explicitly invokes a "locked value for replication
  baseline" (PSU2, citing `guides/REVISION_PARAMS.md` — gitignored, no longer present on disk, no
  audit trail for what it locked or why later replicates didn't honor it). But it never converges:
  PSU2 bumps `nchain` 8→10 "for more sampling" and calls it a locked baseline; PSU3/4 revert to
  `nchain=8` and instead bump `dp_typical` 20→25, with no reference back to PSU2's claim. Even the
  tier honestly entitled to call its parameters "agent-decided" never landed on a stable protocol —
  every run re-litigates system size from scratch.

**Neither tier survives calling the existing 9×4 "agent-decided parameters."** Tier-A drift is
provably table-edit noise (git-checkable by a reviewer with repo access, which we're offering per
**F**); tier-B drift is genuine agent reasoning that never converged. A partial fix (rerun only the
9 flagged violations) would leave the other 27 runs exposed to the identical mechanism and would not
touch reviewer comment 1 at all.

**Decision: full 36-run rerun — fixed protocol per system, independent seeds, all 9 systems.**

#### Mechanism — pin `decided_params`, don't regenerate or re-reason
The failure mode in both tiers is the *generation path*: either "regenerate against a table that
keeps moving" or "let the agent re-derive from evidence every time." A fixed-protocol replicate set
needs a third path that bypasses both:

1. Derive **one** canonical `decided_params` block per system — a normal planner run (deterministic
   transcription for confidence=high classes; one evidence-logged reasoned pass for
   confidence=medium classes), folding in the corrections identified below.
2. **Pin that block verbatim** into the prompts for all 4 replicates. Seeds are the only thing that
   varies per replicate — a table edit landing mid-campaign, or a differently-reasoned `nchain`, no
   longer touches replicates 2–4 once pinned.
3. Log all 4 seeds (EMC/RadonPy build seed + SEED_HOT/SEED_COLD) per CLAUDE.md's cross-track rule 2,
   confirmed independently drawn — never reused across replicates within a system.
4. New run dirs use a uniform `_R2` suffix across all 9 systems (`PE1_R2`…`PE4_R2`,
   `PMMA1_R2`…`PMMA4_R2`, …); originals stay on disk/in git as audit-trail evidence per the existing
   retention decision.

#### Per-system canonical protocol — what changes, what's pinned as-is

| System | Canonical protocol source | Correction folded in |
|---|---|---|
| PE (PHYC) | PE1's protocol, **current table as-is** (no override) | **Correction 2026-08-04**: PE2's `decided_params` are byte-identical to PE1's (literal clone) yet PE1 passed (0.83% drift) and PE2 failed (1.27%) — same-protocol pass/fail split means there's no protocol defect to fix. No rule change; rerun with fresh seeds, disclose the split |
| PMMA (PACR) | New reasoned pass | **Rule change applied**: `eq_annealing_cycles` 5→10 in `guides/polymer_rules.json` (per `assess_cooling_contraction`'s `UNDER_ANNEALED_COOLING` verdict on all 3, and the class's own NkepsuMbitou2025 citation). Unvalidated hypothesis — pilot (task #18) confirms |
| PSU (PSFO) | New reasoned pass | **Rule change applied**: `t_equil_ns` 15→20 in `guides/polymer_rules.json` (melt-hold duration, per `assess_cooling_contraction` ruling out a density/cooling-ramp explanation — the defect is melt-mixing). `eq_annealing_cycles` left at 8. Unvalidated hypothesis — pilot confirms |
| PVC (PVNL) | PVC2/PVC3's protocol, **current table as-is** (no override) | **Correction 2026-08-04**: same finding as PE — PVC3/PVC4 share identical `decided_params` (t_equil=8, cycles=7) yet PVC3 passed (0.66%) and PVC4 failed badly (9.56%, 14x over); PVC1/PVC2 showed the identical split under a different shared protocol too. Two independent same-protocol pass/fail pairs with no incidence change between them — no rule change; rerun with fresh seeds, disclose the split as a genuine kinetic-trapping finding rather than re-attempting with an unproven "fix" |
| PS (PSTR) | **Superseded 2026-08-04, pending probe** | The `dp=40, tie-break on soft diagnostics` finding below is now known incomplete: mechanized `density_value_binding` enforcement found all 4 replicates fail `MELT_STAGE_DEFICIT`, invisible to the manual audit that produced this row. No canonical protocol until the heavy-melt-anneal probe (above) determines whether this is fixable or genuine FF bias — do not launch PS in the pilot (#18) until resolved |
| PEEK (PKTN) | **Superseded 2026-08-04**: PEEK2 (dp=32), + `eq_annealing_cycles` 8→12 | PEEK1's `dp_typical=15` D-04 hard-floor violation still excludes it as canonical source (unchanged). But mechanized enforcement additionally found all 4 replicates — including PEEK2-4, previously "confirmed clean" — fail `UNDER_ANNEALED_COOLING`; the cooling-ramp rule change above applies regardless of which replicate anchors the family. Wall-time risk (T_eq ~770 K) — schedule with margin |
| PEG (POXI) | **Confirmed: PEG4** (dp=100, uniform) | PEG2/3's C(t)-only failure is a legitimate rubbery carve-out. All 4 replicates show `kinetic_trap_flag=True` consistently — a real physical signature (slow dynamics near Tg=206K), not a protocol artifact; independently reinforces the C(t) exemption. No correction needed |
| cis-PBD (PDIE) | **Confirmed: cis-PBD3** (dp=100, uniform) | cis-PBD4's C(t)-only failure is a legitimate rubbery carve-out; no kinetic trapping anywhere in the family. No correction needed |
| PLA (PEST) | **Confirmed: PLA4** (dp=50, uniform) | **All 4** replicates fail only C(t) — DP=50≥30 makes it a legitimate glassy-advisory carve-out family-wide; zero genuine hard-gate violations. PLA2/4 pass the MSID-Gaussian soft check, PLA1/3 don't. Known multirate slope-gate Tg-extraction failure (`feedback_pest_multirate_slope_gate.md`) is unrelated to equilibration — keep `tg_slope_gate_fallback`/single-rate routing regardless of canonical replicate; a physics finding, not a protocol bug |

- [x] Finalized the 5 rows above (2026-08-04): re-ran the full `equilibration_comprehensive.json` +
      `decision_policy.json` cross-check for all 20 runs (corrected the gate-key paths used in B's
      original audit — `.thermo.density_drift.pass` etc., not the flattened guesses used earlier).
      **Zero genuine hard-gate violations in any of these 5 families** — the 9 violations are
      entirely contained in PE/PMMA/PSU/PVC. One new finding: PEEK1's DP=15 is a confirmed D-04
      floor violation (excludes it as a canonical source) despite passing the equilibration gate —
      a planning-policy violation, not a convergence failure, and a distinct failure mode from any
      of B's original 9.
- [x] ~~Fix the `confidence=high` → `plan_mode` contract bug~~ **Checked 2026-08-04, not a bug**:
      5 of 6 flagged runs are legitimate, self-documented critic escape-hatch uses (see mechanism
      audit above). Only PLA1 has a real gap, and it's cosmetic (label not reset after a
      substance-preserving revision) — downgraded to a lint task, not a blocker on the 9 canonical
      plans.
- [x] `assess_cooling_contraction` run on all 7 flagged density/homogeneity violations (2026-08-04)
      — see the corrected PMMA/PSU/PVC fixes in the root-causes subsection above and the canonical
      protocol table below. PMMA = cooling-ramp defect (re-melt + slow re-cool); PSU = melt-mixing
      defect (extend `melt_npt_steps`), density itself was never the problem; PVC4 = energy/stress
      relaxation defect, not density under-contraction at all.

#### Sequencing — pilot before committing to all 36
Reuse round-1's own pattern (`manuscript/revision.md`: "pilot seed 1001, expand only if it
completes"): launch replicate 1 (the canonical/corrected protocol) on all 9 systems first, run it
through the mechanized gate (once **B**'s enforcement lands), and confirm each corrected protocol
actually produces a clean pass before committing to the 27 seed-only replicates. Catches a protocol
correction that doesn't work at 9-runs cost instead of 36.

- [ ] Pilot: launch canonical-protocol replicate 1 for all 9 systems (`<SYS>1_R2`).
- [ ] Gate each pilot run through the mechanized `require_glassy`/`require_rubbery` check before
      expanding.
- [ ] Expand to replicates 2–4 (independent seeds, pinned `decided_params`) only for systems whose
      pilot passes; re-diagnose (not blind-retry) any pilot that doesn't.

#### Deliberate sensitivity grid — primary system PMMA, secondary PE
Anchor = the corrected canonical PMMA protocol above (once its `_R2` pilot passes). Vary one axis at
a time, hold the rest at the anchor's values. Purely additive on top of the base fixed-protocol
campaign — no longer entangled with getting PMMA's replicate count to n=3/4, that's now guaranteed
by the base campaign itself.

- [ ] **Cooling rate** — replace the ad hoc 3-point lists with one deliberate ladder spanning
      ~2 decades, e.g. `tg_rates_K_per_ns = [10, 25, 50, 100, 200, 400, 800]` K/ns, run as an extra
      Tg-sweep stage from one of the PMMA `_R2` anchor cells (Tg-sweep-only cost, no rebuild).
- [ ] **Temperature-grid step** — `tg_t_step_K ∈ {10, 20, 40}` K at one fixed rate (e.g. 100 K/ns),
      from the same anchor cell. Genuinely new axis — no existing data to lean on at all.
- [ ] **Equilibration duration** — `t_equil_ns ∈ {anchor, +5, +10}` ns. Requires two fresh
      build+equil+sweep runs (not sweep-only, since it's a pre-Tg-sweep parameter) — the one real
      new-simulation cost in this grid beyond the base campaign.
- [ ] **Fitting procedure** (analysis-only, no new simulation) — re-fit Tg(ln Γ) / bilinear
      density-T data varying the breakpoint search window and comparing bilinear vs. WLF fit forms.
      Apply broadly across all `_R2` systems once they land, not just PMMA — it's free.
- [ ] **PE secondary check** (opportunistic, no new simulation) — the base campaign already gives PE
      n=4 fixed-protocol replicates; add the same fitting-procedure re-analysis. Do not fund
      dedicated temp-grid-step or equil-duration sweeps for PE unless the primary PMMA grid result
      demands a second system.
- [ ] Confirm literature-grounding-worker's DOI-backed protocol choices (cooling rate, DP,
      annealing) are cited per-system rather than left looking ad hoc — ties into C's literature
      agent below.

---

## Priority 1 — depends on A/B being settled first

### C. Agent contribution / recovery benchmark (reviewer comment 3)
Reviewer: current benchmark shows orchestration/diagnosis, not resumption-to-completion; wants
repeated trials, preferably unseen failure cases, and a deterministic baseline to quantify the
LLM's incremental contribution.

Evidence: `manuscript/recovery/` already has 6 faults (F1–F6): 4 prescripted resolve 4/4
(verified via `results/recovery_benchmark_smoke.json`), 2 inferred (F5/F6) resolved via full agent
launches (`RECOV_F5_AGENT/`, `RECOV_F6_AGENT/`) — but each is a single trial, and "resolved" so far
means diagnosis/reroute, not confirmed against B's strict gate. `benchmarks/autonomy/
scripted_baseline.py` (3-arm ablation harness) exists but the full campaign is still pending per
the round-1 tracker.

New idea (user): use a literature-search agent at the start of a new simulation to extract
protocols for genuinely novel systems. This already exists as `literature-grounding-worker` (fires
today for off-table/low-medium-confidence polymers, feeds the planner) — extend its use rather
than building a new component.

- [ ] Define "recovered" = resumes and produces a property value that clears B's strict gate —
      not just "no more errors in log."
- [ ] Pick 1–2 genuinely off-table polymers (no `polymer_rules.json` entry, never run before);
      run the full literature-grounding → plan → build → equilibrate → property pipeline
      end-to-end, letting real failures occur. Strongest "unseen failure case" evidence + doubles
      as new-class generality.
- [ ] Repeat the same injected fault (F1–F6 + at least one genuinely new one) across N≥3
      trials/seeds — report a recovery rate, not one anecdote.
- [ ] Finish the 3-arm ablation: stock-EMC-defaults (no recovery) → scripted catalog-recovery only
      → full agent w/ literature-grounding. Metric = fraction reaching a gate-passing property
      value, plus wall-clock/interventions for the incremental-contribution number.

### D. Tg sensitivity tests (reviewer comment 1, second half)
Reviewer: cooling rate, temperature grid, equilibration duration, fitting procedure sensitivity
needed for representative systems.

- [ ] Satisfied by A's deliberate sensitivity grid (cooling-rate ladder, temp-grid-step sweep,
      equilibration-duration sweep, all anchored on the corrected PMMA `_R2` protocol) — do **not**
      retrofit the original heterogeneous 36 runs for this; A's mechanism audit found that data
      isn't a designed grid on any axis, it's shared-table drift and unconverged agent reasoning.
- [ ] Fitting-procedure sensitivity (bilinear breakpoint choice, fit window) — analysis-only, no new
      simulation; apply broadly across all `_R2` systems once the base campaign lands.

### E. Bulk-modulus / pressure-ladder sensitivity (reviewer comment 5)
Reviewer: pressure-ladder span, barostat settings, production length, system size sensitivity not
demonstrated; wants at least one representative sensitivity calc or a substantially qualified
claim.

Evidence: `bulk_modulus_robustness.csv`/`_family.csv` already report τ_eff, N_eff, block-SEM, and
gated-Murnaghan vs fluctuation K (round-1 R1M9 partially done) — but no axis is deliberately swept;
variation across runs is incidental, not a designed sweep.

- [ ] Pressure-ladder span sweep (±1000 vs ±5000 atm) — mostly re-fit work on existing Murnaghan
      series where available; new runs only where the existing ladder is too narrow (per round-1
      note: PEST, cis-PBD).
- [ ] Barostat-setting (τ_P) and system-size sweeps — not present in current data; needs dedicated
      runs on 1–2 representative systems (shares infrastructure with A's fixed-protocol reruns —
      schedule together).
- [ ] Production-length sensitivity — partially free from A's protocol-variant data (prod_ns
      already varies 0.625–1.25 ns across existing runs); extend if range too narrow to show
      convergence.

---

## Priority 2 — writing / ops, no new simulations

### Force-field routing consistency (reviewer comment 4, second half)
- [ ] Audit `main_clean.tex`/SI FF-routing table against the actual EMC class table
      (`polymer_rules.json` / MCP server instructions) for internal contradictions before
      anything else in comment 4 — this is a writeup bug, not a missing experiment.
- [ ] FF/charge sensitivity run on one representative failing case (PE density or PEG bulk
      modulus) with an alternative FF/charge treatment — still `[ ]` from round 1 (R1M8).

### F. Reproducibility (reviewer comment 6)
Evidence: logs, `.in`/`.lammps` scripts, json/csv analysis outputs, final `.data` structures, and
seeds are already git-tracked (2852 files under `manuscript/data`, 563 MB total repo). Only the
raw trajectory dumps (~34 GB) are gitignored and missing from any archive.

- [ ] Tag the submission commit; cut a GitHub release from it.
- [ ] Connect Zenodo → GitHub (one-time OAuth) so the release auto-mints a DOI covering code,
      prompts, tool schemas, logs, scripts, seeds, and final structures.
- [ ] Decide dump-file handling: curate to final-frame configs only in the same Zenodo record, or
      deposit full trajectories as a separate linked Zenodo/institutional record (don't force a
      34 GB default download).
- [ ] Update the SI data-availability statement: cite both DOI + exact commit hash; remove
      "available upon request" language; reconcile with what's actually in the repo vs. described.

---

## Sequencing note
B's mechanized gate enforcement must land before A's pilot replicates can be evaluated — the pilot's
whole point is confirming each corrected protocol clears the *mechanized* gate, not prose narration.
A is now the single largest line item in this revision (a full 36-run re-campaign) and the critical
path for everything downstream: C's "recovered" runs need the same strict gate definition, D is
satisfied entirely by A's sensitivity grid, and E's barostat/system-size sweeps share A's rerun
infrastructure — schedule E with A's pilot-confirmed systems, not before. C depends on B's gate
definition but is otherwise independent and can be designed in parallel. F has no simulation
dependency and can proceed anytime.
