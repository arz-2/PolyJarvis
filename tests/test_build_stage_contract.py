"""The build stage must never invent the cell it builds.

Two halves of one guarantee, and both are needed: the planning layer resolves
dp_typical/nchain from the SMILES, and the parameter resolver refuses to substitute a
default when it did not. Before 2026-09-02 neither held. guides/polymer_rules.json's
per-class dp_typical/nchain had been removed (every cell is sized per-SMILES now), but
SNAPSHOT_KEYS can only copy keys the class entry HAS, so a scaffold run_plan.json carried
no cell at all -- and stage_params quietly built 50 chains of DP 50 from its own fallbacks.
Nothing reported it: validate_run_plan's D-04 floor check returns clean on `dp is None`, and
`run_campaign.py --plan` runs no plan validation of its own.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from make_deterministic_plan import make_plan  # noqa: E402
from run_campaign import _base_args  # noqa: E402
from stage_params import resolve_stage_params  # noqa: E402

MAKE_PLAN = REPO_ROOT / "orchestration" / "scripts" / "make_deterministic_plan.py"
RULES = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())

PLA = "*OC(=O)C(*)C"          # PEST member, repeat mass 72.06 g/mol
PS = "*CC(c1ccccc1)*"         # PSTR member, repeat mass 104.15 g/mol


def _args(polymer_class="PEST", smiles=PLA):
    args = _base_args("BUILD_CONTRACT", polymer_class, "/tmp/plan.json")
    args.smiles = smiles
    return args


def _sized_cls(polymer_class="PEST", **overrides):
    """A class entry as apply_plan would hand it over: rules plus decided_params.

    decided_params carries preferred_ff (D-01's resolved field) -- the class entry itself only
    holds ff_accuracy_prior, the literature prior, which the builder never reads.
    """
    cls = dict(RULES["classes"][polymer_class])
    cls.update({"dp_typical": 70, "nchain": 10,
                "preferred_ff": cls["ff_accuracy_prior"]})
    cls.update(overrides)
    return cls


# ─── the resolver refuses to default ──────────────────────────────────────────────────

@pytest.mark.parametrize("missing", ["dp_typical", "nchain"])
def test_an_unsized_cell_is_refused_not_defaulted(missing):
    """The exact regression: cls.get('dp_typical', 50) / cls.get('nchain', 10) used to fire
    silently here and hand EMC a cell nobody chose."""
    cls = _sized_cls()
    del cls[missing]
    with pytest.raises(SystemExit, match=f"{missing} is unresolved"):
        resolve_stage_params("build", _args(), cls)


@pytest.mark.parametrize("missing,default_that_was_invented", [
    ("charge_method", "am1bcc"),     # a RadonPy method; EMC charges come from the field's
                                     # own bond-increment table, so recording it was fiction
    ("preferred_ff", "gaff2_mod"),   # not an EMC field name at all -- it reached the
                                     # builder only to die as "Unknown field_override"
])
def test_an_undecided_forcefield_or_charge_model_is_refused(missing, default_that_was_invented):
    cls = _sized_cls()
    del cls[missing]
    with pytest.raises(SystemExit, match=f"{missing} is unresolved"):
        resolve_stage_params("build", _args(), cls)


def test_a_fully_decided_plan_resolves_without_raising():
    p = resolve_stage_params("build", _args(), _sized_cls())
    assert (p["dp"], p["nchain"]) == (70, 10)
    assert p["preferred_ff"] == "pcff"
    assert p["charge_method"] == "bond-increment"


def test_the_cli_still_outranks_the_plan():
    """Precedence is unchanged by the fail-loud guard: an explicit --dp/--nchain wins."""
    args = _args()
    args.dp, args.nchain = 33, 44
    p = resolve_stage_params("build", args, _sized_cls())
    assert (p["dp"], p["nchain"]) == (33, 44)


def test_dp_zero_is_honored_rather_than_falling_through():
    """The old `args.dp or cls.get(...)` treated 0 as absent. `is not None` does not -- and a
    zero-chain or zero-DP cell should be refused downstream by EMC, loudly, not silently
    replaced by a default."""
    args = _args()
    args.dp = 0
    assert resolve_stage_params("build", args, _sized_cls())["dp"] == 0


# ─── the planning layer supplies the cell ─────────────────────────────────────────────

def test_a_scaffold_plan_carries_a_cell_sized_from_its_own_smiles():
    plan = make_plan("BUILD_CONTRACT", "PEST", PLA, {"density"})
    dp = plan["decided_params"]
    # DP = ceil(SYSTEM_MW_FLOOR_GMOL / (nchain * M_repeat)) = ceil(50000 / (10 * 72.06))
    assert dp["nchain"] == 10
    assert dp["dp_typical"] == 70
    assert any("D-04_system_size resolved" in a for a in plan["assumptions"])


def test_two_members_of_one_class_get_different_cells():
    """The reason per-class dp_typical was removed: repeat mass varies up to 3x WITHIN a
    class, so one number cannot be right for its own members."""
    pla = make_plan("A", "PEST", PLA, {"density"})["decided_params"]["dp_typical"]
    pet = make_plan("B", "PEST", "*OCCOC(=O)c1ccc(C(*)=O)cc1", {"density"})["decided_params"]["dp_typical"]
    assert pla != pet


def test_a_plan_with_no_smiles_says_so_instead_of_sizing_blind():
    plan = make_plan("BUILD_CONTRACT", "PEST", None, {"density"})
    assert "dp_typical" not in plan["decided_params"]
    assert any("D-04_system_size UNRESOLVED" in a for a in plan["assumptions"])


def test_an_unsized_plan_is_refused_at_execution_rather_than_silently_built():
    """End to end: the two halves meet. A plan with no SMILES produces no cell, and the
    resolver then refuses it -- which is the whole point of removing the 50/10 fallbacks."""
    plan = make_plan("BUILD_CONTRACT", "PEST", None, {"density"})
    cls = {**RULES["classes"]["PEST"], **plan["decided_params"]}
    with pytest.raises(SystemExit, match="dp_typical is unresolved"):
        resolve_stage_params("build", _args(smiles=None), cls)


def test_the_generated_plan_artifact_is_sized_too():
    """Through the real CLI, not just the importable function -- the scaffold path is what
    `run-plan` emits on a cache miss and it is what run_campaign is handed."""
    r = subprocess.run(
        [sys.executable, str(MAKE_PLAN), "run-plan", "--run_name", "BUILD_CONTRACT",
         "--polymer_class", "PSTR", "--smiles", PS, "--properties", "density", "--out", "-"],
        capture_output=True, text=True, check=True)
    plan = json.loads(r.stdout)
    assert plan["plan_mode"] == "scaffold"
    assert plan["decided_params"]["dp_typical"] == 49   # ceil(50000 / (10 * 104.15))
    assert plan["decided_params"]["nchain"] == 10
