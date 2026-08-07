---
description: Diagnose and plan recovery for a failed PolyJarvis simulation stage
allowed-tools: Read, Bash, mcp__mcp-lammps-engine__get_run_status, mcp__mcp-lammps-engine__get_run_output, mcp__mcp-mol-builder-server__get_job_status, mcp__mcp-mol-builder-server__get_job_output
---

Recovery procedure for a failed PolyJarvis simulation. Follow these steps exactly:

**1. Find the active run_log.md:**
```bash
find /home/arz2/PolyJarvis/data -name "run_log.md" -newer /home/arz2/PolyJarvis/data/TEMPLATE/run_log.md | sort -t/ -k6 | tail -5
```

**2. Read the SIMULATION STATE table** from that run_log.md. Identify the row with status `monitoring` or `failed` and note the `chain_id` / `run_id`.

**2b. Read the attempt ladder for this run:** `jq -r '.plan_mode' data/<RUN>/raw/run_plan.json`.
- **`reasoned`** — this run is establishing or re-establishing a protocol (grounded/reasoned
  plan, not yet locked via `make_deterministic_plan.py --lock-from`). Max attempts = **5**, and
  protocol-level changes are sanctioned as ladder rungs, not just parameter tweaks — see the
  escalation ladder below.
- **`deterministic`** — this run is replaying an already-locked protocol (this exact canonical
  SMILES is `protocol_validated`, possibly a replicate-2+ of a campaign). Max attempts = **2**,
  and only EXTEND-type recovery
  (parameter tweaks that never touch `decided_params`, e.g. re-running longer at 300K) may
  auto-apply. Any recovery that would change `decided_params` (a different FF, a different
  cooling rate, a different pressure range) must **stop immediately, write the finding to
  run_log.md, and surface for human review** instead of applying it — changing the protocol on
  a locked replicate breaks the fixed-protocol-across-replicates invariant the whole campaign
  depends on. Do not spend an attempt trying it.
- Missing/unreadable `run_plan.json`: fall back to the deterministic rule (max 2, no
  protocol-level changes) — the conservative default.

**3. Get actual status:**
- For a LAMMPS chain: `get_run_status(chain_id)`
- For a RadonPy/EMC job: `get_job_status(job_id)`

**4. Read the error:**
- `get_run_output(run_id)` — read the last 50 lines of the LAMMPS log
- For RadonPy: `get_job_output(job_id)`

**5. Diagnose — consult the recovery playbook first, then the built-in taxonomy:**

- **Read `guides/RECOVERY_PLAYBOOK.md` if it exists** (a generated, local-only artifact — regenerate from past run_logs via `python -m tools.runlog_miner --playbook -o guides/RECOVERY_PLAYBOOK.md`). If a clustered signature matches this failure's symptom/error, prefer its **Recovery action** — those rows carry an empirical success rate (`k/n`) across past runs, so rank by it and skip low-`n` or low-success rows.
- If the playbook is absent, no row matches, or it has no incidents yet, fall back to the built-in taxonomy below:

