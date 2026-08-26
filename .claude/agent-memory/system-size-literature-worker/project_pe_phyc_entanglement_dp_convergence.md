---
name: pe-phyc-entanglement-dp-convergence
description: PE (PHYC, *CC*) system-size literature grounding — verified entanglement DP convergence source, unverified Tg source
metadata:
  type: project
---

For polyethylene (*CC*, PHYC class), tg+bulk_modulus system-size grounding
(`data/PE-test-cost/raw/literature_grounding_system_size.json`, 2026-08-24):

- Verified: Hoy, Foteinopoulou & Kröger, "Topological analysis of polymeric melts:
  Chain-length effects and fast-converging estimators for entanglement length,"
  Phys. Rev. E 80, 031803 (2009), DOI 10.1103/PhysRevE.80.031803 (fetched via arXiv
  preprint 0903.2078, read as saved PDF — see [[feedback_publisher_domains_block_webfetch]]).
  Atomistic united-atom PE MD (N=24 to 1000). Table I shows entanglements/chain Z
  rising smoothly with N (Z=2.876 at N=140, Z=5.089 at N=250, Z=7.168 at N=350);
  text states entanglement-length estimators cannot be reliably extrapolated for
  N<100-200. Used dp_typical=250 (Z~5, comfortably past marginal entanglement) as
  the entanglement_mw convergence basis. Paper does not state a simulation-cell
  nchain for the atomistic PE runs in the pages retrieved — left nchain: null.

- Unverified (publisher 403'd every fetch attempt, listed as candidates only):
  - RSC Advances C5RA21115H (PE Tg vs. chain-length MD study) — Tg-side, would have
    been the Fox-Flory-plateau source; RSC blocked both the DOI redirect and direct
    articlehtml URL.
  - ACS Macromolecules 10.1021/ma302394j (Me=1760±80 g/mol MD claim) — ACS blocked.

**Why:** Tg side of this run has no verified MD convergence citation at all; the
calling session should fall back to polymer_rules.json's PHYC class default for the
Tg-driven DP recommendation, while the bulk_modulus/entanglement side can lean on
the verified PRE 2009 source (confidence: medium).

**How to apply:** if grounding PE or another PHYC-class polymer again, try PMC/arXiv
mirrors for these two unverified DOIs before re-attempting the publisher domain.
