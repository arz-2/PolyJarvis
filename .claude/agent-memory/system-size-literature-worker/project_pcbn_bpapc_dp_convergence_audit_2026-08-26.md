---
name: project-pcbn-bpapc-dp-convergence-audit-2026-08-26
description: PCBN (BPA-PC) dp_typical/nchain class-default re-audit findings, 2026-08-26
metadata:
  type: project
---

PCBN class defaults (dp_typical=40, dp_min=20, nchain=10) NOT contradicted by literature search,
but confidence stays LOW because both directly-relevant papers are paywalled and could not be
content-verified.

- Leon et al. 2005, *Macromolecules*, DOI 10.1021/ma050943m ("Bisphenol A Polycarbonate:
  Entanglement Analysis from Coarse-Grained MD Simulations") — search snippet claims Me = 1200-1400
  g/mol (Ne~5) for BPA-PC. DOI resolves (ACS, redirects fine) but full text blocked (403/paywall) —
  same ACS-domain block noted before. UNVERIFIED. If ever accessible, this would tighten (not
  contradict) the existing polymer_rules.json entanglement_Me_gmol=1660 (Mark 2007) note — both give
  DP@Me in the 5-6.5 range, far below dp_typical=40.
- Hess/Leon/van der Vegt/Kremer 2006, *Soft Matter*, DOI 10.1039/b602076c ("Long time atomistic
  polymer trajectories from coarse grained simulations: bisphenol-A polycarbonate") — search snippet
  claims all-atom backmapped melts of n=100 chains, MW~5217 g/mol/chain => DP~20-21 repeat units
  (BPA-PC repeat unit MW=254.29 g/mol). DOI resolves (RSC redirect) but content blocked, RSC 403 —
  same publisher-block pattern as [[feedback_publisher_domains_block_webfetch]]. UNVERIFIED.
- PMC9824171 (Leelaprachakul, Kubo, Umeno 2022, *Polymers*, DOI 10.3390/polym15010043) — content
  VERIFIED via PMC full-text fetch (PMC always works, MDPI direct blocked). Coarse-grained BPA-PC
  deformation MD used 128/192/256-mer chains (these are CG beads, not atomistic repeat units — do
  not conflate with dp_typical). Reports Ne~26-50 entanglements/molecule. Does NOT discuss
  density/Tg/modulus convergence vs chain length — useful only as context that BPA-PC studies
  routinely use chains well above entanglement onset for mechanical properties.
- Net: confidence=low is the honest call even when the numeric agreement is clean, because the
  agreement here rests on cross-checking polymer_rules.json's own pre-existing Me note's arithmetic
  (DP@Me = Me/repeat_MW ≈ 6.5, well under 40), not on freshly verified literature convergence
  evidence. Don't let a clean number-match upgrade confidence when the backing source itself
  wasn't content-verified.
