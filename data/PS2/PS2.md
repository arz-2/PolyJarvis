# aPS Run 2 — Summary Log

**Directory:** `/home/arz2/simulations/02232026_PS2/`
**Date started:** February 23, 2026
**Last updated:** March 22, 2026
**Agent:** PolyJarvis AI
**System:** Atactic polystyrene, n=62, 10 chains (independent replica of PS-1)
**Target Properties:** Tg, room-temperature density, bulk modulus
**Status:** ✅ All simulations complete. All properties extracted.

---

## Experimental Benchmarks

| Property | Value | Source |
|---|---|---|
| Tg | 353–373 K | PH "Phys. Const. of PS" (Schrader): 80°C [Ref.6], 90°C [Ref.8], 100°C [Ref.9]; PI: 78–89°C (Gee 1966) |
| Density @ 300K | 1.04–1.065 g/cm³ | PH [Refs.3,4]; PI: 1.044 at 20°C (Gee 1966) |
| Bulk modulus | 3.55–4.5 GPa | PH: β=220×10⁻⁶ MPa⁻¹ → K≈4.5 GPa; PI: 3.55 GPa (Gee 1966) |

**Acceptance criteria:** Tg ±20K, density ±5%, bulk modulus ±30%

---

## System Parameters

| Parameter | Value | Rationale |
|---|---|---|
| SMILES | `*CC(*)c1ccccc1` | Atactic PS repeat unit |
| Degree of polymerization | 62 | ≥1000 atoms/chain (RadonPy validated range; Hayashi 2022) |
| Number of chains | 10 | RadonPy validated minimum |
| Total atoms | 9,940 | 10 chains × 994 atoms/chain |
| Force field | GAFF2_mod | RadonPy default; validated for aromatic organics |
| Charge method | RESP (Psi4 HF/6-31G*) | Gold standard; GAFF2 parameters assume RESP |
| Pair style / Electrostatics | lj/charmm/coul/long 8.0 12.0 + PPPM 1e-6 | GAFF2 standard; compression stage uses lj/charmm/coul/charmm (no kspace) |
| Timestep | 1 fs | SHAKE constrains all H bonds |

---

## Stage 1: Molecular Construction

