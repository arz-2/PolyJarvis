---
description: Ingest pending agent memory findings into the codebase — attempt fixes, update docs, mark memories as ingested
allowed-tools: Read, Bash, Edit, Write
---

Ingest pending subagent memory findings into authoritative codebase sources. For each pending memory, attempt a code-level fix if the issue is still present, update documentation, and mark the memory as ingested.

**Arguments:** Optional worker name to scope ingestion (e.g. `/ingest-memory molecule-builder`). Default: all workers.

---

## Step 1 — Scan for pending memories

```bash
# Repo-wide scan: any *.claude/agent-memory/*.md anywhere in the checkout. A single
# rooted find catches the canonical repo-root dir AND every stray dir a worker created
# when its cwd was inside a subdir (data/<run>/..., mcp-servers/<srv>/..., bench/...).
find /home/arz2/PolyJarvis -path "*/.claude/agent-memory/*.md" ! -name "MEMORY.md" \
  2>/dev/null | xargs grep -rL "ingested_at:" 2>/dev/null
```

Each file without `ingested_at:` in its frontmatter is "pending." (Going forward, ingested memories are deleted rather than marked — see Step 7 — so any legacy file still carrying `ingested_at:` is skipped.) The harness resolves a worker's `.claude/agent-memory/<worker>/` dir **relative to its cwd**, so findings strand under whatever subdir the worker ran in — not just `data/<run>/`. The repo-wide `-path` glob catches them all; treat strays identically to canonical ones. If an optional worker-name argument was given, filter to that worker's subdirectory only. If no pending files are found, report "No pending memories — nothing to ingest." and stop.

---

## Step 2 — For each pending memory: read and classify

Read the full file content. Identify the **finding type** using this table:

| Finding type | Indicators |
|---|---|
| Builder/FF completely unsupported | Both builder paths fail; class cannot produce a .data file |
| FF parameter gap (partial) | One path fails; a workaround may exist (e.g., patch script, different FF) |
| Equilibration param correction | Discovered better `T_equil_K`, `annealing_T_high_K`, `eq_annealing_cycles`, etc. |
| Tg sweep range inadequate | Tg outside `[tg_t_low_K, tg_t_high_K]` or fit quality poor due to range |
| SMILES convention error | Wrong `*` placement; EMC rejects SMILES |
| Guide/doc inaccuracy | A claim in a guide or polymer_rules.json is empirically wrong |
| Worker execution pattern | Worker mis-routes, skips, or fails at a step due to bad instructions |
| MCP server code bug | The MCP server returns wrong result or rejects a valid input |
| Codebase improvement / friction | An enhancement, not a bug: an awkward but functioning workflow, a confusing guide, a missing convenience, a "room for improvement" note from a run |

---

## Step 3 — Verify current state

Before applying any fix, check whether the issue is **still present** in the codebase.
Use the appropriate verification command from the table below. This catches stale memories
where a fix was applied manually after the memory was written.

| Finding type | Verification approach |
|---|---|
| Builder/FF unsupported | `grep -n "CLASSID\|class_id.*CLASSID" mcp-servers/mcp-emc-server/server.py` — is the class in the allowlist? Also check `polymer_rules.json` preferred_builder. |
| FF parameter gap | Grep the relevant FF param file or patch script for the missing type. |
| Equilibration/Tg param | `jq '.classes.CLASSID' guides/polymer_rules.json` — compare current values to memory finding. |
| Guide/doc inaccuracy | Read the specific section and compare to the memory claim. |
| MCP server bug | Read the relevant function in the server source. |

**If already fixed externally:** Skip to Step 5. Set internal status = "resolved externally."

**If still broken:** Proceed to Step 4.

---

## Step 4 — Attempt fix

Apply a targeted code-level or config-level change. Use the fix approach for the finding type:

| Finding type | Fix approach |
|---|---|
| **Builder/FF completely unsupported** | If EMC: add the class to the supported-class allowlist in `mcp-servers/mcp-emc-server/server.py`. If RadonPy: check if a GAFF2 param can be added to the patch script or FF file. If out-of-scope (full FF development needed), document the limitation and skip. |
| **FF parameter gap (partial)** | Add the missing param to the relevant patch script (e.g., `mcp-servers/mcp-mol-builder-server/patch_fluorine_params.py`); or add an atom-type mapping; or update `polymer_rules.json` to route to a working FF. |
| **Equilibration/Tg param** | Edit the numeric fields in `polymer_rules.json` for the class. This IS the fix. |
| **Tg sweep range** | Edit `tg_t_high_K`, `tg_t_low_K`, `tg_t_step_K` in `polymer_rules.json`. |
| **SMILES convention** | Correct the SMILES example in the guide. No code change needed. |
| **Guide/doc inaccuracy** | Edit the incorrect field or section. |
| **Worker execution pattern** | Edit the relevant `guides/STAGE_N_*.md` (add a ≤3-line note under a "Known Issues" or "Caveats" heading). Never edit `.claude/agents/*.md` — those files are static descriptors. |
| **MCP server bug** | Fix the code in the relevant server file. |
| **Codebase improvement / friction** | If the change is cheap and safe, apply it per the matching doc/code target above. Otherwise do NOT force a change — append a one-line item to a `## Backlog` list in the most relevant `guides/*.md` (create the list if absent) so the idea is tracked rather than lost. |

