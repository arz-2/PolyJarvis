"""D-01_ff selection, and the vendored record of the installed field tree.

Two things these lock, both of which are easy to quietly undo:
  - the archive prior must stay REPORTED. Its backtest finds extrapolation
    anti-correlated with error, so promoting it to a ranking input would be a
    regression dressed as an improvement.
  - a blocking provenance flag must remain acknowledgeable. Several classes have
    exactly one admissible route; making the flag a veto would make them unrunnable.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import forcefield as sf  # noqa: E402
from forcefield import LINEAGE  # noqa: E402
from validate_run_plan import _forcefield_findings  # noqa: E402

EMC = Path.home() / "emc"
needs_emc = pytest.mark.skipif(not EMC.exists(), reason="no installed EMC field tree")


# --- lineage ---------------------------------------------------------------------

def test_every_registered_field_has_a_lineage():
    """A field with no lineage would silently count as its own, inflating the spread."""
    missing = sorted(set(sf.FIELDS) - set(LINEAGE))
    assert not missing, f"fields missing from LINEAGE: {missing}"


def test_class2_members_share_one_lineage():
    """pcff/pcff_ore/compass are the same functional form and fitting lineage -- two of
    them agreeing is one piece of evidence, not two."""
    assert LINEAGE["pcff"] == LINEAGE["pcff_ore"] == LINEAGE["compass"]


def test_opls_and_class2_are_distinct_lineages():
    assert LINEAGE["opls/2024/opls-aa"] != LINEAGE["pcff"]


# --- case-insensitive default matching --------------------------------------------

def _fake_field(candidate=True):
    return {"candidate": candidate, "integrates": candidate, "types_smiles": candidate,
            "typing_error": None, "cell_dir": None}


def test_every_class_prior_is_a_canonical_field_name():
    """polymer_rules.json stored display casing ("GAFF2_mod", "Dreiding") against FIELDS'
    lowercase keys, so select_forcefield needed a case-insensitive rescue and
    ENUM_OVERRIDES["preferred_ff"] rejected 4 of the 6 values in real use. The values are now
    canonical at the source; pin that so neither workaround has to come back."""
    classes = sf.load_rules()["classes"]
    off = {cid: e.get("ff_accuracy_prior") for cid, e in classes.items()
           if e.get("ff_accuracy_prior") not in sf.FIELDS}
    assert not off, f"ff_accuracy_prior must be a forcefield.FIELDS key verbatim: {off}"


def test_class_prior_is_chosen_when_admissible(monkeypatch):
    """An admissible class prior is chosen at high confidence and proposes no override."""
    fake_cap = {"fields": {"gaff2_mod": _fake_field(), "gaff": _fake_field(),
                          "gaff2": _fake_field(), "dreiding": _fake_field()}}
    monkeypatch.setattr(sf, "assess_all", lambda *a, **k: fake_cap)

    result = sf.select_forcefield("PURA", "*NC(=O)N*")
    assert result["decision"]["choice"] == "gaff2_mod"
    assert result["decision"]["confidence"] == "high"
    assert result["decided_params_override"] == {}
    assert "'gaff2_mod'" in result["decision"]["evidence"][-1]["claim"]


# --- validator -------------------------------------------------------------------

def _plan(**kw):
    d = {"id": "D-01_ff", "choice": kw.get("choice", "pcff"),
         "admissible": kw.get("admissible", ["pcff"]),
         "provenance_flags": kw.get("flags", {})}
    return {"decisions": [d], "decided_params": {"preferred_ff": kw.get("dp", "pcff")},
            "uncertainties": kw.get("uncertainties", [])}


def test_choice_outside_the_measured_admissible_set_is_structural():
    f = _forcefield_findings(_plan(choice="opls/2024/opls-aa", dp="opls/2024/opls-aa"))
    assert [x["severity"] for x in f] == ["structural"]
    assert f[0]["check"] == "ff_not_admissible"


def test_empty_admissible_set_escalates():
    f = _forcefield_findings(_plan(choice=None, admissible=[], dp=None))
    assert any(x["check"] == "ff_no_admissible_field" for x in f)


def test_decided_params_must_match_the_choice():
    # hardware selection keys off decided_params.preferred_ff, so a mismatch silently
    # configures the run for a different field than the one that was chosen
    f = _forcefield_findings(_plan(choice="pcff", admissible=["pcff", "trappe-ua"],
                                   dp="trappe-ua"))
    assert any(x["check"] == "ff_choice_not_applied" for x in f)


def test_blocking_provenance_flag_must_be_acknowledged():
    f = _forcefield_findings(_plan(flags={"LOCAL_PATCH": 7}))
    assert any(x["check"] == "ff_provenance_unacknowledged" for x in f)


def test_acknowledged_provenance_flag_clears():
    """PSIL builds only because of a local patch -- the flag states the uncertainty,
    it does not veto the only field the class has."""
    f = _forcefield_findings(_plan(flags={"LOCAL_PATCH": 7},
                                   uncertainties=[{"name": "ff_parameter_provenance"}]))
    assert f == []


def test_advisory_only_flags_do_not_block():
    f = _forcefield_findings(_plan(flags={"AUTO_FALLBACK": 12}))
    assert f == []


def test_plan_without_a_d01_row_is_unaffected():
    """Plans predating this check must not start failing validation."""
    assert _forcefield_findings({"decisions": [{"id": "D-08_hardware"}]}) == []


# --- vendored field record -------------------------------------------------------

def test_manifest_lists_a_stock_baseline_for_every_patched_file():
    """Diffs alone are not enough: after a reinstall + --apply there is no .bak left to
    diff against, and --patched-rows would lose its reference."""
    m = sf.load_manifest()
    for field, spec in m["fields"].items():
        for basename, f in spec["files"].items():
            assert (REPO_ROOT / f["stock"]).exists(), f"{field}/{basename} has no baseline"
            assert (REPO_ROOT / f["patch"]).exists()
            assert f["sha256_stock"] != f["sha256_patched"]


@needs_emc
def test_verify_matches_the_installed_tree():
    r = sf.verify(sf.load_manifest())
    assert r["ok"], json.dumps(r, indent=2)


@needs_emc
def test_verify_detects_drift(tmp_path):
    m = sf.load_manifest()
    root = tmp_path / "emc" / "field" / "opls" / "2024"
    root.mkdir(parents=True)
    src = EMC / "field" / "opls" / "2024"
    for name in ("opls-aa.define", "opls-aa.top", "opls-aa.prm"):
        (root / name).write_bytes((src / name).read_bytes())
    (root / "opls-aa.prm").write_text((root / "opls-aa.prm").read_text() + "\n")
    assert not sf.verify(m, str(tmp_path / "emc"))["ok"]


@needs_emc
def test_patched_rows_reports_the_locally_authored_parameters():
    rows = sf.patched_rows(sf.load_manifest(), "opls/2024/opls-aa")
    assert rows["n_rows"] > 0
    assert "si4" in rows["typing_rules"]
    # the silanol terminal-cap torsions are the reason this record exists
    assert any(t[:1] == ["si4"] for t in rows["sections"].get("TORSION", []))
