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

**3. Get actual status:**
- For a LAMMPS chain: `get_run_status(chain_id)`
- For a RadonPy/EMC job: `get_job_status(job_id)`

**4. Read the error:**
- `get_run_output(run_id)` — read the last 50 lines of the LAMMPS log
- For RadonPy: `get_job_output(job_id)`

**5. Diagnose — consult the recovery playbook first, then the built-in taxonomy:**

- **Read `guides/RECOVERY_PLAYBOOK.md`** (regenerated from past run_logs by `runlog_miner`). If a clustered signature matches this failure's symptom/error, prefer its **Recovery action** — those rows carry an empirical success rate (`k/n`) across past runs, so rank by it and skip low-`n` or low-success rows.
- If no playbook row matches (or the playbook has no incidents yet), fall back to the built-in taxonomy below:

| Error string / condition | Root cause | Recovery action |
|---|---|---|
| "lost atoms" | Timestep too large or bad geometry | Re-spawn worker with `dt_fs: 0.5` |
| "out of memory" / GPU OOM | Cell too large for VRAM | Re-spawn with `mpi_ranks` halved |
| "unknown atom type" / segfault on startup | FF assigned before polymerization | Re-spawn molecule-builder from `assign_forcefield` step |
| Energy NaN / diverges in first 100 steps | `density_initial` too high | Re-spawn with `density_initial − 0.10 g/cm³` |
| Density drift > 3% after 2 EXTEND cycles | Won't converge at this density | Restart compress with `density_initial − 0.05 g/cm³` |
| Tg sweep R² < 0.80 or fewer than 4 bins | T range too narrow | Re-run sweep: `T_start + 50 K`, `T_end − 50 K` |
| Tg sweep R² 0.80–0.90 | Borderline bilinear fit | Re-run sweep with `T_step` halved |
| RadonPy conformer/charge job `failed` | QM instability | Retry once with `n_conformers` halved; if still fails, use AM1-BCC and note in D-02 |
| "missing FF parameters" (EMC build) | SMILES attachment points wrong | Verify exactly two `*` atoms; try `dp: 15` if `dp: 20` fails |
| LAMMPS crashes steps 0–10, wrong style keyword (`fourier` / `none` / `lj/charmm`) | FF directive mismatch: `generate_script` called without explicit FF flag | Confirm `**lammps_flags` is in `params_deform`; re-generate script passing `use_trappe=True` / `use_pcff=True` / `use_opls=True` explicitly |
| Log truncated, no LAMMPS error string, process gone | External kill (OOM killer / GPU preemption) | Identify last completed stage `_out.data` via `ls`; submit remaining stages as new chain from that checkpoint |
| Background waiter never returns after `run_lammps_chain` | `watch_run` sentinel lost on MCP server restart | `grep -r "STAGE COMPLETE" <work_dir>/` — if all stages present, proceed without waiting and mark done in run_log |
| Submit returns `status=error` with `conflicting_writers` | Double-launch guard: a live LAMMPS/MPI process already holds the target log open (concurrent session, or an orphaned chain from a context restart) | Inspect the listed pid/cmd; if it is a stale orphan, `kill <pid>` then resubmit. If it is a legitimate concurrent run, do NOT relaunch — coordinate via user. Pass `allow_concurrent_writer=True` only after confirming the writer is dead/stale |
| "Out of range atoms — cannot compute PPPM" in npt_compress | PPPM ghost region exceeded during high-pressure box shrink | Switch compress stage pair_style to `lj/cut/coul/cut`; skin=3.0 Å; dt=0.5 fs; restore kspace for all production stages |
| K = negative or density at melt value (~0.8–0.9 g/cm³) for a glassy polymer | deform-worker received `npt_production` (melt) data instead of `npt_prod300` (300 K) data | Verify `equil_data_path` is `npt_prod300_out.data`; if `npt_prod300` missing, run the cool+prod 300 K phase first; re-spawn deform-worker |
| `extract_thermal` returns "fewer than 4 temperature bins" after partial sweep kill | Sweep killed before sufficient T coverage | If ≥ 60% of planned T points completed AND both glassy+rubbery slopes present, attempt `extract_thermal`; if fit_quality ≥ ACCEPTABLE accept; else restart full sweep |

**6. Output a recovery plan in this format:**
```
RECOVERY PLAN
  Stage:        <molecule-builder | equilibration | tg-sweep | murnaghan-worker | deform-worker | bulk-modulus-extractor | phase-2>
  Failure:      <exact error string or condition from log>
  Root cause:   <diagnosis from taxonomy above>
  Action:       <parameter change or step to re-run>
  Worker:       <subagent_type to re-spawn>
  Params changed: <field: old → new>
  Attempt:      <1 or 2 of max 2>
```

**7. Write a RECOVERY block to run_log.md immediately** (before re-spawning anything):
```markdown
## RECOVERY — [Stage] attempt N
- **Trigger:** <error>
- **Diagnosis:** <root cause>
- **Action:** <what changed>
- **Outcome:** pending
```

**Max attempts rule:** After 2 recovery attempts at any stage, write `UNRESOLVED` as the outcome and stop. Do not attempt a third retry without human review.

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