**After applying the fix:** Re-run the verification from Step 3. Note whether the fix is "verified" (symptom gone) or "unverified — requires a real run."

---

## Step 5 — Update documentation

Edit the appropriate codebase files to reflect the current (post-fix or workaround) state.

**Guide conciseness rule:** Each edit to a `guides/STAGE_*.md` file must be the shortest phrasing that preserves the technical meaning. Use one-line bullet points, not prose paragraphs. A new finding should add ≤3 lines total. Prefer appending to an existing bullet list over creating a new section.

Apply the doc targets from this table:

| Finding type | Primary doc target | Secondary doc target |
|---|---|---|
| Builder/FF unsupported | `polymer_rules.json[class]`: set `builder_status: "unsupported"` or `"supported"` as appropriate; fix `preferred_builder`, `preferred_ff`, `ff_notes` | `guides/STAGE_1_MOLECULAR_CONSTRUCTION.md`: Known Warnings (unsupported) or remove warning (now supported) |
| FF parameter gap | `polymer_rules.json[class].notes[]`: append outcome; update `ff_notes` | `guides/STAGE_1_MOLECULAR_CONSTRUCTION.md`: Common Failures |
| Param correction | `polymer_rules.json[class]`: the updated numeric fields are the documentation | — |
| Tg sweep range | `polymer_rules.json[class]`: updated range fields | — |
| SMILES convention | `guides/STAGE_1_MOLECULAR_CONSTRUCTION.md`: SMILES Conventions table | — |
| Guide/doc inaccuracy | The specific guide section | — |
| Worker pattern | `guides/STAGE_N_*.md` relevant section | — |
| MCP server bug | Relevant stage guide if behavior changed | — |
| Codebase improvement / friction | The applied doc/code target, or a `## Backlog` bullet in the most relevant `guides/*.md` | — |

**`builder_status` field values** (add to `polymer_rules.json` class entry as needed):
- `"supported"` — default; omitting means supported
- `"unsupported"` — both builders fail; orchestrator will not spawn molecule-builder
- `"experimental"` — works in some configurations; caveats in `notes`

---

## Step 5b — Refresh the recovery playbook

Regenerate `guides/RECOVERY_PLAYBOOK.md` from the accumulated
`manuscript/data/<RUN>/run_log.md` corpus (the consolidated benchmark runs; live runs
still land in `data/` and join the corpus when consolidated). `runlog_miner` clusters
past RECOVERIES into a signature → diagnosis → fix table ranked by empirical success
rate; the `recover` skill consults this **before** its built-in taxonomy, so a fresh
distillation here closes the learning loop each time memories are ingested.

```bash
python -m tools.runlog_miner --playbook --data-dir manuscript/data -o guides/RECOVERY_PLAYBOOK.md
```

The file carries a `do not edit by hand` header — it is fully generated, so the
overwrite is safe. It is a local-only artifact (gitignored) — do not stage it.
(This is playbook-only; the miner's `--suggest`/`--diff` polymer_rules.json deltas
are intentionally **not** auto-applied here — keep those a separate, reviewed step.)

---

## Step 6 — Commit the fixes (audit trail)

After processing all pending memories, stage the fixes / doc updates / backlog notes and commit. List every source memory in the `Sources:` line — **this commit is the permanent audit trail**, which is why the memory files themselves can be deleted in Step 7.

```
ingest: <worker> memory → <comma-separated list of changes>

Sources: .claude/agent-memory/<worker>/<file1>.md[, <file2>.md]
```

---

## Step 7 — Delete ingested memories

Only after Step 6 has committed (so nothing is lost if interrupted), delete each ingested memory:

1. `rm` the memory `.md` file at the exact path Step 1 reported it (the canonical repo-root `.claude/agent-memory/<worker>/`, or any stray `.../.claude/agent-memory/<worker>/` under a subdir such as `data/<run>/...` or `mcp-servers/<srv>/...`).
2. Remove that file's one-line entry from the corresponding `MEMORY.md` index.

Then commit the deletions:

```
chore: drop ingested <worker> memories (ingested in <Step-6 commit sha/subject>)
```

Memories are NOT marked `ingested_at:` and kept anymore — deletion + git history is the audit trail.

---

## Summary report

After committing, output a table:

| Memory file | Finding type | Status | Fix applied | Docs updated |
|---|---|---|---|---|
| psil_si_ff_gap.md | Builder/FF unsupported | resolved externally | — | polymer_rules.json, STAGE_1 |
