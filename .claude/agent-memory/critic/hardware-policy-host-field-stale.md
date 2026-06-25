---
name: hardware-policy-host-field-stale
description: polymer_rules hardware_policy.host (Quadro RTX 6000) contradicts directional_probe.measured_on + live host (4x A800) — don't false-flag the host-mismatch staleness rule
metadata:
  type: feedback
---

When checking a D-08_hardware staleness clause, do NOT mechanically read `hardware_policy.host` as the live host. It is stale.

**Why:** `guides/polymer_rules.json:hardware_policy.host` still lists `"Quadro RTX 6000 24GB / 18 phys cores"`, but `hardware_policy.directional_probe.measured_on` is `"4x NVIDIA A800 40GB / 32 phys cores"` AND `nvidia-smi` on the live box confirms 4x A800. So the directional_probe was measured ON the live host; the top-level `host` field just lagged behind a hardware swap. The policy require[5]/prefer clauses key off `directional_probe.host != hardware_policy.host` — read literally these two fields differ and you'd demand a hardware_benchmark probe, but that comparison is the bug, not a real host mismatch.

**How to apply:** Verify the live host with `nvidia-smi --query-gpu=name --format=csv,noheader` and compare it to `directional_probe.measured_on` (the field that actually scopes the benchmark), NOT to the stale top-level `hardware_policy.host`. If live == measured_on, the probe is host-matched. Separately: require[5]/staleness only bites a *non-default* pin. A PCFF plan pinning `kokkos/mpi=1/gpu_per_run=1` is identical to BOTH `by_forcefield.pcff` AND `recommended_by_ff.pcff` (they coincide at this cell size), so it is the policy default and no probe is required regardless of `values_are_benchmarked=false`. PVC4 round-2 approved on this basis. See [[hardware-require-mpi4-stale-clause]].

**Codebase friction (for /ingest-memory):** `polymer_rules.json:hardware_policy.host` should be updated to the A800/32-core box (it now matches directional_probe.measured_on) so the require[5] host-mismatch comparison stops reading as a false positive. While `values_are_benchmarked` stays false until a drained-box sweep, the `host` field is purely a bookkeeping lag and is safe to correct now.
