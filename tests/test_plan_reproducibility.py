"""Reproducibility guard for the planner/critic re-architecture (Phase 1).

The confidence gate promises that a *deterministic* run_plan.json reproduces the
pre-architecture pipeline exactly: `gen_prompt.py --plan <deterministic plan>` must
emit byte-identical worker prompts to `gen_prompt.py` with no plan, for every polymer
class and every stage. This protects the fixed-seed REVISION_PARAMS validation runs,
which depend on the deterministic path never changing.

The guarantee holds structurally because make_deterministic_plan.py snapshots only
class keys that already exist, with their existing values, and gen_prompt applies them
as {**cls, **decided_params} — an identity overlay. This test enforces it empirically.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())
CLASSES = sorted(RULES["classes"].keys())
# NB: "born" was removed from the pipeline (2026-06-21, PCFF+PPPM virial incompatibility);
# gen_prompt now errors on --stage born by design, so it is intentionally absent here.
STAGES = ["build", "equil", "tg", "deform", "murnaghan",
          "analyze-tg", "equil-check", "analyze-bm", "run-summary"]

GEN_PROMPT = REPO_ROOT / "scripts" / "gen_prompt.py"
MAKE_PLAN = REPO_ROOT / "scripts" / "make_deterministic_plan.py"


def _run(cmd):
    r = subprocess.run([sys.executable, *cmd], capture_output=True, text=True)
    assert r.returncode == 0, f"command failed: {cmd}\n{r.stderr}"
    return r.stdout


@pytest.fixture(scope="module")
def plan_files(tmp_path_factory):
    """Generate one deterministic run_plan.json per class."""
    d = tmp_path_factory.mktemp("plans")
    paths = {}
    for cls in CLASSES:
        out = d / f"{cls}.json"
        _run([str(MAKE_PLAN), "--run_name", f"REPRO_{cls}",
              "--polymer_class", cls, "--out", str(out)])
        paths[cls] = out
    return paths


@pytest.mark.parametrize("cls", CLASSES)
@pytest.mark.parametrize("stage", STAGES)
def test_deterministic_plan_matches_no_plan(cls, stage, plan_files):
    base = ["--stage", stage, "--run_name", f"REPRO_{cls}", "--polymer_class", cls]
    no_plan = _run([str(GEN_PROMPT), *base])
    with_plan = _run([str(GEN_PROMPT), *base, "--plan", str(plan_files[cls])])
    assert with_plan == no_plan, (
        f"deterministic plan changed {stage} output for {cls} — "
        f"reproducibility guard violated")


@pytest.mark.parametrize("cls,stage,extra_args", [
    # equil-check: uses npt_prod_log path
    ("PACR", "equil-check", [
        "--npt_prod_log", "/tmp/x/09_npt_prod300.log",
        "--npt_prod_dump", "/tmp/x/09_npt_prod300.dump",
        "--data_path", "/tmp/x/09_npt_prod300_out.data",
    ]),
    # analyze-bm (glassy, born path): born args non-null
    ("PACR", "analyze-bm", [
        "--born_log", "/tmp/x/08_nvt_born.log",
        "--born_matrix", "/tmp/x/born_matrix.dat", "--born_n_atoms", "2904",
        "--npt_prod_log", "/tmp/x/09_npt_prod300.log",
        "--is_glassy", "true",
    ]),
    # analyze-bm (rubbery, Murnaghan path): murnaghan_logs non-null
    ("PHYC", "analyze-bm", [
        "--murnaghan_logs", '["/tmp/x/bm_P1.log", "/tmp/x/bm_P100.log"]',
        "--npt_prod_log", "/tmp/x/09_npt_prod300.log",
        "--is_glassy", "false",
    ]),
    # run-summary: smiles + ff + quality
    ("PSTR", "run-summary", [
        "--smiles", "*CC(c1ccccc1)*", "--ff", "pcff",
        "--tg_fit_quality", "EXCELLENT", "--d05", "PASS",
    ]),
])
def test_reproducible_with_production_args(cls, stage, extra_args, plan_files):
    """The identity must hold under the orchestrator's REAL arg set, not just minimal
    args — each stage is invoked with the args the orchestrator actually passes."""
    base = ["--stage", stage, "--run_name", f"REPRO_{cls}", "--polymer_class", cls]
    prod = base + extra_args
    no_plan = _run([str(GEN_PROMPT), *prod])
    with_plan = _run([str(GEN_PROMPT), *prod, "--plan", str(plan_files[cls])])
    assert with_plan == no_plan, f"production-args reproducibility violated for {cls}/{stage}"


def test_decided_params_subset_of_class_entry(plan_files):
    """Every decided_param must be a key already in the class entry with the same
    value — the structural reason the overlay is an identity.

    COMPUTED_KEYS are the exception: they are not raw class-entry fields but are
    derived from class-entry values. gen_prompt.py reads them from cls (plan overlay)
    and produces the same output as its own fallback computation, so the identity still
    holds empirically (verified by test_deterministic_plan_matches_no_plan).
    """
    COMPUTED_KEYS = {
        "T_workflow_K",  # derived: 300.0 if experimental_tg_K<300 else T_equil_K
        "dsc_equiv_rate_K_per_ns",  # derived constant (10 K/min DSC target); class override optional
    }
    for cls, path in plan_files.items():
        plan = json.loads(Path(path).read_text())
        entry = RULES["classes"][cls]
        for k, v in plan["decided_params"].items():
            if k in COMPUTED_KEYS:
                continue
            assert k in entry, f"{cls}: decided_param '{k}' absent from class entry"
            assert entry[k] == v, f"{cls}: decided_param '{k}' value diverges from rules"
