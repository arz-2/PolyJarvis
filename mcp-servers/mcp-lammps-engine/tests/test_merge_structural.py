"""_merge_structural combines two run_structural_analysis() results -- the primary
(fixed-volume NVT, e.g. nvt_kinetic_stability) trajectory and the struct (e.g. npt_final)
trajectory -- into the one dict check_equilibration_comprehensive.py reports.

Ensemble-insensitive per-frame geometry (rg/ree/msid/torsion/p2/density_homogeneity/
backbone_type_coverage) must come from the struct trajectory; MSD/kinetic-trap and C(t)
must stay on the primary trajectory, since a barostatted trajectory affine-scales
coordinates every step and would contaminate cumulative CoM displacement / end-to-end-
vector autocorrelation. A regression here would silently pull MSD back onto an NPT
trajectory, exactly the bug the 8-stage adaptive equilibration redesign moved MSD off of.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent / "analysis_scripts"
sys.path.insert(0, str(REPO))

from check_equilibration_comprehensive import _merge_structural, _STRUCT_SOURCED_KEYS  # noqa: E402


def _fake_structural(tag):
    return {
        "rg": f"rg-{tag}", "ree": f"ree-{tag}", "msid": f"msid-{tag}",
        "torsion": f"torsion-{tag}", "p2": f"p2-{tag}",
        "density_homogeneity": f"density_homogeneity-{tag}",
        "backbone_type_coverage": f"backbone_type_coverage-{tag}",
        "ct": f"ct-{tag}", "msd": f"msd-{tag}",
    }


def test_struct_sourced_keys_come_from_struct_trajectory():
    primary = _fake_structural("primary")
    struct = _fake_structural("struct")
    merged = _merge_structural(primary, struct)
    for key in _STRUCT_SOURCED_KEYS:
        assert merged[key] == f"{key}-struct", key


def test_ensemble_sensitive_keys_stay_on_primary_trajectory():
    primary = _fake_structural("primary")
    struct = _fake_structural("struct")
    merged = _merge_structural(primary, struct)
    assert merged["msd"] == "msd-primary"
    assert merged["ct"] == "ct-primary"


def test_struct_sourced_keys_cover_every_field_build_d05_and_result_consume():
    # Locks the exact key set -- a silent addition/removal here would either leak an
    # ensemble-sensitive field onto the wrong trajectory or leave a new field un-merged.
    assert set(_STRUCT_SOURCED_KEYS) == {
        "rg", "ree", "msid", "torsion", "p2", "density_homogeneity",
        "backbone_type_coverage",
    }
