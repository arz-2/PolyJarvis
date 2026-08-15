---
name: feedback-write-cache-script-flat-field-contract
description: write_characterization_cache.py's --fields gate reads flat top-level derived_* keys; do not pass it the nested system_characterization.json verbatim
metadata:
  type: feedback
---

Step 4 writes `system_characterization.json` (nesting knobs under a `"derived": {...}"` sub-object,
per this agent's own natural layout) and step 6 says to pass `<output_dir>/system_characterization.json`
as `--fields` to `write_characterization_cache.py`. But the script's write gate ("≥1 non-null
derived_* field, else exit 1 with no_derived_field") reads flat top-level keys
(`derived_t_equil_ns`, `derived_K_deform_rate_inv_s`, etc.), not a nested `derived` object, and also
expects `refined_from_full_run`/`reprobe_recommended`/`note` at the top level.

**Why:** confirmed by testing — building a separate flat `--fields` JSON (not
`system_characterization.json` verbatim) was the only way to get the script to evaluate the gate
correctly. This run's probe produced zero derived fields either way so the mismatch was moot, but a
future run that DOES legitimately derive a knob would get a false `no_derived_field` exit if handed
the nested diagnostic file directly — a silent lost cache write, not an obvious error.

**How to apply:** always build a separate, flat `--fields` JSON scratch file for the
`write_characterization_cache.py` call (top-level `derived_*`, `probe_*`, `refined_from_full_run`,
`reprobe_recommended`, `note` keys) — do not assume `system_characterization.json` itself satisfies
the script's schema even though step 6's prose reads that way. Keep `system_characterization.json`
in whatever layout best carries the required rationale per field (step 4's requirement), separately
from the flat cache payload.
