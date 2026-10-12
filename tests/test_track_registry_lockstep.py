"""track_registry must agree with every vocabulary it is replacing.

The property -> stage relation lived in seven hand-written places and drifted. While the shims
land, these assertions are the guard for the migration window; afterwards they are the guard for
anyone who un-shims a site or adds a stage to one table and forgets the others. A new stage name
needs FOUR lockstep updates (make_deterministic_plan.STAGE_TRACK, stage_params._STAGE_RESOLVERS,
decision_policy.track_map, recovery_agent_cli.STAGE_TRACK) and this file is what makes forgetting
one loud rather than silent.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import track_registry as tr  # noqa: E402

POLICY = json.loads((REPO_ROOT / "orchestration" / "decision_policy.json").read_text())


def test_stage_track_matches_make_deterministic_plan():
    import make_deterministic_plan as mdp
    assert tr.STAGE_TRACK == mdp.STAGE_TRACK


def test_every_registry_stage_has_a_resolver():
    """A stage the registry can route but stage_params cannot resolve halts mid-run."""
    import stage_params as sp
    assert set(tr.STAGE_TRACK) == set(sp._STAGE_RESOLVERS)


def test_stage_track_matches_decision_policy():
    """decision_policy.json is inside policy_hashes, so it is deliberately NOT generated from
    the registry -- it stays an independent second opinion that validate_run_plan checks against,
    and editing it rehashes every stage of every run on disk."""
    assert tr.STAGE_TRACK == POLICY["stage_schema_requirements"]["track_map"]


def test_track_names_match_decision_policy():
    assert set(tr.TRACKS) == set(POLICY["stage_schema_requirements"]["valid_tracks"])


def test_stage_track_matches_recovery_agent_cli():
    """recovery_agent_cli's map is tuple-valued (track, step) and additionally accepts the MACRO
    name "equilibration" as an alias -- that extra key is intentional, so compare on the resolver
    vocabulary only."""
    import recovery_agent_cli as rac
    derived = {k: v for k, v in rac.STAGE_TRACK.items() if k in tr.STAGE_TRACK}
    assert {k: v[0] for k, v in derived.items()} == tr.STAGE_TRACK
    for macro, resolver in tr.MACRO_TO_RESOLVER.items():
        if macro in rac.STAGE_TRACK:
            assert rac.STAGE_TRACK[macro][1] == resolver, macro


def test_stage_for_property_matches_the_characterization_cache():
    import write_characterization_cache as wcc
    assert {p: tr.stage_for_property(p) for p in tr.VALID_PROPERTIES} == wcc.STAGE_FOR_PROPERTY


def test_valid_properties_matches_scientific_control():
    import scientific_control as sc
    assert tr.VALID_PROPERTIES == sc.VALID_PROPERTIES


def test_macro_stages_are_a_subsequence_of_stage_order():
    """_dependencies and invalidate_from rely on macro-stage ORDER, so the registry's track
    ordering must never emit a sequence STAGE_ORDER does not contain."""
    import workflow_engine as we
    for props in ({"density"}, {"tg"}, {"bulk_modulus"}, {"density", "tg", "bulk_modulus"}):
        positions = [we.STAGE_ORDER.index(s) for s in tr.macro_stages_for(props)]
        assert positions == sorted(positions), props


@pytest.mark.parametrize("name", sorted(tr.OBSERVABLES))
def test_forced_params_are_registered_in_parameter_stage(name):
    """An unregistered decided_params key falls through PARAMETER_STAGE.get(key, "build") and
    invalidates the BUILD -- so a purely-mechanical routing pin would rebuild the cell on every
    resume. The stronger half is the second assertion: the key must belong to a stage inside the
    observable's own track, or it is mis-scoped even though it is registered."""
    import workflow_engine as we
    obs = tr.OBSERVABLES[name]
    for key in obs.forced_params:
        assert key in we.PARAMETER_STAGE, f"{name} pins unregistered param {key!r}"
        assert we.PARAMETER_STAGE[key] in tr.TRACKS[obs.track].macro_stages, (
            f"{name} pins {key!r}, which hashes to {we.PARAMETER_STAGE[key]!r} -- outside its "
            f"own track {obs.track!r}"
        )


# ─── internal consistency ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(tr.OBSERVABLES))
def test_every_observable_names_a_real_track(name):
    assert tr.OBSERVABLES[name].track in tr.TRACKS


