#!/usr/bin/env python3
"""
make_deterministic_plan.py — Emit the deterministic planning artifact for a polymer class.

One subcommand, `run-plan`: the complete run_plan.json the novel-run-plan skill's literature
critic then CRITIQUES (it does not author it -- see below).

There were two until 2026-09-04. `decision` emitted a separate decision.json carrying the same
decision rows in a second shape, which scientific_control then merged back into the plan; the
two files restated each other almost entirely (evidence blocks byte-identical), so the decision
was folded into the plan and the subcommand deleted. The file the critic adjudicates and the
file that executes are now the same file.

`run-plan` is not a scaffold: it resolves every row itself and writes the rationale too. What is
left for review is `confidence`, which comes back "unreviewed" (invalid per scientific_control's
VALID_CONFIDENCE) and is the ONLY thing blocking materialization. --baseline stamps "low"
instead, for the deterministic arm that runs with no LLM in the loop, and --force is required to
overwrite a plan a reviewer may already have edited.

decisions[] holds exactly ONE row, D-01_ff. D-02_charges, D-03_electrostatics and D-08_hardware
were rows until 2026-09-04 and were never decisions -- each is a pure function of the field D-01
resolves (verified 21/21 across the class table), so _derived_from_field() derives them AFTER
the field is known. D-04_system_size was a solver, not a choice; its result lives in
plan["system_size"].
"""

import argparse
import json
from types import SimpleNamespace
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules_common  # noqa: E402  -- module import so tests can monkeypatch rules_common.canonicalize
from rules_common import load_rules, get_class_entry, hardware_policy, resolve_ff_family  # shared rules access (single source of truth)
import track_registry  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage_params import (_exp_tg_point, _regime_exp_tg,  # reuse the proven resolvers,
                          workflow_reference_temperature)  # don't duplicate them
from select_system_size import derive_cell  # per-SMILES cell derivation; the class dp_typical/nchain keys were removed 2026-09-02
from select_system_size import _is_ua  # noqa: E402  -- one UA-field definition, shared with D-04
from select_system_size import solve_system_size, SYSTEM_MW_FLOOR_DOI  # noqa: E402  -- D-04, the same call materialize_plan makes
from select_hardware import select_hardware       # noqa: E402  -- D-08, live host + derived cell size
from hardware_runtime import gpu_status, host_matches  # noqa: E402  -- D-08 concurrent_load / host_match
from rules_common import primary_source, source_evidence  # noqa: E402  -- citations[] id -> real DOI
import forcefield  # noqa: E402  -- D-01's moiety screen + EMC trial probe

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DECISION_POLICY_PATH = REPO_ROOT / "orchestration" / "decision_policy.json"
# Decision-relevant class keys consumed by stage_params.py. Only keys that
# EXIST in the class entry are snapshotted, so the overlay stays an exact identity.
# charge_method and electrostatics are NOT snapshotted: they are properties of the field D-01
# resolves, derived by _derived_from_field() below. Snapshotting them from the class copied them
# BEFORE resolve_d01 ran, so a SMILES that typed under a field outside its class's family got a
# recorded charge scheme that contradicted preferred_ff.
SNAPSHOT_KEYS = [
    "preferred_builder",
    "cutoff_A", "dt_fs",
    "dp_typical", "nchain", "density_initial_gcm3",
    "T_equil_K", "annealing_T_high_K", "P_equil_atm", "final_T_K", "anneal_margin_K",
    "warmup_steps", "densify_ramp_steps", "densify_check_every_steps", "densify_steps_cap",
    "ff_activate_npt_steps", "anneal_heat_steps", "anneal_check_every_steps",
    "anneal_cap_steps", "cool_block_dT_K", "cool_block_hold_steps", "cool_block_hold_cap_steps",
    "stage8_min_steps", "stage8_cap_steps",
    "melt_ramp_steps", "melt_hold_min_steps", "melt_hold_cap_steps",
    "nvt_melt_min_steps", "nvt_melt_cap_steps",
    "md_tg_ceiling_K", "tg_t_low_K", "tg_t_step_K", "tg_rate_K_per_ns",
    "tg_min_steps_per_T",
    "K_deform_rate_inv_s", "K_deform_rate_slow_inv_s", "K_strain_max",
    "bm_pressures_atm", "ct_min_decay_melt", "bm_temperature_K",
]


def _policy_criteria() -> dict:
    """decision_id -> its policy's evaluate list, read straight from decision_policy.json --
    single source of truth so a row's criteria_evaluated can never drift from the policy that
    validate_run_plan.py checks it against."""
    policy = json.loads(DECISION_POLICY_PATH.read_text())
    return {p["decision_id"]: p.get("evaluate", []) for p in policy.get("policies", {}).values()}


def _field_of(cls: dict, field: str | None = None) -> str | None:
    """The force field a decision row should describe.

    D-01's resolved choice wins; then a plan-overlaid `decided_params.preferred_ff`; then the
    class `ff_accuracy_prior`, which is a literature prior and not by itself a routing decision.
    """
    return field or cls.get("preferred_ff") or cls.get("ff_accuracy_prior")


def _derived_from_field(field: str | None, rules: dict) -> dict:
    """Everything that follows from D-01's resolved field, in one place.

    charge_method, electrostatics and the hardware triple are not independent decisions -- each
    is a property of the force field. Verified across all 21 classes before D-02/D-03/D-08 were
    retired (2026-09-04): every class's curated charge_method and electrostatics equalled the
    value its ff_accuracy_prior's family carries here, 21/21.

    Reuses rules_common.resolve_ff_family (the same alias table stage_params.resolve_hardware and
    select_hardware.plan_cost_estimate key off), so there is exactly one family resolver.
    """
    hp = rules.get("hardware_policy", {})
    fam = resolve_ff_family(field or "", hp)
    pol = hp.get("by_forcefield", {}).get(fam, {})
    return {
        "ff_family": fam,
        "charge_method": pol.get("charge_method"),
        "electrostatics": pol.get("electrostatics"),
        "engine": pol.get("engine"),
        "mpi_ranks": pol.get("mpi"),
        "gpu_per_run": pol.get("gpu_per_run"),
    }


