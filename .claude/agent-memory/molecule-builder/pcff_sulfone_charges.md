---
name: pcff-sulfone-charges
description: PCFF sulfone (PSFO) charges are small by design — do NOT apply OPLS/QM +1.3/-0.55 criterion
metadata:
  type: feedback
---

For PSFO (polysulfone, e.g. PSU/Udel) built via EMC/PCFF, the sulfone S and O
carry SMALL partial charges by design: S ≈ +0.08 e, sulfone O (`o=`) ≈ -0.11 e.

**Why:** PCFF uses bond-increment charges, not QM/RESP. The EMC `pcff.frc`
`bond_increments` row `o= s' -0.1143 0.1143` assigns each sulfone O exactly
-0.1143 e and the bonded S +0.1143 e per bond. Two o= per sulfone plus the
cp–sf increments net the S to ~+0.08. These are the NATIVE PCFF values. A task
spec expecting "S ~+1.3 e, O ~-0.55 e" is quoting an OPLS-AA / AMBER / QM-RESP
expectation that does NOT apply to a PCFF build — applying it would wrongly fail
a correct build.

**How to apply:** When verifying a PSFO (or any PCFF sulfone) build, check the
sulfone *atom typing* (S = `sf` bonded to `o=` oxygens, with the characteristic
`o=,sf,o=` angle ≈ 119.3° and `cp,sf` / `cp,sf,o=` terms in emc_build.params) —
that is the real correctness signal. Do NOT fail on small charge magnitudes.
The failure signature for a genuinely missing increment is a charge of exactly
**0.0000** (fallback), not a specific small nonzero value. A specific value like
-0.1143 means EMC found a real frc increment. Cross-check against
`/home/alexzhao/emc/field/pcff/pcff.frc` bond_increments if in doubt.
See [[emc-output-naming]].
