# Spec — B.4: run_log Mining → Learning Loop

**Status:** Draft for review · **Parent:** `docs/LLM_CONTRIBUTION_PLAN.md` (Part B, lever B.4, P0)
· **Date:** 2026-06-14

> **One-line purpose:** mine the corpus of `data/*/run_log.md` so the LLM's past judgment
> *compounds* — every completed run improves the defaults and the recovery playbook the next run
> starts from, instead of that judgment evaporating per session.

This is the single biggest force-multiplier in Part B because it is the only lever that makes the
system get **better over time** rather than merely **consistent**. It is also low-risk: the miner
is **read-only** and **never auto-edits** the pipeline — it emits *reviewed suggestions*.

---

## 1. Inputs — exact parse targets

The miner reads every `data/*/run_log.md` (the template is `data/TEMPLATE/run_log.md`, which it
**skips**). Each log is semi-structured markdown; parse targets, by section:

| Section | Fields extracted | Parse note |
|---|---|---|
| **Title (L1) + header (L2–3)** | polymer_name, SMILES, FF, charge_method, DP, n_chains, seeds | fixed-position regex |
| **DECISIONS** | `D-01` FF, `D-02` charges, `D-03` electrostatics+cutoff, `D-04` DP/chains/atoms, `D-05` PASS/EXTEND×N/ESCALATE, `D-06` fit tier + R²/F-stat/N-bins | row regex `\| D-0(\d)[^|]*\|([^|]*)\|([^|]*)\|`; **polymer_class** parsed from D-01 rationale (`returned <CLASS>` / `class \w+ \((\w+)\)`) |
| **RECOVERIES** | per-incident: `[Stage N]` trigger line, `Diagnosis:`, `Fix:`, `Outcome:` | block split on `^\[Stage`; `None` ⇒ clean run; tolerant line-key regex |
| **RESULTS** | Tg / ρ / K: computed, experimental, error %, status (✓ / ⚠); cooling_rate; expected-offset | table-row regex; experimental may be blank ⇒ "no anchor" |
| **TIMING** | per-stage wall time, throughput (ns/day), total | optional; feeds the "human-minutes saved" estimate |

**Robustness rule:** logs are LLM-authored free-ish text → parsing is **tolerant** (skip and record
unparseable sections, never crash). A `--strict` mode is used only in CI against synthetic fixtures.

---

## 2. Outputs — three reviewed artifacts (never auto-applied)

### 2.1 `polymer_rules_suggestions.json` + a unified diff
Per-class proposed **default deltas**, each with evidence and a confidence count. Emission is
**gated by agreement** (≥ N independent runs, default N=2) so one anomalous run can't move a default.

```json
{
  "PCBN": {
    "density_initial_gcm3": {
      "current": 0.60, "suggested": 0.55,
      "evidence": "2/3 runs recovered (F1) by lowering density_initial; converged median = 0.55",
      "support_runs": ["PC1", "PC4"], "rule": "density-recovery-consensus"
    }
  }
}
```

**Aggregation rules (concrete):**

| Target default | Trigger signature | Suggested value |
|---|---|---|
| `density_initial_gcm3` | ≥N RECOVERIES whose Diagnosis cites density + Fix lowers `density_initial` + Outcome=converged | median of converged values |
| `tg_t_high_K` | ≥N runs EXTEND/recover by raising the sweep ceiling (Stage-3 "below MD Tg" diagnosis) | median successful ceiling |
| `nchain` / `dp_typical` | ≥N D-04 rationales flag finite-size / "longer DP needed" | flag for review (no auto-number — size is expensive) |
| `eq_annealing_cycles` | ≥N recoveries add annealing cycles to converge | median successful cycle count |

**Safety:** output is a **diff against `guides/polymer_rules.json`**, applied only after human/agent
approval, and **must pass `tests/test_polymer_rules_schema.py`** (the existing 195-test gate) before
commit. The miner never writes the rules file itself.

### 2.2 `RECOVERY_PLAYBOOK.md` entries (feeds lever B.1)
Cluster RECOVERIES by failure signature → emit a playbook row: *signature → diagnosis → fix →
observed success rate (k/n)*. This is how scattered, one-off recoveries become institutional memory
the orchestrator consults **before** improvising.

```
| Signature | Diagnosis | Fix | Success |
|---|---|---|---|
| Stage 2 EXTEND×2, density drift >2% | density_initial too near RT density → over-densified trap | lower density_initial ~0.05, +1 anneal cycle | 3/3 |
| Stage 3 "<4 temperature bins" | sweep ceiling below MD Tg, glassy slope missing | raise tg_t_high_K to ~2×Tg | 4/4 |
```

### 2.3 `confidence_calibration.md` (feeds lever B.2)
Aggregate RESULTS error% per class and compare to the class's stated `confidence` label. **Flag
miscalibration:** e.g. a `confidence: "high"` class whose mean Tg error exceeds a threshold, or a
`"medium"` class consistently within bounds (could be promoted). This is the data-driven check on
the confidence labels Part B.2 propagates to RESULTS — closing the loop between *claimed* and
*observed* reliability.

---

## 3. Module layout

```
tools/runlog_miner/
  parse.py        # run_log.md → structured RunRecord dataclass (tolerant)
  aggregate.py    # corpus of RunRecords → suggestions / clusters / calibration
  emit.py         # → suggestions.json + diff, playbook md, calibration md
  cli.py          # `python -m tools.runlog_miner [--data-dir data] [--min-support 2] [--strict]`
  tests/
    fixtures/     # synthetic run_logs (see §4)
    test_parse.py
    test_aggregate.py
```

`RunRecord` schema (the parse contract): `run_name, polymer_class, ff, dp, nchain, n_atoms,
decisions{D01..D06}, recoveries[{stage, trigger, diagnosis, fix, outcome}], results{tg, rho, k,
cooling_rate}, timing{...}`.

---

## 4. Test plan (golden fixtures)

Hand-craft 4 synthetic `run_log.md` fixtures and assert exact miner output:

1. **Clean PCBN run** (RECOVERIES = None) → contributes to calibration only, no suggestions.
2. **PCBN density-recovery** (F1 signature) → after a 2nd matching fixture, triggers the
   `density_initial` suggestion.
3. **Sweep-window recovery** (F2 signature) → triggers `tg_t_high_K` suggestion + playbook row.
4. **High-error "high confidence" class** → triggers a calibration flag.

CI runs the miner in `--strict` over fixtures; it must never crash on the real (messier) corpus.

---

## 5. Phasing

- **P0a — read-only report:** parse + a summary table of all runs (no suggestions). Immediately
  useful, zero risk; validates parsing against the real corpus.
- **P0b — suggestion engine:** aggregation rules + `suggestions.json` + diff (still human-applied).
- **P0c — calibration + playbook:** emit the B.1 and B.2 feeder artifacts.

## 6. Dependencies & interactions

- **Enables B.1** (playbook is an output here) and **B.2** (calibration report).
- **Assumes B.2's structured RECOVERIES schema** eventually lands — until then, tolerant text
  parsing of the current free-form blocks is sufficient (and is the fallback even after).
- **Guarded by** the existing schema test suite for any applied rule change.

## 7. Open questions

1. Minimum support N — 2 (responsive) vs 3 (conservative) before a default is suggested?
2. Should P0a ship first as a standalone "corpus dashboard" to prove parsing before any
   suggestion logic is written?
3. Apply-path: emit diff only, or also offer an `--apply` that opens a branch + runs the schema
   tests automatically (still requiring review)?
