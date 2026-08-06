---
name: project-cache-writes-zero-value-entries-on-probe-failure
description: RESOLVED (2026-08-06) — the cache write is gated on at least one reliability flag being true; a fully-unreliable characterization writes nothing. Originally proven on the (now-removed) pre-equilibration probe; the same gate is what refine_from_equil relies on today, since it's the only characterization path left.
metadata:
  type: project
---

**Status: fixed, and now the only path.** `system-probe-worker` and `system-probe-analyzer`'s
`analyze_probe` task (the pre-equilibration probe) were removed — `refine_from_equil` against the
real equilibration chain's own stationary hold is now the sole characterization mechanism. The
reliability-gated cache write this memory tracks is unchanged: write/update
`guides/system_characterization_cache.json[canonical_smiles]` **only if at least one of
`tau_relax_reliable`/`K0_reliable` is true**; if both are false, leave the key absent (or, if an
entry already exists from an earlier reliable characterization, leave it untouched).

**Original problem (PVDF1, `*CC(*)(F)F`, PHAL, probe-era):** the write was unconditional, so a
probe that failed both reliability gates for a structural reason still wrote a cache entry with
all `derived_*` fields null. Any future run of that exact SMILES would read `IS_NOVEL=false` off
the bare key-existence novelty gate and skip characterization forever, silently inheriting the
all-null result.

**First clean exercise of the fix (PMMA_PROBETEST1, `*CC(*)(C)C(=O)OC`, PACR, 2026-08-06,
probe-era):** the probe failed both gates again (`decay_fraction_at_end=0.077 < 0.15`; `K0
sem/mean=18.7% > 15%`) from a genuinely short window on a genuinely stationary hold. Confirmed
`guides/system_characterization_cache.json` was left untouched (no key written for this SMILES).

**How to apply going forward:** trust that the gate exists and works — no need to re-verify it
every run. Still worth doing per-run: write a loud `cache_write.performed=false` note in
`system_characterization.json` and the run_log D-09 row explaining *why* nothing was cached, so a
human/grading pass understands this SMILES is still effectively uncharacterized rather than
silently "already characterized."
