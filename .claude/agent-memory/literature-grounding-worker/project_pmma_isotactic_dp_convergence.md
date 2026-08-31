---
name: project-pmma-isotactic-dp-convergence
description: MD literature findings for PMMA/PACR system-size grounding (i-PMMA1 run, 2026-08-23) — verified sources and their limits
metadata:
  type: project
---

For i-PMMA1 (isotactic PMMA, PACR class, target 350 K rubbery probe), two verified MD-only
sources were found for D-04_system_size grounding:

- Min, Silberstein, Aluru 2014 (DOI 10.1002/polb.23437, J. Polym. Sci. B) — tacticity-unspecified
  "linear PMMA", explicit chain-length convergence test: shear stress-strain plateaus by
  DP=200 monomers; production used DP=252, nchain=12; matches Me~10 kg/mol entanglement MW.
- Sahputra, Alexiadis, Adams 2018 (DOI 10.1080/08927022.2018.1450983, Molecular Simulation) —
  the only MD study found that isolates isotactic PMMA specifically while varying DP (6 models,
  nchain=5, up to 400 monomers/chain). Finding: Young's modulus was STILL RISING at DP=400 —
  no plateau reached. This is negative/cautionary evidence, not a convergence value: it suggests
  isotactic PMMA (higher local chain order/stiffer dihedral energy than atactic) may need MORE
  DP than atactic-class entanglement estimates for converged bulk_modulus, not less.

Two other isotactic-PMMA-tacticity papers surfaced (Ute et al. 1995 DSC oligomer fractionation
13mer-50mer; Chat/Tu/Beena Unni/Adrjanowicz 2021 Macromolecules dielectric spectroscopy under
pressure/confinement) are BOTH experimental, not MD — correctly excluded from backing any
dp/nchain value per this worker's MD-only scope, but noted for context (both show tacticity
measurably shifts Tg dynamics, so isotactic ≠ atactic PMMA is not just a bulk-modulus concern).

**Why this matters for future PACR/PMMA runs**: polymer_rules.json's PACR class defaults
(dp_typical=50, dp_min=30, nchain=10) are well below both the atactic MD convergence point (200)
and the isotactic ceiling tested without convergence (400). Any isotactic-PMMA run targeting
bulk_modulus should flag this gap explicitly rather than accept the class default silently.

See [[../../..]] guides/polymer_rules.json PACR entry and D-04_system_size in
orchestration decision_policy.json for how this grounding feeds into the run's system-size decision.

**Update (2026-08-25, EvidenceStoreVerify1 run)**: `docs/protocol_evidence_system_size.json` was
found EMPTY at the start of this run — the i-PMMA1 finding above was apparently never ingested via
`ingest_protocol_evidence.py` in the prior session (this worker only wrote agent-memory, not the
persistent store, back then). For plain PMMA (SMILES `*CC(*)(C)C(=O)OC`, no tacticity marker,
PACR class), re-verified Min 2014 (DOI 10.1002/polb.23437) via WebFetch — still resolves and still
states DP=200 convergence / DP=252,nchain=12 production. Ingested this as the first record in the
system_size store (`records_added: 1`). Lesson: always check the store actually has content after
writing output_path + running the ingest script — a prior session's memory note is not proof the
store was populated.
