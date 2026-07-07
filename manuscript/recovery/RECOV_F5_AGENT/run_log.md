# Polyurea (PURA) Run RECOV_F5_AGENT · 2026-06-28 → 2026-06-28
SMILES: `*NC(=O)NCCCCCC*`  |  FF: PCFF (attempted) → GAFF2_mod (reroute)  |  Charges: RESP (post-reroute)  |  DP: 5  |  Chains: 2  |  GPU: none (build aborted)
Requested: density (foundation build only)  |  Replicate: 1 of 1  |  Seeds: EMC=1001  |  SEED_HOT=N/A  |  SEED_COLD=N/A
Plan: N/A (single foundation build task)  |  mode: deterministic  |  confidence: low  |  critic: N/A  |  T_workflow_K: N/A
Polymer class: PURA (Polyurea)

---

## DECISIONS

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF attempted → **reroute to GAFF2_mod** | Task instructed EMC+PCFF build. Build aborted: PCFF lacks bond-increment params for the urea N-H linkage. polymer_rules.json PURA: `preferred_ff=GAFF2_mod`, `preferred_builder=radonpy`, `ff_note: "EMC does not yet implement PURA."` |
| D-02 Charges        | embedded (PCFF, attempted) → **RESP** (GAFF2_mod path) | PCFF uses embedded bond-increment charges, but the urea increments are missing. polymer_rules.json mandates RESP for the polar urea backbone (N ~-0.5 e, O ~-0.6 e). |
| D-03 Electrostatics | PPPM | Urea linkage (-NH-CO-NH-) has two N-H donors + one C=O acceptor; strongest H-bonding of all classes -> long-range Coulomb mandatory (unchanged by reroute). |
| D-04 System size    | DP=5, 2 chains | As specified by task build command (small probe cell). |
| D-05 Convergence    | N/A — build never produced a cell | EMC aborted at the field-application step before packing. |

---

## RECOVERIES

## RECOVERY — molecule-builder (foundation build) attempt 1
- **Trigger (exact error):** `RuntimeError: EMC build failed (exit 255):` with EMC log:
  `Warning: increment pair {n_2, hn} not found.` /
  `Warning: increment pair {na, c_2} not found.` /
  `Error: core/script/field/entry.c:645 ScriptFieldEntryApply: Missing force field parameters. Program aborted.`
- **Diagnosis (root cause):** Genuine PCFF force-field coverage gap for polyurea, NOT a SMILES/geometry problem. The SMILES has exactly two `*` attachment points (verified) and EMC parsed the repeat/cap groups correctly (4 connects, depth 8). The abort occurs at the charge-increment (`field apply`) step: EMC's PCFF atom typer assigns the urea N-H hydrogen as type `hn` and one nitrogen as `na`, but `pcff.frc` only contains bond-increments for `{n_2, hn2}` (verified present) and has NO `{n_2, hn}` or `{na, c_2}` increment (verified absent in the bond_increments section). Without those increments PCFF cannot assign partial charges to the urea linkage, so EMC aborts. The urea -NH-CO-NH- motif is outside PCFF's parameterized chemistry.
- **Why parameter tweaks would NOT work:** Lowering `dp`, lowering `density`, changing `dt`, or re-checking the `*` count cannot supply a missing force-field increment — the gap is independent of chain length, packing density, and integration. Re-attempting EMC+PCFF in any configuration hits the same abort.
- **Recover.md taxonomy note (prescripted tension):** The taxonomy row keyed on `"missing FF parameters" (EMC build)` matches the error *string*, but its stated root cause ("SMILES attachment points wrong") and remedy ("verify exactly two `*`; try dp 15 if dp 20 fails") are both inapplicable here — the SMILES is valid and the failure is a structural FF gap. The actual fix (switch builders/FF) is NOT in the taxonomy and had to be inferred from the EMC class table and polymer_rules.json. Therefore `prescripted=false`.
- **Action (recovery DECISION):** Reroute the build off the EMC+PCFF path to the **RadonPy builder with GAFF2_mod force field + RESP charges**, the documented `preferred_builder`/`preferred_ff` for PURA in polymer_rules.json. Concrete first step: re-spawn molecule-builder for PURA via the RadonPy path (`build_molecule_from_smiles` -> `submit_assign_charges_job` (RESP) -> `submit_polymerize_job` -> `submit_generate_cell_job`). The RadonPy charge job is a QM step (not cheap), so per task scope it is decided/queued here, not run to completion.
- **Outcome:** rerouted (working path identified: RadonPy/GAFF2_mod). Attempts: 1 of max 2.

<!-- RECOVERY: error_class=emc_pcff_missing_urea_increment prescripted=false outcome=rerouted attempts=1 -->

---

## SIMULATION STATE

| Stage | ID | BgTask | Submitted | Completed | Wall | Status |
|-------|----|--------|-----------|-----------|------|--------|
| build (EMC/PCFF) | — | — | 00:18 | 00:18 | <1m | failed (FF gap -> reroute) |

GPU inventory: N/A — build aborted at field-application step, no simulation launched.

---

## RESULTS

Build did not complete on the EMC/PCFF path. No density/Tg/K computed.
Recovery decision: reroute to RadonPy + GAFF2_mod + RESP (PURA preferred path). See RECOVERIES.

Simulation dir: `data/RECOV_F5_AGENT/`
Outputs: none yet (build aborted).
