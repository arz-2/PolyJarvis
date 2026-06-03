# PolyJarvis Stage Index
**Version:** 1.5 | **Last updated:** May 30, 2026

## Multi-Agent Mode

PolyJarvis runs in multi-agent mode by default. The **orchestrator** (main session) reads only `CLAUDE.md` and this file — it never reads stage guides directly. Stage guides are owned exclusively by their worker:

| Worker | Reads | Owns |
|---|---|---|
| `molecule-builder` | `STAGE_1_MOLECULAR_CONSTRUCTION.md` | Build → `.data` file |
| `equilibration-worker` | `STAGE_2_EQUILIBRATION.md` | Validate → submit chain → return chain_id |
| `tg-sweep-worker` | `STAGE_3_TG_MEASUREMENT.md` | Generate script → submit run → return run_id |
| `analysis-worker` | `STAGE_4_ANALYSIS.md` | Extract properties → return RESULTS block |

The orchestrator owns: `classify_polymer`, `Monitor`, checkpoint writes to `run_log.md`, and all recovery decisions. Workers are stateless — see `CLAUDE.md` for the full orchestrator workflow.

---

## Instructions for AI Agent

Read THIS file first. If you are a **worker agent**, identify your stage and read ONLY that stage file. If you are the **orchestrator**, do not read stage files — spawn the appropriate worker instead.

---

## Stage Map

| Stage | File | You are here if... |
|---|---|---|
| **1** | `STAGE_1_MOLECULAR_CONSTRUCTION.md` | You have a SMILES string and need to build a simulation-ready `.data` file |
| **2** | `STAGE_2_EQUILIBRATION.md` | You have a `.data` file and need to equilibrate it |
| **3** | `STAGE_3_TG_MEASUREMENT.md` | You have an equilibrated cell and need to measure Tg |
| **4** | `STAGE_4_ANALYSIS.md` | You have simulation output and need to extract/validate properties |
| **ref** | `TOOLS_REFERENCE.md` | You need complete tool signatures, parameter tables, or the input compatibility matrix |
| **log** | `data/TEMPLATE/run_log.md` | Copy to `data/[RUN]/run_log.md` at task start; fill in real time |

---

## Full Workflow at a Glance

```
SMILES
  └─ [Stage 1] classify_polymer()
       │
       ├─ EMC (pcff — 15 classes):
       │    PCBN PAMD PKTN PSFO PIMD   ← original engineering thermoplastics
       │    POXI PEST PSUL PURT PANH   ← expanded 2026-05-31 (build-tested)
       │    PPHS PACR PIMN PVNL PPNL   ← expanded 2026-05-31 (build-tested)
       │    ⚠ PURT: aliphatic only (aromatic MDI fails)
       │    ⚠ PPHS: alkoxy substituents tested (Cl-substituted untested)
       │
       ├─ EMC (opls/2024/opls-aa): PHAL
       │
       ├─ EMC (trappe-ua): PHYC PDIE PSTR
       │
       │    └─ all EMC paths: submit_emc_cell_job() → poll → data_path + lammps_flags
       │
       └─ RadonPy (GAFF2_mod + QM charges): PSIL PURA only
            (EMC build fails: PSIL missing {si,osi}; PURA missing {n_2,hn})
            └─ build monomer → charges → polymerize → FF → cell → save_lammps_data()
                 (copolymers: alternating / random / block)
                 (blends: mixture_cell from multiple FF-assigned chains)
       │
       └─ [Stage 2] equilibrate locally (compress → anneal → final eq)
            └─ [Stage 3] Tg sweep → extract Tg
                 └─ [Stage 4] RDF, end-to-end vectors, density → validate vs experiment
```

---

## Scope

All 21 polymer classes returned by `classify_polymer()` are routed. Key edge cases:

- **Semicrystalline polymers (PHAL/PVDF, PHYC/PE, PEST/PLA):** Amorphous cells are built; if `check_equilibration_comprehensive` reports `spatial.p2.ordered_flag=True`, flag Tg as ⚠ in RESULTS.
- **EMC routing (19 of 21 classes):** preferred_builder in polymer_rules.json is authoritative. PSIL and PURA are the only RadonPy-only classes (EMC build fails for both). All other classes use EMC.
- **UNKNOWN class (class_id=0):** Fix SMILES (`*` attachment points missing or malformed) and retry — not a pipeline failure.
- **Low-confidence classes (PPHS, PSIL, PPNL, PIMN):** `classify_polymer` emits a warning; record it in D-01 rationale.

