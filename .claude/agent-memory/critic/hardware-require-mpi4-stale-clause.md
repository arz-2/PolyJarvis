---
name: hardware-require-mpi4-stale-clause
description: decision_policy hardware require[0] "mpi>=4 ... never launch mpi=1" reads as contradicting the live KOKKOS mpi=1 default — do not false-flag PCFF/OPLS mpi=1
metadata:
  type: feedback
---

When critiquing a D-08_hardware decision that pins `engine:kokkos, mpi:1` for a PCFF/OPLS (PPPM/class2) class, do NOT raise a finding on the `mpi>=4` anti-pattern.

**Why:** `guides/decision_policy.json:policies.hardware.require[0]` literally says *"mpi>=4 for any PPPM/charged class2 system (mpi=1 starves kspace ~75x — never launch it)"*. Read alone this contradicts the current `polymer_rules.json:hardware_policy.by_forcefield.pcff` default, which is `engine=kokkos, mpi=1, gpu_per_run=1`. The contradiction is resolved later in the SAME policy block: the `rationale` field states *"mpi=1 IS correct for PCFF/OPLS on KOKKOS, where kspace is on the GPU"*, and the `directional_probe.kokkos_offload_study` (2026-06-20, parity PASS) flipped pcff+opls to KOKKOS full-offload. The `mpi>=4` clause is the STALE GPU-package rule and applies only to `engine=gpu` (the fallback), not KOKKOS.

**How to apply:** mpi=1 is a finding ONLY when the engine is the GPU package (`engine:gpu`) on a PPPM/class2 class. For `engine:kokkos` on PCFF/OPLS, mpi=1 is the correct canonical default — approve it. A KOKKOS PCFF plan adopting the `by_forcefield.pcff` default verbatim (kept off `decided_params`, confidence:low, planned hardware_benchmark probe) when `values_are_benchmarked=false` and host mismatches is fully policy-compliant. See [[gate-mismatch-check]] if it exists. Codebase friction: the require[0] clause text should be reworded to scope it to engine=gpu so it stops reading as a blanket contradiction.
