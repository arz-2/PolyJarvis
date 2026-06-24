# Multi-Machine Integrator Workflow

PolyJarvis revision campaigns run on **two machines** (e.g. `arz2` and `alexzhao`), each handling a
disjoint subset of the revision polymers. Each machine's runs generate agent-memory findings and,
occasionally, code fixes. This guide is the protocol for folding both machines' work back into `main`
without merge pain or path-sanitization churn.

## Why centralized

The files that **conflict** are shared code/config (`gen_prompt.py`, `polymer_rules.json`,
`decision_policy.json`, guides) — not the per-finding memory files (distinct filenames, rarely
collide). So: **distribute findings cheaply, centralize fixes.** One designated *integrator* machine
does all code-fixing on short-lived branches; both machines feed it raw findings via git.

Two long-lived branches that each merge `main` at different times **diverge** and create confusing
"is it merged?" states (this happened with `hardware-optimization`). Avoid that: integration branches
are **fresh off `main` and deleted right after merge**.

## Protocol

### Both machines — after each replicate completes
1. Record run findings to `.claude/agent-memory/<worker>/*.md` as usual.
   Per CLAUDE.md Cross-Track Rule 5, log **repo-relative** paths (`data/<run>/...`), never
   `/home/<user>/...` — keeps captures portable (no sanitization needed).
2. Commit the new memory files to `main` and push frequently. These commits touch only memory files
   → effectively zero conflict surface. (If both machines append to the same `MEMORY.md` index, that
   one file may conflict trivially — resolve by keeping both lines.)

### Integrator machine — to land code + ingest findings
1. `git fetch origin --prune`, then run the helper:
   ```
   python3 scripts/integrate.py --source-ref origin/<other-machine-branch>   # if the other machine pushed code on a branch
   # or, for pure same-repo main-based integration, just branch off main directly
   ```
   `integrate.py` creates an isolated worktree off `origin/main`, merges the source ref
   (conflict-checked first), runs the **foreign-home guard** (flags any `/home/<other-user>/...`),
   and runs the test suite.
2. Open a PR → `main`, **squash-merge**, then **delete the integration branch** (the helper prints
   the exact commands). Never reuse a long-lived branch.
3. Run `/ingest-memory` over the now-combined pending memory queue. Per the
   capture → ingest → drop pattern, expect mostly verify-and-delete with a few genuine code folds.

### Both machines — before the next replicate
`git fetch && git switch main && git pull` so every run uses the improved workflow.

## Path portability (the chore this kills)
`gen_prompt.py` derives all run paths from `REPO_ROOT` (its own checkout dir), so generated worker
prompts are correct on any machine with **zero edits**. Guides/`polymer_rules.json` examples are
repo-relative. The only legitimately machine-specific paths are the LAMMPS/KOKKOS binaries, gated by
the `LAMBDA_LAMMPS` / `LAMBDA_LAMMPS_KOKKOS` env vars — set those per machine, never hard-code them.
If `scripts/integrate.py`'s guard ever flags a foreign `/home/<user>/...`, it's a regression of this
policy — fix at the source, not with a one-off `sed`.
