---
name: project-cache-writes-zero-value-entries-on-probe-failure
description: system_characterization_cache.json step 6 is unconditional, so a fully-failed probe (both reliability gates false) still writes a cache entry, silently disabling future probes for that SMILES via the bare key-existence novelty gate
metadata:
  type: project
---

`analyze_probe` step 6 says write the cache entry unconditionally (it's not a tool-failure case —
the analysis itself completed cleanly, it just measured nothing usable). But
`CLAUDE.md`'s novelty gate (`IS_NOVEL = jq --arg s "$CANONICAL_SMILES" 'has($s) | not'
guides/system_characterization_cache.json`) is a bare key-existence check, not a quality check.

**Why this matters:** the first PVDF1 probe (`*CC(*)(F)F`, PHAL) failed both `probe_tau_relax_reliable`
and `probe_K0_reliable` (see [[feedback-npt-pppm-decompression-ramp-breaks-probe]] — root cause was
a decompression-ramp probe stage, not a bad SMILES). Per protocol we still wrote the cache entry
with all `derived_*` fields null/false. Any future PVDF run will now read `IS_NOVEL=false` and skip
the system probe entirely — meaning the probe-protocol bug will silently persist forever for this
SMILES, since nothing will trigger a re-probe once cached.

**How to apply:** when writing a cache entry after a fully-failed probe (both reliability gates
false), always add an explicit `"note"` field flagging that a re-probe is warranted once the probe
protocol is fixed, and say so plainly in the run_log and RESULT block — don't let the orchestrator
read a cache hit as "already characterized, nothing to do." Consider recommending (to whoever owns
the cache-consumption logic, not this agent) that the novelty gate check for at least one
`derived_*` field being non-null before treating a SMILES as "already characterized" — but that is
a change outside this agent's scope; for now, the mitigation is loud logging, not silently skipping
the cache write (step 6 is unconditional and should stay that way per current instructions).
