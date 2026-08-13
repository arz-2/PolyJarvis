---
name: feedback-docs-output-path-unvalidatable
description: When orchestrator redirects output_path outside data/<run>/raw/ (e.g. docs/), the worker's own permission scope blocks Read and Bash(jq) on that exact path, so step-5 JSON validation cannot be performed at all
metadata:
  type: feedback
---

For a methodology/cross-cutting task, the orchestrator instructed output to
`/home/arz2/PolyJarvis/docs/ff_selection_literature.json` instead of the normal
`data/<RUN>/raw/literature_grounding.json`. Write succeeded, but both `Read` and
`Bash` (python3/jq) on that exact path were denied: "outside your allowed context
(guide + relevant rules JSON + your own data/** workspace + agent-memory)" /
"outside your allowed Bash scope (own data/** workspace + your specific
allowlisted scripts)".

**Why:** the worker's permission scope is hardcoded to `data/**` for output
validation; any output_path outside that tree (docs/, guides/, repo root) is
unreachable for the mandatory "validate it parses" step even though Write to
that same path is permitted.

**How to apply:** if asked to write output outside `data/**`, do not attempt to
self-verify via Read/Bash — Write's success is the only available signal.
Write the file carefully (balanced braces/brackets, no trailing commas) in one
pass since there's no verification loop, and flag this asymmetry (write-allowed,
read/validate-blocked) to the orchestrator/user rather than silently reporting
an unwritten validation checkmark. Related: [[feedback_bash_scope_blocks_polymer_rules_grep]]
covers the same scope boundary for guides/polymer_rules.json.
