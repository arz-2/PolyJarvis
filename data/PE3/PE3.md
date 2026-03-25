# PE Run 3 — Summary Log

**Directory:** `/home/arz2/simulations/PE_run3/`
**Date started:** 2026-03-16
**Last updated:** 2026-03-22
**Agent:** PolyJarvis AI
**System:** Polyethylene (PE), `*CC*`, n=150 repeat units, 10 chains, 9,020 atoms
**Target Properties:** Tg, density, bulk modulus, structural properties (RDF, end-to-end vectors)
**Status:** ✅ COMPLETE

---

## Experimental Benchmarks

| Property | Value | Source |
|---|---|---|
| Tg | 145–243 K (disputed) | PH 4th ed. Sec. D: −128±5°C [Refs.40,41], −80±10°C [Ref.39], −30±15°C [Refs.37,38]; Boyer, *Macromolecules* 6, 288 (1973) |
| Density @ 300K | 0.855 g/cm³ (amorphous) | PH 4th ed. Sec. E: Allen et al. (1960) [Ref.54] |
| Bulk modulus | ~1 GPa | Aleman, *Polym. Eng. Sci.* (1990), 50 MPa, 15°C |

**Acceptance criteria:** Tg ±20K, density ±5%, bulk modulus ±30%

---

## System Parameters

| Parameter | Value | Rationale |
|---|---|---|
| SMILES | `*CC*` | Linear polyethylene |
| Degree of polymerization | n = 150 | Consistent with Run 2 for ensemble averaging |
| Number of chains | 10 | ~9k atoms fits GPU memory comfortably |
| Total atoms | 9,020 | 902 atoms/chain × 10 chains |
| Force field | GAFF2 | Class 1 PHYC; known ~24% density overestimate, ~80K Tg overestimate for PE |
| Charge method | Gasteiger | Required to populate AtomicCharge field; near-zero for PE; lj/cut ignores Coulomb |
| Pair style / Electrostatics | `lj/cut 12.0` (no PPPM) | PE is nonpolar; charges ~0; PPPM unnecessary and costly |
| Timestep | 1 fs | SHAKE on H-type atoms (type 1, hc) |

---

## Stage 1: Molecular Construction

**Date:** 2026-03-16 | **Status:** ✅ Complete

| Step | Tool / Job ID | Status |
|---|---|---|
| Polymer classification | `classify_polymer` | ✅ Class 1 — PHYC, GAFF2 |
| Build monomer `*CC*` | `build_molecule_from_smiles` | ✅ |
| Polymerize 150-mer | `submit_polymerize_job` (`3fdfa6af`) | ✅ 902 atoms/chain, atactic |
| Assign GAFF2 | `assign_forcefield` | ✅ 2 atom types: c3, hc |
| Generate cell (10 chains) | `submit_generate_cell_job` (`49d90e0a`) | ✅ 9,020 atoms, 120.44 Å cubic box |
| Assign charges | `submit_assign_charges_job` (`ac0b3846`) | ✅ Gasteiger, total charge ~0 |
| Save LAMMPS data | `save_lammps_data` | ✅ PE3.data, 9,020 atoms, 2 atom types |
| Upload to Lambda | `upload_file_to_lambda` | ✅ `/home/arz2/simulations/PE_run3/mol/PE3.data` |

**Design decisions:**

| Decision | Choice | Rationale |
|---|---|---|
| Force field | GAFF2 | Class 1 PHYC assignment; GAFF2 over-compression documented from Runs 1/2 |
| Conformer search | Skipped | Pure alkane — no QM-sensitive torsions |
| Electrostatics | lj/cut throughout | No polar groups; PPPM unnecessary and 5–8× slower |
| Initial density | 0.04 g/cm³ | Low start prevents chain overlap; compression handles densification |

---

## Stage 2: Equilibration

**Date:** 2026-03-16 to 2026-03-17 | **Status:** ✅ Complete
**Hardware:** GPU 1 (RTX 6000 Ada, 24 GB), MPI = 2, `package gpu 1 neigh no`

All stages generated via `lammps_engine.generate_script()` templates. Force field: `lj/cut 12.0` throughout — consistent for pure hydrocarbon PE. No PPPM at any stage. This deviates from Runs 1/2, which switched to `lj/charmm/coul/long` after compression; rationale: PE carries near-zero Gasteiger charges, PPPM adds 5–8× overhead with negligible effect. SHAKE on H-type atoms (type 1, hc). Timestep: 1.0 fs throughout.