| Error string / condition | Root cause | Recovery action |
|---|---|---|
| "lost atoms" | Timestep too large or bad geometry | Re-spawn worker with `dt_fs: 0.5` |
| "out of memory" / GPU OOM | Cell too large for VRAM | Re-spawn with `mpi_ranks` halved |
| "unknown atom type" / segfault on startup | FF assigned before polymerization | Re-spawn molecule-builder from `assign_forcefield` step |
| Energy NaN / diverges in first 100 steps | `density_initial` too high | Re-spawn with `density_initial − 0.10 g/cm³` |
| Density drift > 3% after 2 EXTEND cycles | Won't converge at this density | Restart compress with `density_initial − 0.05 g/cm³` |
| Tg sweep R² < 0.80 or fewer than 4 bins | T range too narrow | Re-run sweep: `T_start + 50 K`, `T_end − 50 K` |
| Tg sweep R² 0.80–0.90 | Borderline bilinear fit | Re-run sweep with `T_step` halved |
| Tg sweep killed mid-run | Process death (OOM, GPU preemption, etc.) | Restart from the last completed temperature (max 2 attempts); if still failing, return the error to the orchestrator |
| `Tg_K` vs `Tg_alternative_K` disagree by >20 K | Noisy density or sweep range doesn't bracket the transition | Increase `N_STEPS_PER_T` or extend the T range |
| `extract_thermal` `fit_quality` POOR despite a clean log | Velocity re-init discontinuity or excessive plateau drift exclusion | Plot `tg_density_bins.csv`; check for velocity re-init (Tg-sweep no-reinit rule) and `n_plateaus_skipped_drift` |
| "Bilinear curve_fit failed" | Sweep log spans <~100 K or collapses to a single bin — defective single-isothermal run, not a staircase | Return FAIL, regenerate the sweep; do NOT tune `initial_tg_guess` |
| RadonPy conformer/charge job `failed` | QM instability | Retry once with `n_conformers` halved; if still fails, use AM1-BCC and note in D-02 |
| "missing FF parameters" (EMC build) | SMILES attachment points wrong | Verify exactly two `*` atoms; try `dp: 15` if `dp: 20` fails |
| Polymerization job hangs in "pending" | Job queue stuck / RadonPy worker crash | Check `list_all_jobs()`; `cancel_job(job_id)` if still pending after a reasonable wait, then resubmit `submit_polymerize_job` |
| EMC stalls/fails on amide-N monomers (pcff lacks the amide/lactam/urea N→carbonyl increment, `{na,c_2}`) | Force field constraint, not a build error | Rescue ladder: primary amide (e.g. polyacrylamide) → OPLS-AA; secondary amide/lactam/urea (e.g. PNIPAM, PVP, PURA) → RadonPy/GAFF2 |
| EMC dies with a negative exit code (`segfault (signal N)`, no `Error:` line) | Monomer/field mismatch (typical: chlorinated monomer on trappe-ua/opls-aa), not an unbuildable SMILES | Continue the field cascade (try pcff next) |
| LAMMPS crashes steps 0–10, wrong style keyword (`fourier` / `none` / `lj/charmm`) | FF directive mismatch: `generate_script` called without explicit FF flag | Confirm `**lammps_flags` is in `params_deform`; re-generate script passing `use_trappe=True` / `use_pcff=True` / `use_opls=True` explicitly |
| Log truncated, no LAMMPS error string, process gone | External kill (OOM killer / GPU preemption) | Identify last completed stage `_out.data` via `ls`; submit remaining stages as new chain from that checkpoint |
| Background waiter never returns after `run_lammps_chain` | `watch_run` sentinel lost on MCP server restart | `grep -r "STAGE COMPLETE" <work_dir>/` — if all stages present, proceed without waiting and mark done in run_log |
| Submit returns `status=error` with `conflicting_writers` | Double-launch guard: a live LAMMPS/MPI process already holds the target log open (concurrent session, or an orphaned chain from a context restart) | Inspect the listed pid/cmd; if it is a stale orphan, `kill <pid>` then resubmit. If it is a legitimate concurrent run, do NOT relaunch — coordinate via user. Pass `allow_concurrent_writer=True` only after confirming the writer is dead/stale |
| "Out of range atoms — cannot compute PPPM" in npt_compress | PPPM ghost region exceeded during high-pressure box shrink | Switch compress stage pair_style to `lj/cut/coul/cut`; skin=3.0 Å; dt=0.5 fs; restore kspace for all production stages |
| K = negative or density at melt value (~0.8–0.9 g/cm³) for a glassy polymer | deform-worker received `npt_production` (melt) data instead of `npt_prod300` (300 K) data | Verify `equil_data_path` is `npt_prod300_out.data`; if `npt_prod300` missing, run the cool+prod 300 K phase first; re-spawn deform-worker |
| `extract_thermal` returns "fewer than 4 temperature bins" after partial sweep kill | Sweep killed before sufficient T coverage | If ≥ 60% of planned T points completed AND both glassy+rubbery slopes present, attempt `extract_thermal`; if fit_quality ≥ ACCEPTABLE accept; else restart full sweep |
| `extract_bulk_modulus` K < 0.1 or > 20 GPa | Not fully equilibrated (`diagnostics.drift_check` warns) | Re-spawn bulk-modulus-extractor with `eq_fraction=0.7` |
| `extract_bulk_modulus` `volume_equilibrated=false` | Volume hasn't settled in the production window | Re-spawn bulk-modulus-extractor with `eq_fraction=0.25`; bracket that K against the original `K_block_mean_GPa` |
| `extract_bulk_modulus_murnaghan` K < 0 or `fit_converged=False` | EOS curvature not resolved at this pressure range | Check `volume_equilibrated` per pressure; glassy: narrow to ±500 atm if ±1000 causes creep; `linear_fallback` underestimates K — add pressure points and re-submit via murnaghan-worker |
| `extract_bulk_modulus_murnaghan` `B0_prime` outside [4, 20] | Pressure range too wide (glass yielding) or too narrow (curvature not captured) | Route to deform-worker fallback, or re-submit murnaghan-worker with a wider pressure series |
| `run_bulk_modulus_series`: one pressure point fails / GPU OOM / empty `log_files` | `npt_steps` too large for available VRAM at that pressure | Reduce `npt_steps` to 200000 and re-submit (check `nvidia-smi`) |
| BACKGROUND-WAIT never returns after murnaghan-worker's `watch_run` call | Worker error: `watch_run` was called with `run_bulk_modulus_series`'s placeholder `monitor_command` string instead of the real `chain_id` — no sentinel was ever created (distinct from the generic "background waiter never returns" row above, which is an MCP-server-restart sentinel loss) | Re-run `watch_run(chain_id)` as a real MCP tool call using the actual `chain_id` |
| `extract_bulk_modulus_deform` `fit_r2_C11`/`fit_r2_C12_yy` < 0.90 | Noisy stress-strain fit | Check `THERMO_FREQ` ≤ 100 in the deform script; if `rate_sensitivity` is present with `verdict=WARNING`, the primary rate was too high — the tool already prefers the slow-rate fit when its own R² clears 0.90 |
| `extract_bulk_modulus_deform` `isotropy_delta_pct` ≥ 20% | Cell too small / not isotropic at this strain | BORDERLINE — Murnaghan should have been primary; re-submit murnaghan-worker with a wider/adjusted pressure series instead |
| Deformation run (`npt_deform`) crashes | `dt_fs` too large for SHAKE + deform | Re-spawn deform-worker with `dt_fs=1.0`; if it still crashes, reduce `STRAIN_RATE` 10× (e.g. 1e-8 instead of 1e-7 /fs) |
| `extract_equilibrated_density` returns <0.5 g/cm³ | Log likely contains the compression ramp, not just the production plateau | Verify `plateau_step_range` starts after the ramp; re-spawn equilibration-checker with `eq_fraction=0.7` |
| `check_equilibration_comprehensive` hangs on a large dump (>~1 GB / >1000 frames) | Trajectory I/O timeout | Do not re-run it — rely on `extract_equilibrated_density` plus the most recent pre-extension comprehensive result instead (structural metrics can't have moved over a short extension of an already-equilibrated cell) |
| GPU crash during NPT production | OOM, bad geometry, or pair-style mismatch | Check the log (do NOT switch to CPU): OOM → reduce system size/GPUs; bad geometry → more minimize steps; pair-style mismatch → check params file |
| Density not converging during equilibration | Insufficient annealing | Add annealing cycles (3–5) |
| Chain droplets / vacuum voids in the packed cell | Initial density too high | Rebuild the cell at `density=0.05` |
| "Out of range atoms — cannot compute PPPM" at `nvt_softheat` step 0→1 (minimize completed) | Localized EMC pack overlap for that seed | Rebuild the cell with a fresh EMC seed; if a second seed also fails, drop `density_initial` 0.6 → 0.5 before any deck edits |
| `generate_equilibration_workflow(extend_only=True)` returns 7 stages instead of 1 | Stale MCP server code — should yield `n_stages==1`, `run_order==["npt_extend"]` | Do NOT submit (its `nvt_softheat` re-melts the cooled glassy cell) and do NOT hand-write a `.in`; request an orchestrator server restart |
| Disk-full mid-chain (equilibration) | Ran out of space partway through the chain | Completed stages' `_out.data` stay intact — free disk, delete only the failed stage's partial outputs, regenerate the workflow with identical params, slice the stage list to resume at the failed stage, resubmit (do NOT restart from stage 0). Prevention: below 60 GB free, strip `dump`/`undump`/`write_dump` from production stages' `.in` — but never from `npt_prod300`/`npt_production` if `tg`/`bulk_modulus` was requested and this SMILES was novel (`system-characterization-analyzer`'s post-PASS refinement reads that dump) |

