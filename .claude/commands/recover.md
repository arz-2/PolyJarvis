---
description: Diagnose and plan recovery for a failed PolyJarvis simulation stage
allowed-tools: Read, Bash, mcp__mcp-lammps-engine__get_run_status, mcp__mcp-lammps-engine__get_run_output, mcp__mcp-mol-builder-server__get_job_status, mcp__mcp-mol-builder-server__get_job_output
---

Source of truth for `recovery-agent` (`plan_mode=="reasoned"` runs only — `recovery-agent` is never
spawned for `plan_mode=="deterministic"`; `run_deterministic_replicate.py` owns that path's own
bounded EXTEND-only recovery inline, see §2b) and for a human doing Session Recovery (Mode B, end
of file).

**1. Find the active run_log.md** (skip if the prompt already gave `run_name`/`chain_id`):
```bash
find /home/arz2/PolyJarvis/data -name "run_log.md" -newer /home/arz2/PolyJarvis/data/TEMPLATE/run_log.md | sort -t/ -k6 | tail -5
```

**2. Read the SIMULATION STATE table** for the row with status `monitoring`/`failed`; note `chain_id`/`run_id`.

**2b. Attempt ladder** — `jq -r '.plan_mode' data/<RUN>/raw/run_plan.json`:
- `reasoned` (the only mode this agent runs under): max **5** attempts; protocol-level changes are
  sanctioned as ladder rungs (see the STRUCTURAL_FAIL ladder under Foundation → equil).
- `deterministic`, or plan missing/unreadable: max **2**, EXTEND-type only, any `decided_params`
  change stops immediately for human review — describes `run_deterministic_replicate.py`'s own
  inline logic; not a path this agent ever executes.

**3. Get actual status:** `get_run_status(chain_id)` (LAMMPS) or `get_job_status(job_id)` (RadonPy/EMC).

**4. Read the error:** `get_run_output(run_id)` (last 50 lines) or `get_job_output(job_id)`.

**5. Diagnose:**
- `guides/RECOVERY_PLAYBOOK.md` first if it exists and a clustered signature matches (rows carry
  an empirical `k/n` success rate — rank by it, skip low-`n`/low-success rows).
- Else jump straight to the `## <Track> → <Step>` section below matching the prompt's `track`/
  `step` (`equil`/`equil-check` both map to Foundation → equil). Fall back to Cross-cutting, or the
  reasoned STRUCTURAL_FAIL ladder, only if nothing there matches.
- A row tagged **`[INFO]`** is never a failure — return `verdict: no_action_needed`, spend no
  attempt, write no RECOVERY block.

**5b. Price the rung** — mandatory before recommending any remedy that trades wall time for a
property value (RE-ANNEAL, HEAVY-MELT-ANNEAL, EXTEND beyond the first, a slower Tg rate). Skip only
for REBUILD-LARGER and other Class A structural remedies.

```bash
python3 orchestration/scripts/remedy_economics.py \
  --failing-gate <gate> --gate-class <A|B|C|D> \
  --lever <cooling_rate_K_per_ns|trajectory_ns|nchain> --lever-direction <lower|higher> \
  --history "<lever>:<metric>,..." --next-lever <value> \
  --target-floor <gate threshold> --physical-target <experimental value, not the band edge> \
  --sem <metric SEM> --last-rung-hours <wall time of the most recent rung> \
  --cost-exponent <-1 for cooling rate, +1 for trajectory length>
```

Inputs: `--history` from this run_log's `## RECOVERY` blocks (one lever:metric pair per rung
already spent, including the baseline); `--target-floor`/`--sem` from the gate JSON;
`--physical-target` from the experimental reference, never the band edge; `--last-rung-hours` from
the SIMULATION STATE table.

Route on the verdict — transcribe it and its `reason` into RESULT, never re-derive the arithmetic:

