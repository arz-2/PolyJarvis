"""Single authority for: which stages a requested property needs, and what else you get free.

WHY THIS EXISTS. The property -> stage relation was written out by hand in seven places
(build_planned_stages, WorkflowEngine.enabled_stages, two dry-run branches in run_campaign,
validate_run_plan's coverage check, cost_model's pricing, decision_policy's track_map) and they
drifted: both dry-run branches emit a standalone `deform` stage that build_planned_stages never
produces, so `--dry-run` prints a stage list no real run executes -- and cost_model gates its
deform price on that same absent name, leaving the fallback silently unpriced.

WHAT IT OWNS. Vocabulary and topology only: stage names, their order, track membership,
primary-vs-fallback role, property -> track routing, and which extractor field carries each
observable.

WHAT IT DOES NOT OWN. Any science. Numeric success_criteria, the glassy_hint predicate that
decides whether a murnaghan entry carries its deform fallback, temperature schedules -- all of
those need `cls`/`smiles` and stay with their current callers. Shims import this module; this
module imports nothing repo-local.

STDLIB ONLY, deliberately. workflow_engine is hermetic apart from a sys.path import of
protocol_policy, and a benchmark scorer must be able to import this by path without dragging in
polymer_rules.json or RDKit.

THE TRACK MODEL. A track owns a bundle of observables. Requesting one observable runs its whole
track, so everything else that track produces comes free -- a Tg request already computes thermal
expansion and a density at every temperature in the sweep. Those are BYPRODUCTS: gated on their
own terms, reported marked, never able to fail a run that did not ask for them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

REGISTRY_VERSION = "track-registry-v1"
"""Documentation only. Deliberately NOT threaded into policy_hashes or _input_hash -- if it were,
every edit to this file would invalidate every stage of every resumable run on disk."""


# ─── data model ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ResolverStage:
    """One stage_params._STAGE_RESOLVERS key, and where it sits."""

    name: str
    track: str
    macro: str
    role: str = "primary"
    """"primary" -> emitted as its own planned_stages entry.
    "fallback" -> resolvable, routable and PRICEABLE, but never its own plan entry. `deform` is
    the only one: build_planned_stages attaches it as {"fallback": "deform"} on the murnaghan
    entry when the class is glassy. Consumers that want the executable vocabulary (both dry-run
    branches, cost_model, track_map) take every role; the plan artifact takes primaries only.
    That one distinction is what reconciles the drift without changing either behaviour."""


@dataclass(frozen=True)
class Track:
    """A bundle of observables that one run of one stage-sequence produces."""

    name: str
    order: int
    stages: tuple[ResolverStage, ...]
    macro_stages: tuple[str, ...]
    always: bool = False
    requires: tuple[str, ...] = ()
    """Tracks that must run for THIS track to be able to run, even though no observable of
    theirs was requested. Exists for exactly one relation: mechanical needs a cell at
    bm_temperature_K, which only the cooling track produces, and no mechanical observable maps
    onto the cooling track. Closed over transitively by _tracks_for.

    Every named track must have a STRICTLY LOWER order, so macro_stages_for stays a
    STAGE_ORDER subsequence -- _dependencies and invalidate_from depend on that."""
    note: str = ""


@dataclass(frozen=True)
class Observable:
    name: str
    track: str
    kind: str                       # "requestable" | "byproduct"
    extractor_json: str
    extractor_field: str
    unit: str
    status: str = "wired"           # "wired" | "declared" (routing exists, stages do not yet)
    produced_by: Optional[str] = None      # byproducts only: the request that yields them
    gate_macro_stage: str = ""
    gate_field: Optional[str] = None
    legacy_property: Optional[str] = None  # the plan["properties"] name this maps onto
    summary_path: Optional[tuple[str, ...]] = None
    forced_params: Mapping[str, object] = field(default_factory=dict)
    """decided_params keys this observable pins. EVERY key must be registered in
    workflow_engine.PARAMETER_STAGE or it hashes as "build" and invalidates the whole pipeline
    on the next resume -- guarded by test_track_registry_lockstep."""
    note: str = ""

    @property
    def blocking(self) -> bool:
        """A byproduct is non-blocking BY CONSTRUCTION, not by configuration."""
        return self.kind == "requestable"


# ─── tracks ───────────────────────────────────────────────────────────────────────

_FOUNDATION = Track(
    name="foundation", order=0, always=True,
    stages=(ResolverStage("build", "foundation", "build"),
            ResolverStage("equil", "foundation", "equilibration"),
            ResolverStage("equil-check", "foundation", "equilibration")),
    macro_stages=("build", "equilibration"),
    note="Ends at the MELT HOLD: npt_melt_hold (the gated cell, where melt density is measured) "
         "followed by nvt_melt_hold (the fixed-volume window MSD/C(t) need, and the cell every "
         "downstream track starts from). The descent to final_T_K is the cooling track's job.",
)

_COOLING = Track(
    name="cooling", order=1,
    stages=(ResolverStage("cool", "cooling", "cooling"),
            ResolverStage("cool-check", "cooling", "cooling")),
    macro_stages=("cooling",),
    note="The blockwise descent from the melt hold to final_T_K, then nvt_kinetic_stability and "
         "npt_final -- the assessment cell, carrying the gate set that used to be the only one. "
         "Runs only when something needs a cell at the assessment temperature: a density at "
         "final_T_K, or any mechanical property (see _MECHANICAL.requires).",
)

_THERMAL = Track(
    name="thermal", order=2,
    stages=(ResolverStage("tg", "thermal", "thermal"),
            ResolverStage("analyze-tg", "thermal", "thermal")),
    macro_stages=("thermal",),
    note="The staircase is a continuous cooling run from the MELT HOLD down to tg_t_low_K, at "
         "the same rate the cooling track descends at (see "
         "stage_params.rate_matched_cool_block_hold_steps). It starts from a named, gated stage "
         "rather than a mid-ramp waypoint, so it needs neither a tagged cool_block nor a reheat "
         "probe, and it does NOT depend on the cooling track.",
)

_MECHANICAL = Track(
    name="mechanical", order=3,
    stages=(ResolverStage("murnaghan", "mechanical", "mechanical"),
            ResolverStage("deform", "mechanical", "mechanical", role="fallback"),
            ResolverStage("analyze-bm", "mechanical", "mechanical")),
    macro_stages=("mechanical",),
    requires=("cooling",),
    note="Starts from the COOLING track's npt_final cell, NEVER a thermal staircase waypoint: "
         "npt_final is the gated cell at the assessment temperature, a waypoint is an ungated "
         "mid-sweep transient, and for a high-Tg class the sweep floor sits above "
         "bm_temperature_K so no such waypoint exists. The modulus is measured at "
         "bm_temperature_K, which only the cooldown reaches -- hence `requires`.",
)

_SUMMARY = Track(
    name="summary", order=4, always=True,
    stages=(ResolverStage("run-summary", "summary", "summary"),),
    macro_stages=("summary",),
)

TRACKS: dict[str, Track] = {t.name: t for t in
                            (_FOUNDATION, _COOLING, _THERMAL, _MECHANICAL, _SUMMARY)}

for _t in TRACKS.values():
    for _r in _t.requires:
        assert _r in TRACKS, f"{_t.name} requires unknown track {_r!r}"
        assert TRACKS[_r].order < _t.order, (
            f"{_t.name} requires {_r}, which must sort before it")


# ─── observables ──────────────────────────────────────────────────────────────────

_OBS: tuple[Observable, ...] = (
    # ---- foundation -------------------------------------------------------------
    Observable(
        "equilibration", "foundation", "requestable",
        extractor_json="equilibration.json", extractor_field="equil_verdict", unit="",
        status="declared", gate_macro_stage="equilibration", gate_field="equil_verdict",
        legacy_property="density",
        note="Zero new physics -- density's stage set with the DELIVERABLE being the gate "
             "verdict plus the D-05 markdown, both already produced. Not yet requestable "
             "because plan['properties'] has no name for it.",
    ),
    Observable(
        "melt_density", "foundation", "requestable",
        extractor_json="equilibration.json", extractor_field="density_gcm3", unit="g/cm^3",
        gate_macro_stage="equilibration", gate_field="equil_verdict",
        legacy_property="melt_density",
        summary_path=("results", "melt_density", "value_g_cm3"),
        note="The density of the gated melt at T_melt_hold_K -- what the core equilibration "
             "chain now produces on its own. Requesting it alone is the cheapest real run there "
             "is: build + equilibration + summary, no cooldown. Reported WITH its temperature, "
             "which is per-SMILES (max(T_equil_K, Tg+200)) and so is not comparable between "
             "polymers the way the final_T_K density is.",
    ),
    # ---- cooling ----------------------------------------------------------------
    Observable(
        "density", "cooling", "requestable",
        extractor_json="cooling.json", extractor_field="density_gcm3", unit="g/cm^3",
        gate_macro_stage="cooling", gate_field="cool_verdict",
        legacy_property="density", summary_path=("results", "density", "value_g_cm3"),
        note="The density at final_T_K (300 K by default). Comparable across every run because "
             "no property-conditional path reaches it: every run holds its melt at the same "
             "property-independent T_melt_hold_K and descends at the class's own Tg-sweep rate. "
             "Guarded by test_property_independence. Reads cooling.json, NOT equilibration.json "
             "-- the two gates write the same keys about two different cells.",
    ),
    # ---- thermal ----------------------------------------------------------------
    Observable(
        "tg", "thermal", "requestable",
        extractor_json="thermal.json", extractor_field="Tg_K", unit="K",
        gate_macro_stage="thermal", gate_field="tg_gate_verdict",
        legacy_property="tg", summary_path=("results", "tg", "value_K"),
    ),
    Observable(
        "cte_glass", "thermal", "byproduct", produced_by="tg",
        extractor_json="thermal.json", extractor_field="cte_glassy_per_K", unit="1/K",
        gate_macro_stage="thermal", gate_field="slope_signs_valid", legacy_property="tg",
    ),
    Observable(
        "cte_rubber", "thermal", "byproduct", produced_by="tg",
        extractor_json="thermal.json", extractor_field="cte_rubbery_per_K", unit="1/K",
        gate_macro_stage="thermal", gate_field="slope_ordering_valid", legacy_property="tg",
        note="The natural long-term source for assess_cooling_contraction's alpha_melt, but NOT "
             "usable until a melt-start run raises it toward 5-6e-4 -- see that module's "
             "alpha-calibration block for why substituting it today is circular.",
    ),
    Observable(
        "tg_transition_width", "thermal", "byproduct", produced_by="tg",
        extractor_json="thermal.json", extractor_field="transition_width_c_K", unit="K",
        gate_macro_stage="thermal", gate_field="fit_quality", legacy_property="tg",
    ),
    Observable(
        "thermal_history", "thermal", "requestable",
        extractor_json="thermal_history.json", extractor_field="executed_rate_K_per_ns",
        unit="K/ns", status="declared", gate_macro_stage="thermal", legacy_property="tg",
        note="The sweep without a bilinear fit: schedule fidelity and per-T density only. Needs "
             "resolver stages thermal-history/analyze-thermal-history, which do not exist -- "
             "adding them means a decision_policy.json track_map edit, which rehashes every "
             "stage of every run on disk. Land that once, never incrementally.",
    ),
    # ---- mechanical -------------------------------------------------------------
    Observable(
        "bulk_modulus", "mechanical", "requestable",
        extractor_json="bulk_modulus_murnaghan.json", extractor_field="bulk_modulus_GPa",
        unit="GPa", gate_macro_stage="mechanical", gate_field="bm_gate_verdict",
        legacy_property="bulk_modulus", summary_path=("results", "bulk_modulus", "value_GPa"),
        note="Falls back to the deform path on BM_INADMISSIBLE, whose gate field is "
             "deform_gate_verdict -- see workflow_engine.binding_gate_failure, which reads both.",
    ),
    Observable(
        "shear_modulus", "mechanical", "requestable",
        extractor_json="bulk_modulus_deform.json", extractor_field="G_GPa", unit="GPa",
        gate_macro_stage="mechanical", gate_field="deform_gate_verdict",
        legacy_property="shear_modulus",
        summary_path=("results", "shear_modulus", "value"),
        forced_params={"mechanical_method": "deformation"},
        note="Already computed and already dispatchable -- extract_bulk_modulus_deform emits "
             "G_GPa/E_GPa/nu_Poisson, and run_campaign dispatches on mechanical_method, which is "
             "already in PARAMETER_STAGE. This is a routing entry, not a new code path.",
    ),
    Observable(
        "youngs_modulus", "mechanical", "requestable",
        extractor_json="bulk_modulus_deform.json", extractor_field="E_GPa", unit="GPa",
        gate_macro_stage="mechanical", gate_field="deform_gate_verdict",
        legacy_property="youngs_modulus",
        summary_path=("results", "youngs_modulus", "value"), forced_params={"mechanical_method": "deformation"},
    ),
    Observable(
        "poisson_ratio", "mechanical", "requestable",
        extractor_json="bulk_modulus_deform.json", extractor_field="nu_Poisson", unit="",
        gate_macro_stage="mechanical", gate_field="deform_gate_verdict",
        legacy_property="poisson_ratio",
        summary_path=("results", "poisson_ratio", "value"), forced_params={"mechanical_method": "deformation"},
        note="nu_Poisson, not nu -- the extractor's own key name.",
    ),
)

OBSERVABLES: dict[str, Observable] = {o.name: o for o in _OBS}


# ─── derived vocabularies ─────────────────────────────────────────────────────────

VALID_PROPERTIES = frozenset(
    o.legacy_property for o in _OBS
    if o.kind == "requestable" and o.status == "wired" and o.legacy_property
)
"""Every name a plan may REQUEST. A `declared` observable is routable but not yet nameable."""

DEFAULT_PROPERTIES = frozenset({"density", "tg", "bulk_modulus"})
"""What `--properties all` means: the default suite, NOT every nameable property.

