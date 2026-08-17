"""Every key a remedy can write into effective_parameters must be registered in
PARAMETER_STAGE.

_reconcile_plan() maps a changed key to the stage it invalidates from via
`PARAMETER_STAGE.get(key, "build")` -- an unmapped key silently defaults to "build", the
EARLIEST stage. A remedy that stamps a bookkeeping key (baseline_*, *_attempt,
rerun_homogeneity_gate) into effective_parameters and is never re-registered leaves that key
sitting in workflow_state.json forever; the next engine reconstruction that loads the ORIGINAL
plan (no remedy bookkeeping in its decided_params) then sees that key as "changed" and
invalidates the entire pipeline back to build -- discarding every already-accepted stage's
bookkeeping (not its on-disk manifest/artifacts, but its accepted status). Hit live on PE1
2026-08-17: tg_sampling's baseline_tg_steps_per_t cascaded equilibration's already-verified
PASS (7.5h of real GPU work) back to "stale" the moment a fresh engine was reconstructed to
repair the thermal stage.

This test calls every default remedy action with a representative Finding and asserts every
key in its output is a registered PARAMETER_STAGE key -- so a future remedy that adds a new
bookkeeping key without registering it fails CI instead of silently corrupting a live run's
resumability.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

from workflow_engine import PARAMETER_STAGE, Finding, default_remedies  # noqa: E402

# Minimal details each remedy's action function needs to run without raising.
_DETAILS_BY_REMEDY = {
    "transient_retry": {},
    "finite_size_rebuild": {"required_nchain": 50},
    "safe_hardware": {"recommendation": {"gpu_per_run": 1, "mpi_ranks": 4, "engine": "gpu"}},
    "remove_noop": {"parameter": "some_dead_key"},
    "unique_forcefield": {"admissible_alternatives": [{"forcefield": "pcff"}]},
    "continue_npt": {},
    "slower_cooling": {},
    "melt_hold": {},
    "melt_homogeneity": {},
    "tg_sampling": {},
    "tg_breakpoint": {},
    "deformation_fallback": {},
    "murnaghan_resample": {"nonmonotonic_points": [1, 2, 3]},
    "conditional_deformation": {"is_glassy": True},
    "negative_deformation": {},
    "rate_sensitivity": {},
    "agent_only": {},
}

_BASE_PARAMS = {
    "npt_cool_steps": 100000, "eq_annealing_cycles": 5, "tg_steps_per_t": 250000,
    "tg_t_step_K": 20, "K_deform_rate_inv_s": 1e8, "K_deform_rate_slow_inv_s": 1e6,
    "K_strain_max": 0.03, "is_glassy": True,
}


def test_every_remedy_only_writes_registered_parameter_keys():
    unmapped = {}
    for remedy in default_remedies():
        details = _DETAILS_BY_REMEDY.get(remedy.remedy_id)
        assert details is not None, f"remedy {remedy.remedy_id!r} has no test coverage -- add one"
        finding = Finding(code=next(iter(remedy.codes)), stage=remedy.invalidate_from, details=details)
        try:
            revised = remedy.action(dict(_BASE_PARAMS), finding, 1)
        except ValueError:
            # A handful of remedies validate preconditions (e.g. conditional_deformation
            # requires is_glassy=True) -- ValueError means it declined to act, not that it
            # wrote an unmapped key.
            continue
        new_keys = set(revised) - set(_BASE_PARAMS)
        for key in new_keys:
            if key not in PARAMETER_STAGE:
                unmapped.setdefault(remedy.remedy_id, []).append(key)
    assert not unmapped, f"remedies write keys missing from PARAMETER_STAGE: {unmapped}"
