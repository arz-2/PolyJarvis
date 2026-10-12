# PEG bulk modulus under COMPASS, seed-paired to the PCFF replicates (reviewer comment 4)

**Outcome: n = 1 pair.** PEG_COMPASS_2 was accepted. PEG_COMPASS_1 and PEG_COMPASS_3 stopped in
equilibration with PPPM "Out of range atoms" failures, and the operator chose to stop there rather
than retry further (see [Equilibration failures](#equilibration-failures)). Every number below comes
from the accepted attempts' own JSON, not from plans.

| | PEG_2 (PCFF) | PEG_COMPASS_2 (COMPASS) | COMPASS − PCFF |
|---|---|---|---|
| Density at 300 K (g/cm³) | 1.0600 | **1.1278** | +0.0678 (+6.4 %) |
| vs reference 1.1183–1.1205 | −5.2 to −5.4 % | **+0.65 to +0.85 %** | |
| Murnaghan K (GPa) | 3.534 ± 0.113 | **2.762 ± 0.072** | −0.772 ± 0.134 (−21.8 %, 5.7σ) |
| vs reference K_T 2.09 GPa | +69 % | **+32 %** | |
| Volume-fluctuation K (GPa) | 3.632 | 2.601 | −1.031 (−28.4 %) |

COMPASS closes the PCFF density deficit almost entirely and cuts the K overestimate roughly in half.
With one COMPASS run, COMPASS's own seed-to-seed spread is unmeasured. The COMPASS − PCFF K gap
(0.77 GPa) is about 5.6 times the PCFF three-seed SD (0.137 GPa), but see
[Caveats](#caveats) — the one COMPASS run that survived equilibration could be atypical.

## Design

- **Only change:** `preferred_ff` pcff → compass. Same SMILES (`*CCO*`), cell (DP 114, 10 chains,
  8000 atoms), frozen protocol and seeds as each PCFF replicate.
- **Force-field-derived keys are identical.** `make_deterministic_plan._derived_from_field` returns
  the same `charge_method` (bond-increment), `electrostatics` (pppm), `dt_fs` (1.0) and hardware
  (kokkos, 1 MPI rank, 1 GPU, family pcff) for compass and pcff. `rules_common.resolve_ff_family`
  maps compass to the pcff family.
- **Properties** `["density", "bulk_modulus"]`: stages build → equilibration → cooling → mechanical
  → summary. No thermal stage.
- **Locked exactly like the rev2 replicates:**
  - launched with `agent_api.py resume <RUN>` and no `--recovery-agent-command`;
  - `remedy_counters.total` pre-seeded to `MAX_AUTOMATIC_REMEDIES` = 12;
  - `POLYJARVIS_GATES_ADVISORY=1`, confirmed in each Python process's `/proc/<pid>/environ`;
  - a `replicate_protocol_lock` entry in each `workflow_state.json`.

  The consequence: no automatic remedy of any kind, and a process failure ends the run
  `escalation_required` (`no_recovery_agent_configured`).
- **`WorkflowEngine`** was constructed (executor `None`) only on the three new directories. The
  sha256 of PEG_1/2/3 `workflow_state.json` was identical before and after.
- **GPUs** were not hand-claimed. `run_campaign` claims and releases through
  `hardware_runtime.py` per stage (`gpu_claim`), and a pre-claim under the same run name would take
  a second card. `status` showed all four GPUs free at launch. Each run ran on its own card
  (`CUDA_VISIBLE_DEVICES` 0/1/2, matching the ledger).

### Plan changes vs PEG_<i> (step 1)

Plans were copied from `data/PEG_<i>/raw/run_plan.json`. Full top-level diff:

| Key | Change |
|---|---|
| `run_name` | PEG_<i> → PEG_COMPASS_<i> |
| `goal` | rewritten to name the COMPASS comparison |
| `properties` | `["bulk_modulus","density","tg"]` → `["density","bulk_modulus"]` |
| `planned_stages` | `tg`, `analyze-tg` removed. The rest is identical to `build_planned_stages()` for the new properties |
| `decided_params` | `preferred_ff` pcff → compass; `emc_seed`, `velocity_seed` **added** (pinned, below) |
| `decisions[D-01_ff]` | `choice` pcff → compass, plus an `ff_accuracy_prior_not_met` acknowledgement |
| `overrides` | `{}` → `{"preferred_ff": "compass"}` (read only by `start`, so it records the switch and has no runtime effect) |
| `derived_inputs` | removed (backbone types re-derived from the COMPASS cell) |
| `cost_estimate` | re-priced by `select_hardware.py plan`: cool + murnaghan = **3.67 GPU-h** (was 6.04 with tg); equilibration unpriced |

**Seeds had to be pinned.** PEG_<i> plans carry no seeds. Both seeds derive from `sha256(run_name)`,
so `PEG_COMPASS_<i>` would otherwise have drawn different ones (672446/489530, 413866/144933,
285808/266742). `stage_params.py:61-64` honours `decided_params.emc_seed`/`velocity_seed`, the same
mechanism `benchmarks/stereo_r2/build_matrix.py` uses. Values were read from what actually reached
EMC and LAMMPS in each PCFF run: the `-seed=` line in `emc_build.log` and `velocity all create` in
the equilibration decks.

| Pair | emc_seed | velocity_seed |
|---|---|---|
| 1 | 148731 | 135693 |
| 2 | 798838 | 316927 |
| 3 | 200187 | 631302 |

### Verification before launch (step 2)

- **`decided_params`** differ from PEG_<i> only in `preferred_ff`, `emc_seed` and `velocity_seed`,
  in all three plans.
- **`validate_run_plan.py`** first reported `ff_prior_departure_unacknowledged` (structural): the
  class prior for POXI is pcff. After the D-01 acknowledgement it reports only
  `finite_size_min_image` (info), the same single finding it gives PEG_1's own plan.
- **`agent_api.py resume --dry-run`** resolved `preferred_ff=compass`, the pinned `emc_seed` at
  build, and the pinned `velocity_seed` at equil, cool and murnaghan, for all three runs.
- **Characterization cache is first-writer-wins.** `*CCO*` still names `source_run_name: PEG_1`
  with pcff, so an accepted COMPASS run cannot overwrite the frozen PCFF protocol.

## Cell pairing (step 4)

Accepted build cells compared atom by atom. Script: `provenance/compare_cells.py`; output:
`provenance/step4_cell_comparison.json`.

| Check | Pair 1 | Pair 2 | Pair 3 |
|---|---|---|---|
| Atoms / bonds | 8000 / 7990 both | same | same |
| Angles / dihedrals / impropers | 14820 / 17070 / 9120 both | same | same |
| Box | 51.52205724 Å cube, identical | identical | identical |
| EMC seed (PCFF = COMPASS) | 148731 | 798838 | 200187 |
| Molecule id per atom | identical | identical | identical |
| Initial coordinates | differ (max 133.9 Å) | differ (max 90.3 Å) | differ (max 107.0 Å) |
| Pairing | **by seed only** | **by seed only** | **by seed only** |

Coordinates are not identical, so the pairs start from different configurations. EMC applies the
field before placing chains: the OPLS-AA probe aborts on missing parameters before any cell exists.
So the field changes the placement even with the same seed.

**Atom types and charges** (identical mapping in all three pairs; mean charge per atom):

| Atoms | PCFF type | COMPASS type | q PCFF | q COMPASS |
|---|---|---|---|---|
| ether O (1130) | `oc` | `o2e` | −0.266 | −0.320 |
| C bonded to ether O (2270) | `c` | `c4o` | +0.027 | +0.054 |
| chain-end C (10) | `c` | `c4` | −0.159 | −0.159 |
| H (4570) | `hc` | `h1` | +0.053 | +0.053 |
| hydroxyl O / H (10 / 10) | `oh` / `ho` | `o2h` / `h1o` | −0.557 / +0.424 | −0.580 / +0.420 |

The PCFF ether types are `oc`/`c`. PCFF's `o` is a different, generic sp3 oxygen. Type counts
PCFF → COMPASS: atom 5→6, bond 5→7, angle 8→12, dihedral 9→12, improper 7→10. Net charge is 0 in
every cell.

**The decks load COMPASS parameters.**
- The first equilibration deck (`minimize.in`) reads the run's own COMPASS `cell.data`.
- Later decks `include` the run's own `emc_build.params`, which declares `field compass/compass`.
- The coefficient rows are COMPASS's. Ether O `o2e` pair ε/σ = 0.120/3.300 against PCFF `oc`
  0.240/3.535. C next to O `c4o` = 0.068/3.815 against PCFF `c` 0.054/4.010.
- Style lines are `class2` for both fields and prove nothing on their own.

## Equilibration failures

Every failure is `ERROR on proc 0: Out of range atoms - cannot compute PPPM`. None shows a warning at
1000-step thermo/dump resolution. The last dump frame was written at the failure step itself, and
in it:
- every bond is ≤ 1.17× its r0;
- no hydroxyl H is within 1.6 Å of an O;
- the fastest atoms per type move at 1.4–2.8× the thermal v_rms, an ordinary Maxwell tail.

GPU uncorrected ECC was 0 on all four cards. Kernel Xid messages were not checked (`dmesg` needs
privileges).

| Run / attempt | Segment | Ensemble / T | Died at step | Wall time |
|---|---|---|---|---|
| C_1 / attempt-0001 | `anneal_heat` | NVT 300→625 K, 1 M steps | ~926 000 | 0.93 h |
| C_3 / attempt-0001 | `nvt_melt_hold` | NVT 500 K, 5 M steps | ~851 000 | 2.53 h |
| C_1 / attempt-0002 | `npt_melt_ramp` | NPT 625→500 K, 1 atm, 1 M steps | ~293 000 | 1.63 h |
| C_2 / attempt-0001 | all segments | — | accepted | 6.03 h |

**COMPASS: 3 of 4 equilibration attempts failed**, in three different segments and at 500 K as well
as 625 K. Under PCFF it was 3 of 6 (all PEG_2, all in the 625 K anneal; retried unchanged by an
operator reset, accepted on attempt-0004). GPU time lost to COMPASS failures: 5.09 h.

The one physical difference observed is at 500 K: COMPASS's melt has E_coul ≈ 1.30e4 kcal/mol
against PCFF's ≈ 8.0e3, and density 0.962 against 0.941. That is consistent with COMPASS's larger
ether charges. It was **not** shown to cause the failures.

**Operator decisions:**
- **C_1 after attempt-0001:** retry once, unchanged. Recorded in `operator_resets`:
  - equilibration set back to `pending`, top-level status and `active_finding` cleared;
  - attempt-0001 kept as failed, remedy lock left at 12.
  - Retry confirmed fresh: the `prior_attempts` continuation paths are gated on remedy keys
    (`npt_continuation_ns`, `cooling_continuation_ns`, `equilibration_resume_from`) and
    `effective_parameters` had none. `work_dir` is per attempt. attempt-0002 then failed too.
- **C_3 after attempt-0001:** wait for runs 1 and 2, then stop. No reset.
- **Final:** stop at n = 1.

## Results (step 5)

### Gates, graded under one frozen gate version

`benchmarks/stereo_r2/regrade_gates.py PEG_2 PEG_COMPASS_2 --out-dir peg_compass/regrade` (gate
code HEAD 7ca21b8; energy components judged on drift/σ). None of these accepted attempts has a
continuation segment: `extend_history` is empty and each gate's `log_file` is the single base log.
So the "concatenated log chain" is the base log itself, for both runs.

| Run | Stage | Log | Stored version | Current version | Live verdict |
|---|---|---|---|---|---|
| PEG_2 | equilibration | attempt-0004 `npt_melt_hold.log` | PASS | PASS | PASS |
| PEG_2 | cooling | attempt-0001 `npt_final.log` | FAIL (energy_drift) | FAIL (energy_drift); advisory: msd_not_trapped, residual_stress | EXTEND |
| PEG_COMPASS_2 | equilibration | attempt-0001 `npt_melt_hold.log` | PASS | PASS | PASS |
| PEG_COMPASS_2 | cooling | attempt-0001 `npt_final.log` | PASS | PASS; advisory: msd_not_trapped | PASS |

Mechanical, as recorded: both runs `BM_REPORTABLE`, `BM_LADDER_CONVERGED` (confidence high).
PEG_COMPASS_2 has no `gate_verdict_advisory` on any stage, so no gate failed and was then accepted
under advisory mode.

### Per run

Murnaghan fits used the ladder [−1000, 0, 3000, 7000, 15000] atm at 300 K. Every fit used 5 points
with 0 excluded; points 0 and 1 were flagged but no trim was applied because untrimmed R² ≥ 0.999.

| Run | FF | ρ 300 K | ρ melt 500 K | K ± sem (GPa) | B0′ | R² | LOO max ΔB0 | Fluct. K (divergence) | Ladder | BM gate |
|---|---|---|---|---|---|---|---|---|---|---|
| PEG_1 | pcff | 1.0579 | 0.9391 | 3.297 ± 0.121 | 9.42 | 0.999905 | 6.40 % | 3.282 (0.4 %) | CONVERGED | REPORTABLE |
| PEG_2 | pcff | 1.0600 | 0.9378 | 3.534 ± 0.113 | 8.99 | 0.999922 | 4.51 % | 3.632 (2.8 %) | CONVERGED | REPORTABLE |
| PEG_3 | pcff | 1.0631 | 0.9375 | 3.296 ± 0.123 | 9.58 | 0.999902 | 6.77 % | 3.820 (15.9 %) | CONVERGED | REPORTABLE |
| **PEG_COMPASS_2** | **compass** | **1.1278** | **0.9606** | **2.762 ± 0.072** | **9.64** | **0.999959** | **3.55 %** | **2.601 (5.8 %)** | CONVERGED | REPORTABLE |
| PEG_COMPASS_1 | compass | — | — | — | — | — | — | — | stopped in equilibration | — |
| PEG_COMPASS_3 | compass | — | — | — | — | — | — | — | stopped in equilibration | — |

PCFF three-seed mean ± SD: ρ 1.0603 ± 0.0026 g/cm³; K 3.375 ± 0.137 GPa. The task brief's
"K 3.30 GPa (+58 %)" matches PEG_1 and PEG_3 individually (3.297, +57.7 %). Including PEG_2's
3.534, the three-run mean is 3.375 GPa (+61.5 %). The brief's density "−5.2 %" matches the mean
against the low end of the reference (−5.18 %).

### Pairing by seed

Only pair 2 exists, so per-pair and mean differences coincide.

| Quantity | PEG_2 (PCFF) | PEG_COMPASS_2 | Δ (COMPASS − PCFF) |
|---|---|---|---|
| ρ 300 K (g/cm³) | 1.060015 | 1.127829 | +0.067814 (+6.40 %) |
| ρ melt 500 K (g/cm³) | 0.937757 | 0.960564 | +0.022807 (+2.43 %) |
| Murnaghan K (GPa) | 3.5336 ± 0.1132 | 2.7620 ± 0.0721 | −0.7716 ± 0.1342 (−21.8 %) |
| B0′ | 8.986 | 9.641 | +0.656 |
| Fluctuation K (GPa) | 3.632 | 2.601 | −1.031 (−28.4 %) |

COMPASS_2 against the PCFF three-seed mean: Δρ = +0.0675 g/cm³, ΔK = −0.613 GPa.

### Against reference

Reference values are Mark 2007 Tables 7.1/7.5 melt equations evaluated at 300 K: amorphous PEO
density 1.1183–1.1205 g/cm³, K_T 2.09 GPa.

| | ρ vs 1.1183–1.1205 | K vs 2.09 GPa | Fluct. K vs 2.09 |
|---|---|---|---|
| PCFF mean (n=3) | −5.18 to −5.37 % | +61.5 % | — |
| PEG_2 (PCFF) | −5.21 to −5.40 % | +69.1 % | +73.8 % |
| PEG_COMPASS_2 | **+0.65 to +0.85 %** | **+32.2 %** | +24.4 % |

The round-1 COMPASS density quoted in the task brief (PEGCMP1, 7020 atoms, 1.1241 g/cm³, density
only) is 0.3 % below PEG_COMPASS_2's 1.1278. That run's files are not on this machine and were not
re-checked.

### Measured stage times (PEG_COMPASS_2, wall hours)

build 0.04, equilibration 6.03, cooling 2.51, mechanical 1.64, summary 0.00: **10.2 h total**,
against PCFF's measured 6.3 / 2.6 / 1.7 (~10.5 h). COMPASS was not slower on this host.

## Caveats

1. **n = 1 COMPASS.** COMPASS's seed-to-seed spread is unmeasured, so the ΔK significance rests on
   within-run sem and on PCFF's spread, not on COMPASS's.
2. **Survivor bias is possible.** Three of four COMPASS equilibration attempts crashed; the accepted
   run is the one that did not. Nothing in its gates marks it as unusual (both melt and cooling
   PASS), but a selection effect cannot be excluded.
3. **Paired by seed only.** Starting coordinates differ between force fields, so a pair shares
   seeds, not a starting configuration.
4. **COMPASS in this installation** is EMC's `compass.frc` v1.1 (2009-06-30). No DOI-backed evidence
   covers compass for POXI. The only COMPASS PEO record in the PolyDatabase MD index
   (10.1002/polb.24355) is a reactive-MD, graphene-confined 10-mer study, not a neat bulk melt.
5. **Stability at dt = 1 fs.** COMPASS's failure rate here suggests dt = 1 fs is marginal for this
   field at 500–625 K. A 0.5 fs rerun would change the timestep as well as the field, and was not
   done.

## Side effects handled

- **Evidence store.** On acceptance, `run_campaign` → `protocol_evidence.ingest_from_completed_run`
  wrote 2 records to `docs/protocol_evidence_ff.json` claiming "PolyJarvis validated **pcff** … in
  run PEG_COMPASS_2" (forcefield; cooling_rate). The ingest reads the SMILES's cache entry, which
  is PEG_1's PCFF protocol, without checking that the entry names this run. Both records were
  removed (copies in `provenance/removed_evidence_records.json`) and the file restored to HEAD:
  163 records, no diff. The underlying defect is unfixed.
- **Characterization cache.** Untouched; `*CCO*` still names PEG_1.

## Files

- `regrade/regrade_20260915.{json,md}`: gate regrade of PEG_2 and PEG_COMPASS_2.
- `provenance/step4_cell_comparison.json`: step-4 output for all three pairs.
- `provenance/removed_evidence_records.json`: the 2 false evidence records.
- `provenance/create_states.py`: engine construction, remedy pin and lock.
- `provenance/launch.sh`: `setsid nohup` launch, real PID to `raw/launcher.pid`, advisory env check.
- `provenance/compare_cells.py`: the step-4 comparison.
- `data/PEG_COMPASS_{1,2,3}/`: force-added like commit 7ca21b8 (workflow state, run plans,
  executor state, gate/analysis JSON, decks, launch and chain scripts, builder inputs, plots, logs).
  Excluded: `.dump`, `.data`, `.restart`/`.rst`, `launcher.pid` (271 files, 17.0 GB).
