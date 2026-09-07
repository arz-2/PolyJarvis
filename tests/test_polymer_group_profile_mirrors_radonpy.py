"""guides/polymer_group_profile.json must stay a MIRROR of RadonPy, never a second taxonomy.

The whole reason `classify` calls poly.polyinfo_classifier instead of reimplementing it is
that a parallel SMARTS table drifts, and a drifted class label silently rewrites the entire
protocol (charge_method, electrostatics, cutoff_A, dt_fs, T_equil_K, the experimental
bands). The profile file exists only to LOCATE groups -- which family matched, and whether
it sits on the backbone -- so this test re-derives it straight from RadonPy and asserts the
on-disk copy is identical.

The derivation runs through tools/class_profile/gen_polymer_group_profile.py --stdout in
the mol-builder conda env, NOT by importing radonpy here: this test interpreter is
mcp-servers/.venv (py3.12, no RadonPy), so importing it directly would make the single most
important assertion in this file silently skip.

Structural assertions below it need no RadonPy and run in the default suite.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILE = REPO_ROOT / "guides" / "polymer_group_profile.json"
GENERATOR = REPO_ROOT / "tools" / "class_profile" / "gen_polymer_group_profile.py"

sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))
from mol_python import run_in_mol_env  # noqa: E402

ON_DISK = json.loads(PROFILE.read_text())


@pytest.mark.requires_binaries
def test_profile_groups_match_radonpy_source_exactly():
    r = run_in_mol_env(script_path=GENERATOR, args=["--stdout"], env="mol-builder", timeout=120)
    assert r.returncode == 0, f"generator failed: {r.stderr[:2000]}"
    derived = json.loads(r.stdout)["groups"]
    assert ON_DISK["groups"] == derived, (
        "guides/polymer_group_profile.json has drifted from poly.polyinfo_classifier.\n"
        "Regenerate it rather than editing by hand:\n"
        "  <mol-builder python> tools/class_profile/gen_polymer_group_profile.py --repo-root .\n"
        "A hand-edit here turns a mirror into a competing taxonomy, which is exactly what "
        "this file must never become."
    )


def test_profile_covers_every_class_in_polymer_rules():
    rules = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())["classes"]
    assert set(ON_DISK["groups"]) == set(rules), (
        "the profile and polymer_rules.json disagree about which classes exist: "
        f"profile-only={set(ON_DISK['groups']) - set(rules)}, "
        f"rules-only={set(rules) - set(ON_DISK['groups'])}"
    )


def test_priority_ranks_are_a_total_order():
    groups = ON_DISK["groups"]
    assert sorted(v["priority_rank"] for v in groups.values()) == list(range(1, len(groups) + 1))


def test_priority_ladder_resolves_the_known_co_occurring_pairs():
    """Real polymers carry several of these groups at once; the ladder is what picks one.

    Each pair below is a molecule this repo actually runs, and a reordering would silently
    reroute it to a different protocol -- BPA-PC has both a carbonate and an ester pattern,
    Kapton both an imide and an amide, PSU and PEEK both an aryl ether and their own group.
    """
    rank = {k: v["priority_rank"] for k, v in ON_DISK["groups"].items()}
    assert rank["PCBN"] < rank["PEST"], "carbonate must outrank ester (BPA-PC)"
    assert rank["PIMD"] < rank["PAMD"], "imide must outrank amide (Kapton)"
    assert rank["PURT"] < rank["PAMD"], "urethane must outrank amide (TPU)"
    assert rank["PSFO"] < rank["POXI"], "sulfone must outrank ether (PSU)"
    assert rank["PKTN"] < rank["POXI"], "ketone must outrank ether (PEEK)"


def test_every_tier1_family_carries_smarts_and_element_count_families_carry_none():
    """The tier field is what _group_locations routes on: tier 1 is independently
    re-matchable against the 2-mer, tier 2 and element_count are not (their SMARTS need the
    [14C] mainchain tagging polyinfo_classifier applies internally). A family mislabelled
    here would either lose its pendant detection or generate noise hits."""
    for cls, rule in ON_DISK["groups"].items():
        if rule["tier"] == 1:
            assert rule["smarts"], f"{cls}: tier 1 but no SMARTS"
            assert rule["smarts_var"], f"{cls}: tier 1 but no source variable"
        elif rule["tier"] == "element_count":
            assert rule["smarts"] is None, f"{cls}: element-count tier must carry no SMARTS"
    assert {c for c, r in ON_DISK["groups"].items() if r["tier"] == 2} == {"PSTR", "PACR"}
