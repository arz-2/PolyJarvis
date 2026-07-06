# Polysulfone (PSU, Udel) Run PSU1 · 2026-06-18 → 2026-06-21 · COMPLETE
SMILES: `*Oc1ccc(C(C)(C)c2ccc(Oc3ccc(S(=O)(=O)c4ccc(*)cc4)cc3)cc2)cc1`  |  FF: PCFF  |  Charges: RESP (EMC-embedded)  |  DP: 20  |  Chains: 8  |  GPU: 0,1,2,3 (MPI=4)
Requested: density, tg, bulk_modulus (all)  |  Replicate: 1 of 1  |  Seeds: EMC=random (not persisted by EMC build — cell not bit-reproducible; acceptable for exploratory run)  |  SEED_HOT=723979  |  SEED_COLD=N/A (no velocity reinit after softheat; later stages read restart)
Plan: `data/PSU1/raw/run_plan.json`  |  mode: reasoned  |  confidence: medium  |  critic: approved (2 rounds)  |  T_workflow_K: 700
<!-- D-00: planner reasoned plan. Dominant uncertainty: short_chain_bias_DP15 (D-04 confidence=low, DP=15 below policy DP≥20 floor — deliberate screening choice for 48h budget). reduction_probe: fast_density_screen (PLANNED, blocked per policy). is_glassy=True (Tg_exp=463 K). BM method: born_nvt, deform fallback. -->
<!-- D-04 deviation: DP=15 nchain=8 (MW ~5,304 g/mol) vs policy DP≥20. Expected Tg overestimate ~5-15%, K biased high. Accepted for screening. -->
<!-- Exp anchors: Tg=463 K (PSU/Udel), density=1.24 g/cm³, K=3.0-5.0 GPa, E≈2.5-2.6 GPa. -->
<!-- Tg fit success_criteria: bilinear R²≥0.8, T-range brackets 463 K. -->
<!-- NOTE TO ORCHESTRATOR: SMILES SO2 has no explicit charge; verify EMC PCFF assigns sulfone S type (so2/o_2s) before equil submit (D-02/PSFO note). -->
<!-- POLICY NOTE: properties_requested includes tg, so DO NOT use glassy_hint; is_glassy will be set from extracted Tg_K after thermal track. Provisional is_glassy=True for planning only. -->


