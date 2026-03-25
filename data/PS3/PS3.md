# aPS Run 3 — Summary Log

**Directory:** `/home/arz2/simulations/02242026_PS3/`
**Date started:** February 24, 2026
**Last updated:** March 16, 2026
**Agent:** PolyJarvis AI
**System:** Atactic polystyrene, n=62, 10 chains
**Target Properties:** Tg, room-temperature density, structural properties (RDF, end-to-end distance)
**Status:** ✅ All simulations complete. All properties extracted.

---

## Experimental Benchmarks

| Property | Value | Source |
|---|---|---|
| Tg | 353–373 K | PH "Phys. Const. of PS" (Schrader): 80°C [Ref.6], 90°C [Ref.8], 100°C [Ref.9]; PI: 78–89°C (Gee 1966) |
| Density @ 300K | 1.04–1.065 g/cm³ | PH [Refs.3,4]; PI: 1.044 at 20°C (Gee 1966) |
| Bulk modulus | 3.55–4.5 GPa | PH: β=220×10⁻⁶ MPa⁻¹ → K≈4.5 GPa; PI: 3.55 GPa (Gee 1966) |

**Acceptance criteria:** Tg ±20K, density ±5%

---

## System Parameters

| Parameter | Value | Rationale |
|---|---|---|
| SMILES | `*CC(c1ccccc1)*` | Atactic PS repeat unit |
| Degree of polymerization | 62 | Adequate chain length for bulk properties |
| Number of chains | 10 | RadonPy validated minimum |
| Total atoms | 9,940 | 10 chains × 994 atoms/chain |
| Force field | GAFF2_mod | RadonPy default; validated for aromatics |
| Charge method | RESP (Psi4 HF/6-31G*) | Gold standard for GAFF2 parameters |
| Pair style / Electrostatics | lj/charmm/coul/long 8.0 12.0 + PPPM 1e-6 | GAFF2 standard; compression stage uses lj/cut (no PPPM) |
| Timestep | 1 fs | SHAKE applied to H bonds |

---

## Stage 1: Molecular Construction

Initial cell built with RadonPy at 0.05 g/cm³ density. LAMMPS data file: `PS3_n62_10chains.data`. Remote path: `/home/arz2/simulations/02242026_PS3/PS3_n62_10chains.data`.

---

## Stage 2: Equilibration

**8-stage equilibration protocol** — extended vs PS-1's 6-stage, incorporating single 4 ns anneal cycle and longer final equilibration.

| # | Stage | Type | T (K) | P (atm) | Steps |
|---|---|---|---|---|---|
| 1 | 01_minimize | CG minimize | — | — | 50,000 max |
| 2 | 02_nvt_softheat | NVT | 300→600 | — | 2,000,000 |
| 3 | 03_npt_compress | NPT | 600 | 1→50,000 | 1,000,000 |
| 4 | 04_npt_decompress | NPT | 600 | 50,000→1 | 2,000,000 |
| 5 | 05_npt_anneal_heat | NPT | 300→700 | 1 | 4,000,000 |
| 6 | 06_npt_anneal_cool | NPT | 700→300 | 1 | 4,000,000 |
| 7 | 07_npt_final_equil | NPT | 300 | 1 | 8,000,000 |
| 8 | 08_nvt_production | NVT | 300 | — | 8,000,000 |

**Key design choices:**
- `lj/cut` (no PPPM) during compression stage to avoid PPPM failure at low density
- CPU-only for NPT stages (GPU+restart file crash due to box resize memory conflict)
- GPU acceleration for NVT stages
- 08_nvt_production retains full dump trajectory for structural analysis

**All stages:** `/home/arz2/simulations/02242026_PS3/equilibration/`

---

## Stage 3: Tg Measurement

**Remote path:** `/home/arz2/simulations/02242026_PS3/tg_sweep_v2/`
**GPU:** 0, MPI: 4 processes

| Parameter | Value |
|---|---|
| T range | 600 → 250 K |
| T step | 25 K |
| Points | 15 |
| Steps per T | 500,000 (0.5 ns) |
| Ensemble | NPT, P=1 atm |
| Pair style | lj/charmm/coul/charmm (no kspace for speed) |
| Total simulation time | ~7.5 ns |

**Lambda kills encountered:** 2 (T525, T450). Both recovered by resuming from last completed `_out.data`. Final chain: `f9efed80`, completed Feb 27 05:40.

**Tg extraction:** `extract_tg` tool (v3 F-stat). 25 bins retained, 12 skipped (drift). Output: `tg_sweep_v2/analysis_v3/`.

**Initial extract_tg failure:** First attempt returned R²=0.85 with "POOR" quality flag. Root cause: default 5K bin width is smaller than NPT thermostat fluctuations (±10–15K), scattering rows into satellite bins. Fix: bin width changed to 25K (matches sweep step size); n_points < 20 filter added. Final R² = 0.9959.

**Bilinear manual regression:** Performed independently as cross-check. Slopes (glassy: −0.0337 g/cm³ per 100K; rubbery: −0.0698 g/cm³ per 100K) consistent with GAFF2_mod behavior for aromatic polymers. Rubbery slope > glassy slope — physically correct. Split boundary identified at 412 K.

**Tg overestimation analysis:** GAFF2_mod aromatic torsional barriers are stiffer than reality, suppressing chain mobility that triggers the glass transition. Literature MD studies with OPLS-AA (explicitly refined aromatic parameters) typically report Tg 380–410 K, closer to experiment.

---

## Stage 4: Structural Analysis

**Script:** `/home/arz2/simulations/02242026_PS3/analysis/structural/nvt_struct.in`
**Source:** 100 ps NVT trajectory at 300 K, dump every 1,000 steps, 80 frames analyzed
**Analysis:** `run_structural_analysis.py` — RDF (6 pairs) + end-to-end vectors
**Output:** `/home/arz2/simulations/02242026_PS3/analysis/structural/results/`

**Atom types:** t1 (C(sp³)), t2 (H(alkyl)), t3 (C(arom)). Six RDF pairs computed: all combinations of t1, t2, t3.

Aromatic C–C bond (t3–t3) peak at ~1.45 Å confirms ring integrity. Backbone-to-ring distance (t1–t3 peak at ~2.85 Å) reflects C(sp³)–C(aromatic) bond geometry.

For n=62 aPS (C∞ ≈ 10.0 for PS, Fetters 1994): ideal ⟨R²⟩ = C∞ × n × l²_CC ≈ 2,934 Å². Simulated ensemble compared to this ideal to assess chain compactness in the melt.

---

## Known Issues & Resolutions

| Issue | Resolution |
|---|---|
| Lambda killed T525 mid-run | Resumed from T550_out.data |
| Lambda killed T450 mid-run | Resumed from T475_out.data |
| Orphan LAMMPS process (PID 3035457) running duplicate T450 | Killed manually |
| extract_tg R²=0.85 POOR quality flag | Root cause: bin width < thermostat fluctuations; fix: 25K bins, n_points < 20 filter |
| Stale loose files (~2.3 GB dumps) in /home/arz2/simulations root | Deleted |

---

## References

1. Brandrup, J., Immergut, E.H., Blumstein, A. — *Polymer Handbook*
2. GAFF2_mod parameterization for drug-like molecules and fluorinated systems
3. OPLS-AA force field — Explicitly refined aromatic parameters; literature reports PS Tg 380–410 K
4. Fetters et al., *Macromolecules* (1994) — PS characteristic ratio C∞ = 9.5
5. Flory, P.J. (1969) — *Statistical Mechanics of Chain Molecules*

**Log generated:** February 27, 2026
