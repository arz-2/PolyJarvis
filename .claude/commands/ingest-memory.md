---
description: Ingest pending agent memory findings into the codebase — attempt fixes, update docs, mark memories as ingested
allowed-tools: Read, Bash, Edit, Write
---

Ingest pending subagent memory findings into authoritative codebase sources. For each pending memory, attempt a code-level fix if the issue is still present, update documentation, and mark the memory as ingested.

**Arguments:** Optional worker name to scope ingestion (e.g. `/ingest-memory molecule-builder`). Default: all workers.

---

## Step 1 — Scan for pending memories

```bash
find /home/alexzhao/PolyJarvis/.claude/agent-memory -name "*.md" \
  ! -name "MEMORY.md" | xargs grep -rL "ingested_at:" 2>/dev/null
```

Each file without `ingested_at:` in its frontmatter is "pending." If an optional worker-name argument was given, filter to that worker's subdirectory only. If no pending files are found, report "No pending memories — nothing to ingest." and stop.

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

**`builder_status` field values** (add to `polymer_rules.json` class entry as needed):
- `"supported"` — default; omitting means supported
- `"unsupported"` — both builders fail; orchestrator will not spawn molecule-builder
- `"experimental"` — works in some configurations; caveats in `notes`

---

## Step 6 — Mark memory as ingested

For each processed memory file:

1. Add `ingested_at: YYYY-MM-DD` to the frontmatter (use today's date).
2. In the corresponding `MEMORY.md` index, append ` [ingested YYYY-MM-DD]` to that file's one-liner entry.

The file is NOT deleted or moved — it is the permanent audit trail.

---

## Step 7 — Commit

After processing all pending memories, stage all modified files and commit:

```
ingest: <worker> memory → <comma-separated list of changes>

Sources: .claude/agent-memory/<worker>/<file1>.md[, <file2>.md]
```

---

## Summary report

After committing, output a table:

| Memory file | Finding type | Status | Fix applied | Docs updated |
|---|---|---|---|---|
| psil_si_ff_gap.md | Builder/FF unsupported | resolved externally | — | polymer_rules.json, STAGE_1 |
