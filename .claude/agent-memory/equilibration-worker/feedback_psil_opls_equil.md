---
name: psil-opls-equil-settings
description: PSIL/PDMS OPLS-AA equilibration settings — temp path, use_opls flag, verified FF styles, params_file usage
metadata:
  type: feedback
ingested_at: 2026-06-10
---

PSIL is a rubbery polymer (exp_Tg=148 K < 300 K). Always use temp=300.0 for the rubbery path — ignore T_equil_K=350 from task params or polymer_rules.json for the generate_equilibration_workflow call.

**Why:** rubbery path (exp_Tg<300) sets temp=300.0 so that stage 07 NPT at 300 K is the primary source for density and fluctuation bulk modulus. Using T_equil_K=350 produces a thermally-expanded density that cannot be compared to the 0.97 g/cm³ RT target.

**How to apply:** Check exp_Tg_K in polymer_rules.json. For PSIL: PDMS=148 K, PMHS=158 K → both rubbery → temp=300.0 always.

Force field: use_opls=True IS a real flag in generate_equilibration_workflow. Pass it for all PSIL builds. This is the fix for "GAFF2-style scripts generated" failures. The parameter exists and works correctly.

Force field styles confirmed for PSIL OPLS-AA (after passing use_opls=True):
- pair_style: `lj/cut/coul/long 9.5 9.5` (NOT lj/charmm/coul/long)
- kspace_style: `pppm 1e-6`
- bond_style: `harmonic`, angle_style: `harmonic`, dihedral_style: `multi/harmonic` (NOT fourier)
- special_bonds: `lj/coul 0 0 0.5` (NOT amber)
- pair_modify: `mix geometric tail yes`

Note: emc_build.params contains `special_bonds lj/coul 0 0 0.5` and `pair_modify mix geometric tail yes` — these match OPLS-AA and are safe even though they appear in the include file executed after read_data.
Dihedral Coeffs in emc_build.params are 5-column (multi/harmonic format) — confirmed compatible.

IMPORTANT: Previous memory entry claimed "no use_opls flag exists" and recorded lj/charmm/fourier/amber styles as "confirmed." Those were GAFF2 fallback styles from a failed run where use_opls was omitted. That memory was wrong — use_opls DOES exist and MUST be passed.

Pass params_file to both generate_equilibration_workflow AND run_lammps_chain to suppress Coeffs false-positive preflight block. [[feedback_chain_no_data_file]]
