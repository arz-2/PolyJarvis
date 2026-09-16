# PEG (POXI) force-field comparison · PEGCMP1 · 2026-08-12 → in progress
SMILES: `*CCO*`  |  FF: **compass**  |  Charges: EMC bond-increment  |  DP: 100  |  Chains: 10  |  GPU: 0
Requested: density  |  Replicate: 1 of 1  |  Seeds: EMC=random(-1)  |  velocity_seed=20260812
Plan: `data/PEGCMP1/raw/run_plan.json`  |  mode: deterministic  |  confidence: novel  |  critic: n/a (deterministic)  |  T_workflow_K: 500
Canonical SMILES: `*CCO*`  |  IS_NOVEL: false (POXI class defaults)  |  System confidence: novel

**Purpose — reviewer para 7 alternative-force-field arm.** Baseline is the archived PEG1-4 (PCFF),
which is -5.43% vs experimental rho(T) at 300 K and +50% on K. PEG sits above Tg (206 K) at 300 K,
so npt_production samples an equilibrium liquid and the cooling/trapping explanation is unavailable.
Protocol is held identical to the baseline; only the force field differs.
Cell: 7020 atoms (exact parity with archived PEG1).

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | [GAFF2 / PCFF / OPLS-AA / TraPPE-UA]                | [classify_polymer returned class X → auto-routed / override: REASON] |
| D-02 Charges        | [RESP / AM1-BCC / Gasteiger / embedded in FF]        | [polar backbone / nonpolar / EMC: embedded] |
| D-03 Electrostatics | [PPPM / lj/cut [CUTOFF] Å]                          | [heteroatoms → PPPM / pure C/H → lj/cut 12 Å] |
| D-04 System size    | DP=[N], [N] chains, [N] atoms                        | [polymer_rules.json default / literature N chains / stiff chain] |
| D-05 Convergence    | [PASS / EXTEND×N / ESCALATE]                         | [overall_pass=true / [N] extension(s) needed] |
| D-06 Tg fit quality | [EXCELLENT / ACCEPTABLE / BORDERLINE / ABORT / N/A]  | [R²=[X], N=[N] bins, F-stat=[TIER]; is_glassy=[true/false] (Tg=[X] K > 300 K) / N/A — tg not requested] |
| D-06b Multirate Tg  | [DSC-equiv=[X] K / N/A]                              | [log-linear Tg(Γ) b=[X] K/ln(K/ns), R²=[X], N_rates=[3] @ [40,160,400] K/ns, N_repl=[N]; extrapolated to 1.67e-10 K/ns (10 K/min DSC); VF=[quality] (diagnostic, <2 decades) / N/A — single-rate] |
| D-07 Property method | [born (glassy) / deform fallback (glassy) / murnaghan (rubbery) / fluctuation (rubbery fallback) / N/A] | [Tg=[X] K → is_glassy=[true/false]; bm_pressures_atm=[Y/N] / N/A — bulk_modulus not requested] |

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

None

---

## SIMULATION STATE

<!-- Written before launching each BACKGROUND-WAIT waiter; updated to done/failed on the completion
     wakeup. Used for session restart. BgTask = the run_in_background Bash task id of the live waiter
     (— once it has returned), so a restarting session can tell whether a waiter is still in flight. -->

| Stage | ID | BgTask | Submitted | Completed | Wall | Status |
|-------|----|--------|-----------|-----------|------|--------|
| [equil / tg-sweep / deform / murnaghan] | [chain_id / run_id] | [bg task id / —] | [HH:MM] | [HH:MM / —] | [Xh Ym / —] | [monitoring / done / failed] |

GPU inventory (`nvidia-smi` at run start): GPU [ID]: [model], [VRAM] GB, [free] GB free

---

## D-05 CONVERGENCE DETAIL

