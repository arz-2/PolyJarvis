"""A resolver must find a trajectory that has been gzipped in place.

Completed runs' dumps are stored gzipped (45.7 -> 19 GB on 2026-09-12). MDAnalysis reads
`.gz` transparently via util.anyopen, so re-analysis works -- but only if the path handed to
it names the file that actually exists. stage_params' fallbacks hardcode `.dump`, so without
this resolution a re-analysis of any completed run is handed a missing path.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

from stage_params import _dump_path  # noqa: E402


def test_plain_dump_is_returned_when_it_exists(tmp_path):
    p = tmp_path / "npt_melt_hold.dump"
    p.write_text("ITEM: TIMESTEP\n0\n")
    assert _dump_path(str(p)) == str(p)


def test_gz_is_found_when_the_plain_dump_is_gone(tmp_path):
    gz = tmp_path / "npt_melt_hold.dump.gz"
    gz.write_bytes(b"\x1f\x8b\x08\x00")
    plain = tmp_path / "npt_melt_hold.dump"
    assert _dump_path(str(plain)) == str(gz)


def test_the_plain_dump_wins_when_both_exist(tmp_path):
    plain = tmp_path / "x.dump"
    plain.write_text("ITEM: TIMESTEP\n0\n")
    (tmp_path / "x.dump.gz").write_bytes(b"\x1f\x8b\x08\x00")
    assert _dump_path(str(plain)) == str(plain)


def test_a_path_for_a_file_nothing_has_written_is_unchanged(tmp_path):
    """--dry-run resolves convention-based paths before anything exists. Rewriting them
    there would make resolver output depend on disk state, and would break the existing
    path-wiring assertions in test_analyze_tg_path_wiring.py."""
    missing = tmp_path / "not_yet" / "per_t_structs.dump"
    assert _dump_path(str(missing)) == str(missing)


def test_none_passes_through():
    assert _dump_path(None) is None


def test_an_already_gz_path_is_not_double_suffixed(tmp_path):
    gz = tmp_path / "y.dump.gz"
    assert _dump_path(str(gz)) == str(gz)
