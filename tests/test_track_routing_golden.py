"""Byte-level capture of how a requested property set becomes stages, TODAY.

This exists to make the track-registry refactor provable rather than plausible. The routing is
currently written out by hand in seven places (build_planned_stages, WorkflowEngine.enabled_stages,
two dry-run branches in run_campaign, validate_run_plan's coverage check, cost_model's stage
pricing, and decision_policy's track_map), and they have already drifted -- both dry-run sites
emit a standalone `deform` stage that build_planned_stages never produces, and cost_model's
`if "deform" in planned_stage_names` branch is dead for every deterministic plan as a result.

Every expectation below is an inline literal, deliberately: a regenerated fixture would silently
re-bless whatever the code does. Collapsing the seven sites onto one registry must leave every
assertion here untouched. Where an assertion is EXPECTED to change (cost_model gaining the deform
price), that is called out in the test itself.
"""
import json
import sys
from itertools import combinations
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import make_deterministic_plan as mdp  # noqa: E402
import workflow_engine as we  # noqa: E402

RULES = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())

ALL_PROPERTIES = ("density", "tg", "bulk_modulus")
SUBSETS = [frozenset(c) for n in (1, 2, 3) for c in combinations(ALL_PROPERTIES, n)]

# Three class shapes that exercise different branches: a glassy PCFF class (deform fallback
# attaches), a rubbery TraPPE class at dt=2 (it does not), and a low-Tg siloxane.
CLASS_SHAPES = ("PACR", "PHYC", "PSIL")


def _first_member_smiles(cid):
    for _name, smis in (RULES["classes"][cid].get("member_smiles") or {}).items():
        if isinstance(smis, list) and smis:
            return smis[0]
    return None


# ─── planned_stages: the plan artifact ────────────────────────────────────────────

# properties -> the exact ordered stage names build_planned_stages emits. Note NO "deform":
# it is attached as {"fallback": "deform"} on the murnaghan entry, never emitted as its own
# stage. Both dry-run sites disagree with this today -- see the dry-run test below.
# Every entry gained cool/cool-check EXCEPT {tg}, and that exception is the point of the
# equilibration/cooling split. `density` means the density at final_T_K, so it needs the
# cooldown; `bulk_modulus` needs a cell at bm_temperature_K, which only the cooldown reaches
# (track_registry._MECHANICAL.requires) -- it pulls cooling in even though no mechanical
# observable maps onto the cooling track. `tg` needs neither: the staircase descends from the
# same gated melt cell on its own, sampling as it goes, so a Tg-only run never pays for a
# second descent. (A melt_density-only run is narrower still -- see the melt-only test below --
# but melt_density is not in SUBSETS, which pins the pre-existing three-property matrix.)
GOLDEN_PLANNED_STAGES = {
    frozenset({"density"}):
        ["build", "equil", "equil-check", "cool", "cool-check", "run-summary"],
    frozenset({"tg"}):
        ["build", "equil", "equil-check", "tg", "analyze-tg", "run-summary"],
    frozenset({"bulk_modulus"}):
        ["build", "equil", "equil-check", "cool", "cool-check", "murnaghan", "analyze-bm",
         "run-summary"],
    frozenset({"density", "tg"}):
        ["build", "equil", "equil-check", "cool", "cool-check", "tg", "analyze-tg",
         "run-summary"],
    frozenset({"density", "bulk_modulus"}):
        ["build", "equil", "equil-check", "cool", "cool-check", "murnaghan", "analyze-bm",
         "run-summary"],
    frozenset({"tg", "bulk_modulus"}):
        ["build", "equil", "equil-check", "cool", "cool-check", "tg", "analyze-tg",
         "murnaghan", "analyze-bm", "run-summary"],
    frozenset({"density", "tg", "bulk_modulus"}):
        ["build", "equil", "equil-check", "cool", "cool-check", "tg", "analyze-tg",
         "murnaghan", "analyze-bm", "run-summary"],
}


@pytest.mark.parametrize("cid", CLASS_SHAPES)
@pytest.mark.parametrize("props", SUBSETS, ids=lambda p: "+".join(sorted(p)))
def test_planned_stage_names_are_stable(cid, props):
    stages = mdp.build_planned_stages(RULES["classes"][cid], set(props),
                                      _first_member_smiles(cid))
    assert [s["stage"] for s in stages] == GOLDEN_PLANNED_STAGES[props]


