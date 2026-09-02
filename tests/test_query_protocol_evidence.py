"""protocol_evidence.py query's ranking logic is the load-bearing behavior of this whole
phase — it is what lets a worker skip a fresh web search safely. These tests cover the
tier order (exact_smiles > exact_class > similar_class), the trust-tier/year/doi
tie-break within a tier, --methodology-only, and a missing store file degrading to empty
hits rather than crashing. rules_common.canonicalize and protocol_evidence.compute_similarities
both shell into a conda env, so both are monkeypatched here — no real RDKit call."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import protocol_evidence as pe  # noqa: E402
import rules_common  # noqa: E402  -- pe calls through rules_common.canonicalize

PMMA_SMILES = "*CC(*)(C)C(=O)OC"
PAA_SMILES = "*CC(*)C(=O)O"
PS_SMILES = "*CC(*)c1ccccc1"

RULES = {
    "classes": {
        "PACR": {"member_smiles": {"PMMA": [PMMA_SMILES], "PAA": [PAA_SMILES]}},
        "PSTR": {"member_smiles": {"PS": [PS_SMILES]}},
    }
}


def _record(**overrides):
    base = dict(
        field="forcefield", polymer_class="PACR", polymer_names=["PMMA"],
        smiles=[PMMA_SMILES], claim="claim", value={"recommendation": "PCFF"},
        doi="10.1/default", title="t", year=2025, doi_verified=True,
        trust_tier="peer_reviewed_doi",
        provenance={"origin": "migration", "source_run": None, "migrated_from": None, "added_at": None},
    )
    base.update(overrides)
    return pe.build_record(**base)


@pytest.fixture(autouse=True)
def _identity_canonicalize(monkeypatch):
    # rules_common.canonicalize shells into a conda env; identity is sufficient here
    # since these fixtures never rely on real canonicalization behavior. protocol_evidence
    # protocol_evidence calls rules_common.canonicalize through the module object, so
    # patching it on rules_common is what the call site actually resolves.
    monkeypatch.setattr(rules_common, "canonicalize", lambda smi, *a, **k: smi)


def test_exact_smiles_beats_exact_class_beats_similar_class(monkeypatch):
    exact_smiles_rec = _record(doi="10.1/exact-smiles", smiles=[PMMA_SMILES])
    exact_class_rec = _record(doi="10.1/exact-class", smiles=[], claim="different claim for unique id")
    similar_class_rec = _record(doi="10.1/similar-class", polymer_class="PSTR",
                                 smiles=[PS_SMILES], claim="a PS-specific claim")
    store = {"records": [exact_class_rec, similar_class_rec, exact_smiles_rec]}

    monkeypatch.setattr(pe, "compute_similarities",
                         lambda query, candidates, **k: {"scores": {PS_SMILES: 0.6}, "errors": []})

    result = pe.query(store, polymer_class="PACR", smiles=PMMA_SMILES, field="forcefield",
                        rules=RULES, similarity_threshold=0.4, use_chem_similarity=True, top_k=None)

    tiers = [h["tier"] for h in result["hits"]]
    assert tiers == ["exact_smiles", "exact_class", "similar_class"]
    assert result["hits"][0]["record"]["doi"] == "10.1/exact-smiles"
    assert result["hits"][2]["similarity"] == 0.6


def test_similar_class_below_threshold_is_excluded(monkeypatch):
    similar_class_rec = _record(doi="10.1/below-threshold", polymer_class="PSTR", smiles=[PS_SMILES])
    store = {"records": [similar_class_rec]}

    monkeypatch.setattr(pe, "compute_similarities",
                         lambda query, candidates, **k: {"scores": {PS_SMILES: 0.1}, "errors": []})

    result = pe.query(store, polymer_class="PACR", smiles=PMMA_SMILES, field="forcefield",
                        rules=RULES, similarity_threshold=0.4, use_chem_similarity=True, top_k=None)
    assert result["hits"] == []


def test_tie_break_trust_tier_then_year_then_doi():
    older_peer_reviewed = _record(doi="10.1/b-older", year=2019, trust_tier="peer_reviewed_doi",
                                   smiles=[], claim="claim b")
    newer_preprint = _record(doi="10.1/a-newer-preprint", year=2026, trust_tier="preprint",
                              smiles=[], claim="claim a")
    newer_peer_reviewed = _record(doi="10.1/c-newer", year=2024, trust_tier="peer_reviewed_doi",
                                   smiles=[], claim="claim c")
    store = {"records": [newer_preprint, older_peer_reviewed, newer_peer_reviewed]}

    result = pe.query(store, polymer_class="PACR", smiles=None, field="forcefield",
                        rules=RULES, similarity_threshold=0.4, use_chem_similarity=False, top_k=None)

    dois = [h["record"]["doi"] for h in result["hits"]]
    # trust tier wins first (both peer_reviewed_doi rank above preprint), then year desc.
    assert dois == ["10.1/c-newer", "10.1/b-older", "10.1/a-newer-preprint"]


def test_field_filter_excludes_other_fields():
    matching = _record(doi="10.1/matches-field", field="forcefield")
    other = _record(doi="10.1/other-field", field="electrostatics", claim="different claim")
    store = {"records": [matching, other]}

    result = pe.query(store, polymer_class="PACR", smiles=None, field="forcefield",
                        rules=RULES, similarity_threshold=0.4, use_chem_similarity=False, top_k=None)
    assert len(result["hits"]) == 1
    assert result["hits"][0]["record"]["doi"] == "10.1/matches-field"


def test_top_k_truncates():
    records = [_record(doi=f"10.1/rec{i}", claim=f"claim {i}") for i in range(5)]
    store = {"records": records}
    result = pe.query(store, polymer_class="PACR", smiles=None, field="forcefield",
                        rules=RULES, similarity_threshold=0.4, use_chem_similarity=False, top_k=2)
    assert len(result["hits"]) == 2


def test_missing_store_file_yields_empty_hits_not_a_crash(tmp_path):
    store = pe.load_store(str(tmp_path / "missing.json"))
    result = pe.query(store, polymer_class="PACR", smiles=None, field="forcefield",
                        rules=RULES, similarity_threshold=0.4, use_chem_similarity=False, top_k=None)
    assert result["hits"] == []


def test_methodology_only_returns_criteria_without_hits(tmp_path, monkeypatch, capsys):
    path = str(tmp_path / "ff_store.json")
    store = pe.empty_store(with_methodology=True)
    store["methodology_criteria"] = [{"criterion": "prefer chemistry-matched benchmarks"}]
    store["records"] = [_record()]
    pe.save_store(path, store)

    monkeypatch.setitem(pe.STORE_PATHS, "ff", path)
    monkeypatch.setattr(sys, "argv", ["protocol_evidence.py", "query", "--store", "ff", "--methodology-only"])
    pe.main()

    import json as _json
    payload = _json.loads(capsys.readouterr().out)
    assert "hits" not in payload
    assert payload["methodology_criteria"] == [{"criterion": "prefer chemistry-matched benchmarks"}]
