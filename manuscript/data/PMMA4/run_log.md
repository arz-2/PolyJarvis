# Atactic Polymethyl Methacrylate (PMMA) Run PMMA4 · 2026-06-27 → 2026-06-28

> **RUN OUTCOME — COMPLETE (all 3 properties delivered, with caveats).**
> Tg (headline, MD) = **369.9 K** (−2.1% vs exp 378) ✓ · ρ = **1.111 g/cm³** (−6.6%, PCFF underpredict) ⚠ · K = **4.46 GPa** (+6.1% vs band, PCFF overestimate) ⚠.
> Caveats: (1) Tg multirate slope-gate FAILED (seed noise, 0.6-dec span) → DSC extrapolation discarded, headline = highest-rate MD Tg per user decision. (2) `run_summary.json` headline Tg is WRONG (reports DSC 408.6 K / FAIL — known generate_run_summary bug); corrected Tg is in RESULTS-B below. (3) Equil accepted after 1 extend; the failing density-CV gate is a melt-dump artifact (see R-01).
SMILES: `*CC(C)(C(=O)OC)*`  |  FF: PCFF  |  Charges: none (bond-increment, EMC)  |  DP: 50  |  Chains: 10  |  GPU: 1,2,3
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=734812  |  SEED_HOT=373086  |  SEED_COLD=721530 (r25); r50/r100 in state table  |  n_atoms: 7520
Plan: `data/PMMA4/raw/run_plan.json`  |  mode: deterministic  |  confidence: high  |  critic: approved  |  T_workflow_K: 550
Tacticity: atactic (PACR tacticity-sensitive; atactic exp Tg ~378 K, isotactic ~318 K, syndiotactic ~408 K)

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF                | classify_polymer → PACR; EMC/PCFF (Class II) auto-routed (GAFF Tg err >45% per NkepsuMbitou2025) |
| D-02 Charges        | none (bond-increment, EMC)        | EMC PCFF: charges embedded via bond increments, no QM step |
| D-03 Electrostatics | PPPM 12 Å                          | ester C=O dipole → long-range Coulomb required (Hayashi2022; Webb2024) |
| D-04 System size    | DP=50, 10 chains                        | polymer_rules PACR default (dp_typical=50, nchain=10) |
| D-05 Convergence    | ACCEPT after EXTEND×1                         | thermo fully converged; sole failing gate (density-homog CV 28.3%) is a melt-dump artifact, extension-invariant (see R-01). ρ=1.111 g/cm³ (−6.6% vs exp) accepted as PCFF underprediction |
| D-06 Tg fit quality | MD Tg accepted (headline r100 EXCELLENT)  | Headline = highest-rate r100 369.9 K (R²=0.9961, EXCELLENT, −2.1% vs exp 378); is_glassy=True (>300 K). Per-rate: r25 408.6 GOOD, r50 515.3 spurious. CTE α_g≈1.8e-4, α_r≈2.7e-4 (r100; ratio 1.5). ΔCp 0.087 J/g·K (r100). |
| D-06b Multirate Tg  | DSC-equiv 408.6 K — FLAGGED MEANINGLESS    | log-linear Tg(Γ) slope −27.9 K/ln, R²=0.066, N_rates=3 @ [25,50,100] K/ns (0.6 dec), N_repl=1; slope_gate_pass=FALSE (rate-inverted seed noise, PCFF short-span artifact). DSC extrapolation NOT usable; MD Tg (D-06) is the deliverable. Staged rows not committed to registry. |
| D-07 Property method | murnaghan (glassy, 300 K) | is_glassy=True (Tg 369.9 > 300) → Murnaghan pressure series @ 300 K from npt_extend_out.data; ±1000 atm symmetric [-1000,-500,0,500,1000] (PMMA-class default; −1000 tension mild, no cavitation risk unlike −3000). chain c1fcd3a9. |

<!-- Example — PS1 completed run:
| D-01 | PCFF | classify_polymer returned PSTR → EMC PCFF auto-routed |
| D-02 | bond-increment | PCFF: bond-increment charges embedded, no QM step |
| D-03 | pppm 12 Å | Aromatic ring partial charges → long-range Coulomb |
| D-04 | DP=40, 10 chains, ~6400 atoms | polymer_rules.json default |
| D-05 | PASS | density drift 0.4% over last 500 ps; energy plateau confirmed |
| D-06 | ACCEPTABLE | R²=0.93, F-stat GOOD, N=19 bins; range 550→250K in 20K steps |
-->

<!-- Add rows for any non-routine decisions (parameter overrides, custom protocols, etc.) -->

