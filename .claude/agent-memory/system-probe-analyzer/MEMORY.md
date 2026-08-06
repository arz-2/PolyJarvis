# system-probe-analyzer Memory Index

## Feedback
- [npt_pppm decompression ramp breaks probe](feedback_npt_pppm_decompression_ramp_breaks_probe.md) — PVDF1: tau_relax+K0 both fail reliability gates by >10x when the probe's melt-hold stage is a P-ramp not a stationary hold; 0.15 thresholds are validated, not the problem — flag upstream, don't loosen gates
- [Cache writes zero-value entries on probe failure](project_cache_writes_zero_value_entries_on_probe_failure.md) — step 6 is unconditional; a fully-failed probe still caches, silently disabling future re-probes via the bare key-existence novelty gate — log loudly, recommend re-probe
