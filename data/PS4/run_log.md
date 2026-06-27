# Atactic Polystyrene (PS) Run 4 · 2026-06-24 → 2026-06-25
SMILES: `*CC(c1ccccc1)*`  |  FF: PCFF  |  Charges: bond-increment  |  DP: 40  |  Chains: 10 (6420 atoms)  |  GPU: 1 (sweeps), 0 (Murnaghan) — shared box
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=472913  |  equil velocity_seed=647974
NOTE: EMC seed 472913 matches PS3's known-good build (same 6420-atom cell) — effectively a reproduction of PS3, not an independent replicate. PS3 passed slope-gate, Tg=376.5 K = exp.
Plan: `data/PS4/raw/run_plan.json`  |  mode: reasoned  |  confidence: medium  |  critic: approved (1 round, 0 findings)  |  T_workflow_K: 550

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF                | classify_polymer → PSTR → EMC PCFF (Class II) auto-routed; aromatic ring charges/π-barriers govern PS Tg |
| D-02 Charges        | bond-increment (embedded in PCFF)        | EMC Class-II FF embeds bond-increment charges; no QM step |
| D-03 Electrostatics | PPPM 12 Å                          | PCFF assigns aromatic-ring partial charges → long-range Coulomb non-negligible |
| D-04 System size    | DP=40, 10 chains, 6420 atoms                        | polymer_rules.json default (DP≥30 floor for atactic Tg averaging) |
| D-05 Convergence    | PASS                         | overall_pass=true; density drift 0.22%, all thermo/structural gates pass; C(t) 10% decay advisory (glassy carve-out) |
| D-06 Tg fit quality | GOOD (all 3 rates)  | r25 R²=0.990, r50 R²=0.992, r100 R²=0.989 (all GOOD bilinear); is_glassy=TRUE (highest-rate r100 Tg=501.2 K > 300 K) |
| D-06b Multirate Tg  | DSC-equiv UNRELIABLE → report slowest-rate 434.0 K  | log-linear slope b=+48.5 K/ln(K/ns), R²=0.558 (<0.90 gate), N_rates=3 @ [25,50,100] K/ns, N_repl=1; slope_gate_pass=TRUE (positive slope → no contamination); DSC extrap to 1.67e-10 K/ns = −830.7 K (NONSENSE, 0.6-decade span) → rejected, patched tg_at_slow_rate_K=434.0; VF tg0=414.8 K (POORLY_CONSTRAINED, diagnostic). Known PS/PCFF limitation (memory ps-pcff-tg-slopegate-fail + plan D-06b). |
| D-07 Property method | murnaghan (glassy 300 K, ±1000 atm) | Tg=434 K (slowest rate) / 501 K (highest) → is_glassy=TRUE; Murnaghan NPT compression, 5 pressure pts |

<!-- Example — PS1 completed run:
| D-01 | PCFF | classify_polymer returned PSTR → EMC PCFF auto-routed |
| D-02 | bond-increment | PCFF: bond-increment charges embedded, no QM step |
| D-03 | pppm 12 Å | Aromatic ring partial charges → long-range Coulomb |
| D-04 | DP=40, 10 chains, ~6400 atoms | polymer_rules.json default |
| D-05 | PASS | density drift 0.4% over last 500 ps; energy plateau confirmed |
| D-06 | ACCEPTABLE | R²=0.93, F-stat GOOD, N=19 bins; range 550→250K in 20K steps |
-->

<!-- Add rows for any non-routine decisions (parameter overrides, custom protocols, etc.) -->

---

## RECOVERIES

<!-- One block per incident. Write "None" if the run completed without errors. -->
<!-- Outcome options: converged / failed again / escalated / UNRESOLVED (stop after 2 attempts) -->

No simulation failures — all stages (equil, 3 Tg sweeps, Murnaghan) ran clean on first submission. Operational incidents resolved below.

**R-01 · Equil-check stopped before comprehensive check finished**
Symptom: equilibration-checker returned "waiting for comprehensive check (180+ s)" with no output files written.
Resolution: resumed the same worker via SendMessage; it completed check_equilibration_comprehensive + extract_equilibrated_density and emitted the RESULT block. Outcome: converged (PASS, density 0.987).

