import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from run_campaign import _base_args  # noqa: E402
from stage_params import apply_plan, resolve_hardware  # noqa: E402


RULES = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())
CLASS_NAME = "PSTR"


def _resolved(override, cli_gpu=None, cli_mpi=None):
    args = _base_args("HWFLOW", CLASS_NAME, "/tmp/plan.json")
    args.gpu_ids = cli_gpu
    args.mpi_ranks = cli_mpi
    cls = apply_plan(RULES["classes"][CLASS_NAME], {"decided_params": override}, args)
    resolve_hardware(args, cls, RULES)
    return args


def test_plan_hardware_override_flows_to_runtime():
    args = _resolved({"engine": "gpu", "gpu_per_run": 2, "mpi_ranks": 4})
    assert args.gpu_ids == "0,1"
    assert args.mpi_ranks == 4


def test_explicit_runtime_hardware_wins_over_plan():
    args = _resolved(
        {"engine": "gpu", "gpu_per_run": 2, "mpi_ranks": 4},
        cli_gpu="3",
        cli_mpi=8,
    )
    assert args.gpu_ids == "3"
    assert args.mpi_ranks == 8


# ── The validator's half of the same contract ────────────────────────────────────────────
# _hardware_findings read engine/gpu_per_run/mpi_ranks out of decided_params only. The
# 2026-09-04 fold moved the DERIVED triple to plan["hardware"] and stopped writing it into
# decided_params, so `pin` came back all-None on every planner path and the function returned
# before reaching a single check -- the mpi=1+GPU PPPM anti-pattern and the unbenchmarked
# multi-GPU pin both stopped being enforced, silently, on every plan.

def _plan_with(**decided):
    import make_deterministic_plan as mdp
    plan = mdp.make_plan("HWCHECK", "PSTR", "*CC(c1ccccc1)*", {"density"})
    plan["decided_params"].update(decided)
    return plan


def _checks(plan):
    import validate_run_plan as vrp
    return {(f["check"], f["severity"]) for f in vrp._hardware_findings(plan)}


def test_a_derived_plan_pins_nothing_unsafe():
    assert _checks(_plan_with()) == set()


def test_the_pppm_starvation_anti_pattern_is_caught_again():
    """mpi_ranks=1 with the GPU package (not kokkos) starves PPPM kspace -- decision_policy
    requires mpi>=4 there, and a charged class2 polymer is exactly where it bites."""
    assert ("hardware_anti_pattern", "structural") in _checks(
        _plan_with(engine="gpu", mpi_ranks=1))


def test_a_multi_gpu_pin_with_no_measured_point_is_caught_again():
    assert ("hardware_size_mismatch", "structural") in _checks(_plan_with(gpu_per_run=4))


def test_an_unbenchmarked_deviation_is_reported_but_does_not_block():
    """It was structural, and demanded a D-08_hardware row to acknowledge it. D-08 was retired
    on 2026-09-04, so no legal edit could clear the finding -- an unsatisfiable gate. Writing
    the pin into `overrides` is the acknowledgement now, so this is info."""
    severities = {sev for check, sev in _checks(_plan_with(mpi_ranks=6)) if check ==
                  "hardware_staleness"}
    assert "structural" not in severities