<!-- Paste result["d05_markdown"] from check_equilibration_comprehensive here. -->

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | [X ± Y] Å | CV < 30% → [PASS / FAIL] |
| MSD plateau   | [plateau / still diffusing] | [PASS / FAIL] |
| Density homog (CV) | [X]% | < 25% → [PASS / FAIL] |
| C(t) decay (melt NVT) | [X%] at threshold [Y] / N/A — rubbery | [PASS / FAIL] |
| τ_c chain relax (KWW) | [X] ps / N/A — rubbery | annotation only |
| R_ee mean ± std | [X ± Y] Å (N=[N] chains) | end_to_end_summary.json |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | [X] g/cm³ | [X]–[X] g/cm³ | [X]% | NPT 300K plateau | [✓ / ⚠] |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (DSC-equiv) | [X] K      | [X]–[X] K              | [X]% | log-linear Tg(Γ)→10 K/min (multirate) | [✓ / ⚠] |
| Tg (MD @400 K/ns) | [X] K   | —                      | —    | bilinear fit, highest screening rate | annotation |
| α_g (CTE) | [X]×10⁻⁵ K⁻¹   | [X]–[X]×10⁻⁵ K⁻¹      | [X]% | −a_glassy / ρ_mean_glassy | [✓ / ⚠] |
| α_r (CTE) | [X]×10⁻⁵ K⁻¹   | [X]–[X]×10⁻⁵ K⁻¹      | [X]% | −a_rubbery / ρ_mean_rubbery | [✓ / ⚠] |
| ΔCp at Tg | [X] J/(g·K)     | [X]–[X] J/(g·K)        | [X]% | H(T) bilinear fit         | [✓ / ⚠ / N/A] |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | [X ± Y_sem] GPa | [X]–[X] GPa    | [X]% | born (N_eff=[N], τ_ac≈[X] ps) / deform / murnaghan / fluctuation (N_eff=[N], τ_eff=[X]%) | [✓ / ⚠ / — no exp. ref.] |
| B0' | [X]     | 7–11 (typical) | —    | Murnaghan fit (rubbery only)            | annotation |
| G   | [X] GPa | [X]–[X] GPa    | [X]% | deformation (glassy only)               | [✓ / ⚠ / N/A] |
| E   | [X] GPa | [X]–[X] GPa    | [X]% | deformation (glassy only)               | [✓ / ⚠ / N/A] |

Simulation dir: `data/[RUN]/lammps/`
Outputs: `data/[RUN]/raw/` — JSONs; `data/[RUN]/graphs/` — PNGs; `data/[RUN]/raw/run_summary.json`

## SIMULATION STATE

- **Phase A / foundation — equilibration submitted** 2026-08-12
  - chain_id: `b9b7bf5d`  |  GPU 0 (claimed)  |  engine kokkos, mpi=1  |  9 stages (rubbery + melt split)
  - work_dir: `data/PEGCMP1/lammps/equil/`
  - npt_prod_data: `.../npt_production/npt_production_out.data`
  - npt_prod_log:  `.../npt_production/npt_production.log`
  - Deck verified pre-run: style block byte-identical to the archived PCFF baseline; params
    include md5 6940d0b8 (compass), distinct from pcff (0ff6adfa) and pcff_ore (c46afd53).
  - **Typing verified.** COMPASS assigned 6 types incl. `o2e` (dedicated ether oxygen) and
    distinguishes `c4` from `c4o` (C bonded to O), which PCFF lumps into one `c`. The narrower
    COMPASS template table did NOT force substitute types onto the ether backbone.
  - **Protocol drift caught and corrected pre-execution.** The two workers received identical
    prompts (`npt_prod_ns: 2.0`, `npt_prod_steps: 2000000`) but PEGCMP1's submission emitted
    `run 1000000` in npt_production while PEGORE1's emitted `run 2000000` — half the density
    sampling on one arm of a controlled comparison. All eight other stages matched exactly.
    Corrected the deck in place at 17:10, while the chain was still on npt_cool_melt (stage 5
    of 9) and npt_production had not started. Decks are now byte-identical apart from paths.
  - **Chain COMPLETE** 2026-08-13T00:52. 9/9 stages. npt_production ran the full 2,000,000
    steps after the pre-execution deck correction (loop 8029 s, 7020 atoms, 1 rank).
    All stage `*_out.data` present. Final-frame density 1.1159 g/cm3 at T 300.19 K,
    box 40.33 A cubic. GPU 0 released.

## D-05 EQUIL-CHECK GATE

- **verdict: PASS**, density_status **OK**. plateau density **1.1241 g/cm3**, block-SEM
  3.75e-4 (0.03%), T 300 K, plateau_equilibrated=true.
- vs experimental rho(300 K) 1.1194 → **+0.42%**. vs archived PCFF PEG1-4 mean 1.0586 →
  **+6.19%**. COMPASS closes the PEG density deficit; PCFF is -5.43%, COMPASS +0.42%.
- Read with PEGORE1 (pcff_ore, -5.69%, same 5 atom types as PCFF): a refit of the same
  functional form on the same typing does nothing, while a field that types the ether
  backbone finely (o2e ether O; c4 vs c4o carbons) lands on experiment. The deficit is
  PCFF's ETHER TYPING, not its parameter values.
- Advisory (rubbery carve-out, non-binding): C(t) 2% decayed, tau_relax 1.92 Mps >> 1951 ps
  (33x faster relaxation than pcff_ore's 64.2 Mps); MSD_max 224.9 A^2 < Rg^2 324.1 A^2.
- **Binding-gate caveat:** finite_size min_image not evaluated (cutoff_A unsupported in the
  inspect_data_file schema). Verdict rests on 2*Rg alone, L/2Rg = 1.134 (vs 1.024 for pcff_ore).
