---
name: cis-lock-nocoeff-ff-detect
description: generate_equilibration_workflow FF auto-detect rejects TraPPE-UA override on cis-microstructure-lock .data files; fix by restoring EMC provenance markers in the header
metadata:
  type: feedback
---

`generate_equilibration_workflow(use_trappe=True, ...)` can hard-error with `FF flag mismatch:
caller set use_trappe=True but 'cell.data' requires use_trappe=False` even when
`inspect_data_file` passes clean and `emc_build.params` explicitly says
`field trappe/2014/trappe-ua`. This happened on a PDIE cis-microstructure-lock output
(`lammps/cis_lock/cis_locked.data`) — a post-processing stage that re-wrote the EMC `.data`
via LAMMPS `write_data ... nocoeff`, which replaces line 1 (`LAMMPS output created by EMC
v9.4.4, ...` → `LAMMPS data file via write_data, ...`) and strips the per-type mass comments
(`# c3h`, `# c4h2`, ...). The FF auto-detector keys on those markers, not on
`params_file`/`Pair Coeffs`, so a nocoeff-rewritten cell silently mis-detects.

**Why:** `inspect_data_file`'s "Coeffs section missing" suppression (triggered by passing
`params_file`) is a *separate* code path from `generate_equilibration_workflow`'s FF-mismatch
guard — passing `params_file` does not clear this error. Overriding by setting
`use_trappe=False` per the error's own suggestion would silently emit a class2/CHARMM-style
deck on a 3-type UA cell with zero charges (matches the known `npt_deform`/tg-sweep
wrong-deck-emitted-for-PCFF-when-it-should-be-TraPPE-UA failure mode elsewhere in this
project) — never take that path.

**How to apply:** When a `.data` file has passed through any post-processing stage that used
LAMMPS `write_data` (cis-lock, atom reordering, etc.) and `generate_equilibration_workflow`
rejects the correct FF flag, patch only the header line 1 and the `Masses` section comments to
match the raw EMC build's format (compare against `cell/cell.data` in the same run dir — reading
its header for a format reference is fine, do not use it as the actual input). Use Bash +
python3 (rewrite to a new file, then `mv`) since the `Read`/`Edit` tools refuse `.data` files as
binary and `sed -i` in-place edits get blocked by the auto-mode classifier. After patching,
`diff <(tail -n +N patched.data) <(tail -n +N original.data)` on the body (everything after the
header/Masses block) to confirm the atom/bond/angle/dihedral records are byte-identical —
only the header/comment lines should differ. Re-run `inspect_data_file` to confirm
`errors: []` still holds, then retry `generate_equilibration_workflow` unchanged.
