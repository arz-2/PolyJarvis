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