**`plan_mode=="reasoned"` escalation ladder** (per §2b): a `STRUCTURAL_FAIL` verdict from
`enforce_equilibration_gate` (see `structural_fail_remedy`/`structural_fail_remedy_confidence`
in the equilibration-checker's RESULT block) isn't a log-grep match, so it isn't in the taxonomy
table above — escalate through these rungs in order, spending one attempt each:
1. The named `structural_fail_remedy`:
   - `re_melt_slow_recool` — parameter-level, not a full re-plan: re-melt from the converged
     melt cell with `npt_cool_steps`/`npt_cool300_steps` overridden to 2×/4× baseline across
     the 2 attempts (see "## RE-ANNEAL procedure" below for the exact formula).
   - `heavy_melt_anneal_probe` — no mechanized implementation exists yet (see
     `guides/EQUILIBRATION.md`/`polymer_rules.json`'s NkepsuMbitou-2025 provenance notes);
     treat as a diagnostic investigation, not a parameter to set, and escalate to rung 3 if
     the melt deficit doesn't resolve.
2. If the remedy doesn't resolve it (or `structural_fail_remedy_confidence=low` and it fails
   once), the taxonomy-table fix most consistent with the symptom.
3. A full re-plan with a different force field — routes back through the planner per
   `CLAUDE.md`'s "probe result contradicting a plan assumption" cross-run protocol (re-plan →
   re-critic); counts as one ladder rung, not a restart of the count.
