"""rules_common.resolve_member / resolve_member_value: member-identity resolution via SMILES,
the shared mechanism every run_name-matching consumer this codebase used to hand-roll now
goes through. canon_smiles.canonicalize shells into a conda env, so it's monkeypatched here
rather than actually invoked.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

import canon_smiles  # noqa: E402
import rules_common  # noqa: E402
from rules_common import resolve_member, resolve_member_value  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_canon_cache():
    rules_common._canon_for_match.cache_clear()
    yield
    rules_common._canon_for_match.cache_clear()


CLS = {
    "experimental_tg_K": {"PE": 195, "PP": 258},
    "experimental_density_gcm3": 0.6,
    "member_smiles": {"PE": ["PE_CANON"], "PP": ["PP_CANON"]},
}


def test_scalar_value_field_passes_through_regardless_of_smiles(monkeypatch):
    monkeypatch.setattr(canon_smiles, "canonicalize", lambda smi, *a, **k: smi)
    assert resolve_member_value(CLS, "experimental_density_gcm3", "PE_CANON") == 0.6
    assert resolve_member_value(CLS, "experimental_density_gcm3", "anything") == 0.6


def test_dict_value_field_resolves_the_matched_member(monkeypatch):
    monkeypatch.setattr(canon_smiles, "canonicalize", lambda smi, *a, **k: smi)
    assert resolve_member(CLS, "member_smiles", "PE_CANON") == "PE"
    assert resolve_member_value(CLS, "experimental_tg_K", "PE_CANON") == 195
    assert resolve_member_value(CLS, "experimental_tg_K", "PP_CANON") == 258


def test_dict_value_field_no_match_returns_none(monkeypatch):
    monkeypatch.setattr(canon_smiles, "canonicalize", lambda smi, *a, **k: smi)
    assert resolve_member(CLS, "member_smiles", "UNMATCHED") is None
    assert resolve_member_value(CLS, "experimental_tg_K", "UNMATCHED") is None


def test_empty_or_none_smiles_short_circuits_without_calling_canonicalize(monkeypatch):
    def _fail(*a, **k):
        pytest.fail("must not call canonicalize for empty/None smiles")
    monkeypatch.setattr(canon_smiles, "canonicalize", _fail)
    assert resolve_member(CLS, "member_smiles", "") is None
    assert resolve_member(CLS, "member_smiles", None) is None
    assert resolve_member_value(CLS, "experimental_tg_K", None) is None


def test_canonicalize_raising_degrades_to_none_not_an_exception(monkeypatch):
    def _raise(smi, *a, **k):
        raise RuntimeError("RDKit could not parse SMILES")
    monkeypatch.setattr(canon_smiles, "canonicalize", _raise)
    assert resolve_member(CLS, "member_smiles", "garbage") is None
    assert resolve_member_value(CLS, "experimental_tg_K", "garbage") is None


def test_canon_for_match_is_memoized(monkeypatch):
    calls = []
    def _counting(smi, *a, **k):
        calls.append(smi)
        return smi
    monkeypatch.setattr(canon_smiles, "canonicalize", _counting)
    resolve_member(CLS, "member_smiles", "PE_CANON")
    resolve_member(CLS, "member_smiles", "PE_CANON")
    resolve_member_value(CLS, "experimental_tg_K", "PE_CANON")
    assert calls == ["PE_CANON"]


def test_no_member_smiles_table_on_the_class_returns_none(monkeypatch):
    monkeypatch.setattr(canon_smiles, "canonicalize", lambda smi, *a, **k: smi)
    cls = {"experimental_tg_K": {"PE": 195}}
    assert resolve_member(cls, "member_smiles", "PE_CANON") is None
    assert resolve_member_value(cls, "experimental_tg_K", "PE_CANON") is None


def test_note_key_is_never_treated_as_a_member(monkeypatch):
    monkeypatch.setattr(canon_smiles, "canonicalize", lambda smi, *a, **k: smi)
    cls = {"experimental_tg_K": {"PE": 195}, "member_smiles": {"PE": ["PE_CANON"],
                                                                "note": "some prose"}}
    assert resolve_member(cls, "member_smiles", "note") is None
