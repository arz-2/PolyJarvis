---
name: workdir-double-cell-path
description: The prompt's work_dir already ends in /cell (gen_prompt.py appends it) — do not create {work_dir}/cell/ as the guide's literal text implies
metadata:
  type: feedback
---

The MOLECULE_BUILDER guide says "save outputs into `{work_dir}/cell/`", but
`orchestration/scripts/gen_prompt.py` emits `work_dir: {work_dir}/cell` (line ~347, the
`_v(args.smiles)` prompt block). The prompt therefore already hands over the
appended path, e.g. `data/<RUN>/lammps/cell`.

**Why:** following the guide literally produces a nested
`data/<RUN>/lammps/cell/cell/cell.data` that downstream stages will not find.

**How to apply:** write `cell.data` / `emc_build.params` **directly inside** the
`work_dir` value given in the prompt; `mkdir -p` on it is fine. Report that same
absolute path in the RESULT block.

Related friction in the same prompt block: `phal_patch: <bool>` is generated as
literally `str(polymer_class == 'PHAL').lower()` and has **no consumer** anywhere
(the EMC server mentions PHAL only in routing/doc strings) and no guide entry — it
is a derived hint, not an instruction. Don't spend tool calls chasing it. The one
plausible consumer, `mcp-servers/mcp-mol-builder-server/patch_fluorine_params.py`,
post-processes a **GAFF2/GAFF2_mod** `.data` file to swap F LJ params to the
Watkins&Jorgensen OPLS values — i.e. it exists to rescue the RadonPy path. On the
EMC/OPLS-AA route EMC assigns native `opls_965` F params already, so no patch step
is needed for PHAL builds.
See [[emc-binary-annual-expiry]].
