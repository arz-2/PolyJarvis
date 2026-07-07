# Polyethylene (PE) Run 2 · 2026-06-22 → in progress
SMILES: `*CC*`  |  FF: TraPPE-UA  |  Charges: trappe-ua-fixed  |  DP: 120  |  Chains: 20  |  GPU: 1
Requested: density, tg, bulk_modulus  |  Replicate: 2 of 5  |  Seeds: EMC=1004 | SEED_HOT=1005 | SEED_COLD=1006
Plan: `data/PE2/raw/run_plan.json`  |  mode: reasoned  |  confidence: high  |  critic: approved round 3  |  T_workflow_K: 300

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | TraPPE-UA                                            | PHYC class → auto-routed EMC/TraPPE-UA; apolar backbone, no partial charges needed |
| D-02 Charges        | Bond-increment / library (embedded in TraPPE-UA)     | Pure C/H UA backbone; charge_method_cost=zero (no QM step); no separate assign needed |
| D-03 Electrostatics | lj/cut 14.0 Å                                       | Apolar backbone → lj/cut sufficient; no heteroatoms (doi:10.1021/acs.macromol.5b00823) |
| D-04 System size    | DP=120, 20 chains, 4840 UA atoms                     | polymer_rules.json PHYC default; dp≥60 for Fox-Flory plateau; 20 chains standard |
| D-05 Convergence    | PASS (rubbery gating)                                | density SEM=0.031%, CV=12.9%, P2=0.017 — all hard gates pass; C(t)=2% advisory (τ~33.6 ns, reptation-limited) |
| D-06 Tg fit quality | EXCELLENT (R²=0.9995, N=13 plateau bins) | Tg=232.5 K (is_glassy=false; Tg<300 K) — gate pass |
| D-06b Multirate Tg  | DSC-equiv = 231.5 K                                  | b=+0.361 K/ln(K/ns), R²=0.227 (flat — expected for rubbery PE); rates [40,160,640] K/ns → [231.5, 233.6, 232.5] K; VF underconstrained (1.20 decades < 2); extrapolated to 10 K/min ≈ 231.5 K |
| D-07 Property method | murnaghan (rubbery)                                 | is_glassy=False (Tg=232.5K < 300K) → Murnaghan NPT at 300 K; pressures=[1,100,300,600,1000] atm; input=npt_production_out.data |

<!-- Add rows for non-routine decisions (parameter overrides, custom protocols, etc.) -->

---

## RECOVERIES

<!-- One block per incident. Write "None" if the run completed without errors. -->
<!-- Outcome options: converged / failed again / escalated / UNRESOLVED (stop after 2 attempts) -->

## UNRESOLVED — 2026-06-22

**Stage:** SETUP / critic gate (pre-build)
**Reason:** Critic escalated in round 1. Core finding: D-05 in the plan demotes `check_equilibration_comprehensive.overall_pass` to advisory for a rubbery PE melt (Tg~195K, T_workflow=300K). The policy's `require` clause mandates `overall_pass=True` before ANY property extraction; the only carve-out (`require_glassy`) covers regime=glassy DP≥30 only. No `require_rubbery` clause exists. With tau_relax~88ns the gate is physically unreachable and unextendable — this is a hard require violation with no in-pipeline remedy.

**Fix required (user authorization needed):** Add `require_rubbery` carve-out to `guides/decision_policy.json` D-05 policy, mirroring `require_glassy`. This is a campaign-wide framework change covering all PHYC/PDIE rubbery replicates (PE/PP/PIB/PBD). PE1's critic approved the equivalent override in round 2 with identical physics justification — the new clause would codify that precedent. **No simulation has been launched. GPU 1 is claimed; release after decision.**
**Resolution:** User authorized policy change 2026-06-22. `require_rubbery` added to decision_policy.json. Plan re-critiqued (round 3) → approved. Pipeline resumed.

## RECOVERY — 2026-06-22 — OpenMPI OPAL_PREFIX pointing to non-existent path

**Stage:** equil chain b0ad167b, stage minimize (attempt 1)
**Error:** `MPI_Init` failed — chain.sh set `OPAL_PREFIX=/home/arz2/openmpi` but that directory does not exist on this host. lmp binary links system OpenMPI (`/lib/x86_64-linux-gnu/libmpi.so.40`); the custom path is not needed.
**Fix:** Removed 3 broken env-var lines (`PATH`, `LD_LIBRARY_PATH`, `OPAL_PREFIX` pointing to `/home/arz2/openmpi`) from chain_b0ad167b.sh. Reset sentinel + progress. Re-launched. Minimize completed in ~8 s; nvt_softheat started.
**Status:** converged — chain running cleanly on attempt 2.
**Root cause:** lammps-engine server hardcodes `/home/arz2/openmpi` in chain scripts; directory no longer present on this host.

## RECOVERY — 2026-06-22 — r40 Tg sweep running CPU-only (missing -sf gpu flag)

