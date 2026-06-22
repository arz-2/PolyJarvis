"""Velocity-seed reproducibility (production change in script_generator.py)."""
from pathlib import Path

from script_generator import ScriptGenerator

REPO_ROOT = Path(__file__).resolve().parents[3]
CALIB_PCFF = REPO_ROOT / "data" / "CALIB_PCFF" / "emc_build.data"


def _vel_line(script: str):
    for ln in script.splitlines():
        if ln.strip().startswith("velocity all create"):  # the command, not the comment
            return ln.strip()
    return None


def test_pinned_seed_is_deterministic(tmp_path):
    gen = ScriptGenerator(str(CALIB_PCFF))
    a = gen.generate("nvt", str(tmp_path / "a.in"),
                     params={"init_velocity": 600.0}, velocity_seed=7)
    b = gen.generate("nvt", str(tmp_path / "b.in"),
                     params={"init_velocity": 600.0}, velocity_seed=7)
    la, lb = _vel_line(a), _vel_line(b)
    assert la is not None and la == lb
    assert " 7 " in la  # the pinned seed appears verbatim


def test_unset_seed_still_randomizes(tmp_path):
    # Default behavior preserved: without velocity_seed the line still renders
    # (seed is some integer, not pinned). We only assert it produces a velocity line.
    gen = ScriptGenerator(str(CALIB_PCFF))
    s = gen.generate("nvt", str(tmp_path / "c.in"), params={"init_velocity": 600.0})
    assert _vel_line(s) is not None
