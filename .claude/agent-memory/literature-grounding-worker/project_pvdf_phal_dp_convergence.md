---
name: project-pvdf-phal-dp-convergence
description: PVDF (PHAL class) system-size grounding finding — verified DP=20/nchain=20 MD study with a DP=17 dipole-convergence threshold
metadata:
  type: project
---

For PVDF (`*CC(F)(F)*`, class PHAL), Hu, Hu & Yan, *Int. J. Electrochem. Sci.* 13 (2018) 10088-10100,
doi:10.20964/2018.11.01 ("The Predicted Dielectric Constant of an Amorphous PVDF Changing with
Temperature by Molecular Dynamics Simulations") is a verified, PVDF-specific, peer-reviewed
all-atom MD study (CVFF force field, LAMMPS) that built an amorphous cell of 20 chains x 20
CF2-CF2 monomer units (DP=20, nchain=20) and used that same cell to determine Tg from a
density-vs-temperature NPT sweep (100-400 K). It justifies the DP=20 choice by citing (their
ref [18]) that "when the chain length is greater than 17 monomer units, the dipole moment per
monomer unit converges to a nearly constant value" — a monomer-level dipole-moment convergence,
**not** a direct Tg- or modulus-vs-DP plateau. Filed with `convergence_basis: fox_flory_plateau`
(closest enum fit) and `confidence: medium`, with the caveat spelled out in `dominant_uncertainty`/
`notes` since the underlying convergence property differs from Tg/modulus itself.

No PVDF-specific entanglement Me or packing-length/C-infinity MD study was found despite multiple
targeted searches (bulk-modulus DP-convergence angle came up empty for PVDF specifically) — so no
priority-2 packing-length Me estimate was attempted for this run.

Ingested into `docs/protocol_evidence_system_size.json` via `protocol_evidence.py ingest`
(run_name PVDF_trace, 2026-08-26); future PVDF/PHAL queries should hit this record via
`protocol_evidence.py query` before a fresh search.

Related: [[feedback_publisher_domains_block_webfetch]] — electrochemsci.org PDF fetched fine
(non-major-publisher open-access journal), unlike ACS/RSC/MDPI/ResearchGate.
