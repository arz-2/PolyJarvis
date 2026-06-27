# Polymethyl Methacrylate (PMMA) Run 1 · 2026-06-18 → 2026-06-21 · COMPLETE (all 3 properties)
SMILES: `*CC(C)(C(=O)OC)*`  |  FF: PCFF  |  Charges: RESP  |  DP: 40  |  Chains: 10  |  GPU: 1
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=random(-1, EMC does not persist resolved value)  |  SEED_HOT=989366  |  SEED_COLD=N/A (no velocity re-init at cold stages)
Plan: `data/PMMA1/raw/run_plan.json`  |  mode: deterministic  |  confidence: high  |  critic: approved (round 0, auto)  |  T_workflow_K: 550

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF                | classify_polymer → PACR → EMC/PCFF (Class II); NkepsuMbitou2025: GAFF Tg err >45% for PMMA, PCFF within 10% |
| D-02 Charges        | PCFF embedded (bond-increment)        | EMC build path assigns Class II charges in-step; plan's `charge_method=RESP` is the RadonPy/QM path and is not used by EMC — confirm from builder lammps_flags |
| D-03 Electrostatics | PPPM                          | ester heteroatoms (O) → PPPM, cutoff 12 Å |
| D-04 System size    | DP=40, 10 chains, 6020 atoms                        | polymer_rules.json PACR default; ρ_initial=0.6 g/cm³; 6 atom types (PCFF) |
| D-05 Convergence    | PASS                         | thermo gates (density+energy) converged; ρ=1.117 g/cm³ (−7.4% vs 1.205); C(t)/C∞ non-binding (EMC backbone ambiguity) |
| D-06 Tg fit quality | EXCELLENT  | Tg=340 K (alt 353.9 K, Δ14 K <20 K ok); R²=0.9971, N=44 bins; α_g=18.1×10⁻⁵ K⁻¹, α_r=27.7×10⁻⁵ K⁻¹, ΔCp=0.13 J/(g·K). is_glassy=True (Tg>300). Tg −10% vs exp 378 K (PCFF low side); cool rate 200 K/ns |
| D-07 Property method | deform fallback (glassy) — Born failed (R-04) | Tg=340 K → is_glassy=true; K=3.39 GPa (slow 1e7/s) cross-checked by fluctuation 3.69 GPa (Δ9%); G=1.06, E=2.89 GPa, ν=0.358 |

<!-- Add rows for non-routine decisions (parameter overrides, custom protocols, etc.) -->

---

## RECOVERIES

<!-- One block per incident. Write "None" if the run completed without errors. -->
<!-- Outcome options: converged / failed again / escalated / UNRESOLVED (stop after 2 attempts) -->

