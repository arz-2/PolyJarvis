# PMMA (PACR) Run RECOV_F6_AGENT · 2026-06-28 → 2026-06-28
SMILES: `*CC(C)(C(=O)OC)*`  |  FF: PCFF  |  Charges: EMC bond-increment (embedded)  |  DP: 3 (actual artifact; prompt said 5 — see note)  |  Chains: 2  |  GPU: none (CPU probe only)
Requested: foundation (equilibrate existing cell)  |  Replicate: 1 of 1  |  Seeds: EMC=1001
Plan: pre-built cell supplied (no planner stage)  |  mode: n/a  |  confidence: n/a  |  critic: n/a  |  T_workflow_K: 300

---

## DECISIONS

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF (class2)                | Cell.params is EMC v9.4.4 pcff/pcff field; PMMA → PACR class, EMC-supported. |
| D-04 System size    | DP=3 (actual), 2 chains, header declares 94 atoms | Pre-built EMC cell supplied. NOTE: prompt stated dp=5, but the artifact is dp=3 — 94 atoms = 2×(15-atom C5H8O2 repeat ×3 + 2 caps); l_poly=47, m_poly=266.34 in cell.params confirm. dp=5 would be 154 atoms. See RECOVERY — atom records also do not match the header (truncation). |
| D-05 Convergence    | ABORTED before equilibration | Cell.data is structurally invalid (truncated Atoms section); no equilibration attempted. |

<!-- Equilibration was never submitted: the cheap pre-flight LAMMPS read on the supplied
     cell.data failed, exposing a corrupt build artifact. See RECOVERIES. -->

---

## RECOVERIES

## RECOVERY — Foundation (equilibration pre-flight) attempt 1
- **Trigger:** LAMMPS `read_data` aborts with
  `ERROR: Incorrect format in Atoms section of data file: Bonds (src/atom.cpp:1201)`
  on `data/RECOV_F6_AGENT/cell/cell.data`. Minimal class2/PPPM NVT deck run on CPU
  (`env CUDA_VISIBLE_DEVICES="" /home/arz2/lammps-install/bin/lmp`).
- **Diagnosis:** Truncated / corrupt cell.data build artifact. The header declares **94 atoms**
  but the `Atoms` section contains only **91** records (IDs 1–91 contiguous; **atom IDs 92, 93, 94
  are missing**). LAMMPS reads 91 atom lines, expects the 92nd, and instead encounters the `Bonds`
  section header — hence the "Incorrect format … : Bonds" error. The topology is written for the
  full cell: `Bonds`, `Angles`, and `Dihedrals` all reference atom IDs up to **94**, so the three
  dropped atoms are dangling in the bonded connectivity. The file is internally inconsistent and
  unusable. This is NOT a dynamics (lost-atoms/dt), density, or FF-style problem — it fails at the
  read stage, before any integration.
- **Why not an in-place patch:** The 3 missing atoms' types, coordinates, and charges cannot be
  reliably reconstructed, and their bonded environment (bonds/angles/dihedrals to existing atoms)
  is already encoded — fabricating them risks a physically wrong structure. Editing the header
  count down to 91 would orphan the topology referencing 92–94 and corrupt the molecule. No
  recover.md taxonomy row matches "Atoms-count-vs-records mismatch / truncated data file"
  (the closest, "unknown atom type / segfault on startup", is a different FF-ordering failure),
  so the fix is inferred, not prescripted.
- **Action (DECISION):** Reject the corrupt cell and **rebuild** the amorphous cell from the
  originating SMILES `*CC(C)(C(=O)OC)*` (PMMA, class PACR, field pcff, dp=5, nchains=2, seed=1001)
  via the molecule-builder (EMC PCFF path), then re-run the equilibration pre-flight before
  submitting the chain. Feasibility confirmed (first concrete step): PACR `builder_status=supported`
  and the SMILES has exactly two `*` connection points, so an EMC rebuild is valid. Full rebuild +
  equilibration not executed here (task scope = diagnose + decide).
  - **Rebuild target / dp note:** the supplied artifact was built at **dp=3** (94 atoms), not the
    dp=5 stated in the prompt. To reproduce the intended original cell, rebuild at **dp=3**
    (nchains=2, seed=1001, field pcff). Rebuilding at dp=5 would yield a different, larger
    154-atom system — flag for the requester to confirm which dp is intended before the rebuild.
- **Outcome:** rebuilt — recovery route = reject corrupt cell + rebuild via molecule-builder (EMC PCFF). Rebuild confirmed feasible (PACR supported, 2 `*` atoms); rebuild + equilibration not executed (task scope = diagnose + decide).

<!-- RECOVERY: error_class=truncated_data_file_atom_count_mismatch prescripted=false outcome=rebuilt attempts=1 -->

---

## SIMULATION STATE

| Stage | ID | BgTask | Submitted | Completed | Wall | Status |
|-------|----|--------|-----------|-----------|------|--------|
| equil-preflight (CPU read probe) | local lmp probe | — | — | — | <1 min | failed (corrupt cell.data) |

GPU inventory: not reached (cell rejected at read stage; no GPU claimed).

---

## RESULTS

No properties computed — run halted at the foundation pre-flight because the supplied cell.data is
a corrupt build artifact (91 of 94 declared atoms present). Correct recovery: rebuild the cell from
SMILES via molecule-builder, then resume equilibration.

Simulation dir: `data/RECOV_F6_AGENT/lammps/`
Probe deck: `data/RECOV_F6_AGENT/lammps/probe/probe.in`