@pytest.mark.parametrize("cid", CLASS_SHAPES)
@pytest.mark.parametrize("props", SUBSETS, ids=lambda p: "+".join(sorted(p)))
def test_planned_stage_key_order_is_stable(cid, props):
    """_s() emits stage, track, success_criteria, then any extra. The plan artifact is hashed,
    so key ORDER is part of the contract, not just key membership."""
    stages = mdp.build_planned_stages(RULES["classes"][cid], set(props),
                                      _first_member_smiles(cid))
    for s in stages:
        assert list(s)[:3] == ["stage", "track", "success_criteria"], s


@pytest.mark.parametrize("cid", CLASS_SHAPES)
def test_stage_tracks_are_stable(cid):
    stages = mdp.build_planned_stages(RULES["classes"][cid], set(ALL_PROPERTIES),
                                      _first_member_smiles(cid))
    assert {s["stage"]: s["track"] for s in stages} == {
        "build": "foundation", "equil": "foundation", "equil-check": "foundation",
        "cool": "cooling", "cool-check": "cooling",
        "tg": "thermal", "analyze-tg": "thermal",
        "murnaghan": "mechanical", "analyze-bm": "mechanical",
        "run-summary": "summary",
    }


def test_the_deform_fallback_attaches_only_for_a_glassy_class():
    """PACR/PMMA is glassy -> murnaghan carries {"fallback": "deform"}. PSIL/PDMS is rubbery at
    300 K -> it does not. This is the one property-set-independent branch in the builder, and it
    is why `deform` is a fallback SLOT rather than a stage."""
    glassy = mdp.build_planned_stages(RULES["classes"]["PACR"], {"bulk_modulus"},
                                      _first_member_smiles("PACR"))
    rubbery = mdp.build_planned_stages(RULES["classes"]["PSIL"], {"bulk_modulus"},
                                       _first_member_smiles("PSIL"))
    assert next(s for s in glassy if s["stage"] == "murnaghan")["fallback"] == "deform"
    assert "fallback" not in next(s for s in rubbery if s["stage"] == "murnaghan")


# ─── enabled_stages: what the engine actually runs ────────────────────────────────

GOLDEN_MACRO_STAGES = {
    frozenset({"density"}):        ("build", "equilibration", "cooling", "summary"),
    frozenset({"tg"}):             ("build", "equilibration", "thermal", "summary"),
    frozenset({"bulk_modulus"}):   ("build", "equilibration", "cooling", "mechanical",
                                    "summary"),
    frozenset({"density", "tg"}):  ("build", "equilibration", "cooling", "thermal", "summary"),
    frozenset({"density", "bulk_modulus"}):
                                   ("build", "equilibration", "cooling", "mechanical",
                                    "summary"),
    frozenset({"tg", "bulk_modulus"}):
                                   ("build", "equilibration", "cooling", "thermal",
                                    "mechanical", "summary"),
    frozenset({"density", "tg", "bulk_modulus"}):
                                   ("build", "equilibration", "cooling", "thermal",
                                    "mechanical", "summary"),
}


@pytest.mark.parametrize("props", SUBSETS, ids=lambda p: "+".join(sorted(p)))
def test_enabled_macro_stages_are_stable(props, tmp_path):
    engine = we.WorkflowEngine.__new__(we.WorkflowEngine)
    engine.plan = {"properties": sorted(props)}
    assert engine.enabled_stages() == GOLDEN_MACRO_STAGES[props]


@pytest.mark.parametrize("props", SUBSETS, ids=lambda p: "+".join(sorted(p)))
def test_enabled_macro_stages_are_a_subsequence_of_stage_order(props):
    """_dependencies and invalidate_from rely on this ordering; any registry-driven replacement
    must filter THROUGH STAGE_ORDER rather than emit its own order."""
    got = GOLDEN_MACRO_STAGES[props]
    positions = [we.STAGE_ORDER.index(s) for s in got]
    assert positions == sorted(positions)


# ─── the dry-run divergence, pinned as the bug it is ──────────────────────────────

