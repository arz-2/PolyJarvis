"""Schema/integrity tests for guides/polymer_rules.json.

The orchestrator hard-depends on this file's structure to route builders and set
simulation parameters for all 21 PoLyInfo polymer classes. A malformed entry (a
missing key, a non-numeric temperature, an inverted Tg sweep range) would surface
as a confusing mid-run failure rather than an obvious data error, so we validate
the schema directly.
"""
import json
from pathlib import Path

import pytest

RULES_PATH = Path(__file__).resolve().parent.parent / "guides" / "polymer_rules.json"
RULES = json.loads(RULES_PATH.read_text())
CLASSES = RULES["classes"]

# Keys the orchestrator/workers read for every class (confirmed present across
# both EMC- and RadonPy-routed classes).
REQUIRED_KEYS = [
    "name",
    "preferred_builder",
    "preferred_ff",
    "forcefield",
    "charge_method",
    "dp_typical",
    "dp_min",
    "nchain",
    "density_initial_gcm3",
    "electrostatics",
    "cutoff_A",
    "dt_fs",
    "T_equil_K",
    "tg_t_high_K",
    "tg_t_low_K",
    "tg_t_step_K",
]


def test_has_expected_class_count():
    assert len(CLASSES) == 21


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_required_keys_present(cid):
    missing = [k for k in REQUIRED_KEYS if k not in CLASSES[cid]]
    assert not missing, f"{cid} missing required keys: {missing}"


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_numeric_fields_in_range(cid):
    e = CLASSES[cid]
    assert 0.1 <= e["density_initial_gcm3"] <= 2.5, "initial density out of plausible range"
    assert e["dp_min"] <= e["dp_typical"], "dp_min must not exceed dp_typical"
    assert e["nchain"] >= 1
    assert e["T_equil_K"] > 0
    assert e["dt_fs"] > 0
    assert e["cutoff_A"] > 0


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_tg_sweep_window_is_valid(cid):
    e = CLASSES[cid]
    assert e["tg_t_low_K"] < e["tg_t_high_K"], "Tg sweep low bound must be below high bound"
    assert e["tg_t_step_K"] > 0
    span = e["tg_t_high_K"] - e["tg_t_low_K"]
    assert e["tg_t_step_K"] <= span, "step size larger than the whole sweep window"


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_routing_fields_are_known(cid):
    e = CLASSES[cid]
    assert e["preferred_builder"] in {"emc", "radonpy"}
    assert e["electrostatics"] in {"pppm", "lj_cut"}


# The force-field label and charge handling are NOT independent facts — they are
# determined by (preferred_builder, preferred_ff). Storing them as free fields let
# them drift (10+ classes once read forcefield=GAFF2_mod / charge_method=RESP while
# actually building EMC/PCFF). These invariants pin the derived fields to the route
# so any future drift fails CI instead of surfacing as a wrong mid-run build.
EMC_FF_LABEL = {
    "pcff": "PCFF",
    "opls-aa/2024": "OPLS-AA",
    "trappe-ua": "TraPPE-UA",
}


@pytest.mark.parametrize("cid", sorted(CLASSES))
def test_build_route_consistency(cid):
    e = CLASSES[cid]
    builder, pref_ff = e["preferred_builder"], e["preferred_ff"]
    if builder == "emc":
        # EMC cannot build GAFF2 — it needs one of its own all-atom/UA fields,
        # and it embeds force-field charges directly (no separate charge job).
        assert pref_ff in EMC_FF_LABEL, (
            f"{cid}: EMC build requires an EMC field, got preferred_ff={pref_ff!r}"
        )
        assert e["forcefield"] == EMC_FF_LABEL[pref_ff], (
            f"{cid}: forcefield={e['forcefield']!r} inconsistent with "
            f"preferred_ff={pref_ff!r} (expected {EMC_FF_LABEL[pref_ff]!r})"
        )
        assert e["charge_method"] == "none", (
            f"{cid}: EMC embeds charges → charge_method must be 'none', "
            f"got {e['charge_method']!r}"
        )
    else:  # radonpy — runs a real charge-assignment job with a GAFF2 field
        assert pref_ff in {"GAFF2", "GAFF2_mod"}, (
            f"{cid}: RadonPy route expects a GAFF2 field, got preferred_ff={pref_ff!r}"
        )
        assert e["forcefield"] in {"GAFF2", "GAFF2_mod"}
        assert e["charge_method"] in {"RESP", "AM1-BCC"}, (
            f"{cid}: RadonPy runs a charge job → charge_method must be RESP/AM1-BCC, "
            f"got {e['charge_method']!r}"
        )