Only after all rungs are exhausted at attempt 5 does UNRESOLVED apply (see Max attempts rule).

**6. Output a recovery plan in this format:**
```
RECOVERY PLAN
  Stage:        <molecule-builder | equilibration | tg-sweep | murnaghan-worker | deform-worker | bulk-modulus-extractor | phase-2>
  Failure:      <exact error string or condition from log>
  Root cause:   <diagnosis from taxonomy above, or structural_fail_remedy for STRUCTURAL_FAIL>
  Action:       <parameter change or step to re-run>
  Worker:       <subagent_type to re-spawn>
  Params changed: <field: old → new>
  Attempt:      <N of max 5 (plan_mode=reasoned) | N of max 2 (plan_mode=deterministic)>
```

**7. Write a RECOVERY block to run_log.md immediately** (before re-spawning anything):
```markdown
## RECOVERY — [Stage] attempt N
- **Trigger:** <error>
- **Diagnosis:** <root cause>
- **Action:** <what changed>
- **Outcome:** pending
```

**Max attempts rule:** the cap is read from `plan_mode` (§2b):
- `plan_mode=="reasoned"` — after **5** recovery attempts spanning the escalation ladder above
  without a clean PASS, stop and write a checkpoint note to run_log.md asking the user to
  review, instead of silently writing `UNRESOLVED`.
