# Equilibration Check Guide
**Read when:** You are `equilibration-checker` and need to validate the equil chain and extract density.
**Scope:** Equilibration quality check + density extraction only.

---

## Rules

**`backbone_types`** is **REQUIRED** for `check_equilibration_comprehensive` — do not guess. Derive
it from the **original pre-simulation `.data` file** (the one EMC/RadonPy wrote, e.g. the D-00
build result's `data_path` in `run_log.md`) — **never** a `write_data` output like
`equil_data_path`/`npt_prod_data_path`. `info.atom_type_names` gives each type's FF label
(e.g. `c`, `c1`, `c_1`, `hc`, `o_1`, `o_2`) and `info.h_type_ids` already excludes hydrogens. Pick
the heavy types that continue the polymer backbone; if a side-group heavy (e.g. a carbonyl O)
could be confused with a backbone one, cross-check with `awk '/^Bonds/,/^Angles/' file.data` —
backbone types appear in chain-continuing bonds. E.g. PEEK = `[1,2,5]` (aromatic C + ether O);
type names starting with `h` are never backbone.

`ct_min_decay_melt` null ⇒ aromatic main chain: leave C(t) advisory, do NOT pass `ct_min_decay` to
`check_equilibration_comprehensive`. C(t)/MSD/R_ee are computed on the melt dump regardless, so
`ct_decay_fraction`/`ct_tau_relax_ps` are always populated — report the actual values even when
`ct_min_decay_melt` was null (advisory-only, not N/A). For PHYC (PE): include `ct_decayed` +
`tau_relax_ps` in the RESULT block even on passes.

Density passes within ±5% of experimental; **below −5% is BINDING, not a soft warning.**

**Use `enforce_equilibration_gate`'s `verdict` field directly — do not re-derive PASS/EXTEND/FAIL
from the raw numbers yourself.** The four possible verdicts:
- **`PASS`** → `equil_verdict=PASS`.
- **`EXTEND`** → `equil_verdict=EXTEND`. Only density/energy drift or block-SEM failed — genuinely
  not-yet-converged, more NPT at the same T can fix it.
- **`STRUCTURAL_FAIL`** → `equil_verdict=STRUCTURAL_FAIL`. The cell converged to the *wrong*
  value, not merely an unconverged one — `EXTEND` cannot fix this. Check the `remedy` field:
  - `re_melt_slow_recool` (from `UNDER_ANNEALED_COOLING`) — melt was fine, cooling ramp too fast.
  - `heavy_melt_anneal_probe` (from `MELT_STAGE_DEFICIT`) — melt itself deficient; re-cooling
    slower will NOT help.
  - melt-mixing remedy (`density_homogeneity` failing) — this is what `phase=melt`'s pre-cool
    gate exists to catch (see Phase below): extend melt-stage dwell in place, not the cooling
    ramp, and never re-melt from scratch. Owned by `/recover`'s MELT-MIXING procedure, not this
    worker.
- **`FAIL`** → `equil_verdict=FAIL`. Box collapse, charge imbalance, dead cell (C(t) exactly 0%),
  or any binding-gate failure the mechanized script can't classify into the above. (C(t)
  decaying-but-incomplete is not a FAIL — you should never see it in `failing_binding_gates`.)

## Phase

`phase` from the prompt: `full` (default) is today's gate, after the whole equilibration chain
completes, with density extraction and the cooling-contraction diagnosis available. `melt`
(glassy only) runs against `npt_production`/`nvt_production` — the pre-cool checkpoint — *before*
`npt_cool300`/`npt_prod300` are even submitted. `phase=melt` cannot run `assess_cooling_contraction` (no glass state
exists yet), so `UNDER_ANNEALED_COOLING`/`MELT_STAGE_DEFICIT` are unreachable verdicts there —
only the structural/thermo gates that are meaningful on the melt trajectory alone (density/energy
drift, block-SEM, Rg CV, P2, density-homogeneity CV, C(t)) can fire. The prompt's `tasks:` list
and MECHANIZED GATE args already reflect which phase you're in — follow them, don't infer.

---

## Workflow

### `inspect_data_file` → `backbone_types`

Only if `backbone_types` isn't already given in the prompt — call on the original pre-simulation
`.data` file per the Rules above.

### `check_equilibration_comprehensive`

```python
kwargs = dict(
    log_file=npt_prod_log_path,   # production NPT log → thermo convergence (density/energy drift + block-SEM)
    dump_file=melt_dump_path,     # MELT nvt_production.dump (both phases) → C(t)/MSD/Rg/R_ee on mobile chains.
                                  # NOT the production dump: below Tg C(t) never decays (meaningless by construction)
    data_file=equil_data_path,
    backbone_types=backbone_types,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
if ct_min_decay_melt is not None:
    kwargs["ct_min_decay"] = ct_min_decay_melt
check_equilibration_comprehensive(**kwargs)
```

**Result fields for the RESULT block** (all from this single call):
- `overall_pass`, `d05_markdown`, `density_converged`, `energy_converged`, `ct_decayed`, `warnings`
- `result["chain"]["ct"]["decay_fraction_at_end"]` → `ct_decay_fraction`
- `result["chain"]["ct"]["tau_relax_ps"]` → `ct_tau_relax_ps`
- `result["chain"]["ree"]["mean_R_ee_A"|"std_R_ee_A"|"n_chains"]` → `end_to_end_r_mean_A` / `_std_A` / `_n_chains`

### `extract_equilibrated_density`

```python
extract_equilibrated_density(
    log_file=npt_prod_log_path,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
    eq_fraction=0.5,                 # discard first 50% as burn-in
    target_temp=npt_prod_temp_K,     # filter to production-T rows if log is multi-T
)
```
Primary output: `plateau_density_mean` ± `plateau_density_std`. Verify `plateau_step_range`
starts after the compression ramp.

### `enforce_equilibration_gate`

Call args are filled in above (search "MECHANIZED GATE"). Call it after the equilibration check
and density extraction write their JSON.
