# a3 — recorded protocol vs the deck that ran

36 runs audited by reading the archived `.in` files.

| axis | runs drifting | recorded -> executed |
|---|---|---|
| `cutoff_A` | 32/36 | 12.0 -> 9.5 |
| `eq_annealing_cycles` | 36/36 | 5 -> None |

Axes probed with no drift found: `dt_fs`, `electrostatics`, `tg_t_step_K`, `nchain`.

## Notes

- `eq_annealing_cycles`: generate_equilibration_workflow has no annealing-cycles parameter; the workflow runs one heat/compress/cool pass.
- `cutoff_A` reaches the deck only for TraPPE (`LJ_CUTOFF`); the PCFF and OPLS pair styles are hardcoded constants in `script_generator.py`, so the recorded value was decorative for every Class II run.

This audit reads decks, not code, so an axis absent here is absent from the simulation that produced the published number.
