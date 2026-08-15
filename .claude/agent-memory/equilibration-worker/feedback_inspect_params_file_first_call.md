---
name: feedback_inspect_params_file_first_call
description: Pass params_file on the FIRST inspect_data_file call for EMC builds, not after seeing Coeffs-missing errors
metadata:
  type: feedback
---

On PLA1, the first `inspect_data_file` call omitted `params_file` and came back with
`validation.errors` full of "'X Coeffs' section missing" (5 entries) — even though the guide
text (Step 1) already states EMC `.data` files store coefficients in the params file. Re-running
with `params_file="{work_dir}/emc_build.params"` cleared all five errors on the same cell.

Why: wasted a full inspect_data_file round-trip and made the validation output look like a real
blocking failure when it was just a missing kwarg.

How to apply: for any EMC-class build (params_file exists next to cell.data, as it always does
for POXI/PSTR/PEST/PACR/PSFO/etc.), pass `params_file` on the very first `inspect_data_file` call
— don't wait to see Coeffs-missing errors first. Mirrors [[feedback_cis_lock_nocoeff_ff_detect]]
(same root cause: FF/coeff detection needs the params file, not just the .data file).

Separately: tool-call JSON results (e.g. `generate_equilibration_workflow`'s return dict) are not
auto-persisted to a file on disk — `Bash python3 json.load(open(...))` against a path you never
`Write`'d will fail with FileNotFoundError. To slice `workflow["stages"]` for `phase=melt`,
either transcribe the returned JSON into a `Write` call first, or slice by hand from the tool
result text — there is no shortcut file already sitting in the scratchpad.