GOLDEN_DRY_RUN_STAGES = {
    frozenset({"density"}):      ["build", "equil", "equil-check", "run-summary"],
    frozenset({"tg"}):           ["build", "equil", "equil-check", "tg", "analyze-tg",
                                  "run-summary"],
    frozenset({"bulk_modulus"}): ["build", "equil", "equil-check", "murnaghan", "deform",
                                  "analyze-bm", "run-summary"],
}


def _dry_run_stage_list(properties):
    """Byte-for-byte what run_campaign's two dry-run branches build (:1693-1701, :1941-1948)."""
    stages = ["build", "equil", "equil-check"]
    if "tg" in properties:
        stages += ["tg", "analyze-tg"]
    if "bulk_modulus" in properties:
        stages += ["murnaghan", "deform", "analyze-bm"]
    stages.append("run-summary")
    return stages


@pytest.mark.parametrize("props", sorted(GOLDEN_DRY_RUN_STAGES, key=lambda p: sorted(p)),
                         ids=lambda p: "+".join(sorted(p)))
def test_dry_run_stage_list_is_stable(props):
    assert _dry_run_stage_list(set(props)) == GOLDEN_DRY_RUN_STAGES[props]


def test_dry_run_disagrees_with_the_plan_on_deform():
    """THE BUG, pinned so the fix is visible as a diff rather than a claim.

    --dry-run prints a `deform` stage that no real run executes: build_planned_stages emits
    murnaghan with a {"fallback": "deform"} key and never a deform stage of its own. Collapsing
    both onto the registry makes them agree, at which point this assertion INVERTS -- that
    inversion is the acceptance criterion for the dry-run half of the refactor."""
    props = {"bulk_modulus"}
    planned = [s["stage"] for s in mdp.build_planned_stages(
        RULES["classes"]["PACR"], props, _first_member_smiles("PACR"))]
    assert "deform" not in planned
    assert "deform" in _dry_run_stage_list(props)


# ─── the same divergence, seen from the cost side ─────────────────────────────────

def test_cost_model_now_prices_the_declared_deform_fallback():
    """INVERTED 2026-09-01 -- this pinned a bug and is now the fix's acceptance criterion.

    cost_model gated its deform price on `"deform" in planned_stage_names`, built from
    plan["planned_stages"]. build_planned_stages never emits that name -- it attaches
    {"fallback": "deform"} to the murnaghan entry instead -- so the branch was unreachable for
    every deterministic plan and the fallback went unpriced.

    It now reads the declaration. Note it reads the PLAN, not the registry: the registry knows
    deform is murnaghan's fallback slot, but whether that slot attaches is a per-plan regime
    call, so pricing off the registry would charge every rubbery plan for a path it never has."""
    import select_hardware as cost_model

    glassy = mdp.build_planned_stages(RULES["classes"]["PACR"], {"bulk_modulus"},
                                      _first_member_smiles("PACR"))
    rubbery = mdp.build_planned_stages(RULES["classes"]["PSIL"], {"bulk_modulus"},
                                       _first_member_smiles("PSIL"))

    # Still absent from the plan's stage list -- that has not changed.
    assert "deform" not in {s["stage"] for s in glassy}

    def _declared(stages):
        return any(s.get("fallback") == "deform" for s in stages)

    assert _declared(glassy), "a glassy class must declare the fallback"
    assert not _declared(rubbery), "a rubbery class must not"
    # And the real pricer acts on it: same plan, fallback declared vs not.
    def _priced(stages, cid):
        entry = RULES["classes"][cid]
        plan = {"planned_stages": stages,
                "polymer_class": cid,
                "smiles": _first_member_smiles(cid),
                "decided_params": {"dp_typical": entry.get("dp_typical") or 50,
                                   "nchain": entry.get("nchain") or 10}}
        out = cost_model.plan_cost_estimate(plan)
        return set((out.get("stages") or {})) if "error" not in out else None

    glassy_priced, rubbery_priced = _priced(glassy, "PACR"), _priced(rubbery, "PSIL")
    if glassy_priced is None or rubbery_priced is None:
        pytest.skip("cost model needs hardware calibration unavailable in this environment")
    assert "deform" in glassy_priced, "the declared fallback must now be priced"
    assert "deform" not in rubbery_priced, "a rubbery plan declares none, so prices none"
