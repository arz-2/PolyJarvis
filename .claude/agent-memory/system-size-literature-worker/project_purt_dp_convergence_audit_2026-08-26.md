---
name: project-purt-dp-convergence-audit-2026-08-26
description: PURT class-defaults DP/nchain re-audit findings, only verified source is PTMO soft-segment proxy
metadata:
  type: project
---

PURT class defaults (dp_typical=40, dp_min=20, nchain=10 in guides/polymer_rules.json) were
re-audited 2026-08-26 against MD convergence literature. Only one verified source found: Shireen
et al., arXiv:2202.08993 (preprint, TraPPE-UA united-atom MD via LAMMPS) on PTMO -- the polyether
soft-segment component of segmented PU, not the full urethane-linked repeat unit.

Key facts from that paper:
- Density: converged (<2% deviation) at Nm=50 vs a Nm=555/nchain=20 reference system; paper never
  tested below DP=50.
- Finite-size (chain count): MSD, shear relaxation modulus G(t), and bulk relaxation modulus K(t)
  insensitive to nchain=5 vs 50 (NP=5 sufficient for these); but end-to-end distance Re DOES show
  a real finite-size shift 5->50 -- a structural, not viscoelastic-modulus, effect.
- Shear entanglement plateau only emerges at Nm=200 (Ne=21.4+/-2.0, Me~1397-1685 g/mol, i.e.
  DP~19-23); Nm=90 shows none. This is the SHEAR/viscoelastic entanglement signature -- not the
  static isothermal K_T=-V(dP/dV)_T PolyJarvis computes via Murnaghan fit, see
  [[feedback_bulk_modulus_convergence_not_entanglement]] in the main repo memory.

Verdict: PARTIAL AGREEMENT with current defaults. nchain=10 comfortably clears the paper's
NP=5-sufficient finding. dp_typical=40 sits modestly below the lowest literature-verified
converged point (DP=50) -- not disproof (paper never tested <50), but a caution, not a hard
requirement, given this is a class_analogy (soft-segment proxy) not the actual urethane chain.

**Why:** PURT has no discrete member_smiles (soft/hard segment generic per polymer_rules.json's
own note), and ACS/ScienceDirect sources on the actual segmented-PU repeat unit
(10.1021/ma4006395 and a ScienceDirect shape-memory-PU CG study) were found via search but
blocked on WebFetch (403/paywall), consistent with [[feedback_publisher_domains_block_webfetch]]
-- so they could not be verified or cited.

**How to apply:** If a future PURT-class run or audit needs this again, don't re-search from
scratch -- check `docs/protocol_evidence_system_size.json` first (this record was ingested
2026-08-26, run_name=PURT_rules_audit). Still worth periodically retrying the ACS/ScienceDirect
segmented-PU papers via a route other than WebFetch (e.g. arXiv preprint version, PMC mirror) if
one becomes available, since they would be a direct (non-proxy) source and could resolve the
dp_typical=40-vs-50 ambiguity.