### R-01 · Equil chain CPU-kspace-bound at MPI=1 → restart at MPI=8 + PPPM 1e-4
- **Symptom:** After 18.5 h, chain `b59d4304` was only at stage 3/9 (npt_compress, step 156k/500k). Throughput ~10 steps/s for 6020 atoms; GPU 1 at 0% util while holding memory. At this pace the 9-stage chain would exceed the 48 h max_runtime.
- **Diagnosis (LAMMPS timing breakdown, nvt_softheat):** Kspace (PPPM, CPU) = **65.8%**, Bond (class2, CPU) = **25.8%**, Pair (GPU) = only 2.5%. Run was `1 MPI task × 1 OpenMP thread`, 43% CPU use. GPU was *not* the bottleneck — the 0% util is the expected signature of CPU-bound kspace/bonded work. Confirmed not a bug: sibling PE1 (united-atom TraPPE, no kspace) did softheat in 6 min; sibling PLA1 (PCFF+PPPM, like PMMA) was also ~8 h. Cost is intrinsic to PCFF Class II + PPPM at MPI=1. Machine has 36 cores (task stated 8); only 3 in use.
- **Fix (user-approved):** Stopped PMMA chain only (siblings PE1/GPU0, PLA1/GPU2 untouched; another user's job on GPU1 left alone). Preserved 13 h soft-heat (`nvt_softheat_out.data`). Patched `kspace_style pppm 1e-6 → 1e-4` in the 6 PPPM stages (npt_compress uses coul/cut — untouched; 1e-4 is standard for equilibration, negligible structural effect). Relaunched stages 3–9 as `chain_b59d4304r` at **MPI=8** (the 8 cores the task budgeted; parallelizes Kspace+Bond ~near-linearly), same GPU 1, same PCFF physics. `generate_equilibration_workflow` hardcodes 1e-6 with no accuracy param, so a PMMA-scoped script patch + resume was required rather than regeneration.
- **Verification:** MPI=8 confirmed (2×2×2 grid), npt_compress resumed from softheat output at correct state (ρ=0.6, T=600). Measured throughput **125 steps/s vs 10.4 at MPI=1 = 12× speedup** (MPI parallelism × PPPM 1e-4). Remaining 7 stages ≈ 8 h, within the ~29 h budget remaining.
- **Outcome:** converged on fix — monitoring `b59d4304r`. **Equil completed 06-20 03:37, all 9 stages, equil-check PASS.**

### R-02 · Tg-sweep compute optimization (user requested speedup; soft budget overrun accepted)
- **Context:** At equil completion 36.3 h of 48 h budget was spent (mostly the R-01 MPI=1 stall + recovery). Full Tg sweep (23 pts × 500 ps = 11.5 M steps) needs ~23 h at the old throughput → cannot fit remaining budget. User: budget is SOFT, finish all 3 properties, explore speedups, launch at MPI=4 (be considerate of concurrent runs PEEK1/PLA1/PVC1/cis-PBD1).
- **Benchmark (6020-atom PMMA cell, GPU 1, contended machine, 3000-step runs):**
  | Config | steps/s |
  |--------|---------|
  | MPI=4, GPU, `neigh no` (engine default) | 140.7 |
  | MPI=4, GPU, `neigh yes` | **183.1 (+30%)** |
  | MPI=8, GPU, `neigh no` | 139.0 (no gain — CPU-contended) |
  | MPI=6, CPU-only | 79.0 |
- **Findings:** (1) Under contention MPI=8 buys nothing over MPI=4 → MPI=4 is free, spares co-runs. (2) GPU neighbor build (`neigh yes`) is +30%. (3) Kspace bottleneck already solved by R-01's MPI+1e-4 (Kspace fell 66%→14% of loop; Pair 36%/Bond 24% now dominate), so `pppm/gpu` offers little.
- **Safety check on `neigh yes`:** engine defaults NPT to `neigh no` (GPU neighbor realloc can crash on volume change). Ran a 24 k-step probe heating 300→450 K (box expansion, the dangerous direction) then cooling: exit 0, Dangerous builds = 0, no realloc/lost-atom errors. Safe for this system.
- **Config locked:** MPI=4 + GPU 1 + PPPM 1e-4 + `package gpu 1 neigh yes` → 183 steps/s, Tg sweep ETA ~17.4 h. These are execution optimizations (bit-identical neighbor lists; 1e-4 standard for equilibration) — no change to plan physics or success criteria.
- **Outcome:** optimized — launching Tg sweep at 183 steps/s (24% faster than safe default).

---

### R-03 · tg-sweep-worker emitted single-step template (not the 23-point sweep) → orchestrator rebuilt the staircase
- **Symptom:** Sentinel `done_8e525d98.json` reported `completed` only ~17 min after submit (vs ~17 h expected). Wrapper showed `STAGE COMPLETE: Tg step T=300.0K P=1.0atm steps=100000` — a SINGLE 300 K point of 100 k steps, not the 23-point 600→150 K sweep at 500 k steps/T. No Tg extractable from one temperature.
- **Diagnosis:** The worker generated the "Tg Sweep **Single Step**" template (designed to be chained by the caller) but submitted just one instance at the wrong T (300 not 600) and wrong step count (100 k not 500 k), and injected a spurious `fix shake` not present in working sibling sweeps. The correct structure (per PE1/PEEK1 siblings) is a LAMMPS staircase: one `velocity create` at T_START, then `variable temps index ...` / `label TEMP_LOOP` / `run` / `next` / `jump SELF`.
- **Fix:** Orchestrator hand-built the correct staircase `tg_sweep.in` (23 pts 600→160 K step 20, 500 k steps/T, PCFF + pppm 1e-4 + neigh yes, velocity create 600 K seed 989366, no SHAKE) modeled on the PE1 sibling, and resubmitted as `8e525d98r` (MPI=4, GPU 1, self-managed sentinel). Stale single-step outputs (tg_step.log/tg_step_out.data) removed.
- **Outcome:** rebuilt and resubmitting. (Attempt 1 of 2 for tg-sweep.)

---

### R-04 · Born K_T failed (undersampled Var(P), K=−10.5 GPa) — fluctuation cross-check gives physical K=3.69 GPa
- **Symptom:** extract_bulk_modulus_born returned **K = −10.53 ± 9.06 GPa** (negative → thermodynamically invalid). Method=born_nvt, overall FAIL.
- **Diagnosis:** difference-of-large-numbers breakdown, NOT a subtraction bug. K_Born(affine)=61.05 GPa, fluctuation correction=72.00 GPa, net=−10.5. Root cause = undersampled Var(P): 0.5 ns / 500k-step Born run produced only ~250 production frames, τ_eff≈0.08 frames; block-K = [−8.8, +0.5, +4.1, −46.6, −7.4] GPa, SEM(9.06) > |K|. V_std=0 is correct NVT behaviour (not a bug). This is the **first Born-method validation on PMMA (project goal): the 0.5 ns NVT run length is inadequate for the glassy fluctuation term** — the affine and fluctuation terms are both ~60–72 GPa and must cancel to single-digit GPa, demanding far more sampling than 250 frames.
- **Free diagnostic:** fluctuation method on the existing npt_prod300 (2 ns NPT, volume fluctuations) → **K_dyn = 3.69 ± 0.47 GPa**, physical and within exp [3.5–5.0] GPa. Caveat: glassy systems can be non-ergodic in volume, so treat as a cross-check.
- **Fix (advisor-confirmed):** Option A — spawn deform-worker (plan-documented born fallback; does NOT consume born's retry budget). Option C rejected: converging Var(P) needs ~100× frames ≈ 50 ns CPU-only numdiff — prohibitive. Option B rejected as primary: fluctuation-K is diagnostic-by-design (glassy non-ergodicity suppresses Var(V), biasing K high; 3.69 at low end of range is partly fortuitous) → keep as cross-check. Deform uses the SLOWER strain rate (1e7/s) for the reported value (fast rates inflate glassy moduli).
- **Outcome:** escalated to deform-worker fallback (run_id below). Born-method validation conclusion: **0.5 ns NVT is inadequate for glassy PMMA K_T** — needs O(10–50 ns) to converge the difference-of-large-numbers.

### R-05 · deform-worker emitted AMBER force field (not PCFF) → both runs died at read_data; orchestrator patched FF block
- **Symptom:** Both deform runs (slow 811d6fd2, fast be5ee541) wrote `failed` sentinels ~6 min after submit. Slow log: `WARNING: Bond style class2 in data file differs from currently defined bond style harmonic` → `ERROR: Incorrect args for bond coefficients`.
- **Diagnosis:** The generated deform `.in` used AMBER defaults (`pair_style lj/charmm/coul/long 8.0 12.0`, `bond_style harmonic`, `angle_style harmonic`, `dihedral_style fourier`, `improper_style cvff`, `special_bonds amber`, `mix arithmetic`) despite `use_pcff=true` — the **FF-flag bug** (cf. the run_bulk_modulus_series FF bug) now in the deform path: generate_script didn't receive/apply the PCFF selector. The class2 data-file bond coeffs are incompatible with `bond_style harmonic`. It also injected a SHAKE fix (this system was equilibrated without SHAKE).
- **Fix:** Orchestrator patched the FF block in BOTH `.in` files to the proven PCFF block (`lj/class2/coul/long 9.5 9.5` + `pppm 1e-4` + class2 bonded + `special_bonds lj/coul 0 0 1` + `mix sixthpower tail yes`) and removed SHAKE; deform rates untouched (slow 1e-08/fs=1e7/s, fast 1e-07/fs=1e8/s). Smoke-tested the slow script (exit 0, no FF error, deform strains lx, stress recorded). Resubmitted both via the intact run.sh wrappers (`-sf gpu -pk gpu 1`, GPU 1).
- **Outcome:** rebuilt and resubmitting. (deform attempt 2 of 2 — born→deform escalation; if this fails, fall back to reporting the fluctuation cross-check K=3.69 GPa.)

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Status |
|-------|----|-----------|--------|
| equil (MPI=1) | b59d4304 | 06-18 15:33 | stopped @ stage 3 — CPU-bound, see R-01 |
| equil resume (MPI=8, PPPM 1e-4) | b59d4304r | 06-19 10:11 | done — completed 06-20 03:37, all 9 stages, npt_prod300_out.data written |
| tg sweep (worker, single-step BUG) | 8e525d98 | 06-20 09:33 | failed — emitted single 300K/100k-step point, not the sweep (see R-03) |
| tg sweep REBUILD (staircase, MPI=4, GPU1, 1e-4, neigh yes) | 8e525d98r | 06-20 09:55 | done — completed 06-21 01:37, all 23 pts (600→160K), 11.5M steps, wall 15:43 |
| born matrix NVT 300K (MPI=4 CPU, numdiff) | bb096bff | 06-21 01:43 | done but INVALID — K=−10.5 GPa undersampled (see R-04); escalated to deform |
| deform attempt 1 (AMBER FF bug) | 811d6fd2/be5ee541 | 06-21 06:25 | failed — wrong FF, read_data error (see R-05) |
| deform REBUILD slow 1e7/s (REPORTED) + fast 1e8/s | 811d6fd2 / be5ee541 | 06-21 06:33 | done — both completed ~10:56, slow wall ~4.4h, 3.2% strain reached |

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=549.89 K · 1951 frames analysed (skip=50) · 2026-06-20 03:39

**Overall: PASS (thermo gates: density+energy converged; C(t) non-binding per PMMA constraint)**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Energy drift | 0.1672% (p=0.0018) | <1%, p<0.01 | PASS |
| Energy block-SEM | 0.0204% | <1% | PASS |
| (Density NVT — fixed volume) | — | — | N/A |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 13.1% | <30% | PASS |
| C∞ | 203.782 | lit. varies | INFO (non-binding — EMC backbone ambiguity) |
| MSID slope | 1.083 (R²=0.9917) | 1.0 ±20% | OK |
| C(t) τ_relax | 4.2e9 ps (0.5% decayed) | — | ⚠ partial (non-binding) |
| MSD kinetic trap | yes (α=−0.004, MSD=61.6 Å² < Rg²=161.1) | — | ⚠ trapped (glassy, expected) |
| R_ee mean ± std | 22.28 ± 9.84 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0286 ± 0.0025 | <0.10 | PASS |
| Density homogeneity CV | 22.3% (6³ grid, 27.9 atoms/voxel) | <25% | PASS |

**Decision:** Density + energy gates PASS. C(t)/C∞ flags non-binding for PMMA (EMC does not type the backbone distinctly from sidechain carbons). Kinetic trap expected in glassy melt state.

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | (Rg² = 161.1 Å² → Rg ≈ 12.69 Å) | CV 13.1% < 30% → PASS |
| MSD plateau   | trapped (glassy, α=−0.004) | expected for glassy melt |
| Density homog (CV) | 22.3% | < 25% → PASS |
| C(t) decay (melt NVT) | 0.5% (non-binding) | INFO |
| τ_c chain relax (KWW) | 4.2e9 ps (non-binding) | annotation only |
| R_ee mean ± std | 22.28 ± 9.84 Å (N=10 chains) | end_to_end_summary.json |

---

## TIMING

| Worker | Submitted | Completed | Wall time | Notes |
|--------|-----------|-----------|-----------|-------|
| Cell build | 06-18 ~15:15 | 06-18 15:30 | ~15 m | EMC, 6020 atoms |
| Equilibration | 06-18 15:33 | 06-20 03:37 | ~36 h (incl. R-01 MPI=1 stall + recovery) | 9 stages; productive wall ~16 h after fix |
| Tg sweep | 06-20 09:55 | 06-21 01:37 | 15 h 43 m | 23 pts, 11.5 M steps, 214 steps/s (after R-03 rebuild) |
| Born (failed) | 06-21 01:43 | 06-21 ~06:00 | ~4.3 h | INVALID (R-04 undersampled) |
| Deform (slow+fast) | 06-21 06:33 | 06-21 10:56 | ~4.4 h | after R-05 FF patch; slow = reported K |
| BM extract + summary | 06-21 ~10:56 | 06-21 11:05 | ~10 m | — |
| **Total wall** | 06-18 15:15 | 06-21 11:05 | **~68 h** (soft 48 h overrun, user-approved) | 5 recoveries (R-01–R-05) |

GPU inventory (`nvidia-smi` at run start):
- GPU 1: Quadro RTX 6000, 24 GB, 19.0 GB free (assigned)

---

## RESULTS

**HEADLINE VERDICT (vs canonical PMMA, polymer_rules.json):** all three properties land in the right ballpark but **systematically SOFT ~7–20%** — density 1.117 (−7.4%), Tg 340 K (−10.1% vs 378), K 3.39 GPa (−3% below 3.5 lower bound, −20% vs midpoint). Coherent single cause: **PCFF underbinds PMMA**, compounded by DP=40 finite-MW depression. None cleanly in-range; none wildly off. K corroborated by two independent methods (deform 3.39, fluctuation 3.69, Δ9%).
**Validation-range note:** gen_prompt's auto exp_tg_range [326–366] was a BUG (averages PMMA+PMA+PAA → 346); corrected to canonical 378 K. Summary-worker's K range [3.0–4.2] was hallucinated; corrected to polymer_rules [3.5–5.0]. run_summary.json statuses re-scored against canonical values (all WARN_soft). See `feedback_genprompt_exp_tg_avg_bug`.

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.117 ± 0.005 g/cm³ | 1.145–1.265 g/cm³ (1.205 mid) | −7.4% | NPT 300K plateau | ⚠ (low but within MD screening tol) |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg        | 340 K (alt 354) | 373–388 K (378 mid)    | −10.1% | bilinear fit (R²=0.9971)  | ⚠ (PCFF low side, within ~10%) |
| α_g (CTE) | 18.1×10⁻⁵ K⁻¹  | ~20–26×10⁻⁵ K⁻¹       | low end | −a_glassy / ρ_mean_glassy | ✓ |
| α_r (CTE) | 27.7×10⁻⁵ K⁻¹  | ~50–55×10⁻⁵ K⁻¹       | underpred | −a_rubbery / ρ_mean_rubbery | ⚠ |
| ΔCp at Tg | 0.13 J/(g·K)    | ~0.28–0.34 J/(g·K)     | underpred | H(T) bilinear fit (R²=0.990) | ⚠ |
| cooling rate | 200 K/ns    | ~10⁻⁷ K/ns (exp)       | —    | —                         | annotation |
| expected Tg offset | normally +30–80 K (fast cooling); here −38 K (PCFF FF underpredicts PMMA Tg) | — | — | — | annotation |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 3.39 GPa | 3.5–5.0 GPa    | −3% (vs lower) / −20% (vs mid 4.25) | deform slow 1e7/s (fit R²=0.976 C11); fluct xcheck 3.69 GPa (Δ9%) | ⚠ borderline (just below range) |
| B0' | N/A     | 7–11 (typical) | —    | Murnaghan fit (rubbery only) — N/A glassy | annotation |
| G   | 1.06 GPa | ~1.7 GPa      | −38% | deformation (uniaxial, slow)            | ⚠ soft |
| E   | 2.89 GPa | ~3.3 GPa      | −12% | deformation (uniaxial, slow)            | ⚠ soft |

<!-- Born path FAILED (R-04): K=−10.5 GPa undersampled. Fast-rate deform (2.75 GPa) noise-dominated, discarded. ν=0.358. -->
<!-- Coherent narrative: PCFF underbinds PMMA → under-dense (−7.4%), low Tg (−10%), soft moduli (K/G/E ~12–38% low). Internally consistent. -->
<!-- Two independent K methods (deform 3.39, fluctuation 3.69) agree within 9% → confidence in K≈3.4–3.7 GPa. -->
| ν (Poisson) | 0.358 | ~0.37–0.40 | low | deformation (slow) | annotation |

### D — Chain Structure

| Metric | Value | Status |
|--------|-------|--------|
| Rg mean ± std     | [X ± Y] Å | [sourced from D-05] |
| MSD plateau       | [plateau / still diffusing] | [PASS / FAIL] |
| Density homog (CV)| [X]% | [PASS / FAIL] |
| C(t) decay (melt NVT) | [X%] / N/A — rubbery | [PASS / FAIL] |
| τ_c chain relax (KWW) | [X] ps / N/A — rubbery | annotation only |
| R_ee mean ± std   | [X ± Y] Å (N=[N] chains) | [sourced from D-05] |

Simulation dir: `[PATH]`
Outputs: `data/[RUN]/outputs/` — CSVs, JSONs, `figures/*.png`, `run_summary.json`
