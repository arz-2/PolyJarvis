"""merge_arm_summaries.py: combining two split arms' run_summary.json into one report.

Never guesses which arm's value wins -- these tests pin the three refusal cases (molecule
mismatch, conflicting duplicate value, an --expect'd property missing from both) and the
one clean-merge shape a caller actually needs.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from merge_arm_summaries import merge_summaries  # noqa: E402


def _summary(name, dp, n_chains, results, smiles="*CC(C)(C(=O)OC)*", polymer_class="PACR",
            ff="pcff"):
    return {
        "run": {"name": name, "smiles": smiles, "polymer_class": polymer_class, "ff": ff,
               "dp": dp, "n_chains": n_chains},
        "decisions": {"D-04_system_size": f"DP={dp}, {n_chains} chains"},
        "results": results,
        "convergence": {"verdict": "PASS"},
        "structural_checks": {"rg_cv": 0.1},
        "artifacts": {f"artifact_{name}": f"raw/{name}.json"},
        "artifacts_missing": [],
        "provenance": {"git_commit": "abc123"},
    }


def test_clean_merge_of_disjoint_properties():
    tg_arm = _summary("PMMA1_tg", 20, 10, {"tg": {"value_K": 378.0}, "density": {"value_g_cm3": 1.18}})
    bm_arm = _summary("PMMA1_bm", 125, 10, {"bulk_modulus": {"value_GPa": 4.2}})
    merged = merge_summaries(tg_arm, bm_arm)
    assert merged["results"]["tg"]["value_K"] == 378.0
    assert merged["results"]["density"]["value_g_cm3"] == 1.18
    assert merged["results"]["bulk_modulus"]["value_GPa"] == 4.2


def test_arms_block_records_both_dps():
    tg_arm = _summary("PMMA1_tg", 20, 10, {"tg": {"value_K": 378.0}})
    bm_arm = _summary("PMMA1_bm", 125, 10, {"bulk_modulus": {"value_GPa": 4.2}})
    merged = merge_summaries(tg_arm, bm_arm)
    assert merged["arms"]["a"] == {"run_name": "PMMA1_tg", "dp": 20, "n_chains": 10}
    assert merged["arms"]["b"] == {"run_name": "PMMA1_bm", "dp": 125, "n_chains": 10}


def test_merged_run_block_does_not_misattribute_an_arm_specific_dp():
    """A K measured at DP=125 must never be reported under run.dp=20 (the tg arm's own
    size) -- run.dp/n_chains/name are arm-specific and must be nulled in the merge, not
    silently inherited from whichever arm happened to be passed first."""
    tg_arm = _summary("PMMA1_tg", 20, 10, {"tg": {"value_K": 378.0}})
    bm_arm = _summary("PMMA1_bm", 125, 10, {"bulk_modulus": {"value_GPa": 4.2}})
    merged = merge_summaries(tg_arm, bm_arm)
    assert merged["run"]["dp"] is None
    assert merged["run"]["n_chains"] is None
    assert merged["run"]["name"] is None
    # the real per-arm sizes must still be recoverable, just not under run.*
    assert merged["arms"]["a"]["dp"] == 20 and merged["arms"]["b"]["dp"] == 125


def test_refuses_on_forcefield_mismatch():
    tg_arm = _summary("PMMA1_tg", 20, 10, {"tg": {"value_K": 378.0}}, ff="pcff")
    bm_arm = _summary("PMMA1_bm", 125, 10, {"bulk_modulus": {"value_GPa": 4.2}}, ff="opls")
    with pytest.raises(ValueError, match="run.ff disagrees"):
        merge_summaries(tg_arm, bm_arm)


def test_refuses_on_molecule_mismatch():
    tg_arm = _summary("PMMA1_tg", 20, 10, {"tg": {"value_K": 378.0}}, polymer_class="PACR")
    bm_arm = _summary("PS_bm", 125, 10, {"bulk_modulus": {"value_GPa": 4.2}}, polymer_class="PSTR")
    with pytest.raises(ValueError, match="disagree on run.polymer_class"):
        merge_summaries(tg_arm, bm_arm)


def test_refuses_on_conflicting_duplicate_value():
    tg_arm = _summary("PMMA1_tg", 20, 10, {"tg": {"value_K": 378.0}})
    bm_arm = _summary("PMMA1_bm", 125, 10, {"tg": {"value_K": 400.0}, "bulk_modulus": {"value_GPa": 4.2}})
    with pytest.raises(ValueError, match="disagrees between arms"):
        merge_summaries(tg_arm, bm_arm)


def test_agreeing_duplicate_value_is_not_a_conflict():
    tg_arm = _summary("PMMA1_tg", 20, 10, {"tg": {"value_K": 378.0}})
    bm_arm = _summary("PMMA1_bm", 125, 10, {"tg": {"value_K": 378.0}, "bulk_modulus": {"value_GPa": 4.2}})
    merged = merge_summaries(tg_arm, bm_arm)
    assert merged["results"]["tg"]["value_K"] == 378.0


def test_refuses_when_an_expected_property_is_missing_from_both():
    tg_arm = _summary("PMMA1_tg", 20, 10, {"tg": {"value_K": 378.0}})
    bm_arm = _summary("PMMA1_bm", 125, 10, {"bulk_modulus": {"value_GPa": 4.2}})
    with pytest.raises(ValueError, match="missing from both"):
        merge_summaries(tg_arm, bm_arm, expect={"tg", "bulk_modulus", "density"})


def test_expect_satisfied_across_both_arms_passes():
    tg_arm = _summary("PMMA1_tg", 20, 10, {"tg": {"value_K": 378.0}})
    bm_arm = _summary("PMMA1_bm", 125, 10, {"bulk_modulus": {"value_GPa": 4.2}})
    merged = merge_summaries(tg_arm, bm_arm, expect={"tg", "bulk_modulus"})
    assert set(merged["results"]) == {"tg", "bulk_modulus"}


def test_artifacts_and_artifacts_missing_are_unioned():
    tg_arm = _summary("PMMA1_tg", 20, 10, {"tg": {"value_K": 378.0}})
    tg_arm["artifacts_missing"] = [{"file": "bulk_modulus.json", "found_in": None}]
    bm_arm = _summary("PMMA1_bm", 125, 10, {"bulk_modulus": {"value_GPa": 4.2}})
    merged = merge_summaries(tg_arm, bm_arm)
    assert set(merged["artifacts"]) == {"artifact_PMMA1_tg", "artifact_PMMA1_bm"}
    assert {"file": "bulk_modulus.json", "found_in": None} in merged["artifacts_missing"]