---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF                                                 | classify_polymer → PSFO (class_id=20) → EMC auto-routes PCFF (use_pcff=true). Aryl-SO₂-aryl + aryl-ether covered via Class II cross terms; sulfone S typed `sf`, o= oxygens. |
| D-02 Charges        | PCFF bond-increment (embedded) — **corrected from plan's RESP** | Plan D-02 specified RESP, but RESP cannot be grafted onto a PCFF skeleton (PCFF charges are parameterized self-consistently with its vdW/valence; EMC PCFF emits bond-increment only). Realized S=+0.082 e, O=−0.114 e (pcff.frc `o= s' ±0.1143`). Consistent with cited PSU PCFF lit (Hayashi2022/Afzal2021). Plan D-01↔D-02 were internally inconsistent; native charges are the correct/only consistent choice. See R-01. |
| D-03 Electrostatics | PPPM (cutoff 12.0 Å)                                 | Heteroatom backbone (S, O) → PPPM mandatory per policy; sulfone polarity. |
| D-04 System size    | DP=20, 8 chains, 8656 atoms                          | Policy-compliant (DP≥20 Fox-Flory floor, raised from plan-round-1 DP=15 per critic + user). nchain=8 (PSFO default); self-imaging OK (L/2≈22.8 Å ≫ 12 Å cutoff at ρ=1.24). |
| D-05 Convergence    | overall_pass=False → local gates PASS; ESCALATE (R-03) | Density 1.187 g/cm³ (−4.3%), energy/Rg/homogeneity/nematic PASS. Only terminal-relaxation metrics (C(t)/C∞/MSD) fail — non-binding for density/Tg/glassy-K. Awaiting user call to proceed-with-caveat vs extend. |
| D-06 Tg fit quality | EXCELLENT (40 K/ns, primary) | **Tg=499.7±15 K** (hyperbola, R²=0.9965, 49 plateau bins, width 49.6 K); α_g=20.7×10⁻⁵ K⁻¹, α_r=46.8×10⁻⁵ K⁻¹ (rubbery>glassy ✓), ΔCp=0.148 J/(g·K). Multi-rate: 160 K/ns degenerate (width=0, artifact→565 K); 640 K/ns under-equilibrated per-T (31 ps/T, ΔCp 0.04→464 K). Tg(rate) non-monotonic ⇒ rate-extrapolation unusable; report slowest well-equilibrated rate. **is_glassy=True** (Tg≫300 → glassy Born path for mechanical). |
| D-07 Property method | **murnaghan (glassy, 300 K NPT compression)** — REVISED from plan's born (removed 2026-06-21, R-07); deform fallback | Tg=499.7 K → is_glassy=True. Born removed (PCFF+PPPM virial incompat). Murnaghan ±1000 atm. **Result: K=4.43±0.06 GPa (exp 3–5 ✓), B0'=12.7, r²=0.9997.** Tool `run_bulk_modulus_series` was broken → manual KOKKOS NPT bypass (R-07). |

<!-- Add rows for non-routine decisions (parameter overrides, custom protocols, etc.) -->

| D-06a Tg protocol | **Multi-rate** cooling sweep, 3 rates [40,160,640] K/ns (not the 52 ns single-rate default) | Plan carries tg_rates_K_per_ns=[40,160,640] + analysis tool is extract_tg_multirate. Each rate = stepwise 750→250 K, ΔT=20 K, N_STEPS_PER_T scaled to rate (500k/125k/31k). ~17 ns total vs 52 ns; enables Tg-vs-rate extrapolation toward experimental cooling rates. Cool from npt_production_out.data (700 K rubbery melt). |

---

## RECOVERIES

<!-- One block per incident. Write "None" if the run completed without errors. -->
<!-- Outcome options: converged / failed again / escalated / UNRESOLVED (stop after 2 attempts) -->

### R-00 — Critic revise + budget/hardware conflict (PRE-LAUNCH, escalated to user)
- **Symptom:** Critic round 1 → `revise`. Finding: D-04 DP=15 violates the hard `DP>=20` (Tg) and entanglement-MW (bulk_modulus) requirement in `decision_policy.json:system_size.require`. Planner had flagged DP=15 as a deliberate screening deviation (D-04 confidence=low, dominant uncertainty `short_chain_bias_DP15`) for the 48h budget.
- **Root cause (deeper):** Plan feasibility ("~47h") assumed **4 GPUs**; task allocates **1 GPU (id 3), MPI=1**. Empirical 1-GPU throughput for aromatic/polar PCFF+PPPM systems: BPA-PC (11,898 atoms) 2.3 ns/day; PMMA (5,264) ~3 ns/day prod / 1.77 Tg-sweep; Nylon (9,520) ~5 / 1.6; PDMS (8,020) ~4. PSU DP=15 ≈ 6,500 atoms (BPA backbone) → ~2.5–4 ns/day. Full all-properties pipeline ≈ 40+ ns MD → multiple days. **48h on 1 GPU is infeasible at ANY DP**, so the DP policy fix and the runtime budget must be resolved together.
- **Fix:** Escalated to user (AskUserQuestion) — resource allocation (1 vs 4 GPUs), runtime budget, and scope are the user's decision. Re-plan after answer; do not loop critic a 3rd time.
- **Outcome:** resolved by user — (1) **4 GPUs, MPI=4** (override task GPU=3/MPI=1 → GPUs 0,1,2,3); (2) **DP=20** (policy-compliant, drops the short_chain_bias_DP15 uncertainty). Re-planning round 2 with these mandates, then re-critic. Critic round 2 → approved (0 findings).

### R-01 — D-02 charge-method correction (build stage, no re-sim)
- **Symptom:** Plan D-02 decided `charge_method=RESP`; EMC PCFF build realized bond-increment charges (S=+0.082 e, O=−0.114 e), not QM/RESP. Builder flagged the mismatch.
- **Root cause:** Plan D-01 (PCFF) and D-02 (RESP) are physically inconsistent — PCFF bond-increment charges are parameterized self-consistently with its own vdW/valence terms; grafting external RESP charges onto a PCFF skeleton breaks the FF and is not what cited PSU PCFF studies do. EMC PCFF emits only native bond-increment charges. The "+1.3/−0.55 e" sulfone expectation in polymer_rules notes is an OPLS/QM framing that does not apply to PCFF (a *missing* increment would give exactly 0.000; we got the correct pcff.frc value).
- **Fix:** Accept PCFF native bond-increment charges (correct + only consistent option for an EMC PCFF build). Corrected D-02 in decision record. No re-plan/re-build needed — worker did the physically correct thing transparently, not a silent improvisation of a different science parameter.
- **Outcome:** converged — D-02 corrected to PCFF bond-increment; cell.data accepted (8656 atoms, sulfone verified).

### R-02 — Equil-check C(t) hard-gate failure = backbone_types artifact (re-check, NOT extend)
- **Symptom:** First equil-check returned EXTEND. All physical gates PASS (density 1.187 g/cm³ = −4.3% vs exp; energy converged; Rg CV 26.2% < 30%; density homogeneity CV 20.2% < 25%; nematic 0.014). Only the C(t) chain-relaxation hard gate FAILED: 0.1% decayed (needs ≥10%), τ_relax=1.9×10⁹ ps, **C∞=112** (absurd; PSU expect ~2–10).
- **Root cause:** `check_equilibration_comprehensive` auto-detected backbone_types=[1,2,7,8]. Per emc_build.params the true PCFF type map is 1=c, 2=cp, 5=oe(sulfone =O), 6=oc(**diaryl ether O = backbone linker**), 7=oh(**terminal phenol end-group O**), 8=sf. Auto-detect **excluded the backbone ether O (oc=6)** and **wrongly included the end-group phenol (oh=7)** → broken backbone path → garbage C∞ and a C(t) that cannot decay. Confirmed via bond list: oc appears in cp_oc (Ar-O-Ar backbone); oh appears in cp_oh + ho_oh (Ar-O-H phenol cap, consistent with SMILES `*O…` chain ends). Advisor concurred.
- **Fix:** Do NOT extend the chain (5–10 ns extension cannot fix a mis-defined observable; ~12–24 h wasted). Re-run equil-check with backbone_types=[1,2,6,8] EXPLICITLY (≈40 min on existing dumps). Discriminator: C∞→single digits + C(t)≥10% decay ⇒ artifact confirmed, take tool's overall_pass.
- **MSD note (separate, backbone-independent):** MSD subdiffusion flag (α=0.022) is computed on COM/atoms, not backbone_types, so it may re-flag. Defensible read: melt at 700 K is only ~120–160 K above the MD Tg (~540–580 K expected for PSU), stiff backbone, 2 ns is a short COM-diffusion window → subdiffusive COM expected while all LOCAL packing gates pass. Not treated as an equilibration failure.
- **Outcome:** re-check done with [1,2,6,8]. C∞ 112→53.2 (confirms first value was corrupted) but still >15 — atom-type selection can't define a true backbone *path* for an aromatic main chain (all `cp` ring carbons counted, incl. 4 non-path carbons/ring). C(t) still 0% decay (τ≈1.78×10⁹ ps). overall_pass=**False**, driven ONLY by terminal-relaxation metrics (C(t)/C∞/MSD). All local/thermo/packing gates PASS; density 1.187 g/cm³ (−4.3%). → escalated to user (R-03) since this overrides the hard `overall_pass=True` success_criterion.

### R-07 — Born method removed from pipeline → glassy BM via Murnaghan (tooling-forced D-07 revision)
- **Symptom:** `gen_prompt --stage born` now errors: "Born+NVT removed from pipeline (2026-06-21) — PCFF+PPPM virial incompatibility, failed 3/3 runs (PMMA4/PVC1/PEEK1, K_T=−49.6 GPa). Use --stage murnaghan for glassy bulk modulus." Plan D-07 had chosen born_nvt (deform fallback).
- **Root cause:** PCFF cross-term virial + PPPM kspace inflate K_Born 8–15× and Var(P) ~10⁷× beyond what K_T=K_Born+NkT/V−(V/kT)Var(P) corrects (per guides/BORN_MATRIX.md, Schnell 2011). Not fixable at practical run lengths. born-worker now diagnostic-only, never auto-spawned.
- **Fix (tooling-mandated, deterministic — not a discretionary re-plan):** glassy BM now via **Murnaghan NPT compression at 300 K (primary)** + uniaxial deform (fallback), per guides/MURNAGHAN.md Rule B. Input npt_prod300_out.data; pressures **[-1000,-500,0,500,1000] atm** (guide default ±1000 symmetric); 0.3–0.5 ns/point; KOKKOS. Acceptance: volume_equilibrated per point, B0′∈[4,20], expect K≈3–5 GPa (PSU exp). D-07 updated. (Plan's bm_pressures_atm was null; using guide-default glassy range.)
- **Outcome:** murnaghan-worker FAILED — `run_bulk_modulus_series` has two tooling bugs (confirmed in server.py): (1) no `engine` param → emits gpu-package binary not KOKKOS; (2) feeds absolute log_path into `run_lammps_chain` which mangles the `>>` redirect → chain dies on stage 1 (chain 886eab7d). **Workaround (bypass broken chain tool):** hand-built 4 NPT-at-P scripts from the proven KOKKOS tg `.in` (correct FF block, thermo with `vol` = extractor-matched), launched KOKKOS env-pinned one-per-GPU. Used the existing `npt_prod300.log` (300 K, 1 atm, longest run) as the P≈1 atm anchor → 5 Murnaghan points total. extract_bulk_modulus_murnaghan parses V(P) from logs (eq_fraction=0.5).

### BM SERIES (Murnaghan glassy, manual KOKKOS bypass)
| Pressure (atm) | run | GPU | source |
|---|---|---|---|
| -1000 | bm_P-1000 | 0 | fresh NPT 0.5 ns |
| -500 | bm_P-500 | 1 | fresh NPT 0.5 ns |
| +1 | (npt_prod300) | — | reused equil production (anchor) |
| +500 | bm_P500 | 2 | fresh NPT 0.5 ns |
| +1000 | bm_P1000 | 3 | fresh NPT 0.5 ns |
Gates: volume_equilibrated/point, V(P) monotonic, B0'∈[4,20], K≈3–5 GPa (exp).

**V(P) verified (last 50% production):** all points equilibrated at target P; V monotonic ↓, ρ monotonic ↑:
| P_target | P_actual | V (Å³) | ρ (g/cm³) |
|---|---|---|---|
| -1000 | -1002 | 101783 | 1.155 |
| -500 | -502 | 100217 | 1.174 |
| +1 (anchor=npt_prod300) | -0.7 | 99072 | 1.187 |
| +500 | +497 | 98000 | 1.200 |
| +1000 | +1004 | 97064 | 1.212 |
Secant K (±1000 atm) ≈ 4.3 GPa; (0→1000) ≈ 5.0 GPa → **in PSU exp range 3–5 GPa**. (Note: guide's "ΔV/V 0.1–0.5%/1000atm for K 4–8 GPa" is ~10× off; correct ΔV/V for K=5 GPa is ~2%, which we observe.) Murnaghan fit next.

### R-06 — KOKKOS launch corruption + GPU-pinning bug (orchestrator recovery)
- **Symptom:** User flagged tg_sweep_rate40.log "corrupted" — thermo step column interleaved two streams (high ~138k + stray ~20k). Two processes appending to the same log via the `.in`'s `log ... append` directive.
- **Root causes (two bugs):** (1) The KOKKOS worker's `run_lammps_script` launched a stray **GPU-package** lmp (old binary, np1) alongside the intended KOKKOS run — both read the same `.in` → both wrote the same log → interleaved corruption + GPU contention. (2) Deeper: my direct relaunch via `mpirun -np 1` + `export CUDA_VISIBLE_DEVICES=2` landed on **GPU 0, not GPU 2** — **Open MPI's mpirun does not forward env vars to ranks unless `-x` is passed**, so lmp saw all GPUs and KOKKOS `-k on g 1` grabbed GPU 0 (contended). `export` in the wrapper also proved unreliable across conda/snapshot shells.
- **Fix:** Killed all PSU1 rate40 processes (multiple tangled attempts); archived corrupted logs. Final launch = **single KOKKOS rank, NO mpirun, `env CUDA_VISIBLE_DEVICES=2` prefix** directly on the lmp line (run `psu1r40kk`). Verified via `nvidia-smi pmon`: lmp pid on **GPU Idx 2 @ 83% util**, single log writer, clean monotonic thermo.
- **Outcome:** RESOLVED. Correctly pinned to dedicated GPU 2: **200 ts/s = 17.3 ns/day** (best config; ~2.9× original 4-GPU). Lesson: for single-rank KOKKOS, skip mpirun and use `env VAR=val lmp …` to pin the GPU. [[feedback... hardware]]

### R-05 — Engine switch to KOKKOS (user-directed recovery, mid-thermal-track)
- **Symptom:** GPU-package run b3835541 was (1) double-booked on GPU 0 with PLA1_tg_r160, and (2) fundamentally CPU-bound (GPU ~47% util — class2 bonded + PPPM run on host in the GPU package). User directed switch to KOKKOS engine (whole force calc on GPU).
- **Benchmark (6000 steps, GPU 2, co-tenant present):** KOKKOS `-k on g 1 -sf kk -pk kokkos` (mpi 1) = **13.48 ns/day** vs best GPU-package (np8 neigh-yes) 9.76 — and KOKKOS climbs further once GPU 2 fully clears (uncontended run hit ~26 ns/day). class2 bond/angle/dihedral/improper + pppm all have `/kk` variants and ran clean (0 dangerous builds). KOKKOS binary: `/home/arz2/lammps-install-kokkos/bin/lmp` (built Jun20). The user's "7.9×" is vs a naive GPU-package baseline; vs my optimized config it's ~1.4–2.7× depending on contention — still the clear winner, and mpi=1 frees CPU on the 18-phys-core shared box.
- **Fix:** Killed b3835541 (was 16%). Relaunch rate-40 with **engine=kokkos, gpu_ids=[2], mpi=1** (GPU 2 physically free; stale PLA1_r40 ledger claim being released). 
- **Outcome:** relaunched as 7b212051 (KOKKOS, GPU2, mpi1, vel seed 385703). **VERIFIED in production: 175 ts/s = 15.1 ns/day, GPU2 util 79%** (GPU-package left it CPU-bound at 47%). ~1.55× best GPU-package (9.76), ~2.5× original 4-GPU (6.0); rising as GPU2 co-tenant clears. rate-40 ETA ~21 h. **KOKKOS is the engine for all remaining PSU1 runs (rates 160/640, Born).**

### R-04 — GPU/MPI reconfiguration for speedup (user-directed, mid-thermal-track)
- **Symptom:** Tg rate-40 sweep on 4 GPUs (−pk gpu 4, np 4) ran at only ~6 ns/day for 8656 atoms. User flagged it and suggested dedicated 1 GPU + optimized MPI.
- **Root cause:** (1) Machine is **shared** — concurrent PolyJarvis runs (PEEK1, PLA1, PVC1, PMMA1) occupy all 4 GPUs; my "4-GPU" run was actually contending across all of them, never dedicated. (2) For a small 8656-atom PPPM system, domain-decomposing across 4 GPUs adds inter-GPU+FFT comm that outweighs compute — confirmed by concurrent calibration: PMMA1 (6020 atoms) gets **18.5 ns/day on 1 GPU (np 4)** while PEEK1 (4096) gets only 8.3 on 3 GPUs. (3) The launch also mismatched `-pk gpu 4` (cmdline) vs `package gpu 1` (in-script).
- **Benchmark (GPU 0, shared w/ PEEK1, 3000 steps):** np4=6.5, **np8=8.8**, np16=6.5 ns/day → **np=8 optimal** (np16 over-decomposes).
- **Fix:** Killed rate-40 run e115ffda (was 22%, sunk). Relaunch all rates **sequentially on 1 GPU (GPU 0, least-contended), mpirun -np 8, -pk gpu 1**. Machine has 36 cores (task header said 8; user OK'd more for MPI). Expect ~9–13 ns/day depending on co-tenant load — roughly 2× the old config, and a clean single-GPU footprint on the shared box.
- **Outcome (v1):** reconfigured + VERIFIED. b5c6df20 (np8, neigh no): 8.56 ns/day vs old 6.0 (~43% faster).
- **v2 — user proposed neigh yes + np4; benchmarked all 4 combos (6000-step LAMMPS Performance, GPU0):**
  - neigh no  np4 → 5.38 ns/day
  - neigh yes np4 → 6.89 ns/day
  - neigh no  np8 → 8.52 ns/day
  - **neigh yes np8 → 9.61 ns/day ← OPTIMUM**
  Findings: `neigh yes` (GPU neighbor build) is a real win (+13–28%). BUT np8≫np4 (system is **CPU-bound**: GPU only ~47% util; PCFF class-II bonded/PPPM on CPU is the bottleneck, so more ranks help). User's np4 premise (CPU oversubscription, spare=-2) no longer holds — **PEEK1 finished, freeing cores+GPU** (load 24/36; np8→32, headroom OK). Adopted **neigh yes + np8 = 9.61 ns/day (~60% over original 4-GPU 6.0)**. Relaunching rate-40 (3rd config) as final.

### R-03 — Hard equil gate (overall_pass) vs local-property deliverables (escalated to user)
- **Symptom:** Plan equil success_criterion = `check_equilibration_comprehensive.overall_pass=True`; corrected re-check returns False. Sole cause: terminal end-to-end chain relaxation (C(t) 0% decay, MSD sub-diffusive) — chains haven't reoriented over the 2 ns melt window.
- **Analysis:** For DP=20 stiff aromatic PSU at 700 K, terminal relaxation is ~tens–hundreds of ns (advisor concurred 5–10 ns extension wouldn't reach the 10% C(t) threshold; full relaxation infeasible in budget). Critically, NONE of the 3 requested properties need terminal relaxation: density (local packing, done, −4.3%), Tg (segmental, not terminal), glassy Born-K (plan D-07 explicitly justified as local segmental elasticity, not entanglement network). The failing gate measures a quantity our deliverables don't consume.
- **Fix (proposed):** Proceed to property tracks with documented caveat that chain conformations are not terminally relaxed (any chain-dimension-sensitive interpretation is caveated; our 3 targets are not). Overriding a hard plan gate → user decision required (per advisor + Validator policy). Alternatives offered: extend melt, or stop.
- **Outcome:** RESOLVED by user — **proceed to property tracks** with documented caveat (chain conformations not terminally relaxed; valid since all 3 targets are local properties). D-05 treated as PASS-for-our-purposes; equil .data accepted for Tg sweep + Born K. Caveat carried into RESULTS.

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Status |
|-------|----|-----------|--------|
| equil (9-stage glassy chain) | a3dd19a9 | Jun18 21:10 | done (Jun19 ~23:18, 9/9 completed) |
| tg-sweep rate 40 K/ns (4-GPU) | e115ffda | Jun20 ~01:30 | KILLED @22% — superseded by 1-GPU np8 config (R-04) |
| tg-sweep rate 40 K/ns (1-GPU np8, neigh no) | b5c6df20 | Jun20 ~14:00 | KILLED @~14% — superseded by neigh-yes/np4 (R-04 v2) |
| tg-sweep rate 40 K/ns (np4 neigh yes) | d94a548f | Jun20 ~17:30 | KILLED — np4 slower (CPU-bound); benchmark → np8 best |
| tg-sweep rate 40 K/ns (GPU-pkg np8) | b3835541 | Jun20 ~18:00 | KILLED @16% — double-booked GPU0 + CPU-bound; switched to KOKKOS (R-05) |
| tg-sweep rate 40 K/ns (KOKKOS, mis-pinned/dbl-launch) | 7b212051/kk2 | Jun20 ~23:30 | KILLED — log corruption + ran on GPU0 (R-06) |
| tg-sweep rate 40 K/ns (KOKKOS GPU2 FINAL) | psu1r40kk | Jun21 ~00:30 | DONE Jun21 16:59 (26 T-steps 750→250, wall 17h, clean log verified) |
| tg-sweep rate 160 K/ns (KOKKOS GPU2) | psu1r160kk | Jun21 ~17:05 | DONE Jun21 ~21:20 (26 T-steps, wall 4:14h, clean) |
| tg-sweep rate 640 K/ns (KOKKOS GPU3) | psu1r640kk | Jun21 ~17:05 | DONE Jun21 ~18:07 (26 T-steps, wall 1:02h, clean) |

---

## D-05 CONVERGENCE DETAIL

<!-- CORRECTED run with backbone_types=[1,2,6,8] (see R-02). overall_pass=False driven solely by C(t)/C∞/MSD-trap, which are terminal-chain-relaxation metrics not required by our local target properties (density/Tg/glassy-K). -->

## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` (backbone_types=[1,2,6,8]) · melt NVT T=699.9 K · 1951 frames · 2026-06-20 00:26

