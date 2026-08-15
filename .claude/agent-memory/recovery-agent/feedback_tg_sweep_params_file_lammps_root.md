---
name: tg-sweep-params-file-lammps-root
description: the tg deck's emc_build.params include is deterministically <work_dir>/emc_build.params from the THERMAL_SWEEP guide, and no stage ever populates that dir — read work_dir out of the run's tg_prompt.txt
metadata:
  type: feedback
---

**Resolved (PLA1, 2026-08-14): the path is deterministic, not unpredictable.** The THERMAL_SWEEP
guide inlined into `data/<RUN>/tg_prompt.txt` hardcodes
`params_file: "<work_dir>/emc_build.params"`, and `generate_script` passes that string through
verbatim into the deck's `include`. PLA1 was given `work_dir=<run>/lammps/thermal` and rendered
`thermal/emc_build.params`; PMMA1 was given `work_dir=<run>/lammps/` and rendered the lammps root.
Same rule, different `work_dir` — nothing is caller-*random*. The real defect is that `work_dir` for
the tg stage is a directory no stage ever writes a params copy into (the only copies are `cell/` and
`equil/`, byte-identical), so the tg deck fails at parse time on every EMC run.

So: read `work_dir` from `data/<RUN>/tg_prompt.txt`, predict the include path, and recommend staging
the file **there**. Prefer copying the file over an injected `params_file` override: a re-spawned
tg-sweep-worker re-runs the guide from step 1 and re-substitutes `<work_dir>` mechanically, so a
file on disk at the rendered path is robust to a re-render in a way the override is not. The
shotgun-all-candidates advice below is now belt-and-braces, not the mechanism.

`recover.md`'s Foundation → equil row *"Cannot open input script .../emc_build.params: No such file
or directory"* prescribes *copy `emc_params_path` into `{work_dir}/emc_build.params`*. That is
correct for `generate_equilibration_workflow` and **wrong for the tg-sweep deck**.

**Why:** on PMMA1 (chain `52f84e50`, 2026-08-11) `tg_sweep.in` rendered
`include <run>/lammps/emc_build.params` — the run's `lammps/` root, which is no stage's work_dir and
never holds a params copy. The worker had been given `work_dir=<run>/lammps/thermal` and
`tg_sweep_dir=<run>/lammps/thermal/tg_sweep_r100`; the rendered path matched neither, nor `cell/`
nor `equil/` where the only two real copies live.

**The discriminator that settles "derived from the data file?"** — `npt_cool300.in` reads the exact
same `equil/npt_production/npt_production_out.data` and includes `equil/emc_build.params`, while
`tg_sweep.in` reads that same file and includes `lammps/emc_build.params`. Same input, different
rendered params path ⇒ the path is **caller-supplied**, not derived. Don't burn calls trying to
reverse-engineer the renderer; `mcp-servers/` is outside Bash/Read scope anyway (see
[[diagnosis-tooling-friction]]).

**How to apply:** on any `emc_build.params` staging failure, `grep -n include <stage>.in` and treat
the rendered path as ground truth. Because it is caller-controlled and a re-render is unpredictable,
recommend copying the params to **all** candidate paths (`lammps/`, the stage work_dir, and the
sweep subdir) plus a pre-submit assertion that the file at the rendered `include` path exists.

Two riders on the same run:
- **Including params after a `.data` that already carries inline `Coeffs` is proven safe here** —
  `npt_cool300` did exactly that (same file lineage) and ran 5h44m clean. Prefer the copy over
  editing the deck to drop the `include`.
- Tg decks open with `log tg_sweep.log append`. After a failed parse the log holds an
  `ERROR on proc 0` prefix that the next run appends to, contaminating tg-analysis input — always
  tell the orchestrator to clear/rename `tg_sweep.log`, `log.lammps` and `*_wrapper.stdout` before
  the resubmit.