| Verdict | Action |
|---|---|
| `SPEND` | Recommend the rung. `spend_limit: one rung` means the slope is not yet measured — one rung only, then this check runs again |
| `SPEND_STRUCTURAL` | Class A — recommend the structural remedy; the economics tests do not apply |
| `STOP_ANNOTATE` | `verdict: accept_with_annotation`. Spend no further rung; carry `annotation_required` forward |
| `WRONG_LEVER` | This remedy cannot address this gate — re-diagnose, do not spend the rung |
| `PRECONDITION_UNMET` | Supply the named argument and re-run; never guess it |

Thresholds live in `decision_policy.json` `policies.equilibration.remedy_economics` — the script
reads them, this file does not restate them.

**6. Return your RESULT** in `recovery-agent.md`'s required format — never print free text instead.

**7. (Orchestrator, not this agent) writes this to run_log.md before re-spawning anything** —
format fixed, `protocol-locker` parses it:
```markdown
## RECOVERY — [Stage] attempt N
- **Trigger:** <error>
- **Diagnosis:** <root cause>
- **Action:** <what changed>
- **Outcome:** pending
```

---

## Cross-cutting (any track/step)

| Condition | Root cause | Action |
|---|---|---|
| "lost atoms" | Timestep too large / bad geometry | `dt_fs: 0.5` |
| "out of memory" / GPU OOM | Cell too large for VRAM | halve `mpi_ranks` |
| LAMMPS crashes steps 0–10, wrong style keyword (`fourier`/`none`/`lj/charmm`) | `generate_script` called without an explicit FF flag | confirm `**lammps_flags` present; re-generate with explicit `use_trappe`/`use_pcff`/`use_opls` |
| Background waiter never returns after `run_lammps_chain` | `watch_run` sentinel lost on MCP server restart | `grep -r "STAGE COMPLETE" <work_dir>/` — if all stages present, proceed without waiting |
| Submit returns `status=error`, `conflicting_writers` | Live process already holds the target log open | inspect pid/cmd; stale orphan → `kill` then resubmit; legitimate concurrent run → do NOT relaunch, coordinate via user |
| Log truncated, no error string, process gone | External kill (OOM killer / GPU preemption) | identify last completed stage's `_out.data`; submit remaining stages as a new chain from that checkpoint |
| GPU crash during NPT production | OOM, bad geometry, or pair-style mismatch | check the log (do NOT switch to CPU): OOM → reduce size/GPUs; bad geometry → more minimize steps; pair-style mismatch → check params |

## Foundation → build

| Condition | Root cause | Action |
|---|---|---|
| "unknown atom type" / segfault on startup | FF assigned before polymerization | re-spawn from `assign_forcefield` step |
| RadonPy conformer/charge job `failed` | QM instability | retry once with `n_conformers` halved; still fails → AM1-BCC, note in D-02 |
| "missing FF parameters" (EMC build) | SMILES attachment points wrong | verify exactly two `*` atoms; try `dp: 15` if `dp: 20` fails |
| Polymerization job hangs in "pending" | Job queue stuck / RadonPy worker crash | `list_all_jobs()`; `cancel_job` if still pending; resubmit `submit_polymerize_job` |
| EMC stalls/fails on amide-N monomers (pcff lacks `{na,c_2}`) | FF constraint, not a build error | rescue ladder: primary amide → OPLS-AA; secondary amide/lactam/urea → RadonPy/GAFF2 |
| EMC dies with negative exit code (`segfault`, no `Error:` line) | Monomer/field mismatch, not unbuildable | continue the field cascade (try pcff next) |
| Chain droplets / vacuum voids in packed cell | Initial density too high | rebuild at `density=0.05` |

## Foundation → equil (equilibration-worker + equil-check gate)

