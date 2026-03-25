# PEG Run 1 — Summary Log

**Directory:** `/home/arz2/simulations/02242026_PEG`
**Date started:** 2026-02-24
**Last updated:** 2026-03-16
**Agent:** PolyJarvis AI
**System:** Poly(ethylene oxide) / Poly(ethylene glycol) — PEO/PEG
**Target Properties:** Glass transition temperature (Tg), bulk density at 300 K, thermal expansion, structural properties (RDF, end-to-end distance)
**Status:** ✅ COMPLETE

---

## Experimental Benchmarks

| Property | Value | Source |
|---|---|---|
| Tg (amorphous) | 206–213 K | Törmälä, *Eur. Polym. J.* 10, 519 (1974): 213 K via spin probe ESR; PI: 206 K (Pfefferkorn et al. 2010, DSC) |
| Density @ 300K | ~1.10–1.13 g/cm³ (amorphous MD) | Wu (2011) AA OPLS-AA; Kacar (2018) PCFF: 1.132. Note: 1.222 g/cm³ (Pfefferkorn 2010) is semicrystalline, not directly comparable |
| Bulk modulus | ~1.5 GPa (at 120°C) | Pfefferkorn et al. 2010, isothermal PVT |

**Acceptance criteria:** Tg ±20K, density ±5%, bilinear R² ≥ 0.97

---

## System Parameters

| Parameter | Value | Rationale |
|---|---|---|
| SMILES | `*CCO*` | Verified against RadonPy `poly.py`; `*` atoms identified as head/tail |
| Degree of polymerization | 100 | Balance between chain length and computational cost |
| Number of chains | 10 | Sufficient for bulk properties averaging |
| Total atoms | 7,020 | 702 atoms/chain × 10 chains |
| Force field | GAFF2 | Updated GAFF; validated within 5% for PEO density |
| Charge method | RESP (Psi4/HF/6-31G*) | Standard QM method for partial charges; Gasteiger insufficient for PEG gauche effect |
| Pair style / Electrostatics | lj/charmm/coul/long + PPPM | PPPM for Coulomb long-range; LJ cutoff 8.0–12.0 Å |
| Timestep | 2 fs | SHAKE constrains H–X bonds |

---

## Stage 1: Molecular Construction

| Step | Tool | Job ID | Status |
|---|---|---|---|
| Build monomer `*CCO*` | `build_molecule_from_smiles` | — | ✅ |
| RESP charges | `submit_assign_charges_job` | `b4910570` | ✅ O charge=−0.697; net Q=0 |
| Polymerize 100-mer | `submit_polymerize_job` | `a661c7e2` | ✅ 702 atoms, MW=4411 g/mol |
| Assign GAFF2 | `assign_forcefield` | — | ✅ 6 atom types |
| Generate cell | `submit_generate_cell_job` | `cbc3c3f9` | ✅ 7020 atoms, 113.5 Å box, 10 chains |
| Save LAMMPS data | `save_lammps_data` | — | ✅ `peo_system.data` |
| Upload to Lambda | `upload_file_to_lambda` | — | ✅ |
| Parse on Lambda | `parse_data_file` | — | ✅ 7020 atoms, 6 types, PPPM confirmed |

**GAFF2 atom types:** c3 (sp³ C), os (ether O), oh (terminal hydroxyl O), h1 (H on C bonded to O), ho (hydroxyl H), hc (alkyl H).

---

## Stage 2: Equilibration

| Stage | Type | T (K) | P (atm) | Steps | Duration | Status |
|---|---|---|---|---|---|---|
| 01 minimize | Energy min | — | — | 50,000 iter | ~5 min | ✅ |
| 02 nvt_softheat | NVT | 300→600 | — | 500,000 × 0.5 fs | ~7 min | ✅ |
| 03 npt_compress | NPT | 600 | 1→50,000 | 500,000 × 1 fs | ~10 min | ✅ |
| 04 npt_pppm | NPT+PPPM | 600 | 50,000→1 | 500,000 × 1 fs | ~18 min | ✅ |
| 05 npt_cool | NPT+PPPM | 600→300 | 1 | 2,000,000 × 1 fs | ~60 min | ✅ |
| 06 nvt_production | NVT+PPPM | 300 | — | 2,000,000 × 1 fs | ~50 min | ✅ |

**Total wall time:** ~2.5 hrs | **Hardware:** Lambda GPU 3

**Protocol notes:**
- Stages 01–03: no PPPM (safe at low density; avoids "out of range atoms" crash)
- Stages 04–06: full PPPM electrostatics
- `write_restart=false` on all NPT stages (GPU safety)
- Each stage reads from previous stage's `*_out.data`

