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
| Density not converging during equilibration | Insufficient annealing | add annealing cycles (3–5) |
| `generate_equilibration_workflow(extend_only=True)` returns 7 stages instead of 1 | Stale MCP server code (`n_stages` should be 1) | do NOT submit, do NOT hand-write a `.in`; request an MCP server restart |
| Disk-full mid-chain | Ran out of space partway | keep completed stages' `_out.data`; free disk; delete only the failed stage's partial outputs; regenerate the workflow, slice to resume at the failed stage (never restart from stage 0). Prevention: <60 GB free, strip `dump` from production stages *except* `npt_prod300`/`npt_production` when `tg`/`bulk_modulus` was requested on a novel SMILES (`system-characterization-analyzer` needs that dump) |

**`plan_mode=="reasoned"` STRUCTURAL_FAIL ladder** — a `STRUCTURAL_FAIL` verdict from
`enforce_equilibration_gate` (`phase=full` only; `phase=melt` routes to MELT-MIXING below)
escalates through these rungs, one attempt each:
1. The named `structural_fail_remedy`: `re_melt_slow_recool` → RE-ANNEAL below. `heavy_melt_anneal_probe`
   → no mechanized implementation; treat as a diagnostic investigation, escalate to rung 3 if the
   melt deficit doesn't resolve.
2. Unresolved (or `structural_fail_remedy_confidence=low` and rung 1 fails once) → the closest row
   in Cross-cutting/Foundation → equil above.
3. Full re-plan with a different force field — routes back through planner→critic; counts as one
   rung, not a restart. Only after rung 3 fails at attempt 5 does `escalate_human` apply.

**RE-ANNEAL** (`re_melt_slow_recool`, from `UNDER_ANNEALED_COOLING`): re-melt from the converged
**melt** cell (`npt_production_out.data` at `T_equil_K`, not the 300 K cell) via
`generate_equilibration_workflow`, with `npt_cool_steps`/`npt_cool300_steps` overridden to **2×**
baseline (attempt 1) then **4×** (attempt 2; max 2 — still under-band → re-classify as
`MELT_STAGE_DEFICIT`, rung 3, not a third loop). Baseline: `npt_cool300_steps` (glassy
T_workflow→300K leg) = `int(1.0e6/dt_fs)`; `npt_cool_steps` (rubbery, or melt→target when
`add_melt_npt=True`) = the atom-count tier `generate_equilibration_workflow` already picks
(`n_atoms<5000`→1e6, `<15000`→2e6, else 3e6). Pass as `--npt_cool_steps`/`--npt_cool300_steps` on
the re-spawned equilibration-worker. Log the multiplier used in the RECOVERY block.

**EXTEND** (plain `EXTEND` verdict, either gate — drift not yet converged, not a wrong-value
defect): re-spawn equilibration-worker with `generate_equilibration_workflow(extend_only=True)`
(`mode: extend`), never a hand-written `.in` or a fresh chain. `phase=full` → extend
`npt_prod_data_path` at `temp=npt_prod_temp_K` (never `T_equil_K`/`T_workflow_K` — would re-melt a
cooled glass). `phase=melt` → extend `npt_production_data_path` at `temp=T_workflow_K`, then
re-run the same `phase=melt` gate. `extend_ns = max(1.5, 1.5*ct_tau_relax_ps/1000)` when finite,
else 1.5 ns flat. Cap 2 extensions **per gate** (`phase=full`/`phase=melt` independent budgets).

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

## Thermal → analyze-tg (tg-analysis-worker)

| Condition | Root cause | Action |
|---|---|---|
| `Tg_K` vs `Tg_alternative_K` disagree by >20 K | Noisy density or sweep range doesn't bracket the transition | increase `N_STEPS_PER_T` or extend the T range |
| `fit_quality` POOR despite a clean log | Velocity re-init discontinuity or excessive plateau drift exclusion | plot `tg_density_bins.csv`; check velocity re-init + `n_plateaus_skipped_drift` |
| "Bilinear curve_fit failed" | Sweep log spans <~100 K or collapses to one bin — defective single-isothermal run | return FAIL, regenerate the sweep; do NOT tune `initial_tg_guess` |
| "fewer than 4 temperature bins" after partial kill | Sweep killed before sufficient T coverage | ≥60% planned T points + both slopes present → attempt `extract_thermal`, accept if `fit_quality≥ACCEPTABLE`; else restart full sweep |

## Mechanical → murnaghan (murnaghan-worker)

| Condition | Root cause | Action |
|---|---|---|
| `fit_converged=False` or `K<0` | EOS curvature not resolved at this pressure range | check `volume_equilibrated` per pressure; glassy: narrow to ±500 atm if ±1000 causes creep; add pressure points and re-submit |
| `B0_prime` outside [4, 20] with `fit_converged=True` | **[INFO]** — `guides/BM_ANALYSIS.md`: WARNING annotation only (EOS-nonlinearity artifact or under-constrained curvature at this span); K stays correct. Never triggers deform-worker fallback by itself. |
| `run_bulk_modulus_series`: a pressure point fails / GPU OOM / empty `log_files` | `npt_steps` too large for available VRAM | reduce `npt_steps` to 200000, re-submit (check `nvidia-smi`) |
| Rubbery PROBE ladder's `-200 atm` point crashes / log missing or truncated | **[INFO]** — deliberate outcome of the shallow safety probe (`guides/MURNAGHAN.md`'s two-leg protocol), already handled inline by `MECHANICAL_TRACK.md`: re-run `analyze-bm` on the remaining compression-only logs, never resubmit the probe or attempt Leg 2. Note tension untested; never write a class-level `bm_pressures_atm` from it. |
| BACKGROUND-WAIT never returns after murnaghan-worker's `watch_run` call | Worker passed `run_bulk_modulus_series`'s placeholder string instead of the real `chain_id` — no sentinel created | re-run `watch_run(chain_id)` as a real MCP call with the actual `chain_id` |
| `K` negative or at melt-value density (~0.8–0.9 g/cm³) for a glassy polymer | Worker received `npt_production` (melt) data instead of `npt_prod300` (300 K) data | verify `equil_data_path` is `npt_prod300_out.data`; run the cool+prod300 phase first if missing; re-spawn |

## Mechanical → deform (deform-worker)

| Condition | Root cause | Action |
|---|---|---|
| `fit_r2_C11`/`fit_r2_C12_yy` < 0.90 | Noisy stress-strain fit | check `THERMO_FREQ ≤ 100` in the deform script |
| `rate_sensitivity` present, `verdict=WARNING`, slow-rate `fit_r2 ≥ 0.90` | **[INFO]** — `guides/BM_ANALYSIS.md`: tool already auto-substitutes the slow-rate fit into `K_GPa`/`method`; just surface the flag. |
| `isotropy_delta_pct` ≥ 20% | Cell too small / not isotropic at this strain | BORDERLINE — Murnaghan should have been primary; re-submit murnaghan-worker with a wider/adjusted pressure series |
| `npt_deform` run crashes | `dt_fs` too large for SHAKE + deform | re-spawn `dt_fs=1.0`; still crashes → reduce `STRAIN_RATE` 10× |

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
