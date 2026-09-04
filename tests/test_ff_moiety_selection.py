"""D-01's per-SMILES force-field resolution: the moiety screen and the EMC probe.

The screen NARROWS, a real EMC trial build DECIDES. These tests pin both halves plus the
measured numbers the screen rests on -- a rule that stops predicting fails here rather than
rotting quietly in guides/ff_moiety_rules.json.

Nothing here runs EMC: check_typing is monkeypatched, same pattern as test_select_forcefield.py.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import forcefield as sf                                  # noqa: E402
import make_deterministic_plan as mdp                     # noqa: E402
import scientific_control as sc                           # noqa: E402
from rules_common import load_rules                       # noqa: E402

RULES_PATH = REPO_ROOT / "guides" / "ff_moiety_rules.json"
SWEEP = REPO_ROOT / "docs" / "ff_coverage_sweep" / "arm0.jsonl"
MOIETY_RULES = json.loads(RULES_PATH.read_text())
rdkit = pytest.importorskip("rdkit", reason="moiety matching needs RDKit")
from rdkit import Chem, RDLogger                          # noqa: E402

RDLogger.DisableLog("rdApp.*")


# ─── the rules still measure what they claim ──────────────────────────────────────────

@pytest.fixture(scope="module")
def sweep():
    """(monomer_id -> mol, set of monomer_ids whose class-prior build failed)."""
    rows = [json.loads(line) for line in SWEEP.read_text().splitlines() if line.strip()]
    mols = {r["monomer_id"]: Chem.MolFromSmiles(r["smiles"]) for r in rows}
    return mols, {r["monomer_id"] for r in rows if not r["built"]}


@pytest.mark.parametrize("rule", MOIETY_RULES["moieties"], ids=lambda r: r["id"])
def test_each_rule_still_hits_its_recorded_precision(rule, sweep):
    mols, failed = sweep
    pat = Chem.MolFromSmarts(rule["smarts"])
    assert pat is not None, f"{rule['id']}: unparseable SMARTS {rule['smarts']!r}"
    matched = {mid for mid, m in mols.items() if m is not None and m.HasSubstructMatch(pat)}
    ev = rule["evidence"]
    assert len(matched) == ev["matches"], (
        f"{rule['id']} now matches {len(matched)} monomers, recorded {ev['matches']}")
    hits = len(matched & failed)
    assert hits == ev["failures"]
    assert round(hits / len(matched), 3) == ev["precision"]


def test_every_rule_blocks_every_registered_emc_field(sweep):
    """The measurement that shapes the resolver: these groups are not a PCFF problem. Every
    rule fails at or near 1.00 for all nine registered EMC fields, which is why a blocker
    means "probe the prior once, then refuse" and not "cascade through the alternatives"."""
    for rule in MOIETY_RULES["moieties"]:
        rates = {f: b["fail_rate"] for f, b in rule["blocks"].items()}
        assert len(rates) >= 9, f"{rule['id']}: only {len(rates)} fields measured"
        weak = {f: r for f, r in rates.items() if r < 0.9}
        assert not weak, f"{rule['id']}: {weak} now build often enough to be worth probing"


def test_the_rules_declare_their_own_coverage_gap():
    """No match is UNSCREENED, not cleared. If this ever reads as full coverage, the
    NOT MEASURED path in _coverage_claim stops being honest."""
    assert "77%" in MOIETY_RULES["_metadata"]["coverage_gap"]


# ─── the resolver ─────────────────────────────────────────────────────────────────────

_CLEAN = "*CC(*)c1ccccc1"            # polystyrene: matches no rule
_BLOCKED = "*C(C*)c1c(cccc1)C(=O)NC"  # PI94, a real measured carbonyl_adjacent_N failure


def test_no_blocker_keeps_the_prior_and_runs_no_probe(monkeypatch):
    monkeypatch.setattr(sf, "check_typing",
                        lambda *a, **k: pytest.fail("probed a SMILES with no blocker"))
    out = sf.select_by_moiety(_CLEAN, "pcff")
    assert out["field"] == "pcff"
    assert out["probed"] == []
    assert out["typed"] is None       # NOT True: nothing was measured
    assert out["blockers"] == []


def test_a_blocker_that_still_types_keeps_the_prior(monkeypatch):
    """3% of carbonyl_adjacent_N matches build anyway. The probe is what catches them, so a
    false positive costs one trial build and not a demotion off a DOI-backed field."""
    monkeypatch.setattr(sf, "check_typing", lambda *a, **k: {"types_smiles": True})
    out = sf.select_by_moiety(_BLOCKED, "pcff")
    assert out["field"] == "pcff"
    assert out["probed"] == ["pcff"]
    assert out["typed"] is True
    assert [b["id"] for b in out["blockers"]] == ["carbonyl_adjacent_N"]


def test_a_blocker_that_types_nowhere_refuses_rather_than_defaulting(monkeypatch):
    monkeypatch.setattr(sf, "check_typing", lambda *a, **k: {"types_smiles": False})
    out = sf.select_by_moiety(_BLOCKED, "pcff")
    assert out["field"] is None
    assert out["typed"] is False
    assert "no cascade applies" in out["reason"]


def test_probing_off_leaves_the_prior_explicitly_unverified():
    out = sf.select_by_moiety(_BLOCKED, "pcff", probe=False)
    assert out["field"] == "pcff"
    assert out["probed"] == []
    assert "unverified" in out["reason"]


def test_an_unavailable_screen_is_unscreened_not_clean(monkeypatch):
    monkeypatch.setattr(sf, "_match_moieties", lambda *a, **k: None)
    out = sf.select_by_moiety(_CLEAN, "pcff")
    assert out["unscreened"] is True
    assert out["field"] == "pcff"


def test_a_measured_blocker_removes_every_alternative_from_the_probe_order():
    blockers = sf._match_moieties(_BLOCKED)
    assert sf._ranked_candidates("pcff", blockers) == ["pcff"]


def test_ranking_prefers_the_prior_then_its_own_lineage():
    order = sf._ranked_candidates("pcff", [])
    assert order[0] == "pcff"
    same = [f for f in order[1:] if sf.LINEAGE[f] == "class2"]
    assert order[1:1 + len(same)] == same


def test_no_field_without_a_lammps_deck_can_be_selected():
    """script_generator.py emits class2/opls/trappe/dreiding decks with GAFF as the else
    branch. A CHARMM field has none, so it would silently run the GAFF deck."""
    assert "charmm/c36a" in sf.FIELDS
    assert "charmm/c36a" not in sf.RUNNABLE_FIELDS
    assert "charmm/c36a" not in sf._ranked_candidates("pcff", [])


# ─── what reaches the plan ────────────────────────────────────────────────────────────

def test_not_measured_survives_a_screen_that_found_nothing():
    """A screen passing is not a coverage measurement -- the rules miss 23% of failures --
    so D-01's parameter_coverage must keep the prefix the rationale gap list keys off."""
    claim, _ = mdp._coverage_claim("PSTR", "pcff", "pcff",
                                   {"probed": [], "blockers": []})
    assert claim.startswith("NOT MEASURED")
    assert "moiety screen ran" in claim