#: The plan's decision ids. One, since 2026-09-04. scientific_control validates a supplied
#: plan against this rather than re-deriving it from a build_decisions() call.
KNOWN_DECISIONS = frozenset({"D-01_ff"})


def build_decisions(cls: dict, smiles: str | None = None, field: str = None,
                    resolution: dict = None, rules: dict = None,
                    polymer_class: str = None, hw: dict = None) -> list:
    """The plan's decision rows. Exactly one: D-01_ff.

    D-02_charges, D-03_electrostatics and D-08_hardware were rows until 2026-09-04. None was a
    decision: each is a pure function of the force field D-01 resolves. Verified over all 21
    classes -- charge_method and electrostatics equalled their family's value 21/21 (pcff ->
    bond-increment, opls -> opls-library, trappe -> embedded, gaff -> RESP; lj_cut iff trappe),
    and hardware comes from hardware_policy.by_forcefield[family]. They are now derived by
    _derived_from_field() into decided_params and plan["hardware"], which is also what stops a
    recorded charge scheme from contradicting preferred_ff.

    D-04_system_size was a row too, but it is a solver (select_system_size.solve_system_size),
    not a choice: no agent input, and overrides deliberately cannot carry dp_typical/nchain. Its
    result and reasons live in plan["system_size"].

    D-05_convergence, D-06_tg_fit_quality and D-07_property_method are still excluded:
    decision_policy.json defines all three as mechanized runtime gate verdicts (equil_verdict,
    tg_gate_verdict, bm_gate_verdict) to route on, not re-derive -- they have no pre-simulation
    default choice to annotate here and stay enforced solely via planned_stages success_criteria.

    "confidence" here is a fixed "class_default" placeholder. The scientific control layer
    replaces it with the adjudicating agent's confidence before execution.
    """
    criteria = _policy_criteria()
    if rules is not None:
        # The full row: one evidence entry per criterion the policy names, including the ones
        # this layer cannot reach (they say NOT MEASURED / NOT ASSESSABLE explicitly). This is
        # what decision.json carried until it was folded into run_plan.json on 2026-09-04.
        row = _d01_ff_row(rules, cls, polymer_class or "", hw, criteria.get("D-01_ff", []),
                          field, resolution)
        row = {"id": "D-01_ff", "choice": row.pop("default_choice", None), **row}
        # admissible reads as the answer to "what typed this SMILES", so keep it beside choice
        # rather than after the evidence block it summarizes.
        if "admissible" in row:
            row = {k: row[k] for k in ("id", "choice", "admissible")} | {
                k: v for k, v in row.items() if k not in ("id", "choice", "admissible")}
        return [row]

    ff_evidence = []
    if cls.get("ff_justification_doi"):
        ff_evidence.append({"claim": cls.get("ff_note", "force field choice"),
                            "source_doi": cls.get("ff_justification_doi")})
    for cit in cls.get("citations", []):
        ff_evidence.append({"claim": "supporting validation", "citation": cit})

    return [
        {"id": "D-01_ff",
         "choice": resolution["field"] if resolution else _field_of(cls, field),
         "criteria_evaluated": criteria.get("D-01_ff", []),
         "evidence": ff_evidence, "confidence": "class_default",
         "alternatives": cls.get("forcefield_alternatives", []),
         # Only when a trial build actually ran: validate_run_plan's ff_no_admissible_field
         # gate keys off this, and an unprobed [] would read as "nothing types this SMILES".
         **({"admissible": [resolution["field"]] if resolution["field"] else []}
            if (resolution or {}).get("probed") else {})},
    ]


#: run_plan.json key order. Presentation only -- workflow_engine._canonical_hash sorts keys, so
#: this cannot move plan_hash -- but the file is read by people, so it reads in the order they
#: ask questions in: what is this run, what was decided, how, and then the protocol it implies.
PLAN_KEY_ORDER = [
    "schema_version", "run_name", "polymer_class", "smiles", "goal", "properties",
    "plan_mode", "confidence", "dominant_uncertainty",
    "decisions", "system_size", "hardware", "overrides",
    "decided_params", "planned_stages", "recovery_history", "cost_estimate",
]
PLAN_SCHEMA_VERSION = "2.0"


def ordered_plan(**parts) -> dict:
    """Assemble a plan with PLAN_KEY_ORDER honoured, from whichever writer is building it.

    Every writer routes through here (make_plan, make_plan_from_cache, and
    scientific_control.materialize_plan) so none of them can scramble the order by appending in
    call order, which is what dict.update() did.
    """
    parts.setdefault("schema_version", PLAN_SCHEMA_VERSION)
    plan = {k: parts.pop(k) for k in PLAN_KEY_ORDER if k in parts}
    plan.update(parts)  # anything unrecognised still lands, at the end, rather than vanishing
    return plan


def attach_acknowledgements(d01_row: dict, prior_ack: dict | None, resolution: dict | None):
    """Record on the D-01 row the two facts a plan MUST carry when it departs from its evidence.

    These lived in a top-level uncertainties[] list until 2026-09-04, where validate_run_plan
    matched them by NAME -- a plan-wide bag of strings acting as per-decision flags. They belong
    on the decision they qualify: both describe D-01's field, and nothing else reads them.
    """
    acks = d01_row.setdefault("acknowledgements", {})
    if prior_ack:
        acks["ff_accuracy_prior_not_met"] = prior_ack.get("detail", "")
    flags = (resolution or {}).get("provenance_flags") or {}
    if flags:
        d01_row["provenance_flags"] = flags
    return d01_row