**Overall: FAIL — driven only by terminal-chain-relaxation metrics (C(t)/C∞/MSD trap); ALL local/thermo/packing gates PASS. See R-02 + R-03 for the proceed-with-caveat decision.**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Energy drift | 0.0467% (p=0.4404) | <1%, p<0.01 | PASS |
| Energy block-SEM | 0.0139% | <1% | PASS |
| Density drift/SEM | NVT (fixed V) | — | N/A |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 26.2% (mean Rg 28.06 Å) | <30% | PASS |
| C∞ | 53.223 (was 112 w/ wrong types) | [3,15] | ⚠ INFO — inflated by aromatic ring carbons in atom-type-based path; not a true backbone-path C∞ |
| MSID slope | 0.964 (R²=0.9967), Gaussian pass | 1.0±20% | PASS |
| C(t) τ_relax | 1.78×10⁹ ps, 0% decayed over 1951 ps | ct≥10% | ✗ FAIL — real terminal relaxation ≫ 2 ns for DP=20 stiff aromatic melt; not reachable in budget |
| MSD | α=0.022, MSD_max 102 Å² < Rg² 841 | — | ⚠ sub-diffusive (COM-based, backbone-independent) |
| R_ee mean ± std | 69.42 ± 35.79 Å (N=8) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0139 ± 0.0022 | <0.10 | PASS |
| Density homogeneity CV | 20.2% (7³ grid) | <25% | PASS |

