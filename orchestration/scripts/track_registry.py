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
    note="Ends at npt_final, the cell at final_T_K that carries the full binding gate set.",
)

_THERMAL = Track(
    name="thermal", order=1,
    stages=(ResolverStage("tg", "thermal", "thermal"),
            ResolverStage("analyze-tg", "thermal", "thermal")),
    macro_stages=("thermal",),
    note="The staircase is a continuous cooling run: it starts from the cool_block cell the "
         "foundation track tagged at tg_t_high_K and cools to tg_t_low_K at the same rate the "
         "cooldown used (see stage_params.rate_matched_cool_block_hold_steps).",
)

_MECHANICAL = Track(
    name="mechanical", order=2,
    stages=(ResolverStage("murnaghan", "mechanical", "mechanical"),
            ResolverStage("deform", "mechanical", "mechanical", role="fallback"),
            ResolverStage("analyze-bm", "mechanical", "mechanical")),
    macro_stages=("mechanical",),
    note="Starts from the foundation track's npt_final cell, NEVER a thermal staircase "
         "waypoint: npt_final is the gated cell, a waypoint is an ungated mid-sweep transient, "
         "and for a high-Tg class the sweep floor sits above bm_temperature_K so no such "
         "waypoint exists. Costs nothing to keep -- run_campaign already wires it this way.",
)

_SUMMARY = Track(
    name="summary", order=3, always=True,
    stages=(ResolverStage("run-summary", "summary", "summary"),),
    macro_stages=("summary",),
)

TRACKS: dict[str, Track] = {t.name: t for t in (_FOUNDATION, _THERMAL, _MECHANICAL, _SUMMARY)}


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
        "density", "foundation", "requestable",
        extractor_json="equilibration.json", extractor_field="density_gcm3", unit="g/cm^3",
        gate_macro_stage="equilibration", gate_field="equil_verdict",
        legacy_property="density", summary_path=("results", "density", "value_g_cm3"),
        note="Comparable across every run because no property-conditional cooling path exists: "
             "every run rides the same cool_block cooldown, which since 2026-09-01 runs at the "
             "class's own Tg-sweep rate. Guarded by test_property_independence.",
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
        status="declared", gate_macro_stage="mechanical", gate_field="deform_gate_verdict",
        legacy_property="bulk_modulus",
        forced_params={"mechanical_method": "deformation"},
        note="Already computed and already dispatchable -- extract_bulk_modulus_deform emits "
             "G_GPa/E_GPa/nu_Poisson, and run_campaign dispatches on mechanical_method, which is "
             "already in PARAMETER_STAGE. This is a routing entry, not a new code path.",
    ),
    Observable(
        "youngs_modulus", "mechanical", "requestable",
        extractor_json="bulk_modulus_deform.json", extractor_field="E_GPa", unit="GPa",
        status="declared", gate_macro_stage="mechanical", gate_field="deform_gate_verdict",
        legacy_property="bulk_modulus", forced_params={"mechanical_method": "deformation"},
    ),
    Observable(
        "poisson_ratio", "mechanical", "requestable",
        extractor_json="bulk_modulus_deform.json", extractor_field="nu_Poisson", unit="",
        status="declared", gate_macro_stage="mechanical", gate_field="deform_gate_verdict",
        legacy_property="bulk_modulus", forced_params={"mechanical_method": "deformation"},
        note="nu_Poisson, not nu -- the extractor's own key name.",
    ),
)

OBSERVABLES: dict[str, Observable] = {o.name: o for o in _OBS}


# ─── derived vocabularies ─────────────────────────────────────────────────────────

VALID_PROPERTIES = frozenset(
    o.legacy_property for o in _OBS
    if o.kind == "requestable" and o.status == "wired" and o.legacy_property
)
"""The plan["properties"] vocabulary: {"density", "tg", "bulk_modulus"}. A `declared` observable
is routable here but has no name in the plan artifact yet."""

STAGE_TRACK: dict[str, str] = {
    s.name: s.track for t in sorted(TRACKS.values(), key=lambda t: t.order) for s in t.stages
}

MACRO_TO_RESOLVER: dict[str, str] = {
    "build": "build", "equilibration": "equil", "thermal": "tg",
    "mechanical": "murnaghan", "summary": "run-summary",
}
"""Macro stage -> the resolver stage that represents it, for recovery_agent_cli's prompt text."""


def observable(name: str) -> Observable:
    return OBSERVABLES[name]


def track_for(stage: str) -> str:
    return STAGE_TRACK[stage]


def _tracks_for(properties) -> tuple[Track, ...]:
    """Union the tracks the requested properties need, plus the always-on ones, in order.

    This one function is the routing rule -- "the shortest path to what was asked for" -- and it
    replaces seven hand-written if-chains.
    """
    wanted = {o.track for o in _OBS
              if o.legacy_property in set(properties or ()) and o.kind == "requestable"}
    wanted |= {t.name for t in TRACKS.values() if t.always}
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
    decision_policy's track_map; without == the plan artifact's stage list."""
    return [s.name for t in _tracks_for(properties) for s in t.stages
            if include_fallbacks or s.role == "primary"]


def planned_stage_names(properties) -> list[str]:
    """== [s["stage"] for s in build_planned_stages(...)]."""
    return resolver_stages_for(properties, include_fallbacks=False)


def stage_for_property(prop: str) -> str:
    """== write_characterization_cache.STAGE_FOR_PROPERTY: the macro stage whose acceptance
    proves that property's binding gate passed."""
    for o in _OBS:
        if o.legacy_property == prop and o.kind == "requestable" and o.status == "wired":
            return o.gate_macro_stage
    raise KeyError(prop)


def byproducts_of(prop: str) -> tuple[Observable, ...]:
    """What a request for `prop` yields free. Already computed by that track's extractor; the
    only work is gating them on their own terms and surfacing them marked."""
    return tuple(o for o in _OBS if o.kind == "byproduct" and o.produced_by == prop)


def byproducts_for(properties) -> tuple[Observable, ...]:
    out: list[Observable] = []
    for prop in sorted(set(properties or ())):
        out.extend(byproducts_of(prop))
    return tuple(out)
