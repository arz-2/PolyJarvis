---
name: recovery-r25-absolute-path-fix
description: Tg sweep retry r25 — relative data path in .in caused read_data failure; resubmission with absolute path succeeded
metadata:
  type: feedback
---

**Issue:** Initial r25 submission failed at read_data because the generated .in script contained a RELATIVE data path that did not resolve from the work_dir.

**Root Cause:** generate_script() was called with a relative data_file path argument (or the template did not expand it to absolute form in read_data statement).

**Fix:** Resubmitted with an ABSOLUTE data_file path in the generate_script() call — built by resolving the repo-relative artifact path against `<repo_root>` at runtime (REPO_ROOT = Path(__file__).resolve().parent.parent), never a hard-coded machine path:
```
data_file="<repo_root>/data/PSU3/lammps/equil/npt_extend/npt_extend_out.data"
```

**Verification:** After generation, grepped the .in file for `read_data` and confirmed the absolute path was written before submission.

**Why:** The run's work_dir is a sibling to the equil data file, not a parent — relative paths (e.g., `../equil/npt_extend/npt_extend_out.data`) are fragile across different execution contexts. Always use absolute paths for cross-directory file references.

**How to apply:** When calling generate_script() or run_lammps_script(), always pass absolute paths for data_file, script, work_dir, and progress_file. Verify with a quick grep before submission. This avoids silent I/O failures that are hard to debug (LAMMPS error logs don't always capture the read failure clearly).