| Condition | Root cause | Action |
|---|---|---|
| Energy NaN / diverges in first 100 steps | `density_initial` too high | re-spawn with `density_initial − 0.10` |
| Density drift > 3% after 2 EXTEND cycles | Won't converge at this density | restart compress with `density_initial − 0.05` |
| "Out of range atoms — PPPM" in `npt_compress` | PPPM ghost region exceeded during box shrink | switch compress `pair_style` to `lj/cut/coul/cut`, skin=3.0 Å, dt=0.5 fs; restore kspace for production |
| "Out of range atoms — PPPM" at `nvt_softheat` step 0→1 | Localized EMC pack overlap for that seed | rebuild cell with a fresh EMC seed; 2nd seed also fails → drop `density_initial` 0.6→0.5 before any deck edits |
| `extract_equilibrated_density` returns <0.5 g/cm³ | Log likely has the compression ramp, not the production plateau | verify `plateau_step_range` starts after the ramp; re-spawn equil-checker `eq_fraction=0.7` |
| `check_equilibration_comprehensive` hangs on a large dump (>~1 GB / >1000 frames) | Trajectory I/O timeout | do NOT re-run; use `extract_equilibrated_density` + the last pre-extension comprehensive result |
| Density not converging during equilibration | Insufficient melt annealing | hold longer at the melt temperature: HEAVY-MELT-ANNEAL below (`melt_npt_steps` 10× then 50×). `eq_annealing_cycles` in `polymer_rules.json` is **planning-only** — `generate_equilibration_workflow` has no such argument, so "add cycles" is not an actionable lever. The peak anneal temperature `max_temp` (class `annealing_T_high_K` = `T_equil_K`+80 K) is the other real knob. |
| `generate_equilibration_workflow(extend_only=True)` returns 7 stages instead of 1 | Stale MCP server code (`n_stages` should be 1) | do NOT submit, do NOT hand-write a `.in`; request an MCP server restart |
| Disk-full mid-chain | Ran out of space partway | keep completed stages' `_out.data`; free disk; delete only the failed stage's partial outputs; regenerate the workflow, slice to resume at the failed stage (never restart from stage 0). Prevention: <60 GB free, strip `dump` from production stages *except* `npt_prod300`/`npt_production` when `tg`/`bulk_modulus` was requested on a novel SMILES (`system-characterization-analyzer` needs that dump) |
| "Cannot open input script .../emc_build.params: No such file or directory" | EMC staging omission — `emc_params_path` never copied alongside `cell.data` | copy `emc_params_path` into `{work_dir}/emc_build.params`, resubmit from stage 0 — omit `ladder_rung` (zero stages completed, no gate verdict) |
| `n_eff_density` < 20 (EXTEND) | Density plateau undersampled — too few independent samples | EXTEND with the gate's deficit-scaled `extend_ns = 1.5 * 20/n_eff` (not a flat 1.5 ns); same temperature |
| `finite_size_verdict=SIZE_MIN_IMAGE_VIOLATION` | `L < 2*cutoff_A` — atoms see their own images, the pair potential is wrong | REBUILD-LARGER below; never EXTEND or re-cool |
| `finite_size_verdict=SIZE_CHAIN_SELF_IMAGE` | `L < 2*Rg` — each chain overlaps its own image, biasing packing → density and moduli | REBUILD-LARGER below. PEEK/PSU cells at `L/2Rg` 0.74–0.99 are the archived precedent |
| `L_over_Ree` < 1 alone, `verdict=SIZE_PASS` | **[INFO]** — advisory; common in published polymer MD and much weaker than the `2*Rg` criterion. Report it, spend no attempt. |

**`plan_mode=="reasoned"` STRUCTURAL_FAIL ladder** — a `STRUCTURAL_FAIL` verdict from
`enforce_equilibration_gate` (`phase=full` only; `phase=melt` routes to MELT-MIXING below)
escalates through these rungs, one attempt each:
1. The named `structural_fail_remedy`: `re_melt_slow_recool` → RE-ANNEAL below.
   `heavy_melt_anneal_probe` → HEAVY-MELT-ANNEAL below. `SIZE_MIN_IMAGE_VIOLATION` /
   `SIZE_CHAIN_SELF_IMAGE` → REBUILD-LARGER below (a box too small for its own contents is not
   recoverable by any amount of equilibration — go straight there, do not spend rungs 2–3).