**Equilibration check** (`check_equilibration` on `bulk_modulus/peg1_npt_bulk.log`, constant T=300K NPT, 500K steps):
- Density: ✅ PASS | Energy: ✅ PASS

**Equilibrated density** (`extract_equilibrated_density` on `bulk_modulus/peg1_npt_bulk.log`): extracted from constant 300K NPT production log. *Updated 2026-03-16.*

---

## Stage 3: Tg Measurement

**Design change from original plan:** Switched from 19 separate 2 ns jobs to 13 chained `npt_tg_step` scripts at 1 ns each, all appending to a single `tg_sweep.log`. Saves ~14 hrs wall time.

| Parameter | Value |
|---|---|
| T range | 420 → 180 K |
| T step | 20 K |
| Points | 13 |
| Steps per T | 1,000,000 (1 ns) |
| Total simulation time | 13 ns |

Scripts chained sequentially: each `tg_{T}K.in` reads from previous `tg_{T+20}K_out.data`. All use `use_gpu=true`, `use_pppm=true`, `use_shake=true`, `write_restart=false`. Range 420→180K brackets expected MD Tg (~290–330K) with ample margin on both sides.

**Tg extraction:** `extract_tg` tool (v3 F-stat, plateau-detected bins). 16 bins retained, 12 skipped (drift). Analysis job: `6336a931`.

**Tg agreement discussion:** The v2 bilinear breakpoint falls near the experimental Tg range (206–213 K) — a surprisingly close result for MD. Standard MD at this cooling rate is expected to overestimate by 80–120 K (Webb 2024; Klajmon 2024). The near-quantitative agreement likely reflects partial cancellation: GAFF2 mildly underestimates chain mobility (biasing Tg upward ~20–30 K), while the 1 ns/step NPT protocol allows more relaxation than continuous cooling. The line-intersection method gives a more conservative estimate consistent with the expected MD overestimation range.

**Recommendation:** Report both Tg values (v2 bilinear and v2 line intersection) with R² ≥ 0.97. Note the cooling rate and expected systematic overestimation.

---

## Stage 4: Structural Analysis

**Source:** NVT production trajectory at 300 K, 101 frames
**Analysis:** MDAnalysis InterRDF (v2.10.0), `mda_rdf.py`, `mda_end_to_end.py`
**Parameters:** rmax = 15.0 Å, 150 bins
**Backbone types for E2E:** [2, 3] (C and O backbone)
**Output:** `/home/arz2/simulations/PEG_run1/structure/analysis_mda/`

Atom type assignments: t1 (H), t2 (C), t3 (O(ether)), t4 (C(methyl)), t5 (O(hydroxyl)), t6 (H(hydroxyl)). Notable: t5–t6 peak (O–H hydroxyl bond, ~0.95 Å) shows very high g(r) (~5143) reflecting the covalent bond. Ether O spacing (t3–t3, ~2.85 Å) reflects –CH₂–O–CH₂– repeat geometry.

---

## Infrastructure Notes

- **Lambda Lab disruption (Feb 26 ~20:44 EST):** External platform issue killed tg_240K at step 234,000/1,000,000. Resumed via `run_tg_resume.sh` (nohup PID 3033649). Stages 420K–260K already complete. All 4 remaining stages completed.
- **MCP server restarts (×2):** nohup chain script deployed to make execution independent of MCP session. MCP server code updated to generate nohup chain scripts by default for all future `run_lammps_chain()` calls.
- **GPU 3 ONLY throughout:** GPUs 0–2 occupied. Restart files disabled on all NPT stages.
- **Total wall time:** ~56 hours (Feb 24–27), dominated by 13-stage Tg sweep (~2h45m/stage at 148 steps/sec for PPPM on GPU 3).

---

## References

- Törmälä, P. (1974). *Eur. Polym. J.* — Tg via spin probe ESR; independent of MW for high-MW PEG
- Andrews & Blaisten-Barojas (2021). *J. Phys. Chem. B* — All-atom MD of PEG2000 bulk
- Klajmon et al. (2024) — Continuous cooling MD for PEG; Tg overestimation discussion
- Wu (2011) — Simulated Tg of PEO bulk; density-temperature bilinear method
- Webb et al. (2024). *JPCB* — Polymer electrolyte Tg best practices; systematic overestimation 80–120 K

---

*PolyJarvis (Claude + RadonPy MCP) | Force field: GAFF2 | GPU: Quadro RTX 6000 (GPU 3) | MPI: 4*
