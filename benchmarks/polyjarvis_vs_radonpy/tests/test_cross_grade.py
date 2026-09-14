"""Pure-logic checks for the PEG1 cross-grade harness. The RadonPy and checker halves need their
own interpreters and real run data, so run_cross_grade.py verifies those at run time instead:
RadonPy's analyzer must reproduce its own stored sma_sd, and the rg.profile it parses must
round-trip to the matrix that wrote it."""
import math

import numpy as np

from benchmarks.polyjarvis_vs_radonpy.cross_grade import criteria, rg_profile


def test_nan_sma_sd_is_unevaluable_where_check_eq_would_pass_it():
    # analyze_thermo returns NaN when the log is shorter than 2*width, and check_eq's
    # `NaN > threshold` is False, i.e. converged.
    assert not (math.nan > 17.8)
    entry = criteria.radonpy_criterion(float("nan"), 35670.0, 0.0005, relative=True)
    assert entry["status"] == criteria.UNEVALUABLE


def test_relative_rule_reproduces_radonpy_peg1s_rg_failure():
    # PEG1_retry9's stored Rg_sd_max and Rg: 0.2499 against 1% of 19.861.
    entry = criteria.radonpy_criterion(0.2498677709329026, 19.86109512, 0.01, relative=True)
    assert entry["status"] == criteria.FAIL
    assert abs(entry["threshold"] - 0.1986109512) < 1e-12


def test_absolute_rule_for_vdw():
    assert criteria.radonpy_criterion(24.53, -17610.6, 30.0, relative=False)["status"] == criteria.PASS
    assert criteria.radonpy_criterion(30.01, -17610.6, 30.0, relative=False)["status"] == criteria.FAIL


def test_ungated_term_neither_passes_nor_blocks():
    assert criteria.radonpy_criterion(5.0, 1.0, None, relative=False)["status"] == criteria.NOT_GATED
    assert criteria.combine([criteria.PASS, criteria.NOT_GATED]) == criteria.PASS


def test_combine_never_reads_partial_evidence_as_pass():
    assert criteria.combine([criteria.PASS, criteria.UNEVALUABLE]) == criteria.INCOMPLETE
    assert criteria.combine([criteria.PASS, criteria.UNMEASURED]) == criteria.INCOMPLETE
    assert criteria.combine([criteria.FAIL, criteria.UNEVALUABLE]) == criteria.FAIL
    assert criteria.combine([]) == criteria.INCOMPLETE
    assert criteria.combine([criteria.NOT_GATED]) == criteria.INCOMPLETE


def test_polyjarvis_verdict_is_incomplete_when_a_binding_gate_was_unmeasured():
    assert criteria.polyjarvis_verdict([], ["density_homogeneity"]) == criteria.INCOMPLETE
    assert criteria.polyjarvis_verdict(["energy_drift"], ["density_homogeneity"]) == criteria.FAIL
    assert criteria.polyjarvis_verdict([], []) == criteria.PASS


def test_chain_rg_unwraps_image_flags_and_weights_by_mass():
    # Chain 1 straddles the boundary: x=9.5 (ix 0) and x=0.5 (ix 1) in a 10 A box are 1 A apart,
    # not 9. Masses 1 and 3 put the COM at 10.25; Rg^2 = (1*0.75^2 + 3*0.25^2)/4 = 0.1875.
    columns = ["id", "type", "mol", "x", "y", "z", "ix", "iy", "iz"]
    arr = np.array([
        [1, 1, 1, 9.5, 0.0, 0.0, 0, 0, 0],
        [2, 2, 1, 0.5, 0.0, 0.0, 1, 0, 0],
        [3, 1, 2, 5.0, 5.0, 5.0, 0, 0, 0],
    ])
    ids, rg = rg_profile.chain_rg(columns, arr, np.array([10.0, 10.0, 10.0]), {1: 1.0, 2: 3.0})
    assert list(ids) == [1, 2]
    assert abs(rg[0] - math.sqrt(0.1875)) < 1e-12
    assert rg[1] == 0.0


def test_ave_vector_file_has_the_layout_parse_ave_reads(tmp_path):
    path = tmp_path / "rg.profile"
    rg_profile.write_ave_vector(path, [0, 1000], [[1.5, 2.5], [1.6, 2.6]])
    assert path.read_text().splitlines() == [
        "# Time-averaged data for fix rg1",
        "# TimeStep Number-of-rows",
        "# Row c_gyr1",
        "0 2", "1 1.50000000", "2 2.50000000",
        "1000 2", "1 1.60000000", "2 2.60000000",
    ]


def test_read_masses_stops_at_the_next_section(tmp_path):
    data = tmp_path / "cell.data"
    data.write_text("LAMMPS data\n\n2 atom types\n\nMasses\n\n1 12.01115 # c\n2 1.00797\n\n"
                    "Pair Coeffs # lj/class2/coul/long\n\n1 0.1 3.0\n")
    assert rg_profile.read_masses(data) == {1: 12.01115, 2: 1.00797}


def test_a_truncated_final_dump_frame_is_dropped(tmp_path):
    frame = ("ITEM: TIMESTEP\n{ts}\nITEM: NUMBER OF ATOMS\n2\nITEM: BOX BOUNDS pp pp pp\n"
             "0 10\n0 10\n0 10\nITEM: ATOMS id type mol x y z ix iy iz\n")
    rows = "1 1 1 1 1 1 0 0 0\n2 1 1 2 2 2 0 0 0\n"
    dump = tmp_path / "t.dump"
    dump.write_text(frame.format(ts=0) + rows + frame.format(ts=1000) + rows.splitlines()[0] + "\n")
    frames = list(rg_profile.iter_dump_frames(dump))
    assert [f[0] for f in frames] == [0]


def test_window_stats_uses_population_sd_like_calc_rg():
    matrix = np.array([[1.0, 10.0], [3.0, 10.0], [5.0, 10.0]])
    stats = rg_profile.window_stats(matrix, width=2)
    assert stats["sd_max"] == 1.0  # np.std([3, 5]) with ddof 0
    assert stats["mean_mean"] == (4.0 + 10.0) / 2