2. Unresolved (or `structural_fail_remedy_confidence=low` and rung 1 fails once) → the closest row
   in Cross-cutting/Foundation → equil above.
3. Full re-plan with a different force field — routes back through planner→critic; counts as one
   rung, not a restart. Only after rung 3 fails at attempt 5 does `escalate_human` apply.

Every rung is priced at step 5b before it is recommended. The rung caps below are ceilings only:
a `STOP_ANNOTATE` verdict ends the ladder earlier, and no verdict extends it past its cap.

**RE-ANNEAL** (`re_melt_slow_recool`, from `UNDER_ANNEALED_COOLING`) — price it at step 5b first
(`--lever cooling_rate_K_per_ns --lever-direction lower --cost-exponent -1`): re-melt from the converged
**melt** cell (`npt_production_out.data` at `T_equil_K`, not the 300 K cell) via
`generate_equilibration_workflow`, with `npt_cool_steps`/`npt_cool300_steps` overridden to **2×**
baseline (attempt 1) then **4×** (attempt 2; max 2 — still under-band → re-classify as
`MELT_STAGE_DEFICIT`, rung 3, not a third loop). For a glass the load-bearing leg is
`npt_cool300` (`T_equil_K`→300 K, 250–470 K by class); `npt_cool` spans only
`annealing_T_high_K`→`T_equil_K` = 80 K, so raising `npt_cool_steps` alone does not slow the
quench that forms the glass. Baseline: `npt_cool300_steps` (glassy
T_workflow→300K leg) = `int(1.0e6/dt_fs)`; `npt_cool_steps` (rubbery, or melt→target when
`add_melt_npt=True`) = the atom-count tier `generate_equilibration_workflow` already picks
(`n_atoms<5000`→1e6, `<15000`→2e6, else 3e6). Pass as `--npt_cool_steps`/`--npt_cool300_steps` on
the re-spawned equilibration-worker. Log the multiplier used in the RECOVERY block.

**HEAVY-MELT-ANNEAL** (`heavy_melt_anneal_probe`, from `MELT_STAGE_DEFICIT`) — price it at step 5b
first (`--lever melt_hold_ns --lever-direction higher --cost-exponent 1`): the melt itself never
reached experimental density, so re-cooling cannot help — hold longer at `T_equil_K` instead. The
default melt hold is `melt_npt_steps = int(1.0e6/dt_prod)` ≈ **1 ns**, roughly 100× short of the
~100 ns melt anneal that reached PMMA 1.19 g/cm³ (NkepsuMbitou 2025), so extend it:

```
generate_equilibration_workflow(
    add_melt_npt   = True,                       # inserts npt_cool_melt → npt_melt (→ npt_cool
                                                 # only when temp < t_equil_K, i.e. rubbery)
    t_equil_K      = <class T_equil_K>,          # 350–800 K depending on class; must satisfy
                                                 # temp <= t_equil_K <= max_temp or the call errors
    melt_npt_steps = MULT * int(1.0e6/dt_fs),    # MULT = 10 (attempt 1), 50 (attempt 2)
)   # changed args only. `velocity_seed`, all five step counts, `temp`, the three force-field
    # flags, and `engine` are required on every call — pass them from the prompt, `null` included
```
Re-run the `phase=melt` gate after each rung. `npt_melt` is the melt-density extraction target.
Max 2 rungs; still under-band → rung 3 (different force field). Log `MULT` in the RECOVERY block.

**REBUILD-LARGER** (`SIZE_MIN_IMAGE_VIOLATION` / `SIZE_CHAIN_SELF_IMAGE`) — Class A, exempt from
step 5b: the remedy removes the defect completely at a bounded one-time cost, so it is spent
unconditionally. The cell is too small for
its own contents. `L < 2*cutoff_A` means atoms interact with their own periodic images and the pair
potential is wrong; `L < 2*Rg` means every chain overlaps its own image, biasing packing and hence
density and the moduli. Cell volume scales with `nchain` at fixed density, so `L` grows as
`nchain^(1/3)` — raise `nchain` by `ceil(nchain * (target/current)^3)` where `target/current` is the
shortfall in `L_over_2cutoff` or `L_over_2Rg`, then rebuild from D-00. Never spend EXTEND or
RE-ANNEAL rungs on this: no trajectory length fixes a box dimension.