**Stage:** tg-sweep r40 (run_lammps_script submitted run)
**Error:** `run_lammps_script` generated `tg_sweep_r40_1782114540_run.sh` which called `lmp` without `-sf gpu -pk gpu 1 neigh yes` flags. LAMMPS initialized the GPU package (via `package gpu 1` in the .in file) but `pair_style lj/cut` ran on CPU (no suffix mapping). Speed: ~63 steps/sec vs expected ~1300 steps/sec (GPU). After 60 min only 225,500/4,750,000 steps complete (4.75%).
**Fix:** Killed CPU-only PID (839506). Moved partial log to `tg_sweep_cpu_partial.log`. Re-launched directly: `env CUDA_VISIBLE_DEVICES=1 lmp -sf gpu -pk gpu 1 neigh yes -in tg_sweep.in`. New run: ~1300 steps/sec, 1:18:40 wall time total.
**Status:** converged — r40 sweep completed, Tg=231.5K EXCELLENT.
**Root cause:** `run_lammps_script` does not inject `-sf gpu` into generated run scripts; workaround = launch TraPPE-UA Tg sweeps directly with explicit flags.

## RECOVERY — 2026-06-22 — Murnaghan bm_P1 SHAKE constraint on TraPPE-UA C–C bonds

**Stage:** Murnaghan chain b9eec375, stage bm_P1 (attempt 1)
**Error:** `fix shake_fix all shake 1e-4 1000 0 b 1` — SHAKE on bond type 1 (C–C in TraPPE-UA). LAMMPS: "Shake clusters are connected". TraPPE-UA is a united-atom FF with no C–H bonds; SHAKE is not needed.
**Fix:** Removed `fix shake_fix` and `unfix shake_fix` lines from all 5 bm_P*.in files using `sed -i`. Reset progress.jsonl and sentinel. Re-launched chain from orchestrator shell (no OPAL_PREFIX in env). Chain now running cleanly (bm_P1 NPT underway on GPU 3).
**Status:** converged (in progress) — chain PID 2151074 alive, bm_P1 step ~151k/500k.
**Root cause:** `run_bulk_modulus_series` adds SHAKE block for all FF types; TraPPE-UA should have use_shake=False. Secondary issue: chain launched from subagent shell inherited OPAL_PREFIX → direct re-launch from orchestrator shell required.

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil | b0ad167b | 2026-06-22 ~01:27 | 2026-06-22 ~04:45 | ~3h 18m | done |
| tg-sweep r640 | direct-launch PID 1753369 | 2026-06-22 ~04:43 | 2026-06-22 ~04:48 | 4:53 | done |
| tg-sweep r160 | direct-launch PID 1958051 | 2026-06-22 ~05:02 | 2026-06-22 ~05:22 | 19:32 | done |
| tg-sweep r40  | direct-launch PID 2692589 | 2026-06-22 ~06:01 | 2026-06-22 ~07:19 | 1:18:40 | done |
| murnaghan b9eec375 | chain PID 2151074 | 2026-06-22 09:21 | 2026-06-22 10:03 | ~42 min | done |

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
| ρ (300 K) | 0.859 ± 0.000267 g/cm³ | 0.850–0.950 g/cm³ | −9.6% | NPT 300K plateau (2501 frames, SEM 0.031%) | ⚠ amorphous-only vs semicrystalline exp |

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (slow-MD) | 231.5 K (log-linear) | ~195 K | +18.7% | log-linear Tg(Γ), b=+0.361, R²=0.227; N=3 rates [40,160,640 K/ns] | ⚠ MD systematic overestimate; VF underconstrained |
| Tg (MD @640 K/ns) | 232.5 K | — | — | bilinear density fit (EXCELLENT, R²=0.9995) | annotation |
| Tg (MD @160 K/ns) | 233.6 K | — | — | bilinear density fit (EXCELLENT, R²=0.9982) | annotation |
| Tg (MD @40 K/ns)  | 231.5 K | — | — | bilinear density fit (EXCELLENT, R²=0.9985) | annotation |
| α_g (CTE) | [X]×10⁻⁵ K⁻¹   | [X]–[X]×10⁻⁵ K⁻¹      | [X]% | −a_glassy / ρ_mean_glassy | [✓ / ⚠] |
| α_r (CTE) | [X]×10⁻⁵ K⁻¹   | [X]–[X]×10⁻⁵ K⁻¹      | [X]% | −a_rubbery / ρ_mean_rubbery | [✓ / ⚠] |
| ΔCp at Tg | [X] J/(g·K)     | [X]–[X] J/(g·K)        | [X]% | H(T) bilinear fit         | [✓ / ⚠ / N/A] |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K  | 1.641 ± 0.108 GPa | 1.5–2.0 GPa | +9.4% | Murnaghan EOS, 5 pts [1,100,300,600,1000] atm, R²=0.9996 | ✓ within exp range |
| B0' | 12.27 | 7–11 (typical) | — | Murnaghan fit | annotation (slightly high) |
| G  | N/A | — | — | rubbery — deform not run | N/A |
| E  | N/A | — | — | rubbery — deform not run | N/A |

Simulation dir: `data/PE2/lammps/`
Outputs: `data/PE2/raw/` — JSONs; `data/PE2/graphs/` — PNGs; `data/PE2/raw/run_summary.json`

**Run complete 2026-06-22 ~10:10 EDT.** Total wall: ~8.5h (equil 3h18m + Tg sweeps 1h30m + Murnaghan 42m + analysis).

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 4.6 h  |  **GPU**: 4.6 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1
- Source: `data/PE2/lammps/**/*.log` (Born stages excluded); reproducible via `manuscript/gen_table_compute_cost.py`.
