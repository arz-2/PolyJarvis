"""Flow guard for the D-08 hardware integration (planner/critic → runtime).

A *reasoned* plan may carry a D-08_hardware override (engine / gpu_per_run / mpi_ranks in
decided_params). These tests pin the runtime contract that activates it:

  precedence: CLI > plan > policy

  - a plan override flows into the worker prompt (multi-GPU placeholders, mpi);
  - an explicit CLI --gpu_ids/--mpi_ranks still shadows the plan;
  - an engine=cpu override hides the GPUs (gpu_ids "");
  - the no-override path is byte-identical to the policy default (the deterministic-plan
    reproducibility guarantee is covered separately by test_plan_reproducibility.py).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())
GEN_PROMPT = REPO_ROOT / "orchestration" / "gen_prompt.py"
MAKE_PLAN = REPO_ROOT / "orchestration" / "make_deterministic_plan.py"


def _ff_fam(cls_entry):
    raw = (cls_entry.get("preferred_ff") or cls_entry.get("forcefield") or "").lower()
    return ("pcff" if "pcff" in raw else "opls" if "opls" in raw
            else "trappe" if "trappe" in raw else "gaff")


def _class_for(fam):
    for name, entry in sorted(RULES["classes"].items()):
        if _ff_fam(entry) == fam:
            return name
    pytest.skip(f"no class with FF family {fam}")


PCFF_CLASS = _class_for("pcff")


def _run(cmd):
    r = subprocess.run([sys.executable, *map(str, cmd)], capture_output=True, text=True)
    assert r.returncode == 0, f"command failed: {cmd}\n{r.stderr}"
    return r.stdout


def _hw(prompt):
    """Extract (gpu_ids, mpi_ranks) from a worker prompt."""
    g = re.search(r'gpu_ids:\s*"([^"]*)"', prompt)
    m = re.search(r"mpi_ranks:\s*(\d+)", prompt)
    assert g and m, f"hardware lines not found in prompt:\n{prompt[:400]}"
    return g.group(1), int(m.group(1))


@pytest.fixture(scope="module")
def base_plan(tmp_path_factory):
    out = tmp_path_factory.mktemp("hwplan") / "plan.json"
    _run([MAKE_PLAN, "--run_name", "HWFLOW", "--polymer_class", PCFF_CLASS, "--out", out])
    return out


def _reasoned_with(base_plan, tmp_path, override):
    plan = json.loads(Path(base_plan).read_text())
    plan["plan_mode"] = "reasoned"
    plan["decided_params"].update(override)
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(plan, indent=2))
    return p


def _gen(plan, *extra):
    return _run([GEN_PROMPT, "--stage", "equil", "--run_name", "HWFLOW",
                 "--polymer_class", PCFF_CLASS, "--plan", plan,
                 "--data_path", "/tmp/x.data", *extra])


def test_plan_override_multi_gpu(base_plan, tmp_path):
    """engine=gpu, gpu_per_run=2, mpi=4 → gpu_ids '0,1', mpi 4."""
    plan = _reasoned_with(base_plan, tmp_path,
                          {"engine": "gpu", "gpu_per_run": 2, "mpi_ranks": 4})
    assert _hw(_gen(plan)) == ("0,1", 4)


def test_cli_overrides_plan(base_plan, tmp_path):
    """An explicit CLI pin shadows the plan override (CLI > plan)."""
    plan = _reasoned_with(base_plan, tmp_path,
                          {"engine": "gpu", "gpu_per_run": 2, "mpi_ranks": 4})
    assert _hw(_gen(plan, "--gpu_ids", "3", "--mpi_ranks", "8")) == ("3", 8)


def test_cpu_override_hides_gpus(base_plan, tmp_path):
    """engine=cpu → gpu_ids '' (GPUs hidden)."""
    plan = _reasoned_with(base_plan, tmp_path,
                          {"engine": "cpu", "gpu_per_run": 0, "mpi_ranks": 8})
    gpu_ids, mpi = _hw(_gen(plan))
    assert gpu_ids == "" and mpi == 8


def test_no_override_matches_policy_default(base_plan, tmp_path):
    """A reasoned plan carrying no hardware override resolves to the FF-family policy
    default (PCFF: 1 GPU → '0'), identical to the no-plan path."""
    plan = _reasoned_with(base_plan, tmp_path, {})        # plan_mode flipped, no hw keys
    fam = "pcff"
    pol = RULES["hardware_policy"]["by_forcefield"][fam]
    expect_gpu = "" if pol["engine"] == "cpu" else ",".join(
        str(i) for i in range(max(1, int(pol.get("gpu_per_run", 1) or 1))))
    assert _hw(_gen(plan)) == (expect_gpu, pol["mpi"])
