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

| Error string in log | Root cause | Recovery action |
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

**6. Output a recovery plan in this format:**
```
RECOVERY PLAN
  Stage:        <molecule-builder | equilibration | tg-sweep>
  Failure:      <exact error string from log>
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
