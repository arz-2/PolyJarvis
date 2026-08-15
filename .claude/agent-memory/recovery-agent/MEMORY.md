# Recovery-agent Memory Index

## Known diagnosis issues (check before recommending an action)
- [density_homogeneity mass-CV false positive](feedback_density_homogeneity_mass_cv_false_positive.md) — gate compares a mass-weighted CV against a count-based Poisson floor; the 2026-08-11 `cv_signal<=11%` rewrite is the same bug quadrature-subtracted
- [Degenerate KWW tau → 1.5 ns flat](feedback_degenerate_kww_tau_extend_sizing.md) — `tau_ps` pinned at the 1e9 fit bound is "finite" but unusable for `extend_ns` sizing
- [Marginal density_drift is autocorrelation, not a p-value](feedback_marginal_density_drift_autocorrelation.md) — drift p=0.0 assumes independent rows; break the tie with the P-vs-rho quarter trajectory and size EXTEND from the stationary-noise scale
- [tg deck's emc_build.params include = `<work_dir>/emc_build.params`](feedback_tg_sweep_params_file_lammps_root.md) — deterministic from tg_prompt.txt's work_dir (a dir no stage populates); stage the file there, prefer the copy over a params_file override, clear tg_sweep.log before resubmit
- [UNDER_ANNEALED_COOLING = ramp rate, not anneal cycles](feedback_under_annealed_cooling_ramp_rate_calibration.md) — localize per-bin alpha_V in npt_cool300 and calibrate against the run's own npt_cool stage; PACR needs ~40 K/ns
- [n_eff_density fails on a trend-inflated raw tau](feedback_n_eff_density_tau_inflation.md) — detrended tau + sigma~1/sqrt(N) test size-invariance; re-gate scores the extension stage halved, so the gate's extend_ns under-sizes ~2x; archived unsuffixed JSON is the 300 K glass; block-SEM is not an independent n_eff; never park a cheaper action in `notes`
- [nchain_suggested clears SIZE_CHAIN_SELF_IMAGE by ~0%](feedback_size_self_image_nchain_margin.md) — the remedy solves L/2Rg=1.0 exactly, inside the ~7% SEM of ⟨Rg⟩; re-target to ratio ≥1.08, and rebuild is ~12 min so undershoot is cheap
- [tg_steps_per_t IS the rate lever](feedback_tg_steps_per_t_is_the_rate_lever.md) — reconciles recover.md's two TG_REVIEW rows (rate ≡ ΔT/(steps·dt)); refit a single line before trusting a high-r² Tg

## Tooling friction
- [Read scope + unpersisted gate verdicts](feedback_diagnosis_tooling_friction.md) — guides/ + mcp-servers/ unreadable (diff two generated .in files instead); gate verdicts live only in the injected symptom; `completed_stages: []` trap; stale *melt* dump on `phase=full` re-gates; recovery stages overwrite predecessors; hand-roll the thermo-log parser; `orchestration/` denied too so step 5b is unrunnable — give two reasons when skipping it; test the injected symptom's causal premises; recover.md actions can be step-specific even when the error string matches; `.claude/agents/` denied too — read the worker slug + tool contract from `data/<RUN>/raw/prompts/`
