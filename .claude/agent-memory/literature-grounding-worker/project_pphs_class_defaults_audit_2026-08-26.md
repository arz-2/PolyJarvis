---
name: pphs-class-defaults-audit-2026-08-26
description: PPHS (polyphosphazene) system-size class-default re-audit findings, 2026-08-26
metadata:
  type: project
---

PPHS class defaults (dp_typical=30, dp_min=20, nchain=10) audited 2026-08-26 for
poly(ethoxyphosphazene) (`*N=P(*)(OCC)OCC`). WebSearch budget was exhausted mid-task; ACS/MDPI/
Springer direct fetches blocked as usual (see [[feedback_publisher_domains_block_webfetch]]),
worked around via a PMC mirror search.

Only verified MD polyphosphazene source found: Chen & Demir 2022, *Polymers* 14(7):1451,
DOI 10.3390/polym14071451, PMC9002744 (https://pmc.ncbi.nlm.nih.gov/articles/PMC9002744/ — MDPI
articles often mirror onto PMC, useful when mdpi.com itself 403s). Key facts:
- Cell built from 2000 monomers, ~2% as chain initiators (~40 chains), ~95% monomer consumed
  -> implied average DP ~47, but this is NOT the product of any convergence test.
- The paper explicitly states that prior polyphosphazene MD approaches "are not versatile for
  testing the ultimate properties of PZs as a function of the degree of polymerisation" and does
  not itself close that gap — i.e. this is a citable statement that DP-convergence work for
  polyphosphazenes as a class does not yet exist in the literature, not just an absence-of-evidence
  finding on my part.
- Substituents studied were TFE/azido/nitrato, not the ethoxy substituent PPHS's example member
  uses — a structural mismatch on top of the missing convergence test.

Verdict: NEITHER confirms NOR contradicts PPHS's dp_typical=30/dp_min=20/nchain=10. Recommended
class defaults stay as-is; PPHS remains a genuinely sparse-literature class for DP grounding,
consistent with its pre-existing low-confidence PCFF-parameterization note in polymer_rules.json.

**Why:** this is the first system-size audit specifically for PPHS; worth recording so a future
re-audit doesn't re-spend search budget re-discovering the same single (non-convergence) source.
**How to apply:** if PPHS is re-audited later, start from Chen & Demir 2022 (PMC9002744) as the
known-quantity source, then search for anything newer (2023+) before re-searching this same paper's
neighbors — Zheng2025 ACS iecr.5c00137 and Fried2006 Springer 10.1007/s10904-006-9059-2 were both
found in-search but blocked by paywall; retry those first on a future pass with a fresh budget.