Deliberately narrower than VALID_PROPERTIES. shear/Young's/Poisson force
mechanical_method="deformation", so folding them into "all" would silently switch every
"all" run's bulk modulus from the Murnaghan EOS fit to a deformation fit -- a different
measurement with a different gate, chosen by nobody. They are opt-in by name."""

STAGE_TRACK: dict[str, str] = {
    s.name: s.track for t in sorted(TRACKS.values(), key=lambda t: t.order) for s in t.stages
}

MACRO_TO_RESOLVER: dict[str, str] = {
    "build": "build", "equilibration": "equil", "cooling": "cool", "thermal": "tg",
    "mechanical": "murnaghan", "summary": "run-summary",
}
"""Macro stage -> the resolver stage that represents it, for recovery_agent_cli's prompt text."""


def observable(name: str) -> Observable:
    return OBSERVABLES[name]


def _tracks_for(properties) -> tuple[Track, ...]:
    """Union the tracks the requested properties need, plus the always-on ones, in order.

    This one function is the routing rule -- "the shortest path to what was asked for" -- and it
    replaces seven hand-written if-chains.
    """
    wanted = {o.track for o in _OBS
              if o.legacy_property in set(properties or ()) and o.kind == "requestable"}
    wanted |= {t.name for t in TRACKS.values() if t.always}
    # Close over `requires`: a track can need another track's cell without any observable of
    # that track's having been asked for (mechanical needs the cooldown's npt_final). The
    # order assertion at TRACKS construction makes this terminate and keeps the result a
    # STAGE_ORDER subsequence.
    pending = list(wanted)
    while pending:
        for required in TRACKS[pending.pop()].requires:
            if required not in wanted:
                wanted.add(required)
                pending.append(required)
    return tuple(sorted((TRACKS[n] for n in wanted), key=lambda t: t.order))


