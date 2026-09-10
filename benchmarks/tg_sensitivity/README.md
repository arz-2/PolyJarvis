# tg_sensitivity — controlled Tg sensitivity legs

Answers the second half of reviewer comment 1: *"Controlled Tg sensitivity tests with respect
to cooling rate, temperature grid, equilibration duration, and fitting procedure remain
necessary for representative systems."*

    python3 benchmarks/tg_sensitivity/build_matrix.py --dry-run   # show what would fork
    python3 benchmarks/tg_sensitivity/build_matrix.py             # create the leg run dirs
    python3 benchmarks/tg_sensitivity/verify_matrix.py            # 7 pre-GPU checks, claims no GPU

`MANIFEST.json` is the definition — anchors, the six legs, the cost law, the predeclared
comparison rule. `matrix.json` is generated.

## Why there is no data on these axes today

`tg_t_step_K` is **20 K in all 36 round-1 runs and all 21 stereo_r2 plans**, without exception,
and schema 2.0 collapsed the cooling rate to a single scalar `tg_rate_K_per_ns`. So there is not
even incidental variation to re-analyse. Round 1's rate lists did vary between replicates, but
`manuscript_v2/revision.md` §A established that was table drift, not a designed grid.

## The legs — 22.65 GPU-h for all four axes

