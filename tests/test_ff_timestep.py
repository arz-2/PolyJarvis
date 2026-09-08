"""The integration timestep belongs to the FORCE FIELD, not the polymer class.

dt_fs sat on all 21 class entries in polymer_rules.json as a perfect function of
ff_accuracy_prior -- 21 copies of 5 facts, with nothing keeping them in step. It is set by
the fastest vibration the field has to integrate: united-atom fields carry no explicit
hydrogens, so their fastest mode is a heavy-atom stretch and 2 fs is stable, while every
all-atom field here has explicit C-H and needs 1 fs.

The duplication was not the main problem. The class carries the force-field PRIOR, while the
run integrates with the field D-01 actually resolved for THIS SMILES -- so when the probe
cascades to another field, the class's dt stops describing what runs.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from rules_common import (DEFAULT_TIMESTEP_FS, FF_TIMESTEP_FS,  # noqa: E402
                          hardware_policy, load_rules, timestep_fs)

CLASSES = load_rules()["classes"]


@pytest.mark.parametrize("cls", sorted(CLASSES), ids=sorted(CLASSES))
def test_derived_timestep_reproduces_every_curated_class(cls):
    """The refactor must move no run's numbers. All 21 classes derive to what they stored."""
    entry = CLASSES[cls]
    assert timestep_fs(entry["ff_accuracy_prior"]) == entry["dt_fs"], cls


def test_united_atom_is_the_only_family_that_gets_two_femtoseconds():
    two_fs = {k for k, v in FF_TIMESTEP_FS.items() if v == 2.0}
    assert two_fs == {"trappe"}, "only the united-atom family may integrate at 2 fs"


def test_an_unknown_field_falls_back_to_the_conservative_value():
    """Never 2 fs: an over-long timestep is a silent integration error, not a slow run."""
    assert timestep_fs("some-field-invented-tomorrow") == DEFAULT_TIMESTEP_FS == 1.0
    assert timestep_fs("") == DEFAULT_TIMESTEP_FS
    assert timestep_fs(None) == DEFAULT_TIMESTEP_FS


def test_the_timestep_follows_the_resolved_field_not_the_class_prior():
    """The case the refactor exists for. A PHYC SMILES whose probe cascades off trappe-ua to
    an all-atom field must integrate at 1 fs, even though its class prior says 2."""
    assert CLASSES["PHYC"]["ff_accuracy_prior"] == "trappe-ua"
    assert CLASSES["PHYC"]["dt_fs"] == 2.0
    assert timestep_fs("pcff") == 1.0
    assert timestep_fs("opls/2024/opls-aa") == 1.0


def test_the_plan_records_the_timestep_of_the_field_it_resolved():
    """_derived_from_field is the single place everything the field implies is computed."""
    from make_deterministic_plan import _derived_from_field
    rules = load_rules()
    assert _derived_from_field("trappe-ua", rules)["dt_fs"] == 2.0
    assert _derived_from_field("pcff", rules)["dt_fs"] == 1.0
    # ...and it stays alongside the other field-derived properties, not beside them
    derived = _derived_from_field("trappe-ua", rules)
    assert {"charge_method", "electrostatics", "dt_fs", "ff_family"} <= set(derived)


def test_every_family_the_hardware_policy_names_has_a_timestep():
    """A field family with no entry silently gets the 1 fs fallback, which is safe but wrong
    for a united-atom field -- so every family the router can produce must be named here."""
    families = set(hardware_policy().get("by_forcefield", {}))
    missing = families - set(FF_TIMESTEP_FS)
    assert not missing, f"families with no declared timestep: {missing}"


def test_the_sampling_floor_is_not_derived_from_the_rate():
    """tg_min_steps_per_T is an independent FLOOR and must stay one.

    It equals dT/(rate*dt) for every class that carries it, which invites deriving it -- and
    deriving it destroys the guard, because workflow_engine and scientific_control check a
    proposed remedy against it precisely to catch a change to the rate or the step. A floor
    computed from the rate moves with it and can never bind.

    PSIL shows the numbers are a floor, not a restatement: rate 50 K/ns over a 20 K step is
    0.4 ns per bin against a 0.2 ns floor.
    """
    import rules_common
    assert not hasattr(rules_common, "tg_steps_per_bin")
    psil = CLASSES["PSIL"]
    implied_ns = 20.0 / psil["tg_rate_K_per_ns"]
    floor_ns = psil.get("tg_min_steps_per_T", 200000) * psil["dt_fs"] / 1e6
    assert implied_ns > floor_ns, "PSIL's rate should exceed its floor, not equal it"