**EXTEND** (plain `EXTEND` verdict, either gate — drift not yet converged, not a wrong-value
defect) — the first extension is spent without pricing; price the second at step 5b
(`--lever trajectory_ns --lever-direction higher --cost-exponent 1`): re-spawn
equilibration-worker with `generate_equilibration_workflow(extend_only=True)`
(`mode: extend`), never a hand-written `.in` or a fresh chain. `phase=full` → extend
`npt_prod_data_path` at `temp=npt_prod_temp_K` (never `T_equil_K`/`T_workflow_K` — would re-melt a
cooled glass). `phase=melt` → extend `npt_production_data_path` at `temp=T_workflow_K`, then
re-run the same `phase=melt` gate. `extend_ns = max(1.5, 1.5*ct_tau_relax_ps/1000)` when finite,
else 1.5 ns flat — **except** when `n_eff_density` is the failing gate, where the gate's own
`remedy` carries a deficit-scaled `extend_ns = 1.5 * n_eff_min/n_eff` (e.g. n_eff=11 against a
floor of 20 → 2.7 ns); use that value. Cap 2 extensions **per gate** (`phase=full`/`phase=melt`
independent budgets).

**MELT-MIXING** (`phase=melt` gate: `EXTEND`, or `STRUCTURAL_FAIL` from `density_homogeneity`
alone — never `re_melt_slow_recool`/`heavy_melt_anneal_probe`, which need the post-cool glass
state that doesn't exist yet): apply the EXTEND procedure's `phase=melt` branch. Cap 2 extensions;
still failing → `MELT_STAGE_DEFICIT`-equivalent, escalate to rung 3. Only `phase=melt` PASS reaches
`phase=cooldown`.

## Thermal → tg (tg-sweep-worker)

| Condition | Root cause | Action |
|---|---|---|
| R² < 0.80 or fewer than 4 bins | T range too narrow | re-run: `T_start+50K`, `T_end−50K` |
| R² 0.80–0.90 | Borderline bilinear fit | re-run with `T_step` halved |
| Sweep killed mid-run | Process death (OOM, GPU preemption) | restart from last completed T (max 2 attempts); still failing → return error to orchestrator |
| Tg above the exp band, one rate measured | Cooling-rate offset, slope not yet measured | price at step 5b (`--lever cooling_rate_K_per_ns --lever-direction lower`); a one-rate history returns `SPEND`, `spend_limit: one rung` → add rates, then re-price before any slower single rate |
| `tg_gate_verdict=TG_REVIEW` from `tg_method_gap_K` | Two admissible fits disagree on the same data | **not a rung-pricing question** — no amount of sampling resolves it. Halt to human per THERMAL_TRACK.md; never spend a slower rate to break the tie |

## Thermal → analyze-tg (tg-analysis-worker)

| Condition | Root cause | Action |
|---|---|---|
| `tg_gate_verdict=TG_REVIEW` (`tg_method_gap_K` > 20 K) | Noisy density or sweep range doesn't bracket the transition | double `tg_steps_per_t` (class value 250k–2M), or widen the sweep beyond the class `tg_t_low_K`/`tg_t_high_K` by 50 K on the side nearer the fitted Tg. PKTN/PSFO carry `method_gap_exempt` — for those the gap is recorded, not a REVIEW |
| `tg_gate_verdict=TG_NOT_REPORTABLE`, `transition_width_c_K` < 5 K | Sweep resolved no crossover — a sharp-kink artifact that can still score r²>0.997 (PMMA1: 0.1 K width, EXCELLENT) | halve `tg_t_step_K` (20 K → 10 K for every class except PSIL, already 10) and re-run at the next-slower `tg_rates_K_per_ns` entry; `tg_min_steps_per_T` still applies |
| `tg_gate_verdict=TG_NOT_REPORTABLE`, `slope_signs_valid=false` or `slope_ordering_valid=false` | Non-physical fit: density must fall with T on both branches and α_rubbery must exceed α_glassy | the sweep did not capture a transition — widen the T range and re-run; do not tune `initial_tg_guess` |
| `fit_quality` POOR despite a clean log | Velocity re-init discontinuity or excessive plateau drift exclusion | plot `tg_density_bins.csv`; check velocity re-init + `n_plateaus_skipped_drift` |
| "Bilinear curve_fit failed" | Sweep log spans <~100 K or collapses to one bin — defective single-isothermal run | return FAIL, regenerate the sweep; do NOT tune `initial_tg_guess` |
| "fewer than 4 temperature bins" after partial kill | Sweep killed before sufficient T coverage | ≥60% planned T points + both slopes present → attempt `extract_thermal`, accept if `fit_quality≥ACCEPTABLE`; else restart full sweep |

## Mechanical → murnaghan (murnaghan-worker)

| Condition | Root cause | Action |
|---|---|---|
| `fit_converged=False` or `K<0` | EOS curvature not resolved at this pressure range | check `volume_equilibrated` per pressure; glassy: narrow to ±500 atm if ±1000 causes creep; add pressure points and re-submit |
| `B0_prime` outside [4, 20] with `fit_converged=True` | **[INFO]** — `guides/BM_ANALYSIS.md`: WARNING annotation only (EOS-nonlinearity artifact or under-constrained curvature at this span); K stays correct. Never triggers deform-worker fallback by itself. |
| `bm_gate_verdict=BM_INADMISSIBLE`, `volume_monotonic=false` | dV/dP > 0 somewhere — violates mechanical stability; one point's mean volume is out of sequence | re-run **only** the offending pressure point at `npt_steps`×2; never re-fit the existing series |
| `bm_gate_verdict=BM_INADMISSIBLE`, `V0_A3` outside the sampled range | The ladder brackets the wrong zero-pressure reference state | re-submit with the class `bm_pressures_atm` if set (PDIE/PHYC `[1,1000,2500,5000,10000,15000]`, PEST `[-1000,0,1500,3000,5000]`, POXI `[-1000,0,3000,7000,15000]`, PSIL `[1,100,300,600,1000]`), else `guides/MURNAGHAN.md`'s default — glassy `[-1000,0,3000,7000,15000]`, rubbery PROBE `[-200,0,3000,7000,15000]` |
| `bm_gate_verdict=BM_INADMISSIBLE`, `r_squared` < 0.99 | Murnaghan form does not describe this P–V data at all (model breakdown, not imprecision) | widen the pressure span per the ladders above; if it persists the cell is not in a single elastic regime — check `volume_equilibrated` per point |
| `r_squared` < 0.999 with `bm_gate_verdict=BM_REPORTABLE` | **[INFO]** — precision annotation only. r² at 0.999 does not predict B0 accuracy (4.39% vs 4.37% mean deviation, Welch p=0.990). Spend no attempt. |
| `run_bulk_modulus_series`: a pressure point fails / GPU OOM / empty `log_files` | `npt_steps` too large for available VRAM | reduce `npt_steps` to 200000, re-submit (check `nvidia-smi`) |
| Rubbery PROBE ladder's `-200 atm` point crashes / log missing or truncated | **[INFO]** — deliberate outcome of the shallow safety probe (`guides/MURNAGHAN.md`'s two-leg protocol), already handled inline by `MECHANICAL_TRACK.md`: re-run `analyze-bm` on the remaining compression-only logs, never resubmit the probe or attempt Leg 2. Note tension untested; never write a class-level `bm_pressures_atm` from it. |
| BACKGROUND-WAIT never returns after murnaghan-worker's `watch_run` call | Worker passed `run_bulk_modulus_series`'s placeholder string instead of the real `chain_id` — no sentinel created | re-run `watch_run(chain_id)` as a real MCP call with the actual `chain_id` |
| `K` negative or at melt-value density (~0.8–0.9 g/cm³) for a glassy polymer | Worker received `npt_production` (melt) data instead of `npt_prod300` (300 K) data | verify `equil_data_path` is `npt_prod300_out.data`; run the cool+prod300 phase first if missing; re-spawn |

