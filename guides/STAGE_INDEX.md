# PolyJarvis Stage Index
**Version:** 1.4 | **Last updated:** March 25, 2026

## Instructions for AI Agent

Read THIS file first. Identify which stage applies to your current task. Then read ONLY that stage file. Do not read ahead.

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
       ├─ PCBN/PAMD/PKTN/PSFO/PIMD  →  EMC (pcff)
       ├─ PHAL                       →  EMC (opls/2024/opls-aa)
       ├─ PHYC/PDIE/PSTR             →  EMC (trappe-ua)
       │    └─ submit_emc_cell_job() → poll → data_path + lammps_flags
       │
       └─ all other classes          →  RadonPy (GAFF2_mod + QM charges)
            └─ build monomer → charges → polymerize → FF → cell → save_lammps_data()
                 (copolymers: alternating / random / block)
                 (blends: mixture_cell from multiple FF-assigned chains)
       │
       └─ [Stage 2] equilibrate locally (compress → anneal → final eq)
            └─ [Stage 3] Tg sweep → extract Tg
                 └─ [Stage 4] RDF, end-to-end vectors, density → validate vs experiment
```

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

---

## When You Span Multiple Stages

If your task covers more than one stage (e.g., "run a full simulation from SMILES to Tg"), read the stage files **sequentially as you reach each stage**. Do not load all of them at once.