def build_system_size(decided_params: dict, size_solve: dict | None, assumptions: list) -> dict:
    """The cell, and why. D-04_system_size was a decisions[] row until 2026-09-04; it is a
    solver (select_system_size.solve_system_size), not a choice -- no agent input, and overrides
    deliberately cannot carry dp_typical/nchain.

    Deliberately NOT inside decided_params: workflow_engine.PARAMETER_STAGE maps every
    decided_params key to an owning stage and falls through to "build" for anything unmapped, so
    a reasons/acknowledgements blob there would invalidate the whole pipeline back to build on
    every resume.
    """
    solve = size_solve or {}
    acks = {}
    for u in solve.get("uncertainties", []) or []:
        name = u.get("name")
        if name == "size_over_provisioned":
            name = "system_size_over_provisioned"
        acks[name] = {k: v for k, v in u.items()
                      if k not in ("name", "dominant", "reduction_probe")}
    return {
        "dp_typical": decided_params.get("dp_typical"),
        "nchain": decided_params.get("nchain"),
        "resolved_by": "select_system_size.solve_system_size",
        "reasons": list(solve.get("recommendation_reasons") or []) + list(assumptions or []),
        "acknowledgements": acks,
    }


# Re-exported: recovery_agent_cli, validate_run_plan and the tests all import this name.
STAGE_TRACK = track_registry.STAGE_TRACK


def build_planned_stages(cls: dict, properties: set, smiles: str | None = None) -> list:
    """Experiment DAG with per-stage success_criteria the Validator enforces."""
    # tg-stage accuracy bracket: central Tg estimate (see _exp_tg_point).
    exp_tg_bracket = _exp_tg_point(cls, smiles)
    # murnaghan deform-fallback hint: regime call, not the bracket -- _regime_exp_tg pads an
    # estimated Tg toward glassy (see its docstring), so this can disagree with the bracket.
    # Compared against the ASSESSMENT temperature, not a bare 300 -- the fallback exists
    # because a glassy cell's Murnaghan fit can go inadmissible, and "glassy" means below Tg at
    # final_T_K. On the reasoned path `cls` is the effective class, so an overridden final_T_K
    # reaches here; on the deterministic path no class declares one and it resolves to 300.
    glassy_hint = ((regime_tg := _regime_exp_tg(cls, smiles)) is not None
                   and regime_tg > float(cls.get("final_T_K", 300.0)))

    def _s(stage, criteria, **extra):
        return {"stage": stage, "track": STAGE_TRACK[stage],
                "success_criteria": criteria, **extra}

    # WHICH stages, and in what order, comes from track_registry. WHAT each stage must satisfy
    # stays here: success_criteria need cls/smiles, and the registry deliberately owns no science.
    _CRITERIA = {
        "build":       {"data_file_written": True},
        "equil":       {"check_equilibration_comprehensive.overall_pass": True},
        "equil-check": {"equil_verdict": "PASS"},
        # The cooling stage: the blockwise descent from the gated melt to final_T_K, then the
        # assessment cell. Present only when a property needs a cell at that temperature.
        "cool":        {"chain_submitted": True},
        "cool-check":  {"cool_verdict": "PASS"},
        # One sweep at the class's configured tg_rate_K_per_ns (see stage_params.tg_rate,
        # shared with do_thermal and the cooldown's rate matching).
        "tg":          {"bilinear_fit_r_squared_min": 0.80,
                        "t_range_brackets_exp_tg": exp_tg_bracket},
        "analyze-tg":  {},
        # Murnaghan always submits (2026-08-09): guides/MURNAGHAN.md's rubbery null-fallback
        # resolves to the PROBE ladder instead of an all-null RESULT, so there is no longer a
        # "rubbery without pressures -> fluctuation only, no submit stage" case.
        "murnaghan":   {"chain_submitted": True},
        # Primary only when shear/Young's/Poisson were requested -- they exist only on the
        # deformation path, so the registry forces mechanical_method and swaps this in for
        # murnaghan. Otherwise it is murnaghan's contingent fallback and never a plan entry.
        "deform":      {"chain_submitted": True},
        "analyze-bm":  {},
        # Structure is analysis-only over a cell the foundation track already gated, so there is
        # no submission to assert and no admissibility of its own to check.
        "analyze-structure": {},
        # The vacuum reference: a build, then the NVT hold whose log the extractor reads.
        "vacuum-build":      {"data_file_written": True},
        "vacuum-chain":      {"chain_submitted": True},
        "analyze-solubility": {},
        "run-summary": {},
    }
    # Glassy carries the deform fallback; rubbery (empirical or PROBE ladder) does not. The
    # registry knows deform IS murnaghan's fallback slot; whether it attaches is a regime call,
    # which needs cls/smiles and therefore stays here.
    _EXTRA = {"murnaghan": {"fallback": "deform"}} if glassy_hint else {}

    return [_s(name, _CRITERIA[name], **_EXTRA.get(name, {}))
            for name in track_registry.planned_stage_names(properties)]


def _assert_tg_rate_feasible(cls: dict, polymer_class: str) -> None:
    """Reject a configured Tg rate that gives too few steps per temperature.

    Per-T simulation TIME (not step count) sets bilinear-fit quality: too few ps at each
    temperature collapses the Tg fit (cis-PBD2 r400=50ps, PEEK2 r160/r400 degenerate).
    Rate IS the per-T step knob (N = tg_t_step_K/(rate*dt*1e-6)), so an infeasible rate
    cannot be salvaged at run time - fail at plan time. Floor = tg_min_steps_per_T
    (default 200000 steps = 200 ps at dt=1fs; TraPPE dt=2fs classes set 100000 = 200 ps).

    Checked a whole tg_rates_K_per_ns list until 2026-09-04; there is one rate now, and it is
    the only knob left for a class whose fit will not resolve -- lower it.
    """
    rate = cls.get("tg_rate_K_per_ns")
    t_step = cls.get("tg_t_step_K")
    if not rate or t_step is None:
        return
    dt = cls.get("dt_fs", 1.0)
    floor = cls.get("tg_min_steps_per_T", 200000)
    n_steps = t_step / (rate * dt * 1e-6)
    if n_steps < floor - 1:
        max_rate = t_step / (floor * dt * 1e-6)
        raise ValueError(
            f"{polymer_class}: infeasible tg_rate_K_per_ns {rate} - it gives "
            f"{int(n_steps)} steps/T, below tg_min_steps_per_T={floor} "
            f"(tg_t_step_K={t_step}, dt_fs={dt}). Lower the rate "
            f"so N = tg_t_step_K/(rate*dt*1e-6) >= floor (max feasible rate = {max_rate:.0f} K/ns)."
        )


