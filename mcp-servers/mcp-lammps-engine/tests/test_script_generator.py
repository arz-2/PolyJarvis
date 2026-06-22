"""Tests for script_generator.py — FF auto-detection, npt_tg_step guard, KOKKOS deck.

Covers:
  B1 — _detect_ff_from_data_file + mismatch raise in _build_substitutions
  B2 — npt_tg_step ValueError when T_END/T_STEP are missing
  B3 — KOKKOS deck emits comment, not "package gpu N" command
"""
import warnings
import pytest
from pathlib import Path

from script_generator import ScriptGenerator, _detect_ff_from_data_file

# Absolute paths to committed CALIB data files (EMC-generated, all three FF types)
_REPO = Path(__file__).resolve().parent.parent.parent.parent  # .../PolyJarvis
PCFF_DATA   = _REPO / "data" / "CALIB_PCFF"   / "emc_build.data"
TRAPPE_DATA = _REPO / "data" / "CALIB_TRAPPE" / "emc_build.data"
OPLS_DATA   = _REPO / "data" / "CALIB_OPLS"   / "emc_build.data"

# Minimal GAFF2-style RadonPy data file — has inline Pair Coeffs → detection returns {}
GAFF2_DATA_CONTENT = """\
# RadonPy GAFF2 polymer data file
4 atoms
0 bonds
2 atom types

0.0 10.0 xlo xhi
0.0 10.0 ylo yhi
0.0 10.0 zlo zhi

Masses

1 1.008 # hc
2 12.011 # c3

Pair Coeffs

1 0.0157 2.6495
2 0.1094 3.3996

Atoms

1 1 2 -0.12 1.0 1.0 1.0
2 1 1  0.06 2.0 1.0 1.0
3 1 1  0.06 1.0 2.0 1.0
4 1 2  0.00 2.0 2.0 1.0
"""


# ── _detect_ff_from_data_file ─────────────────────────────────────────────────

def test_detect_pcff_from_calib():
    d = _detect_ff_from_data_file(str(PCFF_DATA))
    assert d == {"use_pcff": True, "use_trappe": False, "use_opls": False}


def test_detect_trappe_from_calib():
    d = _detect_ff_from_data_file(str(TRAPPE_DATA))
    assert d == {"use_pcff": False, "use_trappe": True, "use_opls": False}


def test_detect_opls_from_calib():
    d = _detect_ff_from_data_file(str(OPLS_DATA))
    assert d == {"use_pcff": False, "use_trappe": False, "use_opls": True}


def test_detect_gaff2_returns_empty(tmp_path):
    f = tmp_path / "gaff2.data"
    f.write_text(GAFF2_DATA_CONTENT)
    assert _detect_ff_from_data_file(str(f)) == {}


def test_detect_missing_file_returns_empty():
    assert _detect_ff_from_data_file("/nonexistent/path.data") == {}


# ── B1: FF auto-detect in generate() ─────────────────────────────────────────

def test_pcff_autodetect_sets_class2(tmp_path):
    """No FF flags passed → auto-detect from PCFF file → bond_style class2 in output."""
    out = str(tmp_path / "npt.in")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        script = ScriptGenerator(data_file=str(PCFF_DATA)).generate(
            "npt", output_path=out, params={}
        )
    assert "bond_style class2" in script
    assert any("auto-detected" in str(x.message) for x in w), "expected auto-detect warning"


def test_trappe_autodetect_sets_lj_cut(tmp_path):
    """No FF flags + TraPPE file → auto-detect → lj/cut pair style (no pppm)."""
    out = str(tmp_path / "npt.in")
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        script = ScriptGenerator(data_file=str(TRAPPE_DATA)).generate(
            "npt", output_path=out, params={}
        )
    assert "pair_style lj/cut" in script
    assert "pppm" not in script.lower()


def test_explicit_pcff_true_no_warn(tmp_path):
    """Caller explicitly sets use_pcff=True on PCFF file → no auto-detect warning, class2."""
    out = str(tmp_path / "npt.in")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        script = ScriptGenerator(data_file=str(PCFF_DATA)).generate(
            "npt", output_path=out, params={"use_pcff": True}
        )
    assert "bond_style class2" in script
    assert not any("auto-detected" in str(x.message) for x in w), "spurious warn on explicit flag"


def test_pcff_mismatch_raises(tmp_path):
    """Caller sets use_pcff=False on a PCFF file → ValueError (not a silent bad deck)."""
    out = str(tmp_path / "npt.in")
    with pytest.raises(ValueError, match="FF flag mismatch"):
        ScriptGenerator(data_file=str(PCFF_DATA)).generate(
            "npt", output_path=out, params={"use_pcff": False}
        )


