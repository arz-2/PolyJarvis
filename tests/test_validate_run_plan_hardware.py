"""
_hardware_findings' gpu_per_run>=2 gate. select_hardware.py's D-08 confidence now comes from
cost_model's real multi-point ns_per_day interpolation (see select_hardware.py's Phase 3
rewrite) -- but every real measured point (recommended_by_ff and size_points) so far used
gpu_per_run=1, so "high confidence" describes the ns_per_day number at a given atom count,
not evidence that a >=2-GPU pin is benchmarked. This file locks in that these are treated as
separate claims (advisor-caught regression: the old check conflated them and would have
silently stopped firing once D-08 moved to real interpolation for in-range cells).
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import validate_run_plan as vrp  # noqa: E402


def _plan(**decided_params):
    return {"smiles": "*CC(C)(C(=O)OC)*", "polymer_class": "PACR",
            "decided_params": decided_params, "decisions": []}


def _fake_select_hardware(confidence, cell_atoms, ff_family="pcff"):
    # Signature mirrors select_hardware exactly, `field` included: the real call passes it
    # positionally, and a fake that silently swallowed it would fail the check open.
    def _inner(polymer_class, smiles, dp_typical, nchain, field=None):
        choice = {"engine": "kokkos", "gpu_per_run": 1, "mpi_ranks": 1}
        return {"decision": {"id": "D-08_hardware", "choice": choice,
                             "confidence": confidence, "evidence": [], "alternatives": []},
                "decided_params_override": {}, "uncertainties": [],
                "cell_atoms_estimate": cell_atoms, "ff_family": ff_family}
    return _inner


def test_gpu_pin_2_flags_even_at_high_confidence_when_no_gpu2_point_exists(monkeypatch):
    monkeypatch.setattr(vrp, "select_hardware", _fake_select_hardware("high", 12000))
    monkeypatch.setattr(vrp, "hardware_policy", lambda rules: {"directional_probe": {
        "recommended_by_ff": {"pcff": {"gpu": 1}}, "size_points": {"pcff": [{"gpu": 1}]}}})
    findings = vrp._hardware_findings(_plan(gpu_per_run=2, engine="kokkos", mpi_ranks=1))
    assert any(f["check"] == "hardware_size_mismatch" for f in findings)


def test_gpu_pin_2_does_not_flag_when_a_real_point_used_gpu2(monkeypatch):
    monkeypatch.setattr(vrp, "select_hardware", _fake_select_hardware("high", 12000))
    monkeypatch.setattr(vrp, "host_matches", lambda rules: True)
    monkeypatch.setattr(vrp, "hardware_policy", lambda rules: {"directional_probe": {
        "recommended_by_ff": {"pcff": {"gpu": 2}}, "size_points": {}}})
    findings = vrp._hardware_findings(_plan(gpu_per_run=2, engine="kokkos", mpi_ranks=1))
    assert not any(f["check"] == "hardware_size_mismatch" for f in findings)


def test_gpu_pin_2_flags_on_host_mismatch_even_with_a_real_gpu2_point(monkeypatch):
    monkeypatch.setattr(vrp, "select_hardware", _fake_select_hardware("high", 12000))
    monkeypatch.setattr(vrp, "host_matches", lambda rules: False)
    monkeypatch.setattr(vrp, "hardware_policy", lambda rules: {"directional_probe": {
        "recommended_by_ff": {"pcff": {"gpu": 2}}, "size_points": {}}})
    findings = vrp._hardware_findings(_plan(gpu_per_run=2, engine="kokkos", mpi_ranks=1))
    assert any(f["check"] == "hardware_size_mismatch" for f in findings)


def test_gpu_pin_2_still_flags_on_small_cell_regardless_of_benchmark(monkeypatch):
    monkeypatch.setattr(vrp, "select_hardware", _fake_select_hardware("high", 5000))
    monkeypatch.setattr(vrp, "hardware_policy", lambda rules: {"directional_probe": {
        "recommended_by_ff": {"pcff": {"gpu": 2}}, "size_points": {}}})
    findings = vrp._hardware_findings(_plan(gpu_per_run=2, engine="kokkos", mpi_ranks=1))
    assert any(f["check"] == "hardware_size_mismatch" and "< 10k" in f["detail"]
               for f in findings)


def test_family_has_multi_gpu_benchmark_checks_size_points_too(monkeypatch):
    monkeypatch.setattr(vrp, "host_matches", lambda rules: True)
    monkeypatch.setattr(vrp, "hardware_policy", lambda rules: {"directional_probe": {
        "recommended_by_ff": {"pcff": {"gpu": 1}},
        "size_points": {"pcff": [{"gpu": 1}, {"gpu": 2}]}}})
    assert vrp._family_has_multi_gpu_benchmark("pcff") is True


def test_family_has_multi_gpu_benchmark_false_when_all_points_are_gpu1(monkeypatch):
    monkeypatch.setattr(vrp, "host_matches", lambda rules: True)
    monkeypatch.setattr(vrp, "hardware_policy", lambda rules: {"directional_probe": {
        "recommended_by_ff": {"pcff": {"gpu": 1}},
        "size_points": {"pcff": [{"gpu": 1}, {"gpu": 1}]}}})
    assert vrp._family_has_multi_gpu_benchmark("pcff") is False


def test_family_has_multi_gpu_benchmark_false_on_host_mismatch_regardless_of_data(monkeypatch):
    monkeypatch.setattr(vrp, "host_matches", lambda rules: False)
    monkeypatch.setattr(vrp, "hardware_policy", lambda rules: {"directional_probe": {
        "recommended_by_ff": {"pcff": {"gpu": 2}}, "size_points": {}}})
    assert vrp._family_has_multi_gpu_benchmark("pcff") is False
