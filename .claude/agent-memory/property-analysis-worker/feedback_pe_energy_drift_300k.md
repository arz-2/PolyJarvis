---
name: pe-energy-drift-300k
description: PE/PHYC TraPPE-UA 300K NPT energy drift >2% is a recurring pattern; density and K_fluctuation still reliable
metadata:
  type: project
ingested_at: 2026-06-10
---

In PE4 (stage 09_npt_prod300), PE6 (stage 09_npt_prod300 and 09b_npt_prod300_ext after EXTEND×1), and PE7 (stage 09_npt_prod300), `check_equilibration_comprehensive` returns `overall_pass=False` because energy drift exceeds the 1% threshold. PE6 stage 09: drift=2.30%. PE6 stage 09b (2 ns extension): drift=2.12% — EXTEND reduced drift by only 0.18 pp. PE7: drift=2.23%, confirming this is a slow structural relaxation artefact, not a transient. All other gates pass: density drift, density SEM, energy SEM, Rg CV, MSID slope, P2, density homogeneity.

The density extracted from the same window is stable (plateau_fraction=1.0, block-SEM=0.09%), and the bulk modulus from volume fluctuations also converges (K_SEM=0.14 GPa, ~11% relative).

**Why:** The 300K NPT window is short (~1 ns) for PE chains of DP=120. Chain-scale dynamics (C(t) τ_relax >> T_traj, MSD kinetic trap) are frozen, but local segment packing is equilibrated. The energy continues to show slow drift as residual conformational relaxation continues, but the thermo-mechanical properties are already converged.

**How to apply:** Flag energy drift as WARNING to orchestrator. Do not abort or discard the density/K results. Recommend orchestrator consider extending the 300K NPT run if stricter convergence is needed, but properties can be reported with this caveat. See also [[equilibration_check_quirks]] in property-analysis-worker memory.