def tracks_for(properties) -> tuple[str, ...]:
    return tuple(t.name for t in _tracks_for(properties))


def macro_stages_for(properties) -> tuple[str, ...]:
    """== WorkflowEngine.enabled_stages(). Ordered by track order, which is STAGE_ORDER-compatible
    by construction -- _dependencies and invalidate_from depend on that ordering."""
    out: list[str] = []
    for track in _tracks_for(properties):
        for macro in track.macro_stages:
            if macro not in out:
                out.append(macro)
    return tuple(out)


def resolver_stages_for(properties, include_fallbacks: bool = True) -> list[str]:
    """The executable resolver vocabulary. With fallbacks == both dry-run branches and
    decision_policy's track_map; without == the plan artifact's stage list.

    One substitution: requesting shear/Young's/Poisson forces mechanical_method="deformation"
    (they only exist on that path), so `deform` becomes the mechanical track's PRIMARY and
    murnaghan drops out. Without this the plan would name murnaghan with a `chain_submitted`
    criterion while run_campaign dispatched do_deformation -- an artifact that disagrees with the
    run it describes, which is the whole class of bug this registry exists to end. Requesting
    bulk_modulus alone forces nothing and keeps murnaghan, so the goldens are untouched.
    """
    names = [st.name for t in _tracks_for(properties) for st in t.stages
             if include_fallbacks or st.role == "primary"]
    if forced_params_for(properties).get("mechanical_method") == "deformation":
        names = [n for n in names if n != "murnaghan"]
        if not include_fallbacks and "deform" not in names and "analyze-bm" in names:
            names.insert(names.index("analyze-bm"), "deform")
    return names


