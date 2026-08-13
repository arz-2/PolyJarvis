---
name: feedback-bash-denied-guides-json
description: Bash is sandboxed to own data/** workspace + allowlisted scripts -- cannot grep/jq guides/polymer_rules.json or other repo-root files directly
metadata:
  type: feedback
---

Bash tool calls that reference files outside `data/<run>/**` (e.g. `guides/polymer_rules.json`,
`guides/MURNAGHAN.md`) are denied with "outside your allowed Bash scope (own data/** workspace +
your specific allowlisted scripts)" -- even for read-only `grep`/`jq`/`cat`. This applies even
though the task instructions require reading `guides/polymer_rules.json` (e.g. the
`ct_gate_reliable` lookup in step 1).

**Why:** per-agent context-boundary hook enforces this scope; it is not a one-off permission
prompt, it is a hard deny every time.

**How to apply:** use the `Read` tool (with `offset`/`limit` paging for large files) to inspect
`guides/*.json` and `guides/*.md` instead of `Bash grep`/`jq`/`cat`. Read has no such scope
restriction. For a specific-key lookup in a large JSON (e.g. `classes.PDIE.ct_gate_reliable`),
grep-by-eye across paged Read calls, or `grep -n '"<CLASS>"'` line number then Read with that
offset -- Bash `grep -n` on the file itself is denied, but `Read` after locating context via other
means still works. This is a recurring boundary for this agent since it inspects `polymer_rules.json`
every run (ct_gate_reliable check + class defaults for t_equil_ns/eq_annealing_cycles/K rates).