def _ff_screen_assumptions(resolution) -> list:
    """One line when the moiety screen found a measured blocker that nothing verified.

    Without this a scaffold plan carries the screen result nowhere: build_decisions' D-01 row
    transcribes class fields only and has no parameter_coverage entry to put it in.
    """
    if not resolution or not resolution.get("blockers") or resolution.get("probed"):
        return []
    ids = [b["id"] for b in resolution["blockers"]]
    return [f"D-01_ff UNVERIFIED: guides/ff_moiety_rules.json matched {ids} in this repeat "
            f"unit, groups measured to block every registered EMC field. No trial build was "
            f"run (--with-ff-probe off), so {resolution['prior']!r} is asserted, not measured."]


def resolve_d01(cls: dict, smiles, with_ff_probe: bool = False) -> tuple:
    """(field_for_sizing, resolution). D-01's answer for this SMILES.

    The moiety screen always runs -- it is one RDKit round trip and no trial build -- so even a
    scaffold plan knows whether its chemistry has a measured blocker. `with_ff_probe` adds the
    real EMC trial build that turns the screen into a measurement.

    The returned field is never None: D-04 and D-08 still have to size and price something. A
    resolution that typed nothing says so in resolution["field"], and D-01 refuses on that.
    """
    prior = cls.get("ff_accuracy_prior")
    if not smiles:
        return prior, None
    try:
        resolution = forcefield.select_by_moiety(smiles, prior, probe=with_ff_probe)
    except Exception:  # noqa: BLE001 -- a broken screen must not block planning
        return prior, None
    return resolution["field"] or prior, resolution


def size_the_cell(polymer_class: str, smiles, properties: set,
                  size_solve: dict | None = None, field: str = None) -> tuple[dict, list]:
    """(dp_typical/nchain for decided_params, assumptions) -- the cell, resolved per-SMILES.

    SNAPSHOT_KEYS can only copy keys the class entry HAS, and per-class dp_typical/nchain
    were removed 2026-09-02, so without this a scaffold run_plan.json carried no cell size
    at all. That was not inert: stage_params fell through to hardcoded 50/10 and
    validate_run_plan's D-04 floor check returns clean on `dp is None`, so an unsized plan
    built a wrong cell and reported no finding. Resolve it here, from the same
    solve_system_size() materialize_plan() uses, so every plan artifact carries a real cell
    whatever mode produced it.

    `size_solve` lets a caller that has already run the solve hand it in rather than pay for
    a second RDKit round-trip; materialize_plan() does exactly that.
    """
    if size_solve is None:
        if not smiles:
            return {}, ["D-04_system_size UNRESOLVED: no SMILES was supplied, so the cell "
                        "could not be sized from the repeat unit. run_campaign will refuse "
                        "to build this plan rather than default the cell."]
        try:
            size_solve = solve_system_size(polymer_class, smiles, properties,
                                           dp_typical=None, nchain=None, field=field)
        except Exception as e:  # noqa: BLE001 -- an unsized plan must say so, not crash here
            return {}, [f"D-04_system_size UNRESOLVED: solve_system_size raised {e!r}. "
                        "run_campaign will refuse to build this plan rather than default "
                        "the cell."]
    recommended = size_solve.get("recommended_params") or {}
    sized = {k: v for k, v in recommended.items() if k in ("dp_typical", "nchain")}
    if not sized:
        return {}, ["D-04_system_size UNRESOLVED: solve_system_size returned no "
                    "dp_typical/nchain. run_campaign will refuse to build this plan "
                    "rather than default the cell."]
    reasons = size_solve.get("recommendation_reasons") or []
    return sized, [f"resolved to {sized} by "
                   f"select_system_size.solve_system_size()"
                   + (f" -- {'; '.join(reasons)}" if reasons else ".")]


