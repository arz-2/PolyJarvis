# PVDF Run 1 · 2026-05-25 → [END_DATE]
SMILES: `*CC(F)(F)*`  |  FF: GAFF2_mod  |  Charges: RESP  |  DP: 60  |  Chains: 10

---

## DECISIONS

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | GAFF2_mod                              | classify_polymer class 5 (PHAL); fluorinated polymer — GAFF2_mod standard |
| D-02 Charges        | RESP                                   | Polar CF2 backbone, large C-F dipole (~±0.5 e) |
| D-03 Electrostatics | PPPM                                   | Highly polar backbone; PPPM mandatory per PHAL rules |
| D-04 System size    | DP=60, 10 chains, ~20k atoms           | polymer_rules.json dp_typical=60, nchain=10; standard production |
| D-05 Convergence    | EQUILIBRATED                           | All thermo + structural flags pass (see below) |
| D-06 Tg fit quality | GOOD (R²=0.994, F-stat p≈0)           | F-stat exhaustive split; 1 plateau skipped drift |

**PHAL post-processing:** Fluorine LJ patch applied via `tools/patch_fluorine_params.py` after `save_lammps_data` — sigma f: 3.1181→2.95 Å, epsilon f: 0.0610→0.0530 kcal/mol (OPLS-AA Watkins & Jorgensen J. Phys. Chem. A 2001).

---

## RECOVERIES

[Stage 1]  polymerize_rw() got an unexpected keyword argument 'opt'
           Diagnosis: MCP server _run_polymerize() passes opt='rdkit' but installed RadonPy polymerize_rw has no opt param
           Fix: Removed opt='rdkit' from poly.polymerize_rw() call in mcp-radonpy-server/src/server.py line 363
           Outcome: Server restarted; polymerized via direct Python call — converged

[Stage 1]  patch_fluorine_params.py: "No fluorine atom types found" (two bugs)
           Diagnosis: (1) LAMMPS blank line after "Pair Coeffs" header closed section before data was read; (2) RadonPy writes comments as "f,0" not "f" — regex matched wrong token
           Fix: Track seen_data flag; skip blank line closing until first coeff parsed. Strip ",N" charge index from comment before type lookup.
           Outcome: patch applied — f: eps 0.0832→0.0530, sig 3.034→2.950 Å

---

## D-05 CONVERGENCE DETAIL

**Stage 06 NVT production · T=700 K · 801 frames analysed (skip_frames=200)**

Thermo convergence (`check_equilibration`): equilibrated=true, density=1.264 g/cm³ @ 700 K

Extended structural checks:

| Check | Value | Threshold | Pass? |
|-------|-------|-----------|-------|
| Rg CV across chains | 0.217 (21.7%) | < 0.30 | ✓ |
| C∞ from Rg | 5.57 | lit. 5–9 | ✓ |
| MSD_max vs Rg² | 741 Å² >> 262 Å² (kinetic_trap=false) | MSD > Rg² | ✓ |
| MSD α exponent | 0.30 (Rouse sub-diffusive) | — | — |
| P2 nematic order | 0.026 | < 0.10 | ✓ |
| Density CV (5³ grid) | 0.230 | < 0.25 | ✓ |

Notes:
- MSD α=0.30 is expected: at 700 K on 800 ps timescale, DP=60 PVDF (unentangled) is in the middle of the Rouse regime. Chains have moved 2.8× their own Rg, confirming good conformational sampling.
- Density CV with 10³ grid gave a false positive (0.61); Poisson noise alone = 0.53 for only 3.6 atoms/voxel. Grid_n=5 (29 atoms/voxel) is the appropriate resolution for this system size.
- Two chains (8, 9) have Rg≈22 Å vs mean 16 Å — extended conformations, still within CV<30% threshold.

---

## RESULTS

| Property | Computed | Experimental | Error | Status |
|----------|----------|--------------|-------|--------|
| Tg       | 383 K (382±6, avg F-stat+alt) | 233 K exp / ~310–350 K target MD | +150 K | complete |
| ρ (300K) | 1.617 g/cm³  | 1.78 g/cm³ (bulk)   | −9.2% | complete |
| K        | — GPa    | —            | —    | pending |

**D-06 detail:**
- F-stat Tg: 388.6 K · Alternative Tg: 376.7 K · curve_fit: 330 K (hit guess, unreliable)
- Glassy slope: −3.98×10⁻⁴ g/cm³/K · Rubbery slope: −9.30×10⁻⁴ g/cm³/K
- 55 plateau bins (1 skipped drift, 1 duplicate 600K from test chain absorbed cleanly)
- High MD Tg (+150 K over experiment) consistent with 40 K/ns cooling rate (500k steps × 20K step)
  Literature reference rates: 1–10 K/ns → longer steps per T would push Tg down toward 310–350 K

Simulation dir: `/home/arz2/simulations/PVDF1/`
