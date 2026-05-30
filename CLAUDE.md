# PolyJarvis

AI agent for autonomous polymer MD simulation. Given a SMILES string, runs the full pipeline — molecular construction (RadonPy/EMC MCP servers) → equilibration → Tg sweep → property extraction (LAMMPS engine MCP server, local GPU) — and reports Tg, density, and bulk modulus validated against experiment.

Read `guides/STAGE_INDEX.md` first on every task.

---

## Run Log

Copy `data/TEMPLATE/run_log.md` to `data/[RUN]/run_log.md` at task start. Fill it in real time — not reconstructed at the end.

The **RECOVERIES section is the primary evidence of agent value** over base RadonPy (which retries blindly without diagnosis). Write a RECOVERY block immediately after resolving any LAMMPS or pipeline failure:

```
[Stage N]  <one-line error description>
           Diagnosis: <root cause>
           Fix: <specific change made>
           Outcome: <converged / failed again / escalated>
```

If the run completes without errors, write `None` in RECOVERIES.

---

## Auto-continuation after simulation

After every `run_lammps_chain`, `run_lammps_script`, or analysis tool call:

```
1. result = run_lammps_chain(...)          # submit
2. w = watch_run(result["chain_id"])       # get monitor command
3. Monitor(command=w["monitor_command"])   # block until done — harness re-invokes Claude
4. continue workflow                       # Claude picks up here automatically
```

Never poll `get_run_status` in a loop. The Monitor tool + sentinel file is how PolyJarvis
avoids requiring the user to manually re-trigger Claude after each simulation stage.

---

## Force Field Routing

`classify_polymer` returns `class_name`. Route as follows:

| class_name | Builder | FF | `lammps_flags` |
|---|---|---|---|
| PCBN, PAMD, PKTN, PSFO, PIMD | EMC | PCFF class2 | `use_pcff=True, use_opls=False` |
| PHAL | EMC | OPLS-AA 2024 | `use_pcff=False, use_opls=True` |
| PHYC, PDIE, PSTR | EMC | TraPPE-UA | `use_pcff=False, use_opls=False` |
| PVNL, PACR, POXI, PSUL, PEST, PURT, PURA, PANH, PIMN, PSIL, PPHS, PPNL | RadonPy | GAFF2_mod + QM charges | `use_pcff=False, use_opls=True` |

**EMC path:** `get_emc_job_output()` returns `lammps_flags` — pass directly to `generate_script()` and `generate_equilibration_workflow()`. No manual flag lookup needed.

**PCFF note:** `use_pcff=True` sets class2 bond/angle/dihedral/improper styles, `lj/class2/coul/long` pair style, `special_bonds lj/coul 0 0 1`, `mix sixthpower tail yes`, and disables SHAKE.

---

## Decision IDs

Fill the DECISIONS table in run_log.md at each point below. Hooks will prompt you at the right moment.

**EMC path** (PCBN, PAMD, PKTN, PSFO, PIMD, PHAL, PHYC, PDIE, PSTR):

| ID | Decision | Trigger |
|----|----------|---------|
| D-01 | Force field (auto from polymer_class — record `field` from submit response) | `classify_polymer` returns |
| D-02 | Charge method | `"embedded in FF"` — no action |
| D-03 | Electrostatics | from `lammps_flags` in `get_emc_job_output` |
| D-04 | System size (dp, ntotal) | Before calling `submit_emc_cell_job` |
| D-05 | Convergence verdict | `check_equilibration` returns |
| D-06 | Tg fit quality + Tg value | `extract_tg` returns |

**RadonPy path** (all other classes):

| ID | Decision | Trigger |
|----|----------|---------|
| D-01 | Force field (GAFF2 vs GAFF2_mod) | `classify_polymer` returns |
| D-02 | Charge method (RESP vs AM1-BCC vs Gasteiger) | `classify_polymer` returns |
| D-03 | Electrostatics (PPPM vs lj/cut) | `classify_polymer` returns |
| D-04 | System size (DP, chains) | Before calling `submit_generate_cell_job` |
| D-05 | Convergence verdict | `check_equilibration` returns |
| D-06 | Tg fit quality + Tg value | `extract_tg` returns |

---

## Convergence and Error Recovery

### Equilibration thresholds (Stage 2)

| Verdict | Condition | Action |
|---|---|---|
| **PASS** | Density drift < 1% over last 500 ps of NVT production; energy stable | Proceed to Stage 3 |
| **EXTEND** | Drift 1–3% | Run `check_equilibration_extended`; extend NVT production by 1 ns; max 2 extensions |
| **ESCALATE** | Drift > 3% after 2 extensions | Log in RECOVERIES; check density vs. target ±10% (over-densification?); restart compress stage with `density_initial` reduced by 0.05 g/cm³ |

### Tg sweep thresholds (Stage 3)

| Verdict | Condition | Action |
|---|---|---|
| **EXCELLENT** | R² ≥ 0.95, F-stat tier EXCELLENT | Report as-is |
| **ACCEPTABLE** | R² 0.90–0.95 | Report with note |
| **BORDERLINE** | R² 0.80–0.90 | Re-run with T_STEP halved before reporting |
| **ABORT** | R² < 0.80 or < 4 temperature bins populated | Widen T range by ±50 K and re-run |

### Common recovery actions

1. **`extract_tg` "fewer than 4 bins"** → Widen T_START +50 K and T_END −50 K; re-run sweep.
2. **`check_equilibration` EXTEND loop exhausted** → Run `check_equilibration_extended`; if density ≥ 110% of experimental RT value, over-densification is likely — restart from compress stage with lower `density_initial`.
3. **EMC build "missing FF parameters"** → Verify SMILES has exactly two `*` atoms and correct functional group placement (see TOOLS_REFERENCE SMILES conventions); try `dp=15` if `dp=20` fails.
4. **`run_lammps_chain` crash mid-chain** → Call `get_run_output(run_id)` to read last error; "out of memory" → reduce MPI ranks; "lost atoms" → reduce timestep to 0.5 fs.
