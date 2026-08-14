---
name: feedback-cache-write-blind-no-read
description: never Write guides/system_characterization_cache.json directly -- use write_characterization_cache.py, which read-merges one SMILES key
metadata:
  type: feedback
---

Write the cache entry with `orchestration/scripts/write_characterization_cache.py --smiles ...
--fields <output_dir>/system_characterization.json`, never with the `Write` tool.

**Why:** a `Write` to `guides/system_characterization_cache.json` is a full-file overwrite, and
this agent used to be denied `Read` and `Bash` on it — so the overwrite went through with zero
visibility into the other SMILES entries it was destroying. On cis-PBD1 (2026-08-11) the only
evidence of the file's prior state was the run_plan's own `assumptions[]` note. Both the script
and the cache path are now on this agent's `bash_allow`, and the cache is on its
`extra_read_allow`.

**How to apply:** the script merges one key and preserves everything else, including the
`protocol_validated`/`validated_*` fields owned by `protocol-locker.md` — it refuses to write
those. It also enforces the reliability gate: exit 1 with `no_reliable_measurement` is the
expected outcome when both probe flags are false, not an error to retry. Verify with
`jq --arg s "<smiles>" '.[$s]' guides/system_characterization_cache.json`.
