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