def test_a_real_probe_replaces_not_measured():
    claim, resolver = mdp._coverage_claim("PSTR", "pcff", "pcff", {"probed": ["pcff"]})
    assert claim.startswith("MEASURED")
    assert resolver == "forcefield.select_by_moiety"


def test_a_probe_that_typed_nothing_says_the_plan_must_not_build():
    claim, _ = mdp._coverage_claim("PSTR", "pcff", None, {"probed": ["pcff"]})
    assert "must not build" in claim


def test_a_departure_from_the_prior_carries_its_own_uncertainty():
    u = mdp._ff_prior_uncertainty("PURT", "pcff", "opls/2024/opls-aa", {"blockers": []})
    assert u["name"] == "ff_accuracy_prior_not_met"
    assert "ff_justification_doi does not cover" in u["detail"]
    assert mdp._ff_prior_uncertainty("PURT", "pcff", "pcff") is None


def test_no_admissible_field_is_a_dominant_uncertainty():
    u = mdp._ff_prior_uncertainty("PIMD", "pcff", None, {"blockers": [{"id": "nitro"}]})
    assert u["dominant"] is True
    assert "nitro" in u["detail"]


def test_a_demoted_plan_without_the_uncertainty_is_a_structural_finding():
    import validate_run_plan as vrp
    plan = {"polymer_class": "PSTR", "uncertainties": [],
            "decided_params": {"preferred_ff": "compass"},
            "decisions": [{"id": "D-01_ff", "choice": "compass"}]}
    checks = {f["check"] for f in vrp._forcefield_findings(plan)}
    assert "ff_prior_departure_unacknowledged" in checks
    plan["uncertainties"] = [{"name": "ff_accuracy_prior_not_met"}]
    checks = {f["check"] for f in vrp._forcefield_findings(plan)}
    assert "ff_prior_departure_unacknowledged" not in checks


def test_the_rules_file_is_hashed_into_the_build_stage():
    """Without this, editing a moiety rule invalidates no accepted build."""
    src = (REPO_ROOT / "orchestration" / "scripts" / "run_campaign.py").read_text()
    assert '"ff_moiety_rules.json"' in src


# ─── the override enum ────────────────────────────────────────────────────────────────

def test_every_class_prior_round_trips_through_validate_overrides():
    """The hand-written enum had "trappe" for "trappe-ua" and was lowercase-only, so 4 of the
    6 values in real use were rejected -- which any dynamic resolver hits immediately."""
    for cid, entry in load_rules()["classes"].items():
        sc.validate_overrides({"preferred_ff": entry["ff_accuracy_prior"]})


@pytest.mark.parametrize("value", ["trappe-ua", "gaff2_mod", "dreiding", "opls/2024/opls-ua"])
def test_real_field_names_are_accepted_as_overrides(value):
    sc.validate_overrides({"preferred_ff": value})


def test_a_field_with_no_deck_is_not_an_override():
    with pytest.raises(ValueError):
        sc.validate_overrides({"preferred_ff": "charmm/c36a"})


# ─── the CLI seam ─────────────────────────────────────────────────────────────────────

def test_match_moieties_batches_a_whole_list_in_one_subprocess(tmp_path):
    """A per-SMILES round trip through the conda seam is what made the 982-molecule sweep
    take minutes; the precision test above depends on this staying batched."""
    inp = tmp_path / "smiles.json"
    inp.write_text(json.dumps([_CLEAN, _BLOCKED, "not a smiles"]))
    r = subprocess.run([sys.executable,
                        str(REPO_ROOT / "orchestration" / "scripts" / "rdkit_cli.py"),
                        "match-moieties", "--input", str(inp)],
                       capture_output=True, text=True, timeout=120)
    out = json.loads(r.stdout)["results"]
    assert len(out) == 3
    assert out[0]["moieties"] == []
    assert [m["id"] for m in out[1]["moieties"]] == ["carbonyl_adjacent_N"]
    assert "error" in out[2]


def test_match_moieties_refuses_both_or_neither_input():
    cli = str(REPO_ROOT / "orchestration" / "scripts" / "rdkit_cli.py")
    r = subprocess.run([sys.executable, cli, "match-moieties"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "exactly one" in r.stdout