### Density (glassy 300 K, npt_prod300)
ρ = **1.187 ± 0.0001 g/cm³** (SEM; std 0.0035) at T=300.05 K, plateau_equilibrated=true, 1001 plateau points. Exp PSU 1.24 → **−4.3%**.

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | 28.06 Å (CV 26.2%) | CV < 30% → PASS |
| MSD plateau   | sub-diffusive (MSD_max 102 < Rg² 841 Å²) | ⚠ terminal not relaxed (non-binding for local props) |
| Density homog (CV) | 20.2% | < 25% → PASS |
| C(t) decay (melt NVT) | 0% at threshold 10% | FAIL (terminal-relaxation metric; see R-02/R-03) |
| τ_c chain relax (KWW) | 1.78×10⁹ ps (β=0.535; extrapolated, traj 1951 ps) | annotation only |
| R_ee mean ± std | 69.42 ± 35.79 Å (N=8 chains) | end_to_end_distribution.png |

---

## TIMING

| Worker | Submitted | Completed | Wall time | Throughput |
|--------|-----------|-----------|-----------|------------|
| Cell build | [HH:MM] | [HH:MM] | [Xh Ym] | — |
| Equilibration | [HH:MM] | [HH:MM] | [Xh Ym] | [X ns/day] |
| Tg sweep | [HH:MM] | [HH:MM] | [Xh Ym / — not requested] | [X ns/day] |
| Born / Deform / Murnaghan | [HH:MM] | [HH:MM] | [Xh Ym / — not requested] | — |
| **Total** | | | **[Xh Ym]** | |

