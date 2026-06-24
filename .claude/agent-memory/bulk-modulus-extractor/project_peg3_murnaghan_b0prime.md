---
name: project_peg3_murnaghan_b0prime
description: PEG3/POXI PCFF Murnaghan B0'=1.0 anomaly — pressure range too narrow for rubbery PEO; K=3.61 GPa vs B_dyn=2.73 GPa; exp floor 2.0 GPa; WARNING issued
metadata:
  type: project
---

PEG3 (PEO, POXI/PCFF, rubbery at 300 K): Murnaghan fit with [1, 100, 300, 600, 1000] atm yields B0'=1.0 (at lower numerical clamp, physically expected range 4–20), R²=0.9965 (<0.999 threshold). Fit_converged=True but B0' is unphysical.

**Why:** The 0–1000 atm range (~0.1 GPa) is very narrow relative to PEO's compressibility. Volume changes across 5 pressure points (~1900 Å³ range vs equilibrium V_std ~270 Å³/point) are insufficient to constrain B0' independently. The Murnaghan EOS degenerates toward a linear fit, pulling B0' to ~1.

**How to apply:** For rubbery POXI/PEO at 300 K, widen pressure range to at least [-1000, 0, 3000, 7000, 15000] atm (up to ~1.5 GPa) to get a physical B0'. The K value (3.61 GPa) is likely a slight overestimate vs the true EOS K; B_dyn=2.73 GPa (SEM ±0.16) is the better lower-bound cross-check. Exp floor is 2.0 GPa (amorphous PEO); semicrystalline range 2–4 GPa. Both methods bracket the experimental range. Issue WARNING on B0' anomaly but do not FAIL if K itself brackets experiment.

B_dyn (NPT fluctuation): 2.73 GPa ± 0.16 (SEM); B_def R²=0.046 → unreliable (as expected for soft rubbery polymer, see Wu 2020 warning).

Related: [[project_pvc_murnaghan_b0prime]], [[project_pstr_murnaghan_b0prime]]