def make_plan(run_name: str, polymer_class: str, smiles, properties: set,
              size_solve: dict | None = None, with_ff_probe: bool = False,
              baseline: bool = False) -> dict:
    rules = load_rules()
    if polymer_class.upper() not in rules.get("classes", {}):
        raise ValueError(f"unknown polymer class {polymer_class!r}")
    cls = get_class_entry(rules, polymer_class)
    _assert_tg_rate_feasible(cls, polymer_class.upper())
    decided_params = {k: cls[k] for k in SNAPSHOT_KEYS if k in cls}
    # SNAPSHOT_KEYS copies only keys the class HAS, and four classes declare no slow
    # deformation leg. decided_params is what the _negative_modulus remedy reads, so leaving
    # the key absent made its "switch to the slow rate" step a no-op. Derive it.
    slow_deform_rate = rules_common.resolve_slow_deform_rate(cls)
    if slow_deform_rate is not None:
        decided_params["K_deform_rate_slow_inv_s"] = slow_deform_rate
    # The assessment temperature, for the same reason: no class declares final_T_K OR
    # bm_temperature_K, so SNAPSHOT_KEYS copied NEITHER and both fell to a hardcoded 300.0
    # buried in stage_params. That made final_T_K un-freezable and un-overridable in practice
    # -- the run had no record of the temperature it was assessed at. Derive them so the plan
    # states the assessment temperature, and so a remedy or an agent override has a key to
    # move. bm_temperature_K follows final_T_K because the mechanical track measures on the
    # cooling track's npt_final cell, which is gated at final_T_K and nowhere else;
    # _validate_protocol_relationships holds them equal.
    decided_params.setdefault("final_T_K", float(cls.get("final_T_K", 300.0)))
    decided_params.setdefault("bm_temperature_K", decided_params["final_T_K"])
    # D-01: decided_params.preferred_ff is the field this run BUILDS with, resolved per SMILES.
    # It is never None -- a resolution that typed nothing refuses through the D-01 row's
    # admissible=[] instead, so the cell is still sized and priced against a real field.
    field, ff_resolution = resolve_d01(cls, smiles, with_ff_probe)
    decided_params["preferred_ff"] = field
    # ORDER IS LOAD-BEARING: everything the field implies is derived here, AFTER the field is
    # known. These two used to be snapshotted from the class above, four lines before `field`
    # existed, and were never reconciled with it.
    derived = _derived_from_field(field, rules)
    decided_params["charge_method"] = derived["charge_method"]
    decided_params["electrostatics"] = derived["electrostatics"]
    sized, size_assumptions = size_the_cell(polymer_class, smiles, properties, size_solve, field)
    decided_params.update(sized)
    # Regime call (see _regime_exp_tg): a novel polymer's Tg estimate now drives this instead of
    # defaulting glassy by omission, padded toward glassy for an uncertain estimate.
    exp_tg = _regime_exp_tg(cls, smiles)
    T_equil = decided_params.get("T_equil_K", 600.0)
    # Against the ASSESSMENT temperature, which decided_params now carries (see final_T_K
    # above), not a literal 300 -- shared with stage_params._resolve_t_workflow so the plan
    # records the reference the deck will actually run at.
    decided_params["T_workflow_K"] = workflow_reference_temperature(
        exp_tg, T_equil, decided_params["final_T_K"])
    # T_melt_hold_K is resolved by stage_params.temperature_schedule at execution time from this
    # same class entry plus the SMILES; recording it here makes it visible in the plan artifact,
    # freezable (write_characterization_cache.FREEZE_KEYS), and readable by the cost model, which
    # needs the sweep's top and must not re-derive it from a retired key.
    try:
        import stage_params as _sp
        _sched = _sp.temperature_schedule(
            SimpleNamespace(smiles=smiles, exp_tg_K=None, final_T_K=None,
                            T_equil_K=None, T_anneal_high_K=None), cls)
        decided_params["T_melt_hold_K"] = _sched["T_melt_hold_K"]
    except Exception:  # noqa: BLE001 -- a planning-time convenience, never a hard dependency
        pass
    prior_ack = _ff_prior_uncertainty(polymer_class.upper(), cls.get("ff_accuracy_prior"),
                                      (ff_resolution or {}).get("field", field), ff_resolution)
    # select_hardware prices the resolved cell; its estimate is D-01's computational_cost
    # evidence, so it is resolved here rather than by a second caller.
    try:
        hw = select_hardware(polymer_class.upper(), smiles, decided_params.get("dp_typical"),
                             decided_params.get("nchain"), field)
    except Exception as e:  # noqa: BLE001 -- pricing is evidence, never a hard dependency
        hw = {"error": str(e)}
    rows = build_decisions(cls, smiles, field, ff_resolution, rules=rules,
                           polymer_class=polymer_class.upper(), hw=hw)
    attach_acknowledgements(rows[0], prior_ack, ff_resolution)
    rows[0].setdefault("critique", {"status": "pending_scientific_review", "rounds": 0,
                                    "findings": _ff_screen_assumptions(ff_resolution)})
    return ordered_plan(
        run_name=run_name,
        polymer_class=polymer_class.upper(),
        smiles=smiles,
        goal=f"Predict {', '.join(sorted(properties))} for {polymer_class.upper()}"
             + (f" ({smiles})" if smiles else ""),
        properties=sorted(properties),
        plan_mode="scaffold",
        # "unreviewed" is not in VALID_CONFIDENCE, so it is what blocks materialization until a
        # reviewer sets it. --baseline stamps "low" for the deterministic arm that runs with no
        # LLM in the loop.
        confidence="low" if baseline else "unreviewed",
        dominant_uncertainty="scientific_review_pending",
        decisions=rows,
        system_size=build_system_size(decided_params, size_solve, size_assumptions),
        hardware={k: derived[k] for k in ("engine", "mpi_ranks", "gpu_per_run", "ff_family")},
        overrides={},
        decided_params=decided_params,
        planned_stages=build_planned_stages(cls, properties, smiles),
    )


CACHE_PATH_DEFAULT = REPO_ROOT / "guides" / "system_characterization_cache.json"


