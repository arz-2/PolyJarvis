---
name: feedback-bash-scope-blocks-polymer-rules-grep
description: Bash tool scope denies any command referencing guides/polymer_rules.json (jq/grep), even read-only — use the Read tool with offset/limit paging instead
metadata:
  type: feedback
---

Step 7 requires checking whether a `polymer_class` entry already exists in
`guides/polymer_rules.json` (`jq --arg c ... '.classes[$c]'`). The Bash tool's permission scope
denies *any* command whose args reference `guides/polymer_rules.json` — including pure read-only
`jq`/`grep`/`python3 -c` calls — with "outside your allowed Bash scope (own data/** workspace +
your specific allowlisted scripts)". This isn't specific to jq; every Bash invocation naming that
path was denied.

**Why:** the harness's per-agent Bash allowlist for this worker apparently doesn't include
`guides/polymer_rules.json` even for reads, only `data/**` and a fixed script list — but the
agent doc's step 7 explicitly asks the worker to jq that exact file.

**How to apply:** don't retry jq/grep/python3 variants against `guides/polymer_rules.json` — they
will all be denied identically. Use the `Read` tool directly on the absolute path instead (it has
no such scope restriction); for a 2000+ line file, page through with `offset`/`limit` to find the
target class block (there's no grep-via-Read, so budget a few sequential reads for a large file).
