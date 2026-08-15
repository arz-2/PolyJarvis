---
name: emc-seed-null-conflict
description: Build prompts annotate emc_seed null as "pass seed=-1" while the inlined guide forbids -1; draw an integer instead — EMC echoes it as resolved_seed
metadata:
  type: feedback
---

When a build prompt has `emc_seed: null`, draw a random integer and pass it to
`submit_emc_cell_job(seed=...)`. Never pass `seed=-1`.

**Why:** The prompt's field annotation says null means "pass seed=-1, which makes EMC draw a
random seed and REPORT it", but the inlined MOLECULE_BUILDER guide in the same file states twice
"Never pass `seed=-1`" / "Never set `emc_seed: -1`" because it is irreproducible. A self-drawn
integer satisfies both: the run log's Seeds line is real *and* the cell is reproducible. The
stated purpose of the -1 branch (a real seed in the log) is met without depending on unverifiable
EMC reporting behavior — the EMC server source is outside the Bash scope, so the -1 branch cannot
be checked first.

**How to apply:** On any null-seed EMC prompt, pass a concrete integer. `get_emc_job_output`
returns `result.resolved_seed` echoing exactly the value passed (confirmed PSU1/PSFO: passed
784512, resolved_seed 784512), so report that same integer in the RESULT block's `emc_seed`.
No divergence note is needed — the RESULT contract has no field for one.

Related: [[output-contract-footguns]]