def make_plan_from_cache(run_name: str, polymer_class: str, smiles: str, canonical_smiles: str,
                          properties: set, cache_entry: dict) -> dict:
    """Materialize run_plan.json from a validated cache entry's frozen protocol -- the exact
    protocol previously proven to reach "accepted" for this exact molecule -- instead of
    polymer_rules.json class defaults. This is the "system, not class" fast path.

    Hardware and everything else the force field implies is the exception: always re-derived
    from the frozen field, never replayed. Hardware stays host-dependent, so a run replayed on a
    recalibrated host must pick up the current policy rather than the original cell's.
    """
    rules = load_rules()
    cls = get_class_entry(rules, polymer_class)
    protocol = cache_entry["protocol"]
    decided_params = dict(protocol["decided_params"])  # literal replay, no recomputation
    # Retired rows are dropped on replay: a pre-2026-09-04 freeze carries five, and honouring a
    # frozen D-02/D-03/D-08 would reinstate exactly the field/charge disagreement the
    # derivation exists to prevent. The field is frozen; everything it implies is re-derived.
    decisions = [dict(d) for d in protocol["decisions"] if d.get("id") == "D-01_ff"]
    derived = _derived_from_field(decided_params.get("preferred_ff"), rules)
    decided_params["charge_method"] = derived["charge_method"]
    decided_params["electrostatics"] = derived["electrostatics"]
    replay_note = (
        f"decided_params/decisions/planned_stages replayed verbatim from "
        f"guides/system_characterization_cache.json[{canonical_smiles!r}], validated by "
        f"run {cache_entry.get('source_run_name')!r} on {cache_entry.get('validated_at')}.")
    if decisions:
        decisions[0].setdefault("critique", {"status": "protocol_validated_replay",
                                             "rounds": 0, "findings": [replay_note]})
    return ordered_plan(
        run_name=run_name,
        polymer_class=polymer_class.upper(),
        smiles=smiles,
        goal=f"Predict {', '.join(sorted(properties))} for {polymer_class.upper()} ({smiles})",
        properties=sorted(properties),
        plan_mode="deterministic",
        confidence="high",
        dominant_uncertainty="none_dominant",
        decisions=decisions,
        system_size={"dp_typical": decided_params.get("dp_typical"),
                     "nchain": decided_params.get("nchain"),
                     "resolved_by": "system_characterization_cache (frozen)",
                     "reasons": [replay_note], "acknowledgements": {}},
        hardware={k: derived[k] for k in ("engine", "mpi_ranks", "gpu_per_run", "ff_family")},
        overrides={},
        decided_params=decided_params,
        planned_stages=list(protocol["planned_stages"]),
    )


def _try_cache(run_name: str, polymer_class: str, smiles, properties: set,
               cache_path: Path | None = None) -> dict | None:
    """Look up a validated protocol for this exact SMILES and, if it covers every requested
    property, materialize the plan from it. Returns None (never raises) on any miss -- no smiles,
    no cache file, no entry, not validated, insufficient coverage, or a polymer_class mismatch --
    so callers fall through to the class-default make_plan() unchanged."""
    if not smiles:
        return None
    path = cache_path or CACHE_PATH_DEFAULT
    if not path.exists():
        return None
    try:
        canonical = rules_common.canonicalize(smiles, isomeric=True)
    except (RuntimeError, subprocess.TimeoutExpired):
        return None
    try:
        cache = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    entry = cache.get(canonical)
    if not entry or not entry.get("protocol_validated"):
        return None
    if not set(entry.get("validated_properties", [])) >= properties:
        return None
    if str(entry.get("polymer_class", "")).upper() != polymer_class.upper():
        # Don't trust a cache entry recorded under a different class label -- fall back
        # rather than silently apply a different class's frozen protocol.
        return None
    # A frozen protocol names the stages that ran when it was validated. If the stage vocabulary
    # has since changed (the equilibration/cooling split renamed and added stages), replaying it
    # verbatim produces a plan validate_run_plan rejects as STRUCTURAL -- and because _try_cache
    # has already committed the run to plan_mode="deterministic" by then, the failure surfaces as
    # PLAN_VALIDATION_FAILED rather than as a graceful fall-through to make_plan(). A locked
    # SMILES would become permanently unrunnable. Treat an unknown stage name as a cache MISS.
    frozen_stages = {st.get("stage") for st in
                     ((entry.get("protocol") or {}).get("planned_stages") or [])}
    if not frozen_stages <= set(track_registry.STAGE_TRACK):
        return None
    return make_plan_from_cache(run_name, polymer_class, smiles, canonical, properties, entry)


# ---------------------------------------------------------------------------
# D-01_ff row construction
#
# Every criterion the `forcefield` policy in decision_policy.json names gets its own evidence
# entry, including the ones this layer cannot reach -- those say NOT MEASURED / NOT ASSESSABLE
# explicitly rather than going silent, which is what tells the critic where its search is worth
# the most. Entries are tagged origin: "autofill"; the critic's own additions are tagged
# origin: "critic", and the benchmark's LLM-contribution metric keys off that split.
# ---------------------------------------------------------------------------


def _element_census(smiles: str) -> dict:
    """Crude element count straight off the SMILES string -- no RDKit subprocess.

    Two-letter symbols are matched before one-letter ones so Cl/Br/Si are not miscounted as
    C/B/S. Aromatic lowercase atoms are folded into their uppercase element. This backs D-02's
    backbone_polarity and D-03's backbone_heteroatoms findings, both of which only need
    "are there heteroatoms, and which" -- not a bond-perceived structure.
    """
    counts: dict[str, int] = {}
    for sym in re.findall(r"Cl|Br|Si|[BCNOPSFIbcnops]", smiles):
        el = {"c": "C", "n": "N", "o": "O", "s": "S", "p": "P", "b": "B"}.get(sym, sym)
        counts[el] = counts.get(el, 0) + 1
    return counts


def _electrostatics_guide_rule(rules: dict, polymer_class: str) -> tuple[str, dict]:
    """(rule_name, rule_block) -- whichever of use_lj_cut/use_pppm lists this class."""
    guide = rules.get("electrostatics_decision_guide", {}) or {}
    for name in ("use_lj_cut", "use_pppm"):
        block = guide.get(name) or {}
        if polymer_class.upper() in (block.get("classes") or []):
            return name, block
    return "", {}


def _ev(criterion: str, claim: str, resolver: str, **extra) -> dict:
    """One autofill evidence entry. `origin` is what keeps it out of the LLM-contribution count."""
    out = {"criterion": criterion, "claim": claim, "origin": "autofill", "resolver": resolver}
    out.update({k: v for k, v in extra.items() if v})
    return out


