"""protocol_evidence.py's STORE section — the shared record shape and file I/O every other
protocol-evidence script (migration, query, ingest) depends on. Bugs here propagate to
all three, so this file checks the primitives in isolation: id stability (dedup
correctness rests on it), atomic-write round-tripping, missing-file scaffolding (so
retrieval never hard-fails before the store exists), and the doi_verified-only
admission rule (the store must never hold an unverified finding)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import protocol_evidence as pe  # noqa: E402


def _valid_record(**overrides):
    kwargs = dict(
        field="forcefield", polymer_class="PACR", polymer_names=["PMMA"],
        smiles=["*CC(*)(C)C(=O)OC"], claim="Class II fields reproduce PMMA density within 2%.",
        value={"recommendation": "PCFF"}, doi="10.1234/example", title="Example paper",
        year=2025, doi_verified=True, trust_tier="peer_reviewed_doi",
        provenance={"origin": "worker_run", "source_run": "PE1", "migrated_from": None,
                    "added_at": "2026-08-24T00:00:00Z"},
    )
    kwargs.update(overrides)
    return pe.build_record(**kwargs)


def test_make_record_id_is_stable_and_content_keyed():
    id1 = pe.make_record_id("10.1234/x", "forcefield", "claim text")
    id2 = pe.make_record_id("10.1234/x", "forcefield", "claim text")
    assert id1 == id2
    assert len(id1) == 12

    id3 = pe.make_record_id("10.1234/x", "forcefield", "different claim")
    assert id3 != id1


def test_load_store_scaffolds_missing_file(tmp_path):
    store = pe.load_store(str(tmp_path / "does_not_exist.json"))
    assert store == {"schema_version": 1, "generated_at": None, "records": []}


def test_load_store_scaffolds_missing_file_with_methodology(tmp_path):
    store = pe.load_store(str(tmp_path / "does_not_exist.json"), with_methodology=True)
    assert store["methodology_criteria"] == []


def test_save_store_round_trips(tmp_path):
    path = str(tmp_path / "store.json")
    original = pe.empty_store(with_methodology=True)
    original["records"] = [_valid_record()]
    pe.save_store(path, original)

    reloaded = pe.load_store(path, with_methodology=True)
    assert reloaded["records"] == original["records"]
    assert reloaded["generated_at"] is not None


def test_save_store_is_atomic_no_leftover_tmp_file(tmp_path):
    path = str(tmp_path / "store.json")
    pe.save_store(path, pe.empty_store())
    assert not (tmp_path / "store.json.tmp").exists()


def test_validate_record_accepts_well_formed_record():
    assert pe.validate_record(_valid_record()) == []


def test_validate_record_rejects_missing_doi():
    errors = pe.validate_record(_valid_record(doi=None))
    assert any("doi" in e for e in errors)


def test_validate_record_rejects_missing_claim():
    errors = pe.validate_record(_valid_record(claim=""))
    assert any("claim" in e for e in errors)


def test_validate_record_rejects_unverified():
    errors = pe.validate_record(_valid_record(doi_verified=False))
    assert any("doi_verified" in e for e in errors)


def test_validate_record_rejects_bad_field_enum():
    errors = pe.validate_record(_valid_record(field="not_a_real_field"))
    assert any("field" in e for e in errors)


def test_validate_record_rejects_bad_trust_tier():
    errors = pe.validate_record(_valid_record(trust_tier="made_up_tier"))
    assert any("trust_tier" in e for e in errors)


def test_dedupe_first_write_wins():
    existing = [_valid_record()]
    same_id_again = [_valid_record()]  # identical doi/field/claim -> identical record_id
    different = [_valid_record(doi="10.9999/other", claim="a different claim entirely")]

    merged, skipped = pe.dedupe(existing, same_id_again + different)
    assert len(merged) == 2  # existing + the genuinely new one
    assert skipped == [existing[0]["record_id"]]


def test_dedupe_empty_existing():
    new = [_valid_record()]
    merged, skipped = pe.dedupe([], new)
    assert merged == new
    assert skipped == []


def test_locked_store_is_reentrant_safe_and_creates_sibling_lock_file(tmp_path):
    path = str(tmp_path / "store.json")
    with pe.locked_store(path):
        pe.save_store(path, pe.empty_store())
    assert (tmp_path / "store.json.lock").exists()
    # Lock must be released after the context exits -- a second acquisition must not hang.
    with pe.locked_store(path):
        pass


def test_locked_store_excludes_concurrent_writers(tmp_path):
    import multiprocessing
    import time

    path = str(tmp_path / "store.json")
    pe.save_store(path, pe.empty_store())

    def worker(order_log_path, tag, hold_seconds):
        with pe.locked_store(path):
            with open(order_log_path, "a") as f:
                f.write(f"{tag}-enter\n")
            time.sleep(hold_seconds)
            with open(order_log_path, "a") as f:
                f.write(f"{tag}-exit\n")

    log_path = str(tmp_path / "order.log")
    Path(log_path).write_text("")
    p1 = multiprocessing.Process(target=worker, args=(log_path, "A", 0.3))
    p2 = multiprocessing.Process(target=worker, args=(log_path, "B", 0.0))
    p1.start()
    time.sleep(0.05)  # ensure p1 acquires the lock first
    p2.start()
    p1.join(timeout=5)
    p2.join(timeout=5)

    lines = Path(log_path).read_text().splitlines()
    # B must not enter before A exits -- proves the lock actually excludes, not just logs.
    assert lines.index("A-exit") < lines.index("B-enter")