---

## Error Recovery

### Equilibration thresholds (Stage 2)

Density drift is measured from the NPT log. For deeply glassy systems (Kapton, PSU at 300 K), gate on *no systematic trend* + density within ±5% of experiment.

| Verdict | Condition | Action |
|---|---|---|
| **PASS** | `check_equilibration_comprehensive` returns `overall_pass=True` | Proceed to Stage 3 |
| **EXTEND** | Any hard gate fails; drift 1–3% | Extend final NPT by 1 ns; re-run check; max 2 extensions |
| **ESCALATE** | Hard gates still failing after 2 extensions | Restart compress with `density_initial` − 0.05 g/cm³ |

### Tg sweep thresholds (Stage 3)

| Verdict | Condition | Action |
|---|---|---|
| **EXCELLENT** | R² ≥ 0.95, F-stat tier EXCELLENT | Report as-is |
| **ACCEPTABLE** | R² 0.90–0.95 | Report with note |
| **BORDERLINE** | R² 0.80–0.90 | Re-run with T_STEP halved before reporting |
| **ABORT** | R² < 0.80 or < 4 temperature bins populated | Widen T range by ±50 K and re-run |

### Common recovery actions

1. **`extract_tg` "fewer than 4 bins"** → Widen T_START +50 K and T_END −50 K; re-run sweep.
2. **EXTEND loop exhausted** → re-run `check_equilibration_comprehensive`; if density ≥ 110% of experimental RT value, restart compress with lower `density_initial`.
3. **EMC "missing FF parameters"** → Verify SMILES has exactly two `*` atoms; try `dp=15` if `dp=20` fails.
4. **`run_lammps_chain` crash** → `get_run_output(run_id)` to read last error; diagnose with table below.

### LAMMPS error taxonomy

| Error string in log | Root cause | Action |
|---|---|---|
| "lost atoms" | Timestep too large or bad starting geometry | Reduce timestep to 0.5 fs; verify data file with `validate_data_file` |
| "out of memory" / GPU OOM | Cell too large for available VRAM | Reduce `mpi` ranks; split across more GPU IDs |
| Segfault on startup / "unknown atom type" | FF assigned before polymerization | Re-run Stage 1 from `assign_forcefield` step |
| Energy NaN / diverges in first 100 steps | Bad initial config or `density_initial` too high | Restart compress with `density_initial` − 0.10 g/cm³ |

### RadonPy QM job failure

If `get_job_status` returns `failed` for a conformer search or charge assignment job: retry once with `n_conformers` halved. If still fails, fall back to AM1-BCC charges and note in DECISIONS D-02 ("RESP failed — AM1-BCC fallback"). Do not retry a third time.

### Max attempts rule

After 2 recovery attempts at any stage, write `UNRESOLVED` as the outcome and record the last error verbatim. Stop the run — no third retry without human review.

---

## Cross-Stage Rules (Always Active — Memorize These)

These apply regardless of stage. They are repeated in each stage file but listed here for emphasis.

0. **`classify_polymer(smiles)` is the first call for any new polymer** — it sets FF, charge method, and electrostatics for the entire workflow
1. **RadonPy path: force field AFTER polymerization** — never before (EMC handles this automatically)
2. **All LAMMPS scripts via `lammps-engine:generate_script()`** — no hand-written `.in` files
3. **Check `nvidia-smi` before every submission — confirm free GPU IDs and use them explicitly**
4. **GPU is used for ALL simulation stages** — always pass explicit `gpu_ids` and `mpi`; never leave them unset or default
5. **Check convergence before extracting properties**
6. **Never report Tg without verifying bilinear fit R²**
7. **Fill `run_log.md` in real time** — log each DECISION row when made, each RECOVERY block immediately after resolving an error; do not reconstruct at the end
8. **Record all seeds before submitting any job** — log EMC seed, SEED_HOT, and SEED_COLD in the run_log header. For replication studies, use fixed seeds from `guides/REVISION_PARAMS.md`. For exploratory runs, read seeds back from job output and log them immediately after submission.

---

## When You Span Multiple Stages

If your task covers more than one stage (e.g., "run a full simulation from SMILES to Tg"), read the stage files **sequentially as you reach each stage**. Do not load all of them at once.