## Mechanical → deform (deform-worker)

| Condition | Root cause | Action |
|---|---|---|
| `fit_r2_C11` / transverse fit r² < 0.90 | Noisy stress-strain fit | check `THERMO_FREQ ≤ 100` in the deform script |
| `G_GPa` < 0 on a y/z leg | `deform_direction` not passed (defaults to `x`), so a loading slope entered the transverse average | re-run extraction with `deform_direction` matching the deck's strain axis — not a physics result |
| `rate_sensitivity` present, `verdict=WARNING`, slow-rate `fit_r2 ≥ 0.90` | **[INFO]** — `guides/BM_ANALYSIS.md`: tool already auto-substitutes the slow-rate fit into `K_GPa`/`method`; just surface the flag. |
| `deform_gate_verdict=DEFORM_INADMISSIBLE`, `isotropy_delta_pct` ≥ 20% | Cell genuinely anisotropic, so a single-direction Voigt K is biased | do NOT report this K; re-submit murnaghan-worker with a wider/adjusted pressure series (first confirm `deform_direction` was correct) |
| `npt_deform` run crashes | `dt_fs` too large for SHAKE + deform | re-spawn `dt_fs=1.0`; still crashes → reduce `STRAIN_RATE` 10× |

## Mechanical → aggregate-replicates (cross-replicate)

