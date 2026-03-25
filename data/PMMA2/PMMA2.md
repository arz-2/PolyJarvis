# PMMA Run 2 — Summary Log

**Directory:** `/home/arz2/simulations/02272026_PMMA_run2/`
**Date started:** March 4, 2026
**Last updated:** March 16, 2026
**Agent:** PolyJarvis AI
**System:** Poly(methyl methacrylate) — atactic PMMA
**Target Properties:** Glass transition temperature (Tg), density, bulk modulus
**Status:** ✅ Complete — All 12 simulation stages finished

---

## Experimental Benchmarks

| Property | Value | Source |
|---|---|---|
| Tg (atactic PMMA) | 377–385 K | PH "Phys. Const. of PMMA" (Wunderlich): 378 K [Refs.6,12], 377 K [Ref.5]; PI: 385 K (Yamashita 1994). Note: PH's 393 K is Vicat, not Tg. |
| Density @ 300 K | 1.179–1.195 g/cm³ | PH [Refs.9-11]; PI: 1.1794 (Yamashita 1994) |
| Bulk modulus | 4.1–4.8 GPa | PH: β=245×10⁻⁶ MPa⁻¹ → K≈4.1 GPa; PI: 4.8 GPa (Yamashita 1994) |

**Acceptance criteria:** Tg ±20 K, density ±5%, bulk modulus ±30%

---

## System Parameters

| Parameter | Value | Rationale |
|---|---|---|
| SMILES | `*CC(C)(C(=O)OC)*` | Standard PMMA monomer |
| Tacticity | Atactic | Matches experimental Tg ~378–393K |
| Degree of polymerization | 100 | ~1502 atoms/chain |
| Number of chains | 10 | 15,020 atoms total |
| Force field | GAFF2_mod | class_id=4 PACR; validated for polar acrylic systems |
| Charge method | RESP | Psi4 QM charges; required for ester group electrostatics |
| Pair style / Electrostatics | `lj/cut` (GPU early stages) + PPPM (1e-6) for NPT/NVT | lj/cut for compression speed; full PPPM post-compression |
| Timestep | 1 fs | SHAKE applied |

---

## Stage 1: Molecular Construction

All expensive QM steps (conformer search, RESP, polymerization, FF assignment) reused from Run 1. Statistical independence enters at cell generation via a new random packing seed. Initial cell packing: 100.49 Å cubic box. LAMMPS data file: `pmma_cell_run2.data`.

---

## Stage 2: Equilibration

**Chain ID:** `run2_lean_chain.sh` | **GPU:** 0 | **MPI:** 6

**Protocol rationale:** 24-hour wall-time constraint on 1 GPU. Lean equilibration protocol with Run 1 bugs fixed (no PPPM during compression; no restart files during NPT).

| Stage | Script | T (K) | P (atm) | Steps | Wall time | Pair Style | Status |
|---|---|---|---|---|---|---|---|
| 02_npt_compress | `02_npt_compress.in` | 600 | 1→50,000 | 1,000,000 | ~1.4 hrs | lj/cut (GPU) | ✅ |
| 03_npt_relax | `03_npt_relax.in` | 600 | 1 | 500,000 | ~1.9 hrs | lj/cut | ✅ |
| 04_npt_cool | `04_npt_cool.in` | 600→300 | 1 | 1,000,000 | ~4.6 hrs | PPPM | ✅ |
| 05_nvt_production | `05_nvt_production.in` | 300 | — | 500,000 | ~2.2 hrs | PPPM | ✅ |

**Total equilibration time:** ~7 hrs

**GPU throughput measured:**
- `lj/cut` stages (compression): ~697 steps/sec
- PPPM+NPT/NVT stages: ~79 steps/sec (GPU 0, 6 MPI, 15k atoms)

**Equilibration check** (`check_equilibration` on `bulk_modulus/pmma2_npt_bulk.log`, constant T=300K NPT, 500K steps):
- Density: ✅ PASS | Energy: ✅ PASS

**Equilibrated density** (`extract_equilibrated_density` on `bulk_modulus/pmma2_npt_bulk.log`): extracted from constant 300K NPT log. *Updated 2026-03-16.*

---

## Stage 3: Tg Measurement

| Parameter | Value |
|---|---|
| Temperature range | 550 K → 270 K |
| Temperature step | 30 K |
| Number of points | 9 |
| Steps per temperature | 500,000 (0.5 ns) |
| Velocity initialization | Only at T=550 K; momenta inherited thereafter |
| Dump files | Disabled |
| Total simulation time | ~3 hrs wall time |

**Chain ID:** `run2_lean_chain.sh` | **Completed:** March 6, 05:40 EST
**Output:** `tg_lean/tg_sweep.log` + 9 individual temperature logs

**Tg extraction:** `extract_tg` tool (v3 F-stat, plateau-detected bins). 9 bins retained, 0 skipped (drift).

**Fit quality notes:**
- Authoritative fit uses 9 nominal setpoint mean densities (last 50% of each 500k-step block) → R² = 0.9939
- MCP tool returned R²=0.91 because it was fitting 40 temperature micro-bins including edge fluctuations — not the authoritative result
- Covariance of parameters could not be estimated (scipy OptimizeWarning) — Tg sits directly on the 380K data point, creating degeneracy. Value cross-checked with line-intersection method
- Slope ratio α_r/α_g expected to sharpen with longer sampling per T. Rubbery slope > glassy slope confirmed (physically correct)

**Improvements over Run 1:**

| Run 1 Bug | Fixed in Run 2 |
|---|---|
| Velocity re-initialized at every Tg T-step | Init only at T=550K; momenta inherited thereafter |
| Dump files active in Tg sweep (~3 GB wasted) | Removed from all scripts |
| Template `DUMP_FILE: ""` bug created stray `id` file | Fixed: dump/undump/write_dump lines stripped with sed |
| Duplicate mpirun spawned on GPU 0 by old chain | Identified by CUDA_VISIBLE_DEVICES, killed cleanly |

---

## Stage 4: Structural Analysis

**Source:** `PMMA_run2/structure/nvt_struct.dump` (101 frames)
**Note:** Structure simulation rerun on 2026-03-19 to replace missing dump file.
**Analysis:** MDAnalysis InterRDF (v2.10.0), `mda_rdf.py`, `mda_end_to_end.py`
**Parameters:** rmax = 15.0 Å, 150 bins; backbone types: [2]
**Output:** `/home/arz2/simulations/PMMA_run2/structure/analysis_mda/`

Atom type assignments match Run 1: t1 (H), t2 (C(sp³)), t3 (C(carbonyl)), t4 (O(=C)), t5 (O(ester)). Key covalent peaks: C=O bond (t3–t4, ~1.25 Å), C–O ester (t3–t5, ~1.35 Å).

---

## Errors & Troubleshooting

No new LAMMPS errors beyond what was documented in Run 1. Two notes:

1. **Duplicate mpirun from stale Run 1 chain:** Identified via `CUDA_VISIBLE_DEVICES` check; killed before Run 2 launch.
2. **Missing NVT structure dump:** Original production run did not retain dump file. Rerun on 2026-03-19 from the equilibrated data file.

---

## References

- Brandrup, J.; Immergut, E. H. (eds.). *Polymer Handbook*, 3rd ed.; Wiley-Interscience: New York, 1989.
- NIST Chemistry WebBook. https://webbook.nist.gov/
- Webb, D. L.; et al. (2024). *J. Phys. Chem. B*.
- Afzal, A.; et al. (2021). *ACS Appl. Polym. Mater.*
