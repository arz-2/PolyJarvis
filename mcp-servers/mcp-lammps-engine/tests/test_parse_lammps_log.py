"""Unit tests for parse_lammps_log (LAMMPS thermo-table parser).

Every downstream number (Tg, density, modulus) depends on this parser correctly
finding the thermo blocks and ignoring the surrounding log noise. The sample log
is written into a temp file at test time rather than committed as a fixture --
``*.log`` is gitignored in this repo, so an on-disk fixture would not survive.
"""
import pytest

from extract_thermal import parse_lammps_log

# Two thermo run blocks (5 data rows total) wrapped in realistic log noise.
SAMPLE_LOG = """\
LAMMPS (2 Aug 2023 - Update 1)
Reading data file ...
  orthogonal box = (0 0 0) to (40 40 40)
Per MPI rank memory allocation (min/avg/max) = 12.5 | 12.5 | 12.5 Mbytes
Step Temp Density Press TotEng
0 300.0 0.9500 1.00 -1000.0
1000 305.0 0.9600 1.10 -1010.0
2000 302.0 0.9550 0.90 -1005.0
Loop time of 12.34 on 1 procs for 2000 steps
Per MPI rank memory allocation (min/avg/max) = 12.5 | 12.5 | 12.5 Mbytes
Step Temp Density Press TotEng
3000 300.0 0.9700 1.00 -1012.0
4000 301.0 0.9650 1.05 -1011.0
Loop time of 6.10 on 1 procs for 1000 steps
Total wall time: 0:00:18
"""


@pytest.fixture
def log_file(tmp_path):
    path = tmp_path / "sample_thermo.log"
    path.write_text(SAMPLE_LOG)
    return str(path)


def test_parses_both_run_blocks(log_file):
    df = parse_lammps_log(log_file)
    # 3 rows in the first block + 2 in the second, concatenated
    assert len(df) == 5
    assert list(df.columns) == ["Step", "Temp", "Density", "Press", "TotEng"]


def test_column_values_are_numeric_and_ordered(log_file):
    df = parse_lammps_log(log_file)
    assert df["Step"].iloc[0] == 0.0
    assert df["Step"].iloc[-1] == 4000.0
    # surrounding "Loop time"/preamble lines must not leak into the table
    assert df["Density"].between(0.9, 1.0).all()


def test_no_thermo_data_raises(tmp_path):
    bad = tmp_path / "no_thermo.log"
    bad.write_text("LAMMPS run\nsome preamble\nTotal wall time: 0:00:01\n")
    with pytest.raises(ValueError):
        parse_lammps_log(str(bad))