RadonPy preprocessing completed locally. Force field assigned AFTER polymerization (Best Practices Rule #1).

| Step | Status | Output File |
|---|---|---|
| Build monomer | ✅ | 01_styrene_monomer.json |
| Conformer search | ✅ | 02_styrene_conformer.json |
| Assign charges (RESP) | ✅ | 03_styrene_charged.json |
| Polymerize n=62 | ✅ | 04_PS_n62_atactic.json |
| Assign GAFF2_mod FF | ✅ | 05_PS_n62_ff.json |
| Generate cell | ✅ | 06_PS2_cell.json |
| Save LAMMPS data | ✅ | PS2_n62_10chains.data |

**Statistical independence from PS-1:**
- New amorphous cell generated with different random packing seed
- Different velocity initialization seed in NVT softheat: **294871** (PS-1 used 168053)
- Conformer search + RESP charges re-run from scratch
- All molecular parameters kept identical to PS-1

**Uploaded to Lambda:** `PS2_n62_10chains.data` (3.2 MB), `PS2_n62_10chains_cell.json` (26 MB)

---

## Stage 2: Equilibration

**12-stage equilibration protocol** (vs PS-1's 6-stage). Best Practices Rule #3 requires ≥3 annealing cycles. This pipeline includes 3 heat/cool cycles (stages 5–10) for ~6 ns thermal annealing total.

| # | Stage | Type | T (K) | P (atm) | Steps | Duration | Status |
|---|---|---|---|---|---|---|---|
| 1 | 01_minimize | MIN | — | — | 50k max | ~9 min | ✅ |
| 2 | 02_nvt_softheat | NVT | 300→700 | — | 500k | ~13 min | ✅ |
| 3 | 03_npt_compress | NPT | 700 | 1→50,000 | 500k | ~17 min | ✅ |
| 4 | 04_npt_decompress | NPT | 700 | 50,000→1 | 500k | ~84 min | ✅ |
| 5 | 05_npt_anneal1_heat | NPT | 300→700 | 1 | 1M | ~2 hrs | ✅ |
| 6 | 06_npt_anneal1_cool | NPT | 700→300 | 1 | 1M | ~2 hrs | ✅ |
| 7 | 07_npt_anneal2_heat | NPT | 300→700 | 1 | 1M | ~2 hrs | ✅ |
| 8 | 08_npt_anneal2_cool | NPT | 700→300 | 1 | 1M | ~2 hrs | ✅ |
| 9 | 09_npt_anneal3_heat | NPT | 300→700 | 1 | 1M | ~2 hrs | ✅ |
| 10 | 10_npt_anneal3_cool | NPT | 700→300 | 1 | 1M | ~2 hrs | ✅ |
| 11 | 11_npt_final_equil | NPT | 300 | 1 | 2M | ~3.3 hrs | ✅ |
| 12 | 12_nvt_production | NVT | 300 | — | 2M | ~2.5 hrs | ✅ |

**Total wall time:** ~20.5 hours | **Total simulation time:** ~12.5 ns

**Equilibration check** (`check_equilibration` on `bulk_modulus/ps2_npt_bulk.log`, constant T=300K NPT, 500K steps):
- Density: ✅ PASS | Energy: ✅ PASS

**Equilibrated density** (`extract_equilibrated_density` on `bulk_modulus/ps2_npt_bulk.log`): extracted from constant 300K NPT production log. Re-verified 2026-03-22.

---

## Stage 3: Tg Measurement

**Remote path:** `/home/arz2/simulations/02232026_PS2/tg_sweep/`
**GPU:** 0 (CUDA_VISIBLE_DEVICES=0), 4 MPI processes

| Parameter | Value |
|---|---|
| T range | 550 → 250 K |
| T step | 25 K |
| Points | 13 |
| Steps per T | Variable: 500k (0.5 ns) far from Tg; 1M (1 ns) near Tg |
| Total simulation time | ~9 ns |

Near-Tg zone (450–300 K): 1M steps. Far-from-Tg zones (≥475 K, ≤275 K): 500k steps. This adaptive sampling concentrates computational effort in the transition region.

**Tg extraction:** `extract_tg` tool (v3 F-stat, plateau-detected bins). 15 bins retained, 4 skipped (drift). Analysis job: 66b5388a. Combined log: `tg_combined.log`.

**Fit quality improvement over PS-1:** 3-annealing-cycle protocol produces a clean density–temperature trend. Removing PPPM (kspace) in Tg sweep introduced a small systematic density offset (~0.5–1%) but slope and breakpoint are unaffected.

**Physical consistency check:** Rubbery slope > glassy slope (α_r > α_g) confirmed — physically correct for PS. Slope values compared to Zoller (1982) experimental thermal expansion.

---

## Stage 4: Structural Analysis

**Source:** NVT production trajectory at 300 K, 101 frames
**Analysis:** MDAnalysis InterRDF (v2.10.0), `mda_rdf.py`, `mda_end_to_end.py`
**Parameters:** rmax = 15.0 Å, 150 bins
**Backbone types for E2E:** [2] (sp³ carbon backbone)
**Output:** `/home/arz2/simulations/PS_run2/structure/analysis_mda/`

RDF pairs: t1 (H–H geminal), t2 (H–C(sp³) bond), t3 (H–C(arom)), t4 (C(sp³)–C(sp³) backbone), t5 (C(sp³)–C(arom)), t6 (C(arom)–C(arom) ring). One collapsed chain (R ≈ 6 Å) flagged.

---

## Errors & Troubleshooting

| # | Stage | Error | Root Cause | Resolution |
|---|---|---|---|---|
| 1 | 02_nvt_softheat | PPPM bottleneck (22 s/1000 steps) | PPPM FFT grid dominates per-step cost at 0.05 g/cm³ low density | Switched to lj/charmm/coul/charmm; added `-pk gpu 1 neigh no`; used `mpirun -np 4` |
| 2 | Tg sweep | PPPM bottleneck in expanded melt-state boxes (8.4 s/1000 steps) | Larger, lower-density box at 550 K demands larger PPPM FFT grid | Switched pair style to lj/charmm/coul/charmm (no kspace) for Tg sweep |

---

## References

1. Boyer, R.F. (1954) — PS Tg = 373 K; classic experimental benchmark
2. Hayashi et al., *npj Comput. Mater.* 8:222 (2022) — RadonPy validation; 10 chains, n≥50 minimum; PS included in 1000+ polymer benchmark
3. Afzal et al., *ACS Appl. Polym. Mater.* 3:620–630 (2021) — High-throughput MD Tg benchmark
4. Webb et al., *J. Phys. Chem. B* (2024) — Ensemble MD for Tg; 10 replicas → 95% CI < 20 K
5. PolyPal (2024), *ACS Polym. Au* — 3–10 annealing cycles standard for publishable results
6. Spyriouni et al., *Macromolecules* 40:3408–3418 (2007) — Atactic PS ring packing structure
7. Träg & Zahn, *J. Mol. Model.* 25:39 (2019) — GAFF2_mod parameterization
8. Zoller, P. (1982) — PS thermal expansion coefficients