def planned_stage_names(properties) -> list[str]:
    """== [s["stage"] for s in build_planned_stages(...)]."""
    return resolver_stages_for(properties, include_fallbacks=False)


def stage_for_property(prop: str) -> str:
    """== write_characterization_cache.STAGE_FOR_PROPERTY: the macro stage whose acceptance
    proves that property's binding gate passed.

    Several observables can share one legacy_property -- shear/Young's/Poisson all map onto
    bulk_modulus, since they come out of the same mechanical track. They necessarily agree on
    gate_macro_stage (it is a property of the track), so the first match is the answer; the
    assertion below states that rather than leaving it to luck.
    """
    stages = {o.gate_macro_stage for o in _OBS
              if o.legacy_property == prop and o.kind == "requestable" and o.status == "wired"}
    if not stages:
        raise KeyError(prop)
    assert len(stages) == 1, f"{prop} maps to observables on different macro stages: {stages}"
    return stages.pop()


def forced_params_for(properties) -> dict:
    """decided_params this property set pins, e.g. shear_modulus -> mechanical_method=deformation.

    Applied in materialize_plan BEFORE the agent's own overrides, so a plan may still override a
    forced value deliberately -- but never has to know the routing rule. Conflicting pins from two
    requested observables are a contradiction the caller must not paper over, so they raise.
    """
    out: dict = {}
    # Requesting bulk_modulus AND a deformation modulus is not a conflict: the deform extractor
    # emits K_GPa alongside G/E/nu, so one deformation run satisfies both. Only two observables
    # pinning the SAME key to DIFFERENT values is a real contradiction, and that raises below.
    for prop in sorted(set(properties or ())):
        for o in _OBS:
            if o.legacy_property != prop or o.kind != "requestable":
                continue
            for key, value in o.forced_params.items():
                if out.get(key, value) != value:
                    raise ValueError(
                        f"{prop} pins {key}={value!r} but another requested observable "
                        f"pins {key}={out[key]!r}"
                    )
                out[key] = value
    return out


def byproducts_of(prop: str) -> tuple[Observable, ...]:
    """What a request for `prop` yields free. Already computed by that track's extractor; the
    only work is gating them on their own terms and surfacing them marked."""
    return tuple(o for o in _OBS if o.kind == "byproduct" and o.produced_by == prop)


def byproducts_for(properties) -> tuple[Observable, ...]:
    out: list[Observable] = []
    for prop in sorted(set(properties or ())):
        out.extend(byproducts_of(prop))
    return tuple(out)
