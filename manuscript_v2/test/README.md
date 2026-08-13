# manuscript_v2 tests

Reviewer-driven tests for revision round 2. Designed in `../test_plan.md`; this tree holds the
executable analyses and their outputs.

Currently implemented: **test 1, force-field sensitivity** (`ff_sensitivity/`). Tests 2–4 are
designed but not built.

## Test 1 — free leg

Run in order; `a1` is the gating step.

```
bash ff_sensitivity/run_free_leg.sh
```

| step | question | output |
|---|---|---|
| `a0_extend_decomposition.py` | Is the density deficit in the melt or in the cooling? | `results/a0_decomposition.*` |
| `a1_experimental_melt_reference.py` | Same question, graded against experimental ρ(T) instead of assumed expansivities | `results/a1_experimental_melt.*` |
| `a2_protocol_audit.py` | Which protocol axes vary *within* each replicate set? | `results/a2_protocol_audit.*` |
| `a3_plan_vs_deck_audit.py` | Does each recorded parameter reach the deck that ran? | `results/a3_plan_vs_deck.*` |

None of these runs a simulation. They read archived `.data` and `.in` files and
`db/polymer_db.sqlite`, and write only into `results/`.

### What the free leg found

- **The deficit is in the cooling stage, not PCFF's parameters.** PMMA reproduces experimental melt
  density (+1.0 to +2.5%) while its glass is 6.2% low. PS is mixed — 1 of 4 runs melt-deficient.
- **The uniform 2.04% σ-shrink is falsified.** σ is state-point independent, so it must move melt
  density too, and melt density is already right.
- **The α-based melt heuristic is biased toward blaming the force field**, by ~1.5–2 pp.
- **No family is a seed-only replicate set**; `charge_method` alone varies within 8 of 9.
- **`cutoff_A` and `eq_annealing_cycles` never reached the deck** (32/36 and 36/36 runs).

## Test 1 — funded arms

`ff_sensitivity/arms/build_arms.sh` builds cells only. It launches nothing and claims no GPU;
equilibration is a separate, explicitly authorized step.

Arm E (heavy melt anneal) is the arm the free leg indicates. It is applied at equilibration through
`add_melt_npt` / `melt_npt_steps` — **not** through `eq_annealing_cycles`, which reaches no executor
and is now rejected by `validate_run_plan.py`.

## Tests

`tests/test_ff_sensitivity_analysis.py` in the repo root covers the ρ(T) evaluation, the
validity-range guard, and the independent round-trip of the reference data against the manuscript's
own 300 K comparators.