**R-02 · Tg-sweep Monitor silent (progress-marker grep mismatch)**
Symptom: r25 sweep monitor emitted no PROGRESS lines for 1 h though the run was healthy (log at step 1.6M, GPU 70%).
Root cause: worker-supplied monitor_command greps quoted `"status":"done"`, but npt_tg_step writes UNQUOTED `{stage:T,status:done}` (known issue tg-sweep-monitor-grep-mismatch). Sentinel/PID detection still worked.
Resolution: re-armed all sweep monitors with robust `grep -cE 'status"?:"?done'`. Outcome: converged (progress visible thereafter).

**R-03 · Experimental DB lookup unavailable**
Symptom: exp-lookup-worker failed — db/query_best_match.py and polymer_db.sqlite do not exist on this host.
Resolution: fell back to polymer_rules.json exp ranges (Tg 373–383 K, K 3.3–4.0 GPa [Mark2007], density 1.05 ±5%) threaded into run-summary CLI. Outcome: converged (grading proceeded with documented fallback band).

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-stage chain) | ac214038 | 19:30 | 00:46 | ~5h 16m | done (GPU 1, claim label "PS4") |
| tg-sweep r25 | a6d6a190 | 01:05 | ~11:00 | ~10h | done; analysis: Tg=434.0 K (GOOD, R²=0.990), α_g=3.14e-4, α_r=4.77e-4 |
| tg-sweep r50 | 274c0e9e | ~11:05 | ~16:00 | ~5h | done; analysis: Tg=415.8 K (GOOD, R²=0.992), α_g=2.68e-4, α_r=4.55e-4, ΔCp=0.140 |
| tg-sweep r100 | 05ef3d73 | ~16:05 | ~18:45 | ~2.7h | done; analysis: Tg=501.2 K (GOOD, R²=0.989), α_g=2.92e-4, α_r=4.73e-4, ΔCp=0.150 |
| murnaghan | bd081086 | ~18:30 | ~20:05 | ~1.6h | done (GPU 0, 5/5 pressure pts) → K=2.96 GPa |
| ALL STAGES COMPLETE | — | — | ~20:10 | ~25h wall | done — run_summary.json written |

NOTE (shared box): At Phase B entry only GPU 1 is free — GPU 0=PEG4, GPU 2=PVC4, GPU 3=PSU3 (concurrent sessions). Phase B runs on GPU 1; remaining sweeps + Murnaghan claimed opportunistically as other sessions release. Defer-on-shortfall, never --allow-busy.