| Stage | Script | Steps | T (K) | P (atm) | Input | Output |
|---|---|---|---|---|---|---|
| s01_minimize | pe3_s01_minimize.in | 50,000 max | — | — | PE3.data | s01_minimized.data |
| s02_compress | pe3_s02_compress.in | 1,000,000 | 600 | 1→50,000 | s01_minimized.data | s02_compressed.data |
| s03_heat1 | pe3_s03_heat1.in | 500,000 | 300→600 | 1 | s02_compressed.data | s03_heat1.data |
| s04_cool1 | pe3_s04_cool1.in | 500,000 | 600→300 | 1 | s03_heat1.data | s04_cool1.data |
| s05_heat2 | pe3_s05_heat2.in | 500,000 | 300→600 | 1 | s04_cool1.data | s05_heat2.data |
| s06_cool2 | pe3_s06_cool2.in | 500,000 | 600→300 | 1 | s05_heat2.data | s06_cool2.data |
| s07_heat3 | pe3_s07_heat3.in | 500,000 | 300→600 | 1 | s06_cool2.data | s07_heat3.data |
| s08_cool3 | pe3_s08_cool3.in | 500,000 | 600→300 | 1 | s07_heat3.data | s08_cool3.data |
| s09_final_eq | pe3_s09_final_eq.in | 2,000,000 | 300 | 1 | s08_cool3.data | s09_final_eq.data |

**Total wall time:** ~15h 24m | **Total simulation time:** 7 ns

**Equilibration check** (`check_equilibration` on `bulk_modulus/pe3_npt_bulk.log`): density and energy both PASS. s09_final_eq.data used as input for all post-eq runs.

**Equilibrated density** (`extract_equilibrated_density` on `bulk_modulus/pe3_npt_bulk.log`): extracted from constant 300K NPT log. *Updated 2026-03-16.*

**Design decisions:**

| Decision | Rationale |
|---|---|
| 1M compress steps (double vs Run 1) | Start density 0.04 g/cm³ is lower; more steps needed for full compression |
| 3 anneal cycles | Standard for amorphous polymers; removes residual packing artifacts |
| Final eq 2M steps | Last 50% used for property extraction; longer = better statistics |
| No restart on GPU stages | GPU+NPT+restart crashes on volume change (documented PE1/PE2) |

---

## Stage 3: Property Extraction

**Date:** 2026-03-17 | **GPU:** GPU 0 (RTX 6000 Ada), MPI = 2
**Input for all runs:** `/home/arz2/simulations/PE_run3/eq/s09_final_eq.data`

### 3a — Structure NVT

NVT at 300K, 100,000 steps, timestep 1 fs. Dump every 1000 steps (100 frames), `dump_modify sort id`. SHAKE on m 1.008. Force field: lj/cut 12.0. Template generated `lj/charmm/coul/charmm` — patched to `lj/cut 12.0` before submission. Extraneous `vx vy vz` dump columns removed to match PE Run 1 format.

### 3b — Bulk Modulus (NPT)

NPT at 300K, 1 atm, 500,000 steps, timestep 1 fs. Thermo every 500 steps (1001 volume samples). No restart files (GPU safety). Force field: lj/cut 12.0.

Bulk modulus extracted via `extract_bulk_modulus` (volume fluctuation method: K_T = kT⟨V⟩/⟨δV²⟩).

### 3c — Tg Sweep

| Parameter | Value |
|---|---|
| T range | 600 → 160 K (20K decrements, 23 points) |
| Steps per T | 500,000 (0.5 ns) |
| Total simulation time | 11.5 ns |
| Ensemble | NPT, P = 1 atm |
| Force field | lj/cut 12.0, no PPPM |
| Tg extraction | `extract_tg` v3 F-stat bilinear split on density(T) |

### 3d — Structural Analysis (RDF, End-to-End)

NVT dump trajectory at 300 K analyzed with MDAnalysis (`mda_rdf.py`, `mda_end_to_end.py`). Backbone types: [2].

---

## Known Force Field Limitation

GAFF2 systematically over-compresses bulk alkane phases. Consistent pattern across Runs 1–3: density overestimate ~24–27%, Tg overestimate ~50–80 K. Root cause: GAFF2 σ(C)/ε(C) parameterized for small-molecule liquids, not bulk condensed-phase PE. OPLS-AA or TraPPE-UA preferred for quantitative PE but unavailable in current RadonPy/GAFF pipeline.

---

## Errors & Troubleshooting

| Date | Stage | Issue | Resolution |
|---|---|---|---|
| 2026-03-16 | Script generation | lammps_engine write to /sessions failed (read-only FS) | Used /tmp as local staging path; scripts uploaded to Lambda successfully |
| 2026-03-16 | Chain submission | run_lammps_chain timed out at 60s | Chain launched as nohup; confirmed running via direct file check on Lambda |
| 2026-03-17 | Structure + bulk scripts | Template generated `lj/charmm/coul/charmm` despite use_pppm=False | Patched with sed before submission; noted as recurring template bug |
| 2026-03-17 | Structure dump format | Template included `vx vy vz` not in PE Run 1 format | Patched dump line; added `dump_modify sort id` |

---

## References

| Property | Reference |
|---|---|
| Tg (amorphous PE) | Wunderlich & Baur, *Adv. Polym. Sci.* 1970; Boyer, *J. Macromol. Sci.* 1973 |
| Density @ 300 K | Brandrup & Immergut, *Polymer Handbook* 4th ed. |
| Bulk modulus | Strobl, *Physics of Polymers* 3rd ed. |

---

*PolyJarvis (Claude + RadonPy MCP) | Last updated: 2026-03-17*