GPU inventory (`nvidia-smi` at run start):
- GPU 3: Quadro RTX 6000, 24 GB, 23.1 GB free (assigned)
- GPUs 0,1,2 also present (Quadro RTX 6000, 24 GB each)

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.187 ± 0.0001 g/cm³ | 1.24 g/cm³ (PSU/Udel) | −4.3% | NPT 300K plateau (npt_prod300) | ✓ |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg        | 499.7±15 K (primary); 540 K (alt method) → report **~500–540 K** | 463 K (PSU/Udel) | +8% to +17% | hyperbola fit R²=0.9965 (40 K/ns); broad transition (~50 K) → 40 K gap between fit methods (Rule A flag) | ✓ (broad) |
| α_g (CTE) | 20.7×10⁻⁵ K⁻¹  | ~17–21×10⁻⁵ K⁻¹ (vol., lit.) | ~ok | −a_glassy / ρ (vol. CTE)  | ✓ |
| α_r (CTE) | 46.8×10⁻⁵ K⁻¹  | ~55–60×10⁻⁵ K⁻¹ (vol., lit.) | low | −a_rubbery / ρ (vol. CTE) | ⚠ |
| ΔCp at Tg | 0.148 J/(g·K)   | ~0.18–0.22 J/(g·K)     | low  | H(T) bilinear fit         | ⚠ |
| cooling rate | 40 K/ns      | ~10⁻⁷ K/ns (exp)       | —    | slowest of 3 rates        | annotation |
| expected Tg offset | +50–80 K (production); we got +37 K | — | — | DP=20 policy-compliant, KOKKOS | annotation |
| multirate note | 160/640 K/ns unreliable (fit artifact / under-equilibrated per-T); rate-extrapolation not usable | — | — | — | annotation |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 4.43 ± 0.06 GPa | 3–5 GPa        | in range | Murnaghan EOS (glassy, 300 K NPT, 5 pts ±1000 atm), r²=0.9997 | ✓ |
| B0' | 12.70   | 7–11 (typical) | —    | Murnaghan fit (slightly high, within [4,20] gate) | annotation |
| G   | N/A     | —              | —    | not computed (deform fallback not run — Murnaghan primary succeeded) | N/A |
| E   | N/A (~2.5–2.6 exp) | 2.5–2.6 GPa | — | not computed (would need deform; only K requested via bulk_modulus) | N/A |

