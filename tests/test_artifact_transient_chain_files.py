"""CampaignStageExecutor._artifacts must not declare transient chain-launcher files.

mcp-lammps-engine's own chain-completion housekeeping (_cleanup_chain_files in server.py)
unconditionally deletes chain_<id>.sh / chain_<id>.log / chain_<id>_progress.jsonl once a chain
reaches "completed" -- they are launcher scaffolding, never a real simulation artifact. Before
this fix, _artifacts()'s live rglob() could catch one of these moments before the async cleanup
thread removed it; _finish_attempt's later re-check of that same declared path then raised
"executor declared missing artifact", crashing the whole run after a real, hours-long
equilibration chain had already completed successfully (PE1, 2026-08-17).
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

from run_campaign import CampaignStageExecutor  # noqa: E402


def test_transient_chain_files_excluded(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "chain_abc123.sh").write_text("launcher")
    (work / "chain_abc123.log").write_text("stdout capture")
    (work / "chain_abc123_progress.jsonl").write_text("{}")
    npt = work / "npt_production"
    npt.mkdir()
    (npt / "npt_production.log").write_text("real lammps log")
    (npt / "npt_production_out.data").write_text("real data file")
    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "executor_state.json").write_text("{}")

    artifacts = CampaignStageExecutor._artifacts(tmp_path)

    names = {Path(p).name for p in artifacts}
    assert names == {"npt_production.log", "npt_production_out.data"}


def test_similarly_named_real_stage_file_not_excluded(tmp_path):
    """Only the exact chain_<id>.{sh,log}/chain_<id>_progress.jsonl shape is excluded --
    a real file that happens to start with 'chain_' but doesn't match the launcher's own
    naming convention must still be declared."""
    (tmp_path / "chain_of_custody.data").write_text("not a launcher file")
    (tmp_path / "manifest.json").write_text("{}")

    artifacts = CampaignStageExecutor._artifacts(tmp_path)

    names = {Path(p).name for p in artifacts}
    assert names == {"chain_of_custody.data"}
