---
name: tg-sweep-params-file-lammps-root
description: tg-sweep decks render the emc_build.params include at the run's lammps/ ROOT, not work_dir — recover.md's literal "{work_dir}/emc_build.params" prescription does not fix the tg stage
metadata:
  type: feedback
---

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