GPU inventory (`nvidia-smi` at run start): GPU 0-3: NVIDIA A800 40GB, 40 GB each, ~40.4 GB free each (all idle). Task allocation: 1 GPU.

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=300.02 K · 1951 frames analysed (skip=50) · 2026-06-25 00:48

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.2197% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.2002% (p=0.0395) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0328% | <1% | PASS |
| Energy block-SEM | 0.0249% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 9.5% | <30% | PASS |
| C∞ | 10.922 | lit. varies | INFO |
| MSID slope | 0.951 (R²=0.9934) | 1.0 ±20% | OK |
| C(t) τ_relax | 109275.4 ps (10% decayed) | — | ⚠ partial (advisory, glassy carve-out) |
| MSD kinetic trap | no (α=0.208, MSD=362.11 Å²>>Rg²=168.371) | — | OK |
| R_ee mean ± std | 26.83 ± 8.37 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0231 ± 0.006 | <0.10 | PASS |
| Density homogeneity CV | 24.1% (6³ grid, 29.7 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 10% decayed at end of trajectory (τ_relax=109275.4 ps vs T_traj=1951.0 ps) — advisory under require_glassy carve-out (DP≥30 glassy melt; terminal relaxation unreachable in MD).

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg CV (chain–chain) | 9.5% | CV < 30% → PASS |
| MSD plateau   | still diffusing (α=0.208, no kinetic trap) | OK |
| Density homog (CV) | 24.1% | < 25% → PASS |
| C(t) decay (melt NVT) | 10% at threshold 0.1 | ⚠ partial (advisory) |
| τ_c chain relax (KWW) | 109275.4 ps | annotation only |
| R_ee mean ± std | 26.83 ± 8.37 Å (N=10 chains) | end_to_end_summary.json |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 0.9873 ± 0.0003 g/cm³ | 0.997–1.103 g/cm³ (mid 1.05) | −6.0% (vs mid); −1.0% vs lower bound | NPT 300K plateau | ⚠ (just below exp range; consistent with PS3 0.974, PCFF underpredicts PS density) |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (reported, slowest rate r25) | 434.0 K | 373–378 K | +15% | slowest-rate MD Tg (slope-gate passed → convention); DSC extrap rejected (R²=0.558) | ⚠ PCFF overpredicts |
| Tg (MD @100 K/ns) | 501.2 K | —          | —    | bilinear fit, highest screening rate (drives is_glassy) | annotation |
| Tg (PS3 replicate, r40) | 376.5 K | 373–378 K | ~0% | prior run, same EMC cell, diff vel seed — shows ±40 K PCFF seed-sensitivity spread | annotation |
| α_g (CTE) | 2.92×10⁻⁴ K⁻¹ (r100) | 2.0–6.0×10⁻⁴ K⁻¹ | in range | −a_glassy / ρ_mean_glassy | ✓ |
| α_r (CTE) | 4.73×10⁻⁴ K⁻¹ (r100) | 5.0–6.0×10⁻⁴ K⁻¹ | low | −a_rubbery / ρ_mean_rubbery; ratio α_r/α_g=1.6 | ⚠ |
| ΔCp at Tg | 0.150 J/(g·K) (r100) | 0.28–0.31 J/(g·K) | −50% | H(T) bilinear fit | ⚠ |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 2.96 ± 0.05 GPa | 3.3–4.0 GPa    | −10% (vs lower); −20% (vs mid) | Murnaghan EOS (5 pts ±1000 atm, R²=0.9997); fluctuation cross-check 2.77 GPa (agree 6.3%) | ⚠ PCFF underpredicts (cf PS3 2.44) |
| B0' | 16.07   | 7–11 (typical) | —    | Murnaghan fit; elevated (BORDERLINE — narrow ±1000 atm span inflates B0', cf PVC2 16.3→9.53) | annotation |
| G   | N/A | —    | —    | deformation (not run — Murnaghan accepted) | N/A |
| E   | N/A | —    | —    | deformation (not run — Murnaghan accepted) | N/A |

### Overall verdict

`run_summary.json`: 3/3 FAIL vs experimental bands (Tg +13–16%, density −1.0% [marginal], K −10.4%). **The pipeline executed cleanly — all deviations are force-field/finite-size limitations, not methodological errors:**
- Equilibration PASS (density drift 0.22%, all structural gates pass).
- Tg slope-gate PASSED (positive slope); 3 GOOD bilinear fits; DSC extrapolation correctly rejected (R²=0.558, 0.6-decade span) and patched to slowest-rate 434 K.
- Murnaghan converged (R²=0.9997); fluctuation cross-check agrees within 6.3%.

**Interpretation:** PCFF systematically misses aPS at DP40 — **overpredicts Tg** (434 K vs exp ~378 K; raw PCFF MD is intrinsically ~440–484 K per Soldera2006), **underpredicts density** (0.987 vs ~1.05, −5.5% vs true exp) and **bulk modulus** (2.96 vs 3.3–4.0 GPa). Large Tg seed-sensitivity: the PS3 replicate (same EMC cell 472913, different velocity seed) gave Tg 376.5 K — a ~±40 K spread, confirming PS/PCFF Tg is the unreliable property. Density and K are directionally correct and within ~10% — the trustworthy outputs. Screening-grade Tg only.

Simulation dir: `data/PS4/lammps/`
Outputs: `data/PS4/raw/` — JSONs; `data/PS4/graphs/` — PNGs; `data/PS4/raw/run_summary.json`
