"""Unit tests for parse_lammps_log (LAMMPS thermo-table parser).

Every downstream number (Tg, density, modulus) depends on this parser correctly
finding the thermo blocks and ignoring the surrounding log noise.
"""
from pathlib import Path

import pytest

from extract_tg import parse_lammps_log

FIXTURE = Path(__file__).parent / "fixtures" / "sample_thermo.log"


def test_parses_both_run_blocks():
    df = parse_lammps_log(str(FIXTURE))
    # 3 rows in the first block + 2 in the second, concatenated
    assert len(df) == 5
    assert list(df.columns) == ["Step", "Temp", "Density", "Press", "TotEng"]


def test_column_values_are_numeric_and_ordered():
    df = parse_lammps_log(str(FIXTURE))
    assert df["Step"].iloc[0] == 0.0
    assert df["Step"].iloc[-1] == 4000.0
    # surrounding "Loop time"/preamble lines must not leak into the table
    assert df["Density"].between(0.9, 1.0).all()


def test_no_thermo_data_raises(tmp_path):
    bad = tmp_path / "no_thermo.log"
    bad.write_text("LAMMPS run\nsome preamble\nTotal wall time: 0:00:01\n")
    with pytest.raises(ValueError):
        parse_lammps_log(str(bad))