def test_trappe_mismatch_raises(tmp_path):
    """Caller sets use_trappe=False on a TraPPE file → ValueError."""
    out = str(tmp_path / "npt.in")
    with pytest.raises(ValueError, match="FF flag mismatch"):
        ScriptGenerator(data_file=str(TRAPPE_DATA)).generate(
            "npt", output_path=out, params={"use_trappe": False}
        )


def test_trappe_shake_disabled(tmp_path):
    """TraPPE-UA script must never contain 'fix shake_fix' — C-C backbone SHAKE crashes."""
    out = str(tmp_path / "npt.in")
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        script = ScriptGenerator(data_file=str(TRAPPE_DATA)).generate(
            "npt", output_path=out, params={"use_trappe": True}
        )
    assert "fix shake_fix" not in script, "TraPPE-UA must not have SHAKE"
    assert "SHAKE disabled" in script, "expected explicit SHAKE-disabled comment"


def test_gaff2_no_autodetect_no_raise(tmp_path):
    """RadonPy GAFF2 file: auto-detect returns {}, no raise, GAFF2 styles used."""
    data_file = tmp_path / "gaff2.data"
    data_file.write_text(GAFF2_DATA_CONTENT)
    out = str(tmp_path / "npt.in")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        script = ScriptGenerator(data_file=str(data_file)).generate(
            "npt", output_path=out, params={}
        )
    assert "bond_style harmonic" in script
    assert not any("auto-detected" in str(x.message) for x in w)


# ── B2: npt_tg_step guard ─────────────────────────────────────────────────────

def test_npt_tg_step_missing_ramp_raises(tmp_path):
    """npt_tg_step without T_END and T_STEP raises ValueError immediately."""
    out = str(tmp_path / "sweep.in")
    with pytest.raises(ValueError, match="T_END.*T_STEP|T_END and T_STEP"):
        ScriptGenerator(data_file=str(PCFF_DATA)).generate(
            "npt_tg_step", output_path=out,
            params={"use_pcff": True, "T_START": 600.0}
        )


def test_npt_tg_step_missing_only_t_step_raises(tmp_path):
    """npt_tg_step with T_END but no T_STEP → ValueError."""
    out = str(tmp_path / "sweep.in")
    with pytest.raises(ValueError):
        ScriptGenerator(data_file=str(PCFF_DATA)).generate(
            "npt_tg_step", output_path=out,
            params={"use_pcff": True, "T_START": 600.0, "T_END": 200.0}
        )


def test_npt_tg_step_with_ramp_emits_staircase(tmp_path):
    """npt_tg_step with T_END + T_STEP generates a LAMMPS staircase (variable loop)."""
    out = str(tmp_path / "sweep.in")
    script = ScriptGenerator(data_file=str(PCFF_DATA)).generate(
        "npt_tg_step", output_path=out,
        params={"use_pcff": True, "T_START": 300.0, "T_END": 200.0, "T_STEP": 20.0,
                "N_STEPS_PER_T": 100}
    )
    # Staircase uses LAMMPS variable + loop/jump flow control
    assert "variable temps index" in script or "jump" in script


# ── B3: KOKKOS deck regression ────────────────────────────────────────────────

def test_kokkos_deck_no_pkg_gpu_command(tmp_path):
    """KOKKOS engine: deck uses comment placeholder, not a 'package gpu N' command."""
    out = str(tmp_path / "npt.in")
    script = ScriptGenerator(data_file=str(PCFF_DATA)).generate(
        "npt", output_path=out,
        params={"use_pcff": True, "engine": "kokkos", "use_gpu": True}
    )
    # The template comment may say "package gpu 1 neigh no" as an example; the actual
    # command line must NOT appear uncommented.
    lines = script.splitlines()
    assert not any(
        line.lstrip().startswith("package gpu") for line in lines
    ), "KOKKOS deck must not emit 'package gpu N' command"
    assert "# KOKKOS" in script


@pytest.mark.xfail(
    reason="server.py uses @mcp.tool() decorators at module level and cannot be imported "
           "outside the MCP runtime. Verify _engine_launch flags via integration test or "
           "manually: grep server.py for '-k on g {n_gpu} -sf kk -pk kokkos'.",
    strict=False,
)
def test_engine_launch_kokkos_flags():
    """_engine_launch('kokkos') returns the correct KOKKOS flag set."""
    import importlib
    server = importlib.import_module("server")
    _, flags = server._engine_launch("kokkos", 1)
    assert "-k on g 1" in flags
    assert "-sf kk" in flags
    assert "-pk kokkos" in flags


@pytest.mark.xfail(
    reason="server.py uses @mcp.tool() decorators at module level and cannot be imported "
           "outside the MCP runtime.",
    strict=False,
)
def test_engine_launch_gpu_flags():
    """_engine_launch('gpu') returns the GPU-package flag set."""
    import importlib
    server = importlib.import_module("server")
    _, flags = server._engine_launch("gpu", 2)
    assert "-sf gpu" in flags
    assert "-pk gpu 2" in flags
