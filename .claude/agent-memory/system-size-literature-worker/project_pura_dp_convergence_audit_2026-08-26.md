---
name: project-pura-dp-convergence-audit-2026-08-26
description: PURA (polyurea) class-defaults DP/nchain re-audit found no direct evidence either way
metadata:
  type: project
---

polymer_rules.json PURA class defaults are dp_typical=30, dp_min=20, nchain=10 (already
self-flagged low-confidence, "inferred from PURT analogy" in its own notes). Re-audit on
2026-08-26 found zero MD convergence-DP or entanglement-Me/packing-length sources for a generic
homopolymer polyurea (-NH-CO-NH- repeat unit).

The only verified polyurea MD paper found: Zheng et al. 2021, "Revealing the role of hydrogen
bonding in polyurea with multiscale simulations," DOI 10.1080/08927022.2021.1967346 (Molecular
Simulation). Open-access SI PDF at figshare.com/ndownloader/files/30445338 (tandfonline.com and
sciencedirect.com both 403 WebFetch as usual, per [[feedback_publisher_domains_block_webfetch]] —
figshare mirrors of supplementary materials are a good alternate route worth trying first for
Taylor & Francis papers). Confirmed by reading the actual SI PDF: all-atom reference model uses
COMPASS FF (not GAFF2 — PURA's actual FF), 50 chains, but each "chain" is one FIXED segmented
oligomer (soft-hard-soft PTMO/urea block), not a DP sweep of a homopolymer repeat unit. No
DP/chain-length convergence check performed at all. Structurally mismatched to a generic
homopolymer polyurea proxy — cannot confirm or refute PURA's dp_typical/nchain.

No polyurea entanglement-Me or packing-length/C-infinity source exists either (OpenAlex search
came back empty) — priority-2 (packing-length-to-Me derivation) also unavailable for this class.

**Why:** PURA is a from-scratch RadonPy-only class (EMC can't build it) with genuinely sparse
literature — this audit is a negative result worth recording so a future re-audit doesn't repeat
the same dead-end searches.

**How to apply:** If asked to re-ground PURA system size again, don't expect the Zheng 2021 paper
to help beyond confirming "50-chain segmented-oligomer cells are used in polyurea MD literature,
but not as a DP-convergence data point." A genuine dp_typical/nchain grounding for generic
polyurea homopolymers likely does not exist in the literature yet.