### D — Chain Structure

| Metric | Value | Status |
|--------|-------|--------|
| Rg mean ± std     | [X ± Y] Å | [sourced from D-05] |
| MSD plateau       | [plateau / still diffusing] | [PASS / FAIL] |
| Density homog (CV)| [X]% | [PASS / FAIL] |
| C(t) decay (melt NVT) | [X%] / N/A — rubbery | [PASS / FAIL] |
| τ_c chain relax (KWW) | [X] ps / N/A — rubbery | annotation only |
| R_ee mean ± std   | [X ± Y] Å (N=[N] chains) | [sourced from D-05] |

Simulation dir: `/home/arz2/PolyJarvis/data/PSU1/lammps/`
Outputs: `data/PSU1/raw/` — `run_summary.json`, `tg_summary.json` (+tg_r40/160/640/), `equilibrated_density.json`, `bulk_modulus_murnaghan.json`; figures in `data/PSU1/graphs/`

### FINAL RESULT (all 3 properties, vs experiment)
| Property | Computed | Exp | Error | Status |
|----------|----------|-----|-------|--------|
| ρ (300 K) | 1.187 g/cm³ | 1.24 | −4.3% | ✓ PASS |
| Tg | 499.7 K (alt 540; ~500–540) | 463 | +8% (to +17%) | ⚠ high by expected MD cooling-rate bias |
| K (bulk modulus) | 4.43 ± 0.06 GPa | 3–5 (5.3 DB) | in range | ✓ PASS |

Tg "FAIL" vs the tight 439–479 summary band is the **expected MD overestimate** (fast cooling, 40 K/ns ≫ exp), not a model failure — magnitude (+8%) is good for PCFF/MD. All physically sound.

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 55.0 h  |  **GPU**: 55.0 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1/4
- Source: `data/PSU1/lammps/**/*.log` (Born stages excluded); reproducible via `paper/gen_table_compute_cost.py`.
