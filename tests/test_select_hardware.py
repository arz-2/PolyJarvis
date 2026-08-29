"""
select_hardware.py -- D-08 hardware selection now prices its one real candidate config
(by_forcefield[fam], which IS the config recommended_by_ff/size_points measured) via
cost_model.py's real multi-point interpolation instead of a hand-rolled single-point
in-window check. _monomer_atoms_and_mw shells into RDKit/conda -- monkeypatched everywhere
here, same convention as tests/test_select_system_size.py.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import select_hardware as sh  # noqa: E402


def test_in_window_cell_gets_high_confidence_and_no_uncertainty(monkeypatch):
    monkeypatch.setattr(sh, "_monomer_atoms_and_mw", lambda smiles, is_ua: (10, 100.0))
    # "high" confidence requires a host-matched box too (cost_model.estimate_ns_per_day());
    # this test is about the in-window check, not live GPU fingerprinting, so pin it True --
    # same convention tests/test_cost_model.py already uses throughout.
    monkeypatch.setattr(sh.cost_model, "host_matches", lambda rules: True)
    # PACR/pcff has real size_points bracketing [3020, 15040]; dp=50*nchain=15 -> 7500 atoms.
    result = sh.select_hardware("PACR", "*CC(C)(C(=O)OC)*", dp_typical=50, nchain=15)
    assert result["decision"]["confidence"] == "high"
    assert result["uncertainties"] == []
    assert result["decision"]["choice"] == {"engine": "kokkos", "gpu_per_run": 1, "mpi_ranks": 1}
    assert result["cell_atoms_estimate"] == 7500


def test_out_of_range_cell_gets_low_confidence_and_uncertainty(monkeypatch):
    monkeypatch.setattr(sh, "_monomer_atoms_and_mw", lambda smiles, is_ua: (10, 100.0))
    # dp=200*nchain=18 -> 36000 atoms, well outside the measured [3020,15040] pcff range.
    result = sh.select_hardware("PACR", "*CC(C)(C(=O)OC)*", dp_typical=200, nchain=18)
    assert result["decision"]["confidence"] == "low"
    assert any(u["name"] == "hardware_optimum" for u in result["uncertainties"])
    # Still the by_forcefield default -- there is no priced alternate config to switch to.
    assert result["decision"]["choice"] == {"engine": "kokkos", "gpu_per_run": 1, "mpi_ranks": 1}


def test_family_with_no_benchmark_data_degrades_to_none_confidence_not_an_error(monkeypatch):
    monkeypatch.setattr(sh, "_monomer_atoms_and_mw", lambda smiles, is_ua: (10, 100.0))
    # PURA/gaff has no recommended_by_ff or size_points entry at all in polymer_rules.json.
    result = sh.select_hardware("PURA", "*NC(=O)N*", dp_typical=50, nchain=10)
    assert "error" not in result
    assert result["decision"]["confidence"] == "none"
    assert result["decision"]["evidence"][0]["basis"] == "no benchmark data exists for 'gaff' at all"
    assert any(u["name"] == "hardware_optimum" for u in result["uncertainties"])


def test_small_cell_floor_forces_one_gpu_regardless_of_family_default(monkeypatch):
    monkeypatch.setattr(sh, "_monomer_atoms_and_mw", lambda smiles, is_ua: (10, 100.0))
    monkeypatch.setattr(sh, "hardware_policy", lambda rules=None: {
        "values_are_benchmarked": True,
        "ff_aliases": {"testff": "pcff"},
        "by_forcefield": {"pcff": {"engine": "gpu", "mpi": 4, "gpu_per_run": 2}},
        "directional_probe": {},
    })
    monkeypatch.setattr(sh, "get_class_entry",
                        lambda rules, cls, warn_on_miss=False: {"preferred_ff": "testff"})
    # dp=5*nchain=5 -> 250 atoms, far under the 10k floor.
    result = sh.select_hardware("ANYCLASS", "*CC*", dp_typical=5, nchain=5)
    assert result["decision"]["choice"]["gpu_per_run"] == 1
    assert result["decided_params_override"]["gpu_per_run"] == 1
    assert any("< 10k" in e["claim"] for e in result["decision"]["evidence"])
