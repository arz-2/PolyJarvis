"""decided_params that no executor consumes.

`eq_annealing_cycles` was raised as a remedy twice (PACR 5->10, PKTN 8->12) on the
strength of assess_cooling_contraction's UNDER_ANNEALED_COOLING verdicts, with notes
citing NkepsuMbitou's 10-cycle precedent. `generate_equilibration_workflow` has no
annealing-cycles parameter, so neither raise changed anything that ran. The failure is
silent in both directions: the plan records a protocol that did not happen, and the
remedy produces no behaviour change to explain its own ineffectiveness.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from validate_run_plan import (  # noqa: E402
    UNIMPLEMENTED_PARAMS,
    _unimplemented_param_findings,
)


def test_set_unimplemented_param_is_structural():
    f = _unimplemented_param_findings({"decided_params": {"eq_annealing_cycles": 10}})
    assert len(f) == 1
    assert f[0]["severity"] == "structural"
    assert f[0]["check"] == "decided_param_not_executed"
    assert "10" in f[0]["detail"]


def test_unset_and_null_are_silent():
    """A plan that never claims the parameter has nothing to answer for."""
    assert _unimplemented_param_findings({"decided_params": {}}) == []
    assert _unimplemented_param_findings(
        {"decided_params": {"eq_annealing_cycles": None}}) == []
    assert _unimplemented_param_findings(
        {"decided_params": {"eq_annealing_cycles": "null"}}) == []


def test_zero_still_reports():
    """0 is a claim about protocol, not an absence of one -- and it is also wrong,
    since the workflow always runs exactly one heat/compress/cool pass."""
    assert len(_unimplemented_param_findings(
        {"decided_params": {"eq_annealing_cycles": 0}})) == 1


def test_missing_decided_params_does_not_crash():
    assert _unimplemented_param_findings({}) == []


def test_every_entry_carries_a_traced_reason():
    """Entries must be verified against a call path, not guessed from a name grep --
    a false entry here would block plans over a parameter that does work."""
    for key, why in UNIMPLEMENTED_PARAMS.items():
        assert isinstance(why, str) and len(why) > 30, key


def test_implemented_params_are_not_listed():
    """cutoff_A does reach the deck (as a hardcoded style constant, which is a
    separate reporting bug) -- it must not be flagged as unimplemented."""
    for k in ("cutoff_A", "dp_typical", "nchain", "tg_rates_K_per_ns"):
        assert k not in UNIMPLEMENTED_PARAMS


# ── add_melt_npt: a parameter that EXISTS but was silently ignored ──────────────
# The eq_annealing_cycles species above is "no such parameter". This is the harder
# species: the parameter is real, the tool accepts it, returns status=success, and
# builds a deck identical to the baseline. Measured on the values gen_prompt emits for a
# glassy run (temp = T_workflow = T_equil_K = 770): the melt split armed only on
# temp < t_equil_K, so heavy_melt_anneal_probe, the melt_density_in_band remedy and the
# CHAIN_COLLAPSED melt-anneal -- all three glassy-only -- changed nothing, reproduced the
# same failure, and burned a capped recovery attempt.

def _minimal_cell(tmp_path):
    """Smallest .data generate_equilibration_workflow will accept. params_file carries the
    coefficients, as an EMC-built cell does, so no Coeffs sections are needed."""
    data = tmp_path / "cell.data"
    data.write_text(
        "LAMMPS data\n\n2 atoms\n1 bonds\n1 atom types\n1 bond types\n\n"
        "0.0 40.0 xlo xhi\n0.0 40.0 ylo yhi\n0.0 40.0 zlo zhi\n\n"
        "Masses\n\n1 12.011\n\nAtoms\n\n"
        "1 1 1 0.0 1.0 1.0 1.0 0 0 0\n2 1 1 0.0 2.5 1.0 1.0 0 0 0\n\n"
        "Bonds\n\n1 1 1 2\n")
    params = tmp_path / "ff.params"
    params.write_text("# coefficients\n")
    return str(data), str(params)


def _workflow(tmp_path, **kw):
    pytest.importorskip("mcp")
    sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"))
    import server

    data, params = _minimal_cell(tmp_path)
    args = dict(data_file=data, work_dir_base=str(tmp_path), velocity_seed=1,
                npt_prod_steps=None, npt_cool_steps=None, npt_cool300_steps=None,
                melt_npt_steps=None, extend_steps=None, temp=770.0, use_pcff=False,
                use_trappe=False, use_opls=False, engine="kokkos", max_temp=800.0,
                params_file=params)
    args.update(kw)
    return server.generate_equilibration_workflow(**args)


def test_glassy_melt_anneal_actually_inserts_a_melt_hold(tmp_path):
    """temp == t_equil_K is the glassy case, and it must arm the split."""
    baseline = [s["name"] for s in _workflow(tmp_path)["stages"]]
    assert "npt_melt" not in baseline

    r = _workflow(tmp_path, add_melt_npt=True, t_equil_K=770.0,
                  melt_npt_steps=10 * int(1.0e6 / 1.0))
    stages = {s["name"]: s["params"] for s in r["stages"]}
    assert "npt_melt" in stages, "the remedy must change the deck it claims to change"
    assert stages["npt_melt"]["N_STEPS"] == 10_000_000
    assert stages["npt_melt"]["T_START"] == stages["npt_melt"]["T_FINAL"] == 770.0

    # The gate's own measurement targets must NOT be resized by the remedy: phase=melt
    # grades npt_production, so an anneal knob that lengthened it would be feeding the
    # gate a log the remedy itself changed.
    for stage in ("npt_production", "npt_cool300", "npt_prod300"):
        assert stages[stage]["N_STEPS"] == \
            {s["name"]: s["params"] for s in _workflow(tmp_path)["stages"]}[stage]["N_STEPS"]

    # Nothing left to cool at equality -- no zero-width ramp.
    assert "npt_cool" not in stages


def test_rubbery_melt_split_still_ends_with_a_cooling_leg(tmp_path):
    stages = [s["name"] for s in _workflow(
        tmp_path, temp=300.0, add_melt_npt=True, t_equil_K=550.0)["stages"]]
    assert stages.index("npt_cool_melt") < stages.index("npt_melt") < stages.index("npt_cool")


def test_unarmable_melt_split_is_an_error_not_a_silent_baseline(tmp_path):
    """The whole point: an ignored flag must never come back as success."""
    r = _workflow(tmp_path, temp=900.0, add_melt_npt=True, t_equil_K=770.0)
    assert r["status"] == "error"
    assert "add_melt_npt" in r["error"]