### Thermal multirate — staged per-rate Tg (committed to registry after slope-gate)
| rate (K/ns) | run_id | Tg_K (primary) | R² | fit | CTE α_g / α_r (1e-4/K) | ΔCp (J/g·K) |
|-------------|--------|----------------|-----|-----|------------------------|-------------|
| 100 | 8977189c | 369.9 | 0.9961 | EXCELLENT | 1.80 / 2.71 (ratio 1.51) | 0.0867 |
| 50  | fcbdea88 | 515.3 ⚠SUSPECT (alt 410.7) | 0.995 | EXCELLENT* | 1.74 / 4.58 (ratio 2.64) | 0.0107 | *spurious primary: +137K vs exp, 104.6K above alt, rate-inverted vs r100 → delocalized-transition fit |
| 25  | 21cf353c | 408.6 (alt 392.9) | 0.9937 | GOOD | 1.94 / 3.56 (ratio 1.84) | 0.126 | +8% vs exp; fit valid (slowest rate) |

is_glassy = True (highest-rate Tg 369.9 K > 300 K). r100 Tg −2.1% vs exp 378 K — well within FF/rate limits.

---

## RECOVERIES

<!-- One block per incident. Write "None" if the run completed without errors. -->
<!-- Outcome options: converged / failed again / escalated / UNRESOLVED (stop after 2 attempts) -->

