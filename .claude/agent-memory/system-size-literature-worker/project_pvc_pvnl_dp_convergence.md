---
name: project-pvc-pvnl-dp-convergence
description: PVC (PVNL class) DP convergence literature finding vs polymer_rules.json class defaults, 2026-08-26 rules audit
metadata:
  type: project
---

Olowookere, Al Alshaikh, Bara & Turner, *Molecular Simulation* 49(15), 2023,
DOI 10.1080/08927022.2023.2234493 — verified (DOI resolves via tandfonline redirect;
abstract cross-confirmed via Semantic Scholar API since tandfonline itself 403s, consistent
with [[feedback_publisher_domains_block_webfetch]]). Seven atomistic PVC models, DP 5-240
repeat units, simulated in THF/DMF (polar solvents, NOT bulk melt). Finding: most properties
(Rg, end-to-end distance, RDFs, Tg, melt viscosity) converge at DP~100-120.

`guides/polymer_rules.json` PVNL class currently sets `dp_typical=60`, `dp_min=30`, `nchain=10`.
This is the only PVC-specific MD DP-convergence study found — it disagrees with the current
class default (100-120 > 60), but the mismatch is softened by a real caveat: the study is
solvent-phase, not the neat bulk amorphous cell PolyJarvis actually builds. No bulk-melt
PVC-specific convergence study, entanglement Me, or packing-length/C-infinity source was found
for PVC despite two focused search rounds.

**Why:** flagged so a future rules-audit or planning run doesn't re-litigate this search from
scratch, and so any decision to raise PVNL's dp_typical toward ~100 carries the correct caveat
about solvent vs. bulk conditions rather than treating DP=100-120 as directly bulk-melt-validated.

**How to apply:** if PVNL's `dp_typical` is ever raised based on this finding, note in the
provenance that the source convergence study was solvent-phase; if a stronger bulk-melt PVC
MD convergence study surfaces later, it should supersede this one as primary evidence.
