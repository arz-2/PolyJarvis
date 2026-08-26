---
name: pktn-peek-rules-audit-ff-density-tg-corroboration
description: PKTN/PEEK rules-audit findings (2026-08-26) — PEEK2020 exp Tg/density targets corroborated, PCFF vs COMPASS II density sign flip noted
metadata:
  type: project
---

Re-audited PKTN's polymer_rules.json class defaults against literature (run PKTN_rules_audit,
SMILES `*Oc1ccc(C(=O)c2ccc(Oc3ccc(*)cc3)cc2)cc1`).

Findings:
- Only on-chemistry MD benchmark available is PEEK2020 (10.3390/polym12051054), already cited in
  polymer_rules.json — uses COMPASS II (not PCFF) on a simplified catechol-based cyclic-oligomer
  model, not a full linear amorphous melt. It over-predicts density +2.2% (1.364 vs exp 1.328
  g/cm3), opposite sign from PolyJarvis's own measured PCFF result (-5.1% under-dense). No
  same-force-field, same-model PEEK MD study exists to confirm or refute PCFF specifically.
- Semantic Scholar abstract text explicitly labels PEEK2020's 1.328 g/cm3 experimental density
  comparator as the "experimentally observed infinite semi-crystal" — i.e. that paper's own
  validation target is semicrystalline PEEK, NOT amorphous. This independently corroborates
  polymer_rules.json's existing exp_density_note caution (amorphous=1.263, semicrystalline=1.30-
  1.32, PEEK1 R-01 previously mis-used 1.32 and got a false error). Do not treat 1.328 (or any
  ~1.3 g/cm3 PEEK figure) as an amorphous-cell density target without checking crystallinity.
- PEEK2020's own experimental Tg comparator, 418.2 K, agrees with polymer_rules.json's
  experimental_tg_K.PEEK=418 to within 0.2 K — corroborated, no change needed.
- electrostatics (pppm), cooling_rate_K_per_ns, and cte_glass_melt fields could NOT be freshly
  searched this session — WebSearch budget (200/200) was exhausted mid-task, and most publisher
  domains (MDPI included, per [[feedback_publisher_webfetch_403_arxiv_fallback]]) 403'd WebFetch.
  Only Semantic Scholar's API (`api.semanticscholar.org/graph/v1/paper/DOI:<doi>?fields=...`)
  worked as a fallback for already-identified DOIs when the publisher page itself 403'd — worth
  trying earlier in future sessions before burning WebSearch calls on MDPI-hosted papers.
- Net verdict: no change recommended to PKTN's current PCFF/pppm/1.263 g cm-3/418 K defaults;
  dominant_uncertainty is the FF's aromatic-backbone density-sign question (PCFF -6.3%/-6.5% vs
  COMPASS -1.1%/-1.2% on benzene/toluene, per the store's own methodology_criteria) remaining
  theoretically-flagged but empirically unconfirmed for PEEK specifically.
