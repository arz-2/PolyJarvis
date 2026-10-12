"""
calibrate_hardware._carry_provenance -- what survives a directional_probe rebuild.

`size_points` is this box's MEASURED ns/day-vs-atoms curve, and select_hardware._size_points
prefers it over the freshly measured single point while reporting "high" confidence as soon as
hardware_policy.host matches. Since a calibration overwrites `host` with the box it just ran on,
carrying size_points across a host change would make the cost model quote the OLD machine's
throughput at high confidence on hardware it never ran on. It must be dropped on a host change;
`kokkos_offload_study` is hand-authored cross-host rationale and must NOT be.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "hardware"))

import calibrate_hardware as ch  # noqa: E402

THIS_HOST = {"gpus": 4, "gpu_model": "Quadro RTX 6000", "phys_cores": 18}
PRIOR_PROBE = {
    "kokkos_offload_study": {"gate": "GREEN"},
    "size_points": {"pcff": [{"atoms": 3020, "ns_per_day": 42.3},
                             {"atoms": 15040, "ns_per_day": 17.4}]},
    "measured_on": "4x Quadro RTX 6000 / 18 phys cores",
}


def test_same_host_matches_a_differently_formatted_gpu_model():
    # nvidia-smi says "Quadro RTX 6000"; the saved policy says "... 24GB". Same card.
    assert ch._same_host({"gpus": 4, "gpu_model": "Quadro RTX 6000 24GB",
                          "phys_cores": 18}, THIS_HOST)


def test_same_host_rejects_a_different_box_and_an_uncalibrated_policy():
    assert not ch._same_host({**THIS_HOST, "phys_cores": 64}, THIS_HOST)
    assert not ch._same_host({"gpus": 2, "gpu_model": "A100", "phys_cores": 18}, THIS_HOST)
    assert not ch._same_host(None, THIS_HOST)      # fresh clone, never calibrated anywhere
    assert not ch._same_host({}, THIS_HOST)


def test_size_points_survive_a_recalibration_on_the_same_host():
    probe = {}
    note = ch._carry_provenance(PRIOR_PROBE, probe, same_host=True)
    assert probe["size_points"] == PRIOR_PROBE["size_points"]
    assert note is None


def test_size_points_are_dropped_when_the_host_changed():
    probe = {}
    note = ch._carry_provenance(PRIOR_PROBE, probe, same_host=False)
    assert "size_points" not in probe, (
        "another machine's measured throughput curve must not be carried onto this box -- "
        "select_hardware would prefer it over the fresh measurement and call it high confidence")
    assert note and "size_points DROPPED" in note
    assert "--size-points" in note, "the note must say how to re-measure"


def test_engine_rationale_always_survives_because_it_is_not_a_measurement():
    for same_host in (True, False):
        probe = {}
        ch._carry_provenance(PRIOR_PROBE, probe, same_host=same_host)
        assert probe["kokkos_offload_study"] == {"gate": "GREEN"}


def test_carry_over_is_silent_when_there_were_no_prior_size_points():
    probe = {}
    assert ch._carry_provenance({"kokkos_offload_study": {}}, probe, same_host=False) is None


# --- --size-points: turning timed records into an interpolatable curve -----------------

def _rec(fam, atoms, ns, size_point=False, status="ok"):
    return {"ff": fam, "atoms": atoms, "ns_per_day": ns, "status": status,
            "engine": "kokkos", "mpi": 1, "gpu_per_run": 1, "size_point": size_point}


def test_a_family_measured_at_several_sizes_gets_a_sorted_curve():
    curves = ch._fresh_size_curves([
        _rec("pcff", 15040, 17.384, size_point=True),
        _rec("pcff", 3020, 42.269),                      # base cell, measured with parity
        _rec("pcff", 5140, 30.63, size_point=True),
    ])
    assert [p["atoms"] for p in curves["pcff"]] == [3020, 5140, 15040]
    assert curves["pcff"][0]["ns_per_day"] == 42.269


def test_a_single_measured_size_writes_no_curve():
    # select_hardware._size_points needs 2 points to interpolate; a lone point in the JSON
    # would read as a curve it is not. This is the plain --revalidate case.
    assert ch._fresh_size_curves([_rec("pcff", 3020, 42.269)]) == {}


def test_a_family_missing_its_size_cells_is_omitted_not_half_written():
    curves = ch._fresh_size_curves([
        _rec("pcff", 3020, 42.269), _rec("pcff", 15040, 17.384, size_point=True),
        _rec("gaff", 3000, 20.0),                        # no CALIB_GAFF_5K/_15K in-repo
    ])
    assert "pcff" in curves and "gaff" not in curves


def test_repeated_atom_counts_do_not_fake_a_second_point():
    assert ch._fresh_size_curves([_rec("pcff", 3020, 42.0), _rec("pcff", 3020, 41.0)]) == {}


def test_records_without_a_throughput_number_are_ignored():
    curves = ch._fresh_size_curves([
        _rec("pcff", 3020, 42.269), _rec("pcff", 5140, None, size_point=True)])
    assert curves == {}