- `plan_mode=="deterministic"`, or `run_plan.json` missing/unreadable (conservative default) —
  after **2** attempts (EXTEND-type only; any `STRUCTURAL_FAIL` stops immediately at attempt 1
  per §2b, it is never auto-applied), write `UNRESOLVED` and stop.
Do not attempt a retry beyond the applicable cap without human review.

---

## RE-ANNEAL procedure (`structural_fail_remedy: re_melt_slow_recool`)

Triggered by an equil-checker verdict of `UNDER_ANNEALED_COOLING`: melt density right but cooling
froze in free volume. Do NOT `EXTEND` at 300 K (a glass can't densify below Tg). Re-melt from the
converged **melt** cell (`npt_production_out.data` at T_equil, NOT the 300 K cell) via
`generate_equilibration_workflow`, slowing the cool ramp with the explicit
`npt_cool_steps`/`npt_cool300_steps` overrides. Compute the baseline being overridden, then pass
**2×** it on the first RE-ANNEAL attempt, **4×** on the second (max 2 attempts; if still
under-band, re-classify as `MELT_STAGE_DEFICIT` and record the evidence rather than looping — this
remedy targets a too-fast *cooling* ramp, not a deficient melt, and cannot fix the latter):

- `npt_cool300_steps` (glassy — the T_workflow→300 K leg, the stage most directly implicated
  by "cooling too fast to 300 K"): baseline = `int(1.0e6 / dt_fs)` (~1 ns at the class's
  production timestep).
- `npt_cool_steps` (rubbery, or the melt→target leg when `add_melt_npt=True`): baseline =
  the atom-count tier `generate_equilibration_workflow` would otherwise pick —
  `n_atoms < 5000` → 1,000,000; `< 15000` → 2,000,000; else → 3,000,000 (`n_atoms` is already
  known from this stage's own `inspect_data_file` call).

Pass the multiplied value(s) as `--npt_cool_steps`/`--npt_cool300_steps` on the re-spawned
equilibration-worker's `gen_prompt.py --stage equil` call (reasoned path), or patch
`decided_params.npt_cool_steps`/`npt_cool300_steps` in `run_plan.json` (deterministic path —
flows through `apply_plan()`'s `{**cls, **decided_params}` overlay the same way every other
D-09-style numeric refinement does). Log the multiplier used (2× or 4×) in the RECOVERY block.

---

## Session Recovery (Mode B)

When the Claude process dies while a background waiter is in flight (no tmux, machine reboot, or session killed):

1. `ssh lambda && pj && claude --continue` (or start fresh if conversation unavailable)
2. Read `data/[RUN]/run_log.md` → find the row where `status = monitoring`; note the `id` value
3. Call `get_run_status(id)`:
   - **running** → `watch_run(id)` → relaunch the waiter via BACKGROUND-WAIT (`Bash(command=monitor_command, run_in_background=true)`, the CLAUDE.md canonical pattern) → update run_log back to `monitoring`, then **end your turn**; the harness re-invokes you when it exits. `RUN_COMPLETE` (exit 0) → completed; `PROCESS_DEAD_NO_SENTINEL` (exit 3) → treat as **failed** below.
   - **completed** → update run_log to `done` → continue from the next orchestrator step
   - **failed** → `get_run_output(id)` → diagnose with taxonomy above → re-spawn worker (counts as attempt 1)
   - **not found** → wait 60–90 s for MCP server restart; retry; if still missing, treat as failed
4. `monitor_command` is deterministic — `watch_run(id)` regenerates it from the ID alone; always safe to re-call

If tmux is still alive (B-1): `ssh lambda && pj` to re-attach; the background waiter is still running and will re-invoke the session on exit — no action needed.
