---
name: degenerate-kww-tau-extend-sizing
description: recover.md's extend_ns = max(1.5, 1.5*ct_tau_relax_ps/1000) "when finite" means physically resolved — a bound-pinned KWW fit (tau_ps at 1e9 exactly, low beta, <10% decay) is numerically finite but unusable; fall back to the 1.5 ns flat floor
metadata:
  type: feedback
---

`recover.md`'s EXTEND sizing is `extend_ns = max(1.5, 1.5*ct_tau_relax_ps/1000)` when finite, else
1.5 ns flat. Read "finite" as **physically resolved**, not "not NaN/inf".

**Why:** `check_equilibration_comprehensive`'s C(t) KWW fit pins at its upper bound when the
trajectory is far shorter than the true relaxation time. The tell is `chain.ct.tau_ps` sitting at
exactly `1.0e9` together with a small `beta` and a tiny `decay_fraction_at_end`. The derived
`tau_relax_ps` is then a huge but finite number, and applying the formula literally asks for an
absurd run. PMMA1 (2026-08-10): `tau_ps=1.000000000e9` (bound), `beta=0.266`,
`decay_fraction_at_end=0.026` over `trajectory_ps=1951` → `tau_relax_ps=1.69e10 ps`, which the
formula would turn into a ~2.5e7 ns extension.

**How to apply:** check `chain.ct.tau_ps` against the 1e9 bound and `decay_fraction_at_end` before
using tau to size anything. Bound-pinned → use the 1.5 ns flat floor and say so in `notes`. Second
independent reason to distrust it on glassy runs: `ct` is *advisory* under the `require_glassy`
carve-out, so it should not size a binding-gate remedy at all.

Related: [[density-homogeneity-mass-cv-false-positive]]