| Condition | Root cause | Action |
|---|---|---|
| `dispersion_outliers` non-empty (>4 leave-one-out SD AND >10% from the other replicates' mean) | One replicate disagrees with its siblings while passing every per-run gate — cis-PBD3 is the archived case (16.0 LOO-SD, 20.9% low, r²=0.9985) | do NOT drop it silently. Re-run that replicate's Murnaghan series with a fresh `velocity_seed`; if the value reproduces, keep it and widen the reported family SD instead of excluding it |
| `reportable=false` (fewer than 3 replicates with a value) | Not enough replicates to state a family value | run more replicates; never publish a family K from n<3 |

## Mechanical → analyze-bm (bulk-modulus-extractor, fluctuation path)

| Condition | Root cause | Action |
|---|---|---|
| `K < 0.1` or `> 20` GPa | Not fully equilibrated (`diagnostics.drift_check` warns) | re-spawn with `eq_fraction=0.7` |
| `volume_equilibrated=false` | Volume hasn't settled in the production window | re-spawn with `eq_fraction=0.25`; bracket K against the original `K_block_mean_GPa` |

---

## Session Recovery (Mode B)

When the Claude process dies while a background waiter is in flight (no tmux, machine reboot,
session killed):

1. `ssh lambda && pj && claude --continue` (or start fresh if conversation unavailable).
2. Read `data/[RUN]/run_log.md` → find the row where `status = monitoring`; note the `id`.
3. `get_run_status(id)`:
   - **running** → `watch_run(id)` → relaunch the waiter (`Bash(command=monitor_command, run_in_background=true)`) → update run_log to `monitoring`, end your turn. `RUN_COMPLETE` (exit 0) → completed; `PROCESS_DEAD_NO_SENTINEL` (exit 3) → treat as failed below.
   - **completed** → update run_log to `done` → continue from the next orchestrator step.
   - **failed** → `get_run_output(id)` → diagnose with the tables above → re-spawn worker (attempt 1).
   - **not found** → wait 60–90s for MCP server restart; retry; still missing → treat as failed.
4. `monitor_command` is deterministic — `watch_run(id)` regenerates it from the ID alone; always
   safe to re-call.

If tmux is still alive: `ssh lambda && pj` to re-attach; the background waiter is still running and
will re-invoke the session on exit — no action needed.