def _coverage_claim(polymer_class, prior, ff, resolution=None):
    """(claim, resolver) for D-01's parameter_coverage criterion.

    The "NOT MEASURED" prefix is emitted unless a real EMC trial build typed THIS SMILES.
    A moiety screen that found no known blocker does not count: 16% of the measured failures
    in docs/ff_coverage_sweep/SUMMARY.json matched no rule.
    """
    probed = list((resolution or {}).get("probed") or [])
    if not probed:
        # Say WHY no build ran, not which flag was passed: with --with-ff-probe on, a SMILES
        # that matches no rule is still never probed, and reporting that as "flag off" is wrong.
        blockers = (resolution or {}).get("blockers")
        if blockers is None:
            why = "The moiety screen was unavailable, so nothing narrowed the risk either."
        elif blockers:
            why = (f"The moiety screen matched {[b['id'] for b in blockers]}, groups measured to "
                   "block every registered EMC field, but probing was off (--with-ff-probe).")
        else:
            why = ("The moiety screen ran and matched no rule, so no trial build was triggered. "
                   "That narrows the risk and measures nothing: the rules cover 77% of the "
                   "measured failures (guides/ff_moiety_rules.json), so this SMILES is "
                   "UNSCREENED for the rest, not cleared.")
        return (f"NOT MEASURED for this SMILES. No EMC trial build was run, so coverage is "
                f"asserted from polymer_rules.json:classes.{polymer_class}."
                f"ff_accuracy_prior={prior!r} only; whether {ff!r} can type THIS repeat unit is "
                f"unverified until the build stage runs. {why}",
                f"polymer_rules.json:classes.{polymer_class}.ff_accuracy_prior")
    if not ff:
        return (f"MEASURED: an EMC trial build was run against {probed} and none typed this "
                f"repeat unit. There is no admissible field; this plan must not build.",
                "forcefield.select_by_moiety")
    return (f"MEASURED: an EMC trial build with {ff!r} typed this repeat unit "
            f"(fields probed: {probed}).",
            "forcefield.select_by_moiety")


def _ff_prior_uncertainty(polymer_class, prior, ff, resolution=None):
    """The uncertainty a plan MUST carry when it does not build with its class prior.

    D-01's only DOI-backed evidence is the class ff_justification_doi, which describes `prior`.
    Once the field changes, that citation no longer covers the run.
    """
    if ff == prior:
        return None
    blockers = [b.get("id") for b in (resolution or {}).get("blockers") or []]
    return {
        "name": "ff_accuracy_prior_not_met",
        "dominant": ff is None,
        "reduction_probe": "literature_anchor",
        "detail": (f"polymer_rules.json:classes.{polymer_class}.ff_accuracy_prior={prior!r} is "
                   f"the literature-supported field for this class, but this SMILES "
                   + (f"builds with {ff!r} instead" if ff else "has no admissible field")
                   + (f" (blocking moieties: {blockers})" if blockers else "")
                   + f". The class ff_justification_doi does not cover {ff!r}."),
    }


def _d01_ff_row(rules, cls, polymer_class, hw, criteria, field=None,
                resolution=None) -> dict:
    """D-01_ff. evidence_required=true, so at least one entry must carry source_doi/citation.

    `prior` is the class's literature recommendation; `ff` is what this run will build with.
    They differ when the resolver demotes the prior for this SMILES -- the DOI evidence below
    still describes `prior`, so a demoted plan must also carry an ff_accuracy_prior_not_met
    uncertainty (see _ff_prior_uncertainty).
    """
    prior = cls.get("ff_accuracy_prior")
    # A resolution is authoritative even when it says None -- that is "nothing types this
    # SMILES", not "no field was supplied", and _field_of cannot tell the two apart.
    ff = resolution["field"] if resolution else _field_of(cls, field)
    ev = []

    # literature_support -- the class's own FF justification, with a real DOI. 7 of 21 classes
    # carry no ff_justification_doi; for those, fall back to the first resolvable citations[] id
    # rather than emitting an uncited claim.
    note = cls.get("ff_note") or f"class default force field for {polymer_class}"
    if cls.get("ff_justification_doi"):
        ev.append(_ev("literature_support",
                      f"polymer_rules.json:classes.{polymer_class}.ff_note: {note}",
                      f"polymer_rules.json:classes.{polymer_class}.ff_justification_doi",
                      source_doi=cls["ff_justification_doi"]))
    else:
        backup = next((sid for sid in (cls.get("citations") or [])
                       if primary_source(rules, sid)), None)
        e = source_evidence(
            rules, backup,
            f"polymer_rules.json:classes.{polymer_class} carries no ff_justification_doi; "
            f"{prior!r} is the class prior and the strongest support on file is the class's own "
            f"first cited source. {note}",
            criterion="literature_support",
            resolver=f"polymer_rules.json:classes.{polymer_class}.citations[0]")
        ev.append(e)

    # validation_data -- one entry per cited source, ids resolved to real citations.
    for sid in (cls.get("citations") or []):
        src = primary_source(rules, sid)
        if not src:
            continue
        ev.append(source_evidence(
            rules, sid, src.get("relevance") or f"cited by class {polymer_class}",
            criterion="validation_data",
            resolver=f"polymer_rules.json:_metadata.primary_sources[{sid}]"))

    # parameter_coverage -- honest only when a real EMC trial build ran. The "NOT MEASURED"
    # prefix is load-bearing: the rationale gap list below collects criteria whose claim starts
    # with it, so it must survive every path where nothing was actually measured.
    ev.append(_ev("parameter_coverage",
                  *_coverage_claim(polymer_class, prior, ff, resolution)))

    # computational_cost -- reuse the D-08 pricing, don't re-call.
    if hw and "error" not in hw:
        est = (hw["decision"]["evidence"] or [{}])[0]
        ev.append(_ev("computational_cost",
                      f"{hw['ff_family']}-family cell of {hw['cell_atoms_estimate']} atoms "
                      f"({hw['cell_mass_g_per_mol_estimate']} g/mol): {est.get('claim', 'unpriced')}. "
                      f"electrostatics={cls.get('electrostatics')}, cutoff_A={cls.get('cutoff_A')}.",
                      "select_hardware.select_hardware"))
    else:
        ev.append(_ev("computational_cost",
                      f"NOT PRICED: select_hardware returned {(hw or {}).get('error', 'no result')}.",
                      "select_hardware.select_hardware"))

    # No class carries forcefield_alternatives (0/21), so there is no deterministic source for
    # an alternative. Say that rather than inventing one or leaving a bare [].
    # No class carries forcefield_alternatives (0/21). `alternatives` stays a list of FIELD
    # NAMES -- the prose that used to be its single element read as a field to anything
    # iterating it -- and the explanation moves to its own string beside it.
    alts = list(cls.get("forcefield_alternatives") or [])
    row = {"default_choice": ff, "criteria_evaluated": criteria,
           "evidence": ev, "alternatives": alts,
           "resolved_by": (f"polymer_rules.json:classes.{polymer_class}.ff_accuracy_prior"
                           if ff == prior and not (resolution or {}).get("probed")
                           else "forcefield.select_by_moiety")}
    if not alts:
        row["alternatives_note"] = (
            f"NONE ENUMERATED DETERMINISTICALLY -- polymer_rules.json:classes.{polymer_class} "
            f"has no forcefield_alternatives, and this layer will not invent one. The moiety "
            f"probe names what actually types this SMILES; the literature critic may name a "
            f"candidate on the evidence.")
    # Only when a probe actually ran: validate_run_plan's ff_no_admissible_field /
    # ff_not_admissible gates key off this list, and an unprobed [] would read as a
    # measurement that nothing types.
    if (resolution or {}).get("probed"):
        row["admissible"] = [ff] if ff else []
    return row


