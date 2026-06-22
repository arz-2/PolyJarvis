"""Unit tests for ScriptGenerator FF-style / template / KOKKOS-deck logic.

These lock in the fixes for three bugs that produced failed runs (see PEG1 run log):
  B1 — use_pcff silently defaulted to GAFF2/harmonic styles on a Class II (PCFF) cell.
  B2 — a Tg sweep silently rendered a single-temperature NPT instead of a cooling ramp.
  B3 — the KOKKOS deck must not emit invalid `neighbor ... bin/kk` or `package kokkos gpu N`.
"""
import textwrap

import pytest

from script_generator import ScriptGenerator


# ── Fixtures ───────────────────────────────────────────────────────────────────

# Minimal LAMMPS data-file header (EMC-style: coefficients live in the params file).
_DATA_HEADER = textwrap.dedent("""\
    LAMMPS output created by EMC v9.4.4

        20  atoms
        10  bonds

         2  atom types

         0  10.0  xlo xhi
         0  10.0  ylo yhi
         0  10.0  zlo zhi

    Masses

       1  12.011  # c
       2   1.008  # hc
    """)

# EMC PCFF params file: 4-arg quartic bond_coeff + class2 cross-term fingerprints.
_CLASS2_PARAMS = textwrap.dedent("""\
    pair_coeff  1 1  0.054  4.010  # c,c
    bond_coeff  1  1.530  299.67 -501.77  679.81  # c,c
    # BondBond Coeffs
    angle_coeff 1 bb  3.3872  1.530  1.101  # c,c,hc
    """)

# Harmonic / GAFF2-style params file: 2-arg bond_coeff, no class2 cross-terms.
_HARMONIC_PARAMS = textwrap.dedent("""\
    pair_coeff  1 1  0.054  4.010  # c,c
    bond_coeff  1  340.0  1.090   # c,hc
    """)


@pytest.fixture
def data_file(tmp_path):
    p = tmp_path / "cell.data"
    p.write_text(_DATA_HEADER)
    return str(p)


@pytest.fixture
def class2_params(tmp_path):
    p = tmp_path / "emc_build.params"
    p.write_text(_CLASS2_PARAMS)
    return str(p)


@pytest.fixture
def harmonic_params(tmp_path):
    p = tmp_path / "harmonic.params"
    p.write_text(_HARMONIC_PARAMS)
    return str(p)


# ── B1: use_pcff auto-detect / validate ─────────────────────────────────────────

def test_class2_detected_from_params_file(data_file, class2_params):
    gen = ScriptGenerator(data_file=data_file)
    assert gen._detect_class2(data_file, class2_params) is True


def test_class2_detected_from_embedded_data_sections(tmp_path):
    df = tmp_path / "radon.data"
    df.write_text(_DATA_HEADER + "\nBondBond Coeffs\n\n 1 0.0 1.5 1.1\n")
    gen = ScriptGenerator(data_file=str(df))
    assert gen._detect_class2(str(df)) is True


def test_harmonic_params_not_class2(data_file, harmonic_params):
    gen = ScriptGenerator(data_file=data_file)
    assert gen._detect_class2(data_file, harmonic_params) is False


def test_unreadable_returns_none(tmp_path):
    gen = ScriptGenerator(data_file=str(tmp_path / "missing.data"))
    assert gen._detect_class2(str(tmp_path / "missing.data")) is None


def test_use_pcff_autocorrects_on_class2_cell(data_file, class2_params):
    """The bug: use_pcff omitted → harmonic styles on a class2 cell. Now auto-corrected."""
    gen = ScriptGenerator(data_file=data_file)
    subs = gen._build_substitutions("npt", {"params_file": class2_params}, data_file)
    assert subs["BOND_STYLE"] == "class2"
    assert "lj/class2" in subs["PAIR_STYLE_BLOCK"]


def test_explicit_use_pcff_false_on_class2_raises(data_file, class2_params):
    gen = ScriptGenerator(data_file=data_file)
    with pytest.raises(ValueError, match="Class II"):
        gen._build_substitutions("npt", {"params_file": class2_params, "use_pcff": False}, data_file)


def test_use_pcff_true_on_harmonic_cell_raises(data_file, harmonic_params):
    gen = ScriptGenerator(data_file=data_file)
    with pytest.raises(ValueError, match="no Class II"):
        gen._build_substitutions("npt", {"params_file": harmonic_params, "use_pcff": True}, data_file)


def test_opls_cell_skips_pcff_guard(data_file, class2_params):
    """use_opls runs bypass the class2 guard entirely (different FF family)."""
    gen = ScriptGenerator(data_file=data_file)
    subs = gen._build_substitutions("npt", {"params_file": class2_params, "use_opls": True}, data_file)
    assert subs["BOND_STYLE"] != "class2"


# ── B2: Tg-sweep template guard ─────────────────────────────────────────────────

def test_tg_sweep_without_ramp_bounds_raises(tmp_path, data_file, class2_params):
    gen = ScriptGenerator(data_file=data_file)
    out = str(tmp_path / "tg.in")
    with pytest.raises(ValueError, match="ramp bounds"):
        gen.generate("npt_tg_step", out, {"params_file": class2_params, "T_START": 440})


def test_tg_sweep_with_ramp_renders_staircase(tmp_path, data_file, class2_params):
    gen = ScriptGenerator(data_file=data_file)
    out = str(tmp_path / "tg.in")
    script = gen.generate(
        "npt_tg_step", out,
        {"params_file": class2_params, "use_pcff": True,
         "T_START": 440, "T_END": 100, "T_STEP": 20},
    )
    assert "variable temps index" in script          # multi-T cooling loop present
    assert "class2" in script
    assert "jump SELF" in script


# ── B3: KOKKOS deck validity ────────────────────────────────────────────────────

def test_kokkos_deck_has_no_invalid_lines(tmp_path, data_file, class2_params):
    gen = ScriptGenerator(data_file=data_file)
    out = str(tmp_path / "tg.in")
    script = gen.generate(
        "npt_tg_step", out,
        {"params_file": class2_params, "use_pcff": True, "use_gpu": True, "engine": "kokkos",
         "T_START": 440, "T_END": 100, "T_STEP": 20},
    )
    assert "bin/kk" not in script                     # neighbor takes no /kk suffix
    assert "package kokkos gpu" not in script         # illegal: no `gpu N` keyword
    assert "package gpu" not in script                # kokkos loads via CLI -pk kokkos
    assert "# KOKKOS" in script


def test_gpu_engine_deck_emits_package_gpu(tmp_path, data_file, class2_params):
    gen = ScriptGenerator(data_file=data_file)
    out = str(tmp_path / "tg.in")
    script = gen.generate(
        "npt_tg_step", out,
        {"params_file": class2_params, "use_pcff": True, "use_gpu": True, "engine": "gpu",
         "T_START": 440, "T_END": 100, "T_STEP": 20},
    )
    assert "package gpu" in script
    assert "bin/kk" not in script
