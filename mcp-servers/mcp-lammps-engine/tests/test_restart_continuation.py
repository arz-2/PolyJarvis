"""Restart-based continuation mechanism (nvt/npt/npt_compress templates + script_generator).

Every adaptive stage in the redesigned equilibration protocol (densify, anneal-hold,
cool-block, kinetic-stability test, final NPT) must, on EXTEND, genuinely continue the
same simulation -- read_restart (preserving thermostat/barostat extended-system state and
step count), no re-issued `velocity create`, log/dump opened in append mode onto the SAME
files -- rather than resubmitting a fresh stage from a plain .data file with a longer step
count. This is a regression guard against silently reverting to that old behavior.
"""
import sys
from pathlib import Path

import pytest


def _noncomment_lines(script):
    """Rendered command lines only -- every template's header comment documents both
    read_data/read_restart, dump_modify append, and velocity-create as prose, which
    would otherwise false-positive a naive substring check."""
    return [l for l in script.splitlines() if not l.strip().startswith("#")]


def _read_command_line(script):
    return next(l for l in _noncomment_lines(script)
               if l.startswith("read_data ") or l.startswith("read_restart "))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_script_generator import PCFF_DATA  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from script_generator import ScriptGenerator  # noqa: E402


@pytest.mark.parametrize("template_name,dump_id", [
    ("nvt", "dump_nvt"),
    ("npt", "dump_npt"),
    ("npt_compress", "dump_comp"),
])
def test_fresh_start_reads_data_no_append_no_velocity_skip(tmp_path, template_name, dump_id):
    """A normal (non-continuation) call: read_data, fresh log/dump, no dump_modify append."""
    out = str(tmp_path / f"{template_name}.in")
    script = ScriptGenerator(data_file=str(PCFF_DATA)).generate(
        template_name, output_path=out,
        params={"N_STEPS": 1000, "T_START": 300.0, "T_FINAL": 300.0,
               "T_DAMP": 100.0, "P_START": 1.0, "P_FINAL": 1.0, "P_DAMP": 1000.0},
    )
    lines = _noncomment_lines(script)
    assert _read_command_line(script).startswith("read_data ")
    assert not any(l.startswith(f"dump_modify {dump_id} append") for l in lines)
    log_line = next(l for l in lines if l.startswith("log "))
    assert not log_line.strip().endswith("append")
    # Every stage writes a definitive restart file, fresh-start or not.
    assert any(l.startswith("write_restart ") for l in lines)


@pytest.mark.parametrize("template_name,dump_id", [
    ("nvt", "dump_nvt"),
    ("npt", "dump_npt"),
    ("npt_compress", "dump_comp"),
])
def test_continuation_reads_restart_appends_no_velocity_create(tmp_path, template_name, dump_id):
    """A continuation call: read_restart from the PRIOR block's restart file, log/dump
    append onto the same filenames, and no `velocity create` (state comes from the
    restart file, not reinitialized)."""
    restart_file = tmp_path / "prior_block_out.restart"
    restart_file.write_text("not a real binary restart -- generate() never reads this content")
    out = str(tmp_path / f"{template_name}_continue.in")

    script = ScriptGenerator(data_file=str(PCFF_DATA)).generate(
        template_name, output_path=out,
        params={
            "N_STEPS": 1000, "T_START": 300.0, "T_FINAL": 300.0,
            "T_DAMP": 100.0, "P_START": 1.0, "P_FINAL": 1.0, "P_DAMP": 1000.0,
            "use_restart": True,
            "LOG_APPEND": True,
            "dump_append": True,
            "init_velocity": None,
            "LOG_FILE": f"{template_name}.log",       # same name as the original block
            "DUMP_FILE": f"{template_name}.dump",      # same name as the original block
        },
        data_file_override=str(restart_file),
    )

    lines = _noncomment_lines(script)
    read_line = _read_command_line(script)
    assert read_line.startswith("read_restart ")
    assert str(restart_file) in read_line
    assert not any("velocity all create" in l for l in lines)
    assert any(l.startswith(f"dump_modify {dump_id} append") for l in lines)
    log_line = next(l for l in lines if l.startswith("log "))
    assert log_line.strip().endswith("append")
    # Still writes its own restart file, so a further continuation is possible.
    assert any(l.startswith("write_restart ") for l in lines)


def test_minimize_writes_a_restart_file(tmp_path):
    """minimize is the first stage in every equilibration chain and, unlike every other
    stage, used to write only a .data file on completion -- no restart checkpoint at all.
    A chain that crashes before the next stage's own checkpoint exists (e.g. disk-full
    mid-chain) then has nothing newer than the as-built cell to resume from. minimize must
    write a definitive restart file too, same as nvt/npt/npt_compress already do."""
    out = str(tmp_path / "minimize.in")
    script = ScriptGenerator(data_file=str(PCFF_DATA)).generate(
        "minimize", output_path=out, params={},
    )
    lines = _noncomment_lines(script)
    assert any(l.startswith("write_restart ") for l in lines)


def test_continuation_and_fresh_start_use_the_same_dump_and_log_filenames(tmp_path):
    """The whole point of continuation is one growing trajectory -- fresh-start and its
    continuation must target the identical DUMP_FILE/LOG_FILE, not per-attempt names."""
    fresh_out = str(tmp_path / "anneal_hold.in")
    fresh_script = ScriptGenerator(data_file=str(PCFF_DATA)).generate(
        "nvt", output_path=fresh_out,
        params={"N_STEPS": 1000, "T_START": 300.0, "T_FINAL": 600.0, "T_DAMP": 100.0,
               "LOG_FILE": "anneal_hold.log", "DUMP_FILE": "anneal_hold.dump"},
    )

    restart_file = tmp_path / "anneal_hold_out.restart"
    restart_file.write_text("placeholder")
    cont_out = str(tmp_path / "anneal_hold_continue.in")
    cont_script = ScriptGenerator(data_file=str(PCFF_DATA)).generate(
        "nvt", output_path=cont_out,
        params={
            "N_STEPS": 1000, "T_START": 600.0, "T_FINAL": 600.0, "T_DAMP": 100.0,
            "use_restart": True, "LOG_APPEND": True, "dump_append": True,
            "init_velocity": None,
            "LOG_FILE": "anneal_hold.log", "DUMP_FILE": "anneal_hold.dump",
        },
        data_file_override=str(restart_file),
    )

    assert "anneal_hold.log" in fresh_script and "anneal_hold.log" in cont_script
    assert "anneal_hold.dump" in fresh_script and "anneal_hold.dump" in cont_script
