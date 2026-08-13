---
name: murnaghan-glassy-vs-rubbery-null-ladder-CONTENT-LOST
description: PLACEHOLDER — original content of this file was accidentally overwritten (2026-08-11) by a planner Write() without a prior Read(); the file was untracked in git so it is unrecoverable. See MEMORY.md / feedback_murnaghan_glassy_ladder_policy_drift.md (critic dir) for a possibly-related surviving memory on the same topic.
metadata:
  type: feedback
---

INCIDENT: on 2026-08-11, during a PMMA1 rung-3 STRUCTURAL_FAIL re-plan, the planner agent called `Write` on this exact path to save a new, unrelated feedback memory (about rung-3 non-FF protocol reasoning) without first calling `Read` on it, even though `git status` at session start showed this file as untracked (`??`) — meaning it already existed on disk with prior content that was never read. The `Write` tool did not block the overwrite. The original content is unrecoverable (untracked, no git history: `git show HEAD:<path>` confirms the path exists on disk but not in HEAD).

**Why this matters:** the filename topic ("murnaghan glassy vs rubbery null ladder") suggests this held guidance about `guides/MURNAGHAN.md`'s branching between the glassy single-leg universal pressure ladder and the rubbery two-leg PROBE protocol on a null `bm_pressures_atm` — likely written by a prior critic or planner session. The critic agent-memory dir has an apparently-related file `feedback_murnaghan_glassy_ladder_policy_drift.md` (still untracked as of this incident) which may cover overlapping or complementary ground and should be checked/cross-linked when reconstructing this topic.

**How to apply:** ALWAYS `Read` a target memory file before `Write`-ing to it, even for a brand-new-seeming topic — an untracked file in `git status` is a strong signal the path is already in use by a concurrent or prior session. Prefer checking `ls` on the target agent-memory directory (or grepping `MEMORY.md`) before choosing a filename, not just picking a plausible-sounding slug. If a future session has independent knowledge of the original Murnaghan glassy/rubbery null-ladder content, please replace this placeholder.
