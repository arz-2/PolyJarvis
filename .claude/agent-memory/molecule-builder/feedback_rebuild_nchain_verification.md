---
name: rebuild-nchain-verification
description: On a finite-size rebuild, verify nchains actually took effect from natoms/atoms-per-chain before reporting — EMC can silently fall back to ntotal mode
metadata:
  type: feedback
---

When a build is a rebuild driven by a finite-size gate (e.g. SIZE_CHAIN_SELF_IMAGE,
L/2Rg < 1), confirm the new chain count landed before reporting: check
`result.natoms == nchains x (dp x atoms_per_repeat_unit + 2)` and that the box edge grew by
roughly `nchain_new/nchain_old` to the 1/3 power.

**Why:** `nchains > 0` puts EMC in "number" mode and `ntotal` is ignored, but that is the one
argument whose silent fallback would reproduce the exact failure the rebuild exists to fix.
PSU1 rebuild: PSFO repeat unit C27H22O4S = 54 atoms, dp=25 -> 1352 atoms/chain,
x32 = 43264 natoms, box 84 -> 98.25 A, so the gate ratio moved 0.946 -> ~1.11. Verified, not
assumed.

**How to apply:** compute the expected atom count from the SMILES before calling
`get_emc_job_output`, compare, and only then copy the artifact. If it matches the *old* chain
count, emit the RESULT error block instead of shipping a cell that fails the same gate. Do not
report the L/2Rg ratio in RESULT — the gate belongs to the orchestrator and the block has no
field for it.

Related: [[output-contract-footguns]], [[emc-wait-patterns-blocked]]
