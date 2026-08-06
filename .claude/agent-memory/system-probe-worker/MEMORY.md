# System-Probe-Worker Memory Index

- [melt_npt_steps is a no-op for npt_pppm](feedback_melt_npt_steps_noop.md) — only sizes npt_melt (add_melt_npt=True path); npt_pppm duration is size-tiered off n_atoms, no override; report actual steps used
- [npt_pppm is a decompress ramp, not a hold](project_npt_pppm_is_decompress_ramp.md) — P_START=max_press→P_FINAL=1atm at const T; flag to analyzer as non-stationary, don't improvise add_melt_npt