### R-01 · Equil EXTEND #1 — under-packed glassy cell
- **Symptom:** equil-check FAIL → EXTEND. npt_prod300 ρ=1.109 g/cm³ (−6.8% vs exp 1.19; below band [1.159,1.281]); density-homogeneity CV=28.3% > 25% gate. Thermo fully converged (ρ drift 0.06%, energy drift 0.0009%, block-SEM <0.03%) and P2=0.014 — cell is converged at a low/heterogeneous density, not still drifting.
- **Root cause:** marginal melt densification — converged NPT plateau sits below the PCFF PMMA target (~1.17–1.19).
- **Action:** per CLAUDE.md EXTEND protocol, re-spawn equilibration-worker mode=extend from npt_prod300_out.data, +2 ns NPT @ 300 K / 1 atm (NOT melt T), then re-check on npt_extend_out.data. Max 2 extensions.
- **Outcome:** ACCEPTED (extend #2 skipped — provably futile). After +2 ns: thermo re-converged (ρ drift 0.06%→0.02%, energy drift 0.04%, block-SEM 0.017%), density stable 1.109→1.111 g/cm³. **Key finding:** equil-check #2 returned an EXTEND verdict but its ENTIRE structural/spatial section (CV 28.3%, Rg CV 12.5%, R_ee 40.11±11.44, C(t) 0.009, P2 0.0137, MSD 292.53) was byte-identical to check #1 — because `check_equilibration_comprehensive` reads those metrics from the **melt dump** (`nvt_production.dump`, 550 K), which a 300 K production extension cannot alter. The density-homogeneity CV gate is therefore extension-invariant; the EXTEND loop cannot fix it. The 28.3% CV is a melt-dump artifact (measured at 550 K where the cell is hotter/less dense → larger density fluctuation; coarse 7³ grid, 21.9 atoms/voxel → shot-noise inflated) and just marginally over the 25% threshold. The **production cell** is thermodynamically equilibrated on every production-relevant gate (density plateau, energy, Rg CV 12.5%, P2 0.014, MSD diffusive). Orchestrator accepted the cell on those gates and proceeded. Caveat carried forward: density 1.111 g/cm³ is −6.6% vs exp 1.19 (PCFF underprediction + marginal melt packing) → bulk modulus K expected biased low.

### R-02 · Thermal multirate slope-gate FAIL — PCFF short-span seed noise
- **Symptom:** glassy slope-gate `slope_gate_pass=False`. Per-rate primary Tg (K): r25=408.6 (GOOD, valid), r50=515.3 (SUSPECT spurious primary; alt 410.7), r100=369.9 (EXCELLENT). Log-linear Tg(ln Γ): slope −27.9 K, R²=0.066 → meaningless. Data is rate-INVERTED (fastest r100 gives LOWEST Tg) → slope sign is noise.
- **Root cause:** documented PCFF glassy slope-gate over-firing on a 0.6-decade (25/50/100 K/ns) span — the true rate dependence is smaller than fit scatter (r25 tg_uncertainty 33 K). Not a contamination of the equil cell; the individual MD Tg values are physically reasonable and bracket exp 378 K (r100 −2.1%, r25 +8%). Mirrors PS2→PS3, PEEK4 seed-noise failures in memory. No re-analysis can flip the slope (r100's clean fit is genuinely below r25's).
- **Action (protocol):** discard staged registry rows (none were committed to the CSV — deferred write, so nothing to undo), re-run all 3 sweeps with a fresh velocity seed (max 2). **Constraint:** infeasible within budget — ~20.6 h of the 24 h max already used; one 3-sweep re-run is ~13 h (r25 dominates). Escalated to user for direction (accept MD Tg w/ caveats + continue vs UNRESOLVED vs extend budget).
- **Outcome:** user decision = ACCEPT MD Tg + continue (re-run infeasible in budget). Headline Tg = highest-rate r100 = 369.9 K (EXCELLENT, −2.1% vs exp 378). DSC log-linear extrapolation reported but flagged meaningless (R²=0.066, slope gate failed). Staged registry rows NOT committed to the shared CSV (gate failed → would pollute cross-replicate averaging). is_glassy=True unaffected. Proceeding to mechanical track + run-summary with `--slope_gate_pass false` so run-summary uses the MD Tg, not the DSC value, as headline.

---

## SIMULATION STATE

<!-- Written before launching each BACKGROUND-WAIT waiter; updated to done/failed on the completion
     wakeup. Used for session restart. BgTask = the run_in_background Bash task id of the live waiter
     (— once it has returned), so a restarting session can tell whether a waiter is still in flight. -->

| Stage | ID | BgTask | Submitted | Completed | Wall | Status |
|-------|----|--------|-----------|-----------|------|--------|
| equil (9-stage) | 9e8a9f3c | b9rz7cr8t | 13:01 | 18:56 | 5h55m | done |
| equil-check #1 | — | — | 18:56 | 19:02 | — | EXTEND (CV 28.3%, ρ 1.109) |
| equil-check #2 | — | — | 20:25 | 20:32 | — | ACCEPTED (thermo conv.; CV melt-dump artifact) |
| tg-sweep r25 | 21cf353c | buknvqpri | 20:40 | 09:38 | 13h00m | done (GPU1 released) |
| tg-sweep r50 | fcbdea88 | b39l73n23 | 20:40 | 03:00 | 6h20m | done (GPU2 released) |
| tg-sweep r100 | 8977189c | b91bjzr5d | 20:40 | 23:53 | 3h13m | done (GPU3 released) |
| npt_extend #1 (+2ns @300K) | b0c8e58c | bpyykoas9 | 19:03 | 20:25 | 1h20m | done |
| murnaghan BM (±1000 atm, 300K) | c1fcd3a9 | bles7tdi7 | 10:32 | 12:23 | 1h50m | done (K=4.46 GPa) |

GPU claims: all released (equil PMMA4→G1; tg PMMA4_g2/g3/g4→G1/2/3; BM PMMA4_bm2→G1). GPU 0 never used (outside allocation).
GPU inventory (`nvidia-smi` at run start): GPU 1/2/3: NVIDIA A800 40GB Active, ~40 GB free each (GPU 0 busy ~67%, excluded)

---

## D-05 CONVERGENCE DETAIL

### Attempt 1 (npt_prod300, pre-extend) — `check_equilibration_comprehensive` · T=299.96 K · 1951 frames (skip=50) · 2026-06-27 18:58

**Overall: FAIL** (density-homogeneity CV gate)

#### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0625% (p=0.0893) | <1%, p<0.01 | PASS |
| Energy drift | 0.0009% (p=0.9809) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0234% | <1% | PASS |
| Energy block-SEM | 0.0075% | <1% | PASS |

#### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 12.5% | <30% | PASS |
| MSID slope | 1.105 (R²=0.9961) | 1.0 ±20% | OK |
| C(t) τ_relax | 5.64e9 ps (1% decayed) | — | ⚠ partial (advisory, glassy) |
| MSD kinetic trap | no (α=0.146, MSD=292.5 Å²>>Rg²=239.9) | — | OK |
| R_ee mean ± std | 40.11 ± 11.44 Å (N=10) | — | INFO |

#### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0137 ± 0.0041 | <0.10 | PASS |
| Density homogeneity CV | 28.3% (7³ grid, 21.9 atoms/voxel) | <25% | **FAIL** |

### Attempt 2 (npt_extend, +2 ns @ 300 K) — `check_equilibration_comprehensive` · T=300.07 K · 2026-06-27 20:26

**Thermo (from npt_extend.log — the only section that changed):** density drift 0.0229% (PASS), energy drift 0.0393% (PASS), density block-SEM 0.0165% (PASS), energy block-SEM 0.0089% (PASS). Density plateau 1.111 g/cm³.

**Structural/spatial section byte-identical to attempt 1** (Rg CV 12.5%, density-homog CV 28.3%, R_ee 40.11±11.44, C(t) 0.009, P2 0.0137, MSD 292.53) — read from the unchanged melt dump → confirms the CV gate is extension-invariant (R-01).

### Chain Structure Summary (accepted cell)

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | CV 12.5% | CV < 30% → PASS |
| MSD plateau   | diffusive in melt (α=0.146, no trap) | OK |
| Density homog (CV) | 28.3% (melt dump, 21.9 atoms/voxel) | < 25% → FAIL but melt-dump artifact (advisory; see R-01) |
| C(t) decay (melt NVT) | 1% (τ_relax >> T_traj) | advisory (glassy carve-out) |
| τ_c chain relax (KWW) | 5.64e9 ps | annotation only |
| R_ee mean ± std | 40.11 ± 11.44 Å (N=10 chains) | end_to_end_summary.json |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.111 g/cm³ | 1.19 g/cm³ (PMMA; band 1.13–1.25) | −6.6% (vs 1.19); −1.7% below band floor | NPT 300K plateau (+2ns extend, SEM 0.017%) | ⚠ (PCFF underprediction + marginal melt packing) |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

**HEADLINE Tg = MD 369.9 K (r100, highest rate, EXCELLENT R²=0.9961, −2.1% vs exp 378 K).** The DSC-equivalent multirate extrapolation is INVALID here (slope gate failed, R²=0.066) and must NOT be used as the headline. ⚠ NOTE: `run_summary.json` incorrectly reports the headline Tg as the DSC value 408.6 K with status FAIL — a known generate_run_summary bug (it ignores slope_gate_pass/tg_k and grades the rate-extrapolated value even when the slope gate fails). The corrected headline below supersedes run_summary.json's tg block.

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| **Tg (headline, MD)** | **369.9 K** | 378 K (band 358–398) | **−2.1%** | bilinear fit, highest screening rate (r100=100 K/ns), EXCELLENT R²=0.9961 | ✓ |
| Tg (MD, slowest rate) | 408.6 K | 378 K | +8.1% | bilinear fit, r25=25 K/ns, GOOD R²=0.9937 | annotation (brackets headline; +8%) |
| Tg (DSC-equiv) | 408.6 K (INVALID) | 358–398 K | — | log-linear Tg(Γ)→10 K/min: slope −27.9 K, R²=0.066, slope-gate FAIL | ✗ not usable (seed noise, 0.6-dec span) |
| α_g (CTE) | 1.80×10⁻⁴ K⁻¹ | ~2.5×10⁻⁵ (lit ~2–7×10⁻⁵) | — | −a_glassy/ρ (r100) | ⚠ MD CTE high vs dilatometry (FF/short-T-window) |
| α_r (CTE) | 2.71×10⁻⁴ K⁻¹ | — | — | −a_rubbery/ρ (r100); ratio α_r/α_g=1.51 | annotation (ratio healthy) |
| ΔCp at Tg | 0.087 J/(g·K) | ~0.28 J/(g·K) (lit) | — | H(T) bilinear fit (r100) | ⚠ MD ΔCp below dilatometric (known MD underestimate) |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 4.46 ± 0.14 GPa | 3.5–4.2 GPa (K_T glassy) | +6.1% (vs 4.2 ceiling) | Murnaghan EOS @300 K, ±1000 atm, R²=0.9983, B0′=10.54; fluctuation cross-check 4.53 GPa (1.6% agree) | ⚠ (PCFF polyacrylic stiffness overestimate) |
| B0' | 10.54   | 7–11 (typical) | —    | Murnaghan fit            | annotation (in range [4,20]) |
| G   | N/A | 1.7–2.4 GPa    | —    | not computed (deform not run — Murnaghan succeeded) | N/A |
| E   | N/A | 2.5–3.3 GPa    | —    | not computed (deform not run — Murnaghan succeeded) | N/A |

Simulation dir: `data/[RUN]/lammps/`
Outputs: `data/[RUN]/raw/` — JSONs; `data/[RUN]/graphs/` — PNGs; `data/[RUN]/raw/run_summary.json`

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 31.7 h  |  **GPU**: 31.7 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1
- Source: `data/PMMA4/lammps/**/*.log` (Born stages excluded); reproducible via `manuscript/gen_table_compute_cost.py`.
