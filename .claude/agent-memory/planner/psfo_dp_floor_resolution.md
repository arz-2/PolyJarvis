---
name: psfo-dp-floor-resolution
description: PSFO/polysulfone class default dp_typical=15 violates the DP>=20 Fox-Flory hard floor; medium-confidence -> reasoned -> policy floor governs, not the class default
metadata:
  type: project
  ingested_at: 2026-06-22
---

PSFO (polysulfone) `polymer_rules.json` default is `dp_typical=15, dp_min=15, nchain=8`, but the class note itself says "Aim for DP=20 if budget allows" and DP=15 (per-chain MW ~5,304) is below the Fox-Flory plateau.

**Why:** `decision_policy.json:policies.system_size.require[0]` is a HARD floor "DP>=20 for Tg targets". On a medium-confidence class the plan is reasoned, so the fixed policy floor governs over the class default — the critic bounces DP=15 for any Tg/bulk_modulus target. See [[reasoned_override_confidence]].

**How to apply:** For PSFO with tg or bulk_modulus requested, set `dp_typical=20` (per-chain MW ~8,850 g/mol, repeat unit ~442.5 g/mol). Keep `nchain=8` — self-imaging check passes: at final density 1.24 g/cm3 cell edge L~45.6 A so L/2~22.8 A >> cutoff 12.0 A. No per-class Me is tabulated, so justify bulk_modulus chain-length validity on glassy Born/NVT being a LOCAL segmental-elastic response (CED + packing), not the entanglement network — do NOT assert "above entanglement MW" (DP=20 is only ~1 Me, marginal).

**Dominant-uncertainty flip:** when a DP bump resolves the short-chain bias, move `dominant:true` to the next residual (here `ff_transferability`, probe=`literature_anchor`) and remove the short-chain uncertainty entirely rather than leaving it dominant=false clutter.