def _dominant_uncertainty(cls, size, hw) -> str:
    names = {u.get("name") for u in (size.get("uncertainties") or [])}
    if not cls.get("ff_justification_doi"):
        return "ff_transferability"
    if "RIGID_BACKBONE_CHAIN_LENGTH_BIAS" in names or "rigid_backbone_chain_length_bias" in names:
        return "system_size_chain_length_bias"
    if size.get("floor_was_unknown") or "MW_FLOOR_UNKNOWN" in names:
        return "system_size_mw_floor_unknown"
    if hw and "error" not in hw and hw["decision"].get("confidence") != "high":
        return "hardware_optimum"
    return "protocol_transferability"


def _properties_from_arg(properties: str) -> set:
    props_str = properties.strip().lower()
    return (set(track_registry.DEFAULT_PROPERTIES) if props_str == "all"
            else {x.strip().lower() for x in props_str.split(",") if x.strip()})


def _cmd_run_plan(args) -> int:
    properties = _properties_from_arg(args.properties)
    cache_path = Path(args.cache_path) if args.cache_path else None
    plan = (_try_cache(args.run_name, args.polymer_class, args.smiles, properties, cache_path)
            or make_plan(args.run_name, args.polymer_class, args.smiles, properties,
                         with_ff_probe=args.with_ff_probe,
                         baseline=getattr(args, "baseline", False)))
    text = json.dumps(plan, indent=2)

    if args.out == "-":
        print(text)
        return 0
    out_path = (Path(args.out) if args.out
                else REPO_ROOT / "data" / args.run_name / "raw" / "run_plan.json")
    # Refuse to clobber: this file is where the critique is adjudicated, so regenerating it
    # after a review has begun would silently discard that work. Inherited from the `decision`
    # subcommand -- the protection has to follow the file the reviewer edits.
    if out_path.exists() and not getattr(args, "force", False):
        print(json.dumps({"status": "exists", "run_plan": str(out_path),
                          "detail": "refusing to overwrite; pass --force to replace it"}))
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(json.dumps({"status": "success", "run_plan": str(out_path),
                      "plan_mode": plan["plan_mode"], "confidence": plan["confidence"]}))
    return 0


def main():
    p = argparse.ArgumentParser(description="Emit the deterministic planning artifacts.")
    sub = p.add_subparsers(dest="command", required=True)

    def _common(sp):
        sp.add_argument("--run_name")
        sp.add_argument("--polymer_class", required=True)
        sp.add_argument("--smiles", default=None)
        sp.add_argument("--properties", default="all",
                        help="Comma-separated: density,tg,bulk_modulus or 'all'")
        sp.add_argument("--out", default=None, help="Output path; '-' = stdout")
        sp.add_argument("--with-ff-probe", action="store_true",
                        help="Run a real EMC trial build for D-01 when the moiety screen finds "
                             "a known blocker, instead of asserting the class prior "
                             "(~0.5-3 s, only for a SMILES that matches a rule)")
        return sp

    rp = _common(sub.add_parser("run-plan", help="emit run_plan.json"))
    rp.add_argument("--force", action="store_true",
                    help="Overwrite an existing run_plan.json (default: refuse, to protect "
                         "in-progress critique work)")
    rp.add_argument("--baseline", action="store_true",
                    help="Stamp confidence='low' instead of 'unreviewed', so the plan "
                         "materializes with no LLM in the loop. For the deterministic benchmark "
                         "arm only -- a normal reasoned run leaves this off and the literature "
                         "critic's review sets the confidence.")
    rp.add_argument("--cache_path", default=None,
                    help="Override guides/system_characterization_cache.json path (testing only)")
    rp.set_defaults(func=_cmd_run_plan)

    args = p.parse_args()
    if not args.run_name:
        p.error("--run_name is required")
    # `decision` hard-required a SMILES, because it resolved the cell and the hardware from the
    # molecule. `run-plan` now does that same resolution but deliberately tolerates None: the
    # cache-replay and class-default paths have no SMILES to give, and the no-SMILES case is
    # SAFE rather than silent -- size_the_cell records D-04 UNRESOLVED and run_campaign refuses
    # to build, instead of defaulting the cell (test_a_plan_with_no_smiles_says_so_instead_of_
    # sizing_blind). A hard error here would break replay for no gain.
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