@pytest.mark.parametrize("name", sorted(tr.OBSERVABLES))
def test_byproducts_are_non_blocking_and_share_their_producers_track(name):
    obs = tr.OBSERVABLES[name]
    if obs.kind != "byproduct":
        return
    assert obs.blocking is False
    producer = tr.OBSERVABLES[obs.produced_by]
    assert producer.kind == "requestable"
    assert producer.track == obs.track, (
        f"{name} is billed as free with {obs.produced_by} but sits on a different track"
    )


def test_requestables_are_blocking():
    for o in tr.OBSERVABLES.values():
        if o.kind == "requestable":
            assert o.blocking is True, o.name


@pytest.mark.parametrize("props", [{"density"}, {"tg"}, {"bulk_modulus"},
                                   {"density", "tg", "bulk_modulus"}],
                         ids=lambda p: "+".join(sorted(p)))
def test_routing_is_order_stable_and_bookended(props):
    tracks = tr.tracks_for(props)
    assert tracks[0] == "foundation" and tracks[-1] == "summary"
    assert list(tracks) == sorted(tracks, key=lambda n: tr.TRACKS[n].order)


@pytest.mark.parametrize("props", [{"density"}, {"tg"}, {"bulk_modulus"},
                                   {"density", "tg", "bulk_modulus"}],
                         ids=lambda p: "+".join(sorted(p)))
def test_the_plan_list_is_the_executable_list_minus_fallbacks(props):
    """The single distinction that reconciles the drift: `deform` is routable, resolvable and
    priceable, but is never its own plan entry."""
    executable = tr.resolver_stages_for(props, include_fallbacks=True)
    planned = tr.planned_stage_names(props)
    fallbacks = {s.name for t in tr.TRACKS.values() for s in t.stages if s.role == "fallback"}
    assert [s for s in executable if s not in fallbacks] == planned


# ─── the deformation moduli, requestable by name ──────────────────────────────────

def test_the_deformation_moduli_are_requestable():
    """G/E/nu are already computed and already saved on every deformation run -- the extractor
    emits G_GPa/E_GPa/nu_Poisson and run_campaign already dispatches on mechanical_method. Making
    them requestable is three table entries, no new simulation stage, no decision_policy edit,
    and therefore no pipeline-wide rehash."""
    for name in ("shear_modulus", "youngs_modulus", "poisson_ratio"):
        obs = tr.OBSERVABLES[name]
        assert obs.kind == "requestable" and obs.status == "wired"
        assert obs.legacy_property == name, "requestable by its own name, not via bulk_modulus"
        assert name in tr.VALID_PROPERTIES
        assert obs.forced_params == {"mechanical_method": "deformation"}


def test_requesting_a_deformation_modulus_swaps_deform_in_for_murnaghan():
    """Otherwise the plan would name murnaghan with a chain_submitted criterion while
    run_campaign dispatched do_deformation -- an artifact disagreeing with the run it describes,
    which is the exact class of bug this registry exists to end."""
    assert tr.planned_stage_names({"bulk_modulus"})[-3:] == ["murnaghan", "analyze-bm",
                                                             "run-summary"]
    assert tr.planned_stage_names({"shear_modulus"})[-3:] == ["deform", "analyze-bm",
                                                              "run-summary"]


def test_bulk_modulus_alongside_a_deformation_modulus_is_not_a_conflict():
    """One deformation run satisfies both -- extract_bulk_modulus_deform emits K_GPa alongside
    G/E/nu. So the pair resolves to the deform path rather than raising."""
    assert tr.forced_params_for({"bulk_modulus", "shear_modulus"}) == {
        "mechanical_method": "deformation"}
    assert "deform" in tr.planned_stage_names({"bulk_modulus", "shear_modulus"})


def test_all_means_the_default_suite_not_every_nameable_property():
    """--properties all must not silently switch a run's bulk modulus from the Murnaghan EOS fit
    to a deformation fit. Those are different measurements with different gates, and folding the
    new names into "all" would make that choice for every existing caller."""
    assert tr.DEFAULT_PROPERTIES == {"density", "tg", "bulk_modulus"}
    assert tr.DEFAULT_PROPERTIES < tr.VALID_PROPERTIES
    assert tr.forced_params_for(tr.DEFAULT_PROPERTIES) == {}