| # | Axis | Anchor | Override | GPU-h |
|---|---|---|---|---|
| — | baseline | PE_1 | 40 K/ns, dT=20 | 0 (campaign's own) |
| L1 | rate | PE_1 | `tg_rate_K_per_ns: 20` | 1.85 |
| L2 | rate | PE_1 | `tg_rate_K_per_ns: 10` | 3.70 |
| — | baseline | iPMMA_1 | 100 K/ns, dT=20 | 0 (campaign's own) |
| L3 | rate | iPMMA_1 | `tg_rate_K_per_ns: 50` | 8.80 |
| L4 | T-grid | PE_1 | `tg_t_step_K: 10` @ 20 K/ns | 1.85 |
| L5 | T-grid | PE_1 | `tg_t_step_K: 40` @ 20 K/ns | 1.85 |
| L6 | T-grid | iPMMA_1 | `tg_t_step_K: 40` | 4.60 |

Equilibration duration and fitting procedure are deferred rather than dropped — see
`MANIFEST.deferred`. The fitting axis is free (re-analysis); the duration axis should first be
harvested from the pilot's own adaptive EXTEND attempts, because `t_equil_ns` **does not exist in
v2** and there is no baseline to add to until a real equilibration has reported its executed
`melt_hold_min_steps`.

## Why a leg is nearly free

`track_registry.macro_stages_for(["tg"])` is `(build, equilibration, thermal, summary)` — **no
cooling stage** — and `stage_params._resolve_tg_params` starts the staircase from the
equilibration stage's `melt_start_data_path`. So a leg is one `thermal` stage off a melt cell
that already exists.

It does not copy that cell. The leg's `workflow_state.json` records `build` and `equilibration`
as accepted with the **anchor's own** `executor_state.json` as the manifest, and
`workflow_engine._accepted_manifest` re-verifies every artifact's sha256 on load. A leg is
therefore **28 kB on disk**, and it fails loudly rather than silently if the anchor's melt cell is
ever moved, truncated, or garbage-collected by a disk-retention pass.

`stages_for("tg_rate_K_per_ns")` is `("thermal", "cooling")`, so a rate change would normally
invalidate the cooldown too; `properties: ["tg"]` drops `cooling` from `enabled_stages()` and
`_reconcile_plan`'s `affected & set(enabled)` filters it out. Check 3 asserts that, because it is
worth about 5 GPU-h across the rate legs.

## The production rate is the fastest rate the floor allows — everywhere

Measured across `guides/polymer_rules.json`, **all 21 classes sit at `steps_per_T ÷
tg_min_steps_per_T` = exactly 1.00**:

| Classes | dt | floor | default rate |
|---|---|---|---|
| 18 (PACR, PSTR, PEST, PKTN, PSFO, POXI, …) | 1 fs | 200 000 | **100 K/ns** |
| PHYC, PDIE | 2 fs | 250 000 | 40 K/ns |
| PSIL (dT=10) | 1 fs | 200 000 | 50 K/ns |

The per-class default rate is not a chemistry preference — it is the fastest rate that class's
own sampling floor permits at its own `tg_t_step_K` and `dt_fs`. Two consequences:

1. **100 K/ns needs no leg.** It is `iPMMA_1`'s baseline and the baseline of five other
   stereo_r2 systems, all free — the campaign's own thermal stages. It is the most-measured
   rate in the study. L3 (50 K/ns) brackets it from below.
2. **The ladder can only ever probe slower.** Any rate sensitivity reported here is a
   sensitivity *at the production boundary*, because there is no headroom above the default
   without dropping under the floor. State that in the writeup — it bounds what the Tg claim
   can say.

PE is where this bites hardest: at its baseline dT=20 a 100 K/ns sweep is 100 000 steps/T
against a 250 000 floor, and even dT=40 only reaches 200 000. PE can reach 100 K/ns *only* at
dT=50 (exactly 250 000), which moves the grid and the rate together — a legitimate combined
probe, but not a point on the rate ladder, and deliberately not in the leg table above.

## The temperature-grid axis is exactly controlled on PE

At 20 K/ns and dt = 2 fs, `tg_t_step_K` ∈ {10, 20, 40} gives 250 000 / 500 000 / 1 000 000 steps
per bin over 48 / 24 / 12 bins — **12 M steps in every case**. Identical cost, identical total
simulated time, only the staircase resolution differs, and dT=10 sits exactly on PHYC's
`tg_min_steps_per_T` floor. L1 doubles as the dT=20 member.

**A reportable infeasibility**: `tg_t_step_K=10` at iPMMA's 100 K/ns baseline is rejected at plan
time (100 000 steps < the 200 000 floor). Report that — the grid cannot be refined below 20 K at
the production rate without dropping under the per-bin sampling floor. Do **not** override
`tg_min_steps_per_T` to dodge it, even though it is in `OVERRIDE_RANGES`; that changes the
sampling the axis exists to hold fixed.

## Anchors

**iPMMA_1** is primary — the representative system named in `manuscript_v2/revision.md` §A. It
carries an unvalidated `eq_annealing_cycles` 5→10 change, so **PLLA_1** is the named fallback
(cleanest round-1 family; all four replicates failed only the legitimate glassy C(t) carve-out).
Do not fall back to aPS_1 — its `MELT_STAGE_DEFICIT` is unresolved. Swap with
`--anchor-override iPMMA_1=PLLA_1`; leg names are anchor-qualified so the two never collide.

**PE_1** carries the wide-span axes: 12× cheaper per ns than any PCFF member. It is rubbery at
300 K and semicrystalline in practice, so the glassy PCFF anchor carries the "representative
system" weight. L2's 10 K/ns is PHYC's validated floor — going slower risks measuring
crystallisation rather than Tg.

## Sequencing

`build_matrix.py` **refuses to fork an anchor whose equilibration is not `accepted`**, and says
which anchor it is waiting on. Legs can be built the moment an anchor gates, without waiting for
its thermal stage. Launch a built leg exactly as stereo_r2 does:

    RUN=TGS_iPMMA_1_L3_r50
    setsid nohup mcp-servers/.venv/bin/python orchestration/scripts/agent_api.py resume $RUN \
      > data/$RUN/raw/launch_$(date +%Y%m%d_%H%M%S).log 2>&1 &
    echo $! > data/$RUN/raw/launcher.pid

`resume`, never `start` — `start` re-materializes and re-derives system size, which is the drift
vector this whole line of work exists to eliminate. Use `mcp-servers/.venv/bin/python`; bare
`python3` dies on `ModuleNotFoundError: mcp` before claiming a GPU.

## The comparison rule is predeclared

An axis is called **sensitive** when |Tg(leg) − Tg(anchor baseline)| exceeds the **pooled
within-system SD across all completed stereo_r2 runs**; the anchor's own n=3 SD is a secondary
check. Pooled is primary because an n=3 SD carries 2 dof and is itself uncertain to roughly ±50%
— quoting it alone would reproduce the conflation reviewer comment 1 caught the first time.

## Verification

All seven checks in `verify_matrix.py` have been negative-tested: each was confirmed to FAIL on a
deliberately broken leg (extra key moved, stale `plan_hash`, infeasible rate, `cooling` re-enabled,
missing melt manifest, leg plan hardlinked to the anchor's, seed drift), not merely to pass on a
good one.
