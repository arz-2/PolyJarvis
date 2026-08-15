#!/usr/bin/env python3
"""
make_deterministic_plan.py — Emit a deterministic run_plan.json for a polymer class.

This is the *deterministic* branch of the Planner — the validated-system path (see
decision_policy.json:confidence_gate): used as-is when this exact canonical SMILES
already has a `protocol_validated` entry in guides/system_characterization_cache.json,
and as the starting-hypothesis scaffold (class defaults only — never a trust signal)
every reasoned plan for a novel SMILES begins from. It transcribes the decision-relevant
defaults from guides/polymer_rules.json into a structured, self-documenting plan artifact.

Reproducibility guarantee: decided_params snapshots ONLY keys already present in
the class entry, with their existing values. gen_prompt.py --plan overlays them as
{**cls, **decided_params}, which is therefore an identity — worker prompts are
byte-identical to the pre-architecture pipeline. The regression test
tests/test_plan_reproducibility.py enforces this for every class and stage.

The reasoned branch (Planner agent, novel/partially-validated SMILES) writes a
run_plan.json with the SAME schema but possibly-different decided_params and a
non-trivial critique block. gen_prompt.py --plan consumes both identically.

Usage:
  python3 orchestration/make_deterministic_plan.py \
      --run_name PE7 --polymer_class PHYC \
      [--smiles "*CC*"] [--properties density,tg,bulk_modulus] \
      [--out PATH]        # default: data/<run_name>/raw/run_plan.json; "-" = stdout
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hw_common import load_rules, get_class_entry  # shared rules access (single source of truth)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_PATH = REPO_ROOT / "guides" / "polymer_rules.json"

# Decision-relevant class keys consumed by gen_prompt.py builders. Only keys that
# EXIST in the class entry are snapshotted, so the overlay stays an exact identity.
#
# eq_annealing_cycles is deliberately ABSENT: generate_equilibration_workflow has no
# annealing-cycles argument, so snapshotting it into decided_params records a protocol
# that never runs. The class-level values stay in polymer_rules.json as a documented
# hypothesis; they just no longer masquerade as executed protocol.
SNAPSHOT_KEYS = [
    "preferred_ff", "preferred_builder", "charge_method", "electrostatics",
    "cutoff_A", "dt_fs",
    "dp_typical", "nchain", "density_initial_gcm3",
    "T_equil_K", "annealing_T_high_K", "P_equil_atm",
    "t_equil_ns", "npt_prod_ns", "melt_npt_ns",
    "tg_t_high_K", "tg_t_low_K", "tg_t_step_K", "tg_steps_per_t", "tg_rates_K_per_ns",
    "tg_min_steps_per_T", "tg_slope_gate_fallback",
    "K_deform_rate_inv_s", "K_deform_rate_slow_inv_s", "K_strain_max",
    "bm_pressures_atm", "ct_min_decay_melt",
    "alpha_glass_per_K", "alpha_melt_per_K",
]

# ── Protocol freezing (per exact canonical SMILES) ───────────────────────────
# A frozen protocol records what ONE molecule actually executed, so a replicate can reproduce it
# with different seeds. Three categories, explicit so they cannot drift:
#
#   FREEZE_KEYS   physics — reproduce exactly.
#   NEVER_FREEZE  seeds (must VARY per replicate) and host wiring (must be RE-DERIVED from
#                 hardware_policy, or a frozen protocol stops being portable off this box).
#
# Distinct from SNAPSHOT_KEYS above: that list is the class-default scaffold, read from
# polymer_rules.json. FREEZE_KEYS is read from a finished run's own decided_params, and adds two
# keys the class scaffold cannot supply — backbone_types (molecule-specific; run_deterministic_
# replicate.py hard-halts BACKBONE_TYPES_UNRESOLVED without it) and the pinned scalar
# experimental_tg_K (_exp_tg_bracket leaves it None for multi-member classes, since the scaffold
# cannot map SMILES -> member; a finished run knows which member it is).
NEVER_FREEZE = {
    "engine", "mpi_ranks", "gpu_per_run", "gpu_ids",   # re-derive per host
    "emc_seed", "velocity_seed",                        # vary per replicate
}
FREEZE_EXTRA_KEYS = ["backbone_types", "experimental_tg_K"]
FREEZE_KEYS = [k for k in [*SNAPSHOT_KEYS, *FREEZE_EXTRA_KEYS] if k not in NEVER_FREEZE]

# The same freeze/vary/re-derive split applied to an equilibration STAGE's resolved params.
# Whitelist, not blacklist: a stage dict also carries absolute output paths and the launch engine,
# and freezing either would pin the protocol to one run directory and one machine.
STAGE_PARAM_KEEP = {
    "T_START", "T_FINAL", "TEMP", "T_DAMP",
    "P_START", "P_FINAL", "PRESS", "P_DAMP",
    "TIMESTEP", "N_STEPS",
    "use_pppm", "use_pcff", "use_trappe", "use_opls", "use_shake",
}


def freeze_stage_params(params: dict) -> dict:
    """Physics only. Drops LOG_FILE/DUMP_FILE/WRITE_DATA_FILE/params_file (run-specific paths)
    and engine/use_gpu/write_restart (host wiring)."""
    return {k: v for k, v in (params or {}).items() if k in STAGE_PARAM_KEEP}

# Which track each frozen key belongs to, so a run can freeze the tracks whose physical validity
# gates passed and leave the rest unfrozen. Mirrors STAGE_TRACK below (stages -> tracks); this is
# params -> tracks. Anything unlisted falls to "foundation", which both other tracks depend on.
# alpha_glass_per_K/alpha_melt_per_K are deliberately foundation, not thermal: the thermal track
# MEASURES them, but as decided_params they are INPUTS to enforce_equilibration_gate's
# cooling-contraction check, which runs at equil-check.
_TRACK_PREFIXES = [("thermal", ("tg_", "dsc_")), ("mechanical", ("K_", "bm_"))]


def key_track(key: str) -> str:
    """Track owning a frozen decided_params key. Prefix-driven so a new tg_*/K_*/bm_* key lands in
    the right track without being enumerated here."""
    for track, prefixes in _TRACK_PREFIXES:
        if key.startswith(prefixes):
            return track
    return "foundation"


def partition_frozen_params(decided_params: dict) -> dict:
    """Split a finished run's decided_params into {track: {key: value}}, dropping NEVER_FREEZE."""
    out = {"foundation": {}, "thermal": {}, "mechanical": {}}
    for k in FREEZE_KEYS:
        if k in decided_params:
            out[key_track(k)][k] = decided_params[k]
    return out


def _load(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def read_validity_gates(raw_dir: Path) -> dict:
    """Per-track PHYSICAL VALIDITY verdicts for a finished run, read from its own raw/*.json.

    This is what freezing binds on -- NOT run_summary.json's results[<prop>].status, which is
    agreement with experiment. A protocol can be physically sound and still miss an experimental
    band for force-field reasons (PCFF glassy density runs 4.5-6.2% low as a cooling artifact, and
    a replicate should reproduce that deficit); it can also land inside every band while violating
    minimum image, and that protocol must never be frozen.

    Returns {track: {"pass": bool|None, "gates": {name: verdict}, "missing": [...]}}.
    pass=None means the track was not run / cannot be adjudicated -- never treat that as a pass.
    """
    tracks = {}

    # ── foundation: equilibration + finite size + homogeneity ──
    gate = _load(raw_dir / "equilibration_gate_full.json")
    comp = _load(raw_dir / "equilibration_comprehensive.json")
    spatial = (comp or {}).get("spatial") or {}
    fs = spatial.get("finite_size") or {}
    hom = spatial.get("density_homogeneity") or {}
    g = {
        "equil_verdict": (gate or {}).get("verdict"),
        # available=False means the check could not run -- report None, not a pass.
        "finite_size_verdict": (gate or {}).get("finite_size_verdict")
                               or (fs.get("verdict") if fs.get("available") else None),
        # HOMOG_PASS already subtracts Poisson counting noise (cv_signal, not raw cv_mean), so
        # the documented "CV>25% is melt-only" concern is handled inside the verdict itself --
        # read the verdict, never re-derive from cv_mean.
        "homogeneity_verdict": (gate or {}).get("homogeneity_verdict") or hom.get("verdict"),
    }
    expected = {"equil_verdict": "PASS", "finite_size_verdict": "SIZE_PASS",
                "homogeneity_verdict": "HOMOG_PASS"}
    missing = [k for k, v in g.items() if v is None]
    tracks["foundation"] = {
        "pass": None if missing else all(g[k] == want for k, want in expected.items()),
        "gates": g, "missing": missing,
    }

    # ── thermal: Tg reportability ──
    tg = _find_one(raw_dir, "tg_summary.json")
    tg_reportable = (tg or {}).get("tg_reportable")
    tracks["thermal"] = {
        "pass": None if tg is None else bool(tg_reportable),
        "gates": {"tg_gate_verdict": (tg or {}).get("tg_gate_verdict")},
        "missing": [] if tg is not None else ["tg_summary.json"],
    }

    # ── mechanical: Murnaghan, or the deform fallback route ──
    murn = _find_one(raw_dir, "bulk_modulus_murnaghan.json")
    defo = _find_one(raw_dir, "bulk_modulus_deform.json")
    bm_reportable = bool((murn or {}).get("bm_reportable"))
    deform_ok = (defo or {}).get("deform_gate_verdict") == "DEFORM_REPORTABLE"
    if murn is None and defo is None:
        mech = {"pass": None, "gates": {}, "missing": ["bulk_modulus_*.json"]}
    else:
        # BM_FALLBACK_DEFORM is a ROUTE, not a failure: a Murnaghan fit that was rejected and
        # handed off to deform is freezable on the deform gate, recorded as bm_method="deform".
        mech = {
            "pass": bm_reportable or deform_ok,
            "gates": {"bm_gate_verdict": (murn or {}).get("bm_gate_verdict"),
                      "deform_gate_verdict": (defo or {}).get("deform_gate_verdict")},
            "missing": [],
            "bm_method": "murnaghan" if bm_reportable else ("deform" if deform_ok else None),
        }
    tracks["mechanical"] = mech
    return tracks


def _find_one(raw_dir: Path, filename: str):
    """Analysis artifacts land in per-stage subdirs of raw/ (tg_summary.json under the analyze-tg
    output_dir, bulk_modulus_* under analyze-bm's). Search raw/ and one level of nesting; if a
    rerun left several, take the newest."""
    hits = sorted(raw_dir.rglob(filename), key=lambda p: p.stat().st_mtime, reverse=True)
    return _load(hits[0]) if hits else None


def _load_equil_workflow(raw_dir: Path, replay: dict = None) -> dict:
    """generate_equilibration_workflow persists its RESOLVED return dict into work_dir_base
    (data/<RUN>/lammps/equil/). Fall back to raw/ so a hand-placed copy also works.

    Last resort, for runs that predate that persistence: the replay's own regenerated workflow.
    Only legitimate when foundation replayed CLEAN — that is precisely the proof that the
    regenerated decks are the decks that ran, so their resolved step counts are too."""
    run_dir = raw_dir.parent
    for candidate in (run_dir / "lammps" / "equil" / "equil_workflow.json",
                      raw_dir / "equil_workflow.json"):
        wf = _load(candidate)
        if wf:
            return wf
    if ((replay or {}).get("tracks", {}).get("foundation") or {}).get("verified"):
        wf = _load(raw_dir / "replay" / "equil" / "equil_workflow.json")
        if wf:
            wf["_source"] = "regenerated_by_verified_deck_replay"
            return wf
    return {}


def _seeds_used(raw_dir: Path, run_name: str) -> dict:
    """The seeds this run actually used. executor_state.json is authoritative where it exists;
    otherwise fall back to run_log.md's `Seeds:` line, then to the run_name-derived velocity
    seed gen_prompt._velocity_seed computes when nothing is pinned."""
    seeds = {"emc_seed": None, "velocity_seed": None}
    state = _load(raw_dir / "executor_state.json") or {}
    build = ((state.get("stages") or {}).get("build") or {}).get("result") or {}
    seeds["emc_seed"] = build.get("emc_seed")

    run_log = raw_dir.parent / "run_log.md"
    if run_log.exists():
        text = run_log.read_text(errors="ignore")
        for label, key in (("EMC", "emc_seed"), ("velocity", "velocity_seed")):
            if seeds[key] is None:
                m = re.search(rf"Seed logged \({label}\):\s*`(-?\d+)`", text)
                if m:
                    seeds[key] = int(m.group(1))
    if seeds["velocity_seed"] is None:
        digest = hashlib.sha256(run_name.encode()).hexdigest()
        seeds["velocity_seed"] = 10000 + int(digest, 16) % 989_999
        seeds["velocity_seed_source"] = "derived_from_run_name"
    return seeds


def _executed_route(plan: dict, raw_dir: Path, gates: dict, workflow: dict) -> dict:
    """The branches this run actually took, per track. These are protocol too: a K from the deform
    fallback and a K from Murnaghan are not the same measurement, so a replicate has to be told
    which one to reproduce rather than re-deciding from its own gate."""
    dp = plan.get("decided_params", {})
    dt = dp.get("dt_fs") or 1.0

    # Total npt production time as ACTUALLY run, EXTENDs included. Frozen as a total so a replicate
    # runs the same simulated time up front instead of replaying an EXTEND remedy it may not need.
    total_steps = sum(
        s.get("params", {}).get("N_STEPS") or 0
        for s in (workflow.get("stages") or [])
        if "npt_prod" in (s.get("name") or "") or "npt_extend" in (s.get("name") or "")
    )
    npt_prod_total_ns = round(total_steps * dt * 1e-6, 4) if total_steps else None

    t_workflow = dp.get("T_workflow_K")
    route = {
        "foundation": {"is_glassy": (t_workflow != 300.0) if t_workflow is not None else None,
                       "npt_prod_total_ns": npt_prod_total_ns},
        "thermal": {},
        "mechanical": {},
    }

    rates = dp.get("tg_rates_K_per_ns") or []
    tg = _find_one(raw_dir, "tg_summary.json")
    rate_ran = (tg or {}).get("cooling_rate_K_per_ns")
    if rates and rate_ran is not None:
        # Match on value, not on the "highest rate" convention -- a slope_gate_fallback class
        # deliberately runs rates[0], and the frozen route must say which index actually ran.
        matches = [i for i, r in enumerate(rates) if abs(float(r) - float(rate_ran)) < 1e-9]
        route["thermal"] = {"tg_rate_index": matches[0] if matches else None,
                            "tg_rate_K_per_ns": rate_ran}

    bm_method = (gates.get("mechanical") or {}).get("bm_method")
    if bm_method:
        route["mechanical"] = {"bm_method": bm_method}
    return route


def build_frozen_protocol(plan: dict, raw_dir: Path, run_name: str,
                          replay: dict = None) -> dict:
    """Assemble the per-track `protocol` block written into
    guides/system_characterization_cache.json[canonical_smiles].

    A track freezes only when BOTH hold:
      1. its PHYSICAL VALIDITY gates passed (not agreement with experiment), and
      2. its decks replay from this plan (verify_protocol_replay) — so a plan value that never
         reached a deck cannot be frozen as protocol.

    (2) is not hypothetical. PLA1's plan records tg_steps_per_t=500000 while its sweep ran
    200000 (the value rate=100 K/ns implies) — freezing that would give every replicate a 2.5x
    slower cooling rate, and hence a different Tg, than the run it is meant to replicate.

    Foundation is a prerequisite of both other tracks, so if foundation does not freeze, nothing
    does.
    """
    gates = read_validity_gates(raw_dir)
    workflow = _load_equil_workflow(raw_dir, replay)
    params_by_track = partition_frozen_params(plan.get("decided_params", {}))
    route = _executed_route(plan, raw_dir, gates, workflow)
    summary = _load(raw_dir / "run_summary.json") or {}
    agreement = {p: (summary.get("results", {}).get(p) or {}).get("status")
                 for p in plan.get("properties", [])}
    now = datetime.now(timezone.utc).isoformat()

    replay_tracks = (replay or {}).get("tracks") or {}

    def _freezable(track):
        if not gates[track]["pass"]:
            return False, "validity_gates_not_passed"
        if replay is None:
            return True, "replay_not_run"
        verified = (replay_tracks.get(track) or {}).get("verified")
        if verified is False:
            return False, "deck_replay_diverged"
        if verified is None:
            # Nothing was proven either way. Refuse: an unverified protocol is exactly the
            # decorative-params situation this gate exists to prevent.
            return False, "deck_replay_unverified"
        return True, "verified"

    ok, why = _freezable("foundation")
    if not ok:
        return {}, {"gates": gates, "replay": replay_tracks, "foundation_refused": why}

    protocol = {}
    for track in ("foundation", "thermal", "mechanical"):
        ok, why = _freezable(track)
        if not ok:
            continue
        block = {
            "source_run_name": run_name,
            "frozen_at": now,
            "verified_by_deck_replay": why == "verified",
            "validity_gates": gates[track]["gates"],
            "decided_params": params_by_track[track],
            "route": route[track],
            # Advisory only -- recorded so a reader can see the experimental comparison, but it
            # played no part in whether this track froze.
            "agreed_with_experiment": agreement,
        }
        if track == "foundation":
            block["equil_stages"] = [
                {"name": s.get("name"), "params": freeze_stage_params(s.get("params"))}
                for s in (workflow.get("stages") or [])
            ]
            block["n_atoms"] = workflow.get("n_atoms")
            # Recorded so a replicate can ASSERT it drew different ones -- never to reuse them.
            # EMC has returned a previous run's seed while reporting it as a fresh draw
            # (cis-PBD1 was handed cis-PBD4's 482913, matching box included), which silently
            # destroys the independence replicate aggregation assumes.
            block["seeds_used"] = _seeds_used(raw_dir, run_name)
        protocol[track] = block
    return protocol, gates


def _exp_tg_scalar(cls: dict):
    """Tg used ONLY for the glassy-vs-rubbery REGIME (and hence equil temperature). For a
    multi-member class the members sit on the same side of 300 K, so the dict median picks the
    regime correctly — keep it, so the deterministic plan reproduces the no-plan equil prompt."""
    tg = cls.get("experimental_tg_K")
    if isinstance(tg, dict):
        vals = sorted(v for v in tg.values() if isinstance(v, (int, float)))
        return vals[len(vals) // 2] if vals else None
    return tg if isinstance(tg, (int, float)) else None


def _exp_tg_bracket(cls: dict):
    """Tg ACCURACY success_criterion (t_range_brackets_exp_tg). A multi-member dict has no
    SMILES->member mapping, so the scaffold cannot tell which member this run is — leave the
    bracket UNPINNED (None) rather than silently picking a wrong member (the old median pick
    gave PEKK/433 for a PEEK/418 run). The planner must pin the member from the SMILES (see each
    class's experimental_tg_K.multi_member_note in polymer_rules.json). Single-member passes through."""
    tg = cls.get("experimental_tg_K")
    return tg if isinstance(tg, (int, float)) else None


def build_decisions(cls: dict) -> list:
    """Structured decision rows carrying evidence/confidence/alternatives, mirroring
    run_summary.json decision IDs. Evidence is transcribed from existing class fields.

    "confidence" here is a fixed "class_default" placeholder, not a per-decision
    quality tier: this output is either used as-is for an already-`protocol_validated`
    SMILES (where per-decision confidence is moot -- the exact molecule already passed
    a full reasoned+critic review once), or as a scaffold the reasoned Planner
    immediately revises with real evidence and its own confidence per decision
    (planner.md step B). Never left as "class_default" in a plan that actually ships.
    """
    ff_evidence = []
    if cls.get("ff_justification_doi"):
        ff_evidence.append({"claim": cls.get("ff_note", "force field choice"),
                            "source_doi": cls.get("ff_justification_doi")})
    for cit in cls.get("citations", []):
        ff_evidence.append({"claim": "supporting validation", "citation": cit})

    conf = "class_default"
    return [
        {"id": "D-01_ff", "choice": cls.get("preferred_ff"),
         "criteria_evaluated": ["literature_support", "parameter_coverage",
                                 "validation_data", "computational_cost"],
         "evidence": ff_evidence, "confidence": conf,
         "alternatives": cls.get("forcefield_alternatives", [])},
        {"id": "D-02_charges", "choice": cls.get("charge_method"),
         "criteria_evaluated": ["backbone_polarity", "ff_embedded_vs_qm"],
         "evidence": [], "confidence": conf, "alternatives": []},
        {"id": "D-03_electrostatics", "choice": cls.get("electrostatics"),
         "criteria_evaluated": ["backbone_heteroatoms", "max_partial_charge"],
         "evidence": [{"claim": "see electrostatics_decision_guide",
                       "source": "polymer_rules.json:electrostatics_decision_guide"}],
         "confidence": conf, "alternatives": []},
        {"id": "D-04_system_size",
         "choice": f"DP={cls.get('dp_typical')}, nchain={cls.get('nchain')}",
         "criteria_evaluated": ["property_target", "finite_size_effects", "gpu_budget"],
         "evidence": [], "confidence": conf, "alternatives": []},
    ]


STAGE_TRACK = {
    "build":       "foundation",
    "equil":       "foundation",
    "equil-check": "foundation",
    "tg":          "thermal",
    "analyze-tg":  "thermal",
    "analyze-tg-multirate": "thermal",
    "deform":      "mechanical",
    "murnaghan":   "mechanical",
    "analyze-bm":  "mechanical",
    "run-summary": "summary",
}


def build_planned_stages(cls: dict, properties: set) -> list:
    """Experiment DAG with per-stage success_criteria the Validator enforces."""
    exp_tg = _exp_tg_scalar(cls)                 # regime/temperature (median ok for multi-member)
    glassy_hint = (exp_tg is not None and exp_tg > 300)
    exp_tg_bracket = _exp_tg_bracket(cls)        # accuracy gate (None for multi-member → planner pins)

    def _s(stage, criteria, **extra):
        return {"stage": stage, "track": STAGE_TRACK[stage],
                "success_criteria": criteria, **extra}

    stages = [
        _s("build",       {"data_file_written": True}),
        _s("equil",       {"check_equilibration_comprehensive.overall_pass": True}),
        _s("equil-check", {"equil_verdict": "PASS"}),
    ]
    if "tg" in properties:
        # Single-rate-primary: one sweep at the class's primary configured rate (highest by
        # default; tg_slope_gate_fallback="slowest_rate" classes run rates[0] instead — their
        # highest-rate fit is documented as degenerate/inverted). Multirate extrapolation
        # (extract_tg_multirate.py, select_tg_path.py, the analyze-tg-multirate stage) remains
        # available as a legacy/opt-in capability but is not part of the default plan DAG.
        stages.append(_s("tg", {"bilinear_fit_r_squared_min": 0.80,
                                "t_range_brackets_exp_tg": exp_tg_bracket}))
        stages.append(_s("analyze-tg", {}))
    if "bulk_modulus" in properties:
        # Murnaghan always submits now (2026-08-09): guides/MURNAGHAN.md's rubbery
        # null-fallback resolves to the PROBE ladder instead of an all-null RESULT, so
        # there is no longer a "rubbery without pressures -> fluctuation only, no submit
        # stage" case. Glassy still carries the deform fallback; rubbery (empirical
        # ladder or PROBE ladder) does not.
        stages.append(_s("murnaghan", {"chain_submitted": True},
                          **({"fallback": "deform"} if glassy_hint else {})))
        stages.append(_s("analyze-bm", {}))
    stages.append(_s("run-summary", {}))  # always terminal
    return stages


def _assert_tg_rates_feasible(cls: dict, polymer_class: str) -> None:
    """Reject a multirate Tg set where any rate gives too few steps per temperature.

    Per-T simulation TIME (not step count) sets bilinear-fit quality: too few ps at each
    temperature collapses the Tg fit (cis-PBD2 r400=50ps, PEEK2 r160/r400 degenerate).
    Rate IS the per-T step knob (N = tg_t_step_K/(rate*dt*1e-6)), so an infeasible rate
    cannot be salvaged at run time — fail at plan time. Floor = tg_min_steps_per_T
    (default 200000 steps = 200 ps at dt=1fs; TraPPE dt=2fs classes set 100000 = 200 ps).
    """
    rates = cls.get("tg_rates_K_per_ns")
    t_step = cls.get("tg_t_step_K")
    if not rates or t_step is None:
        return
    dt = cls.get("dt_fs", 1.0)
    floor = cls.get("tg_min_steps_per_T", 200000)
    bad = [(r, int(t_step / (r * dt * 1e-6)))
           for r in rates if t_step / (r * dt * 1e-6) < floor - 1]
    if bad:
        max_rate = t_step / (floor * dt * 1e-6)
        raise ValueError(
            f"{polymer_class}: infeasible tg_rates_K_per_ns {rates} — "
            f"rate(s) {[b[0] for b in bad]} give {[b[1] for b in bad]} steps/T, below "
            f"tg_min_steps_per_T={floor} (tg_t_step_K={t_step}, dt_fs={dt}). Lower the rates "
            f"so N = tg_t_step_K/(rate*dt*1e-6) >= floor (max feasible rate = {max_rate:.0f} K/ns)."
        )


def load_frozen_protocol(canonical_smiles: str, cache_path: Path = None) -> dict:
    """This exact SMILES's frozen `protocol` block, or {}. Keyed per-SMILES, so two validated
    molecules in one class never overwrite each other the way the class-level --lock-from
    backfill does."""
    cache_path = cache_path or (REPO_ROOT / "guides" / "system_characterization_cache.json")
    if not canonical_smiles:
        return {}
    cache = _load(cache_path) or {}
    return (cache.get(canonical_smiles) or {}).get("protocol") or {}


def make_plan(run_name: str, polymer_class: str, smiles, properties: set,
              frozen_protocol: dict = None, with_chain: bool = True) -> dict:
    rules = load_rules()
    cls = get_class_entry(rules, polymer_class)
    _assert_tg_rates_feasible(cls, polymer_class.upper())
    decided_params = {k: cls[k] for k in SNAPSHOT_KEYS if k in cls}
    # A frozen protocol overrides the class scaffold: it records what THIS molecule actually ran,
    # verified against its own decks, whereas the class entry is a starting hypothesis shared with
    # every other SMILES in the class.
    frozen_protocol = frozen_protocol or {}
    for track_block in frozen_protocol.values():
        decided_params.update(track_block.get("decided_params") or {})
    exp_tg = _exp_tg_scalar(cls)
    T_equil = decided_params.get("T_equil_K", 600.0)
    decided_params["T_workflow_K"] = 300.0 if (exp_tg is not None and exp_tg < 300) else T_equil
    # Derived constant (like T_workflow_K, not snapshotted from cls): the DSC-equivalent
    # cooling rate (10 K/min = 1.6667e-10 K/ns) that the multirate Tg fit extrapolates to.
    # Class entries may override via polymer_rules.json; otherwise this default applies.
    decided_params["dsc_equiv_rate_K_per_ns"] = cls.get("dsc_equiv_rate_K_per_ns", 1.6667e-10)
    uncertainties = [
        {"name": "ff_transferability",
         # This script's own raw output only "means" something as the validated/
         # deterministic case (an already-protocol_validated SMILES, or a scaffold
         # the reasoned Planner is about to overwrite with its own real dominant
         # uncertainty) -- never a signal in itself, so not dominant here.
         "dominant": False,
         "reduction_probe": "none"},
    ]
    plan = {
        "schema_version": "1.0",
        "goal": f"Predict {', '.join(sorted(properties))} for {polymer_class.upper()}"
                + (f" ({smiles})" if smiles else ""),
        "run_name": run_name,
        "polymer_class": polymer_class.upper(),
        "smiles": smiles,
        "properties": sorted(properties),
        # Always emitted as "validated" -- this script's raw output is used either
        # as-is for a SMILES already protocol_validated in
        # guides/system_characterization_cache.json, or as a scaffold the reasoned
        # Planner immediately overwrites to "novel" (planner.md step B) once it
        # starts revising. A plan that ships with confidence="validated" and
        # plan_mode="reasoned" together is a bug in the caller, never in this script.
        "confidence": "validated",
        "plan_mode": "deterministic",
        "assumptions": [
            "polymer_rules.json class defaults are a starting hypothesis, not a "
            "trust signal -- validity for THIS run rests on plan_mode/confidence "
            "above, sourced from this exact canonical SMILES's "
            "system_characterization_cache.json entry, not from this class.",
        ],
        "uncertainties": uncertainties,
        "decided_params": decided_params,
        "decisions": build_decisions(cls),
        "planned_stages": build_planned_stages(cls, properties),
        "critique": {"status": "approved", "rounds": 0,
                     "findings": ["deterministic plan: defaults transcribed verbatim; "
                                  "auto-approved -- this exact canonical SMILES is "
                                  "already protocol_validated"]},
        "provenance": {"generator": "make_deterministic_plan.py",
                       "generated_at": datetime.now(timezone.utc).isoformat()},
    }
    if frozen_protocol:
        plan["frozen_protocol"] = frozen_protocol
        plan["provenance"]["protocol_source"] = {
            track: {"source_run_name": b.get("source_run_name"), "frozen_at": b.get("frozen_at"),
                    "verified_by_deck_replay": b.get("verified_by_deck_replay")}
            for track, b in frozen_protocol.items()
        }
    if with_chain:
        plan["execution_chain"] = _execution_chain(plan, rules, properties, frozen_protocol)
    return plan


def _execution_chain(plan: dict, rules: dict, properties: set, frozen_protocol: dict) -> list:
    """The ordered, fully-resolved stage chain this plan runs end to end. Imported lazily so the
    plan writer keeps working (minus the chain) if the resolver's heavier deps are unavailable —
    a chain is a convenience for inspection and execution, never a prerequisite for planning."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import execution_chain as ec
        from gen_prompt import apply_plan, resolve_hardware
    except ImportError as e:
        return [{"error": f"execution chain unavailable: {e}"}]
    args = ec.base_args(plan["run_name"], plan["polymer_class"], "<in-memory>")
    cls = apply_plan(get_class_entry(rules, plan["polymer_class"]), plan, args)
    resolve_hardware(args, cls, rules)
    return ec.build_execution_chain(args, cls, plan, properties, frozen_protocol)


def _recovery_summary(run_plan_path: Path) -> str:
    """Best-effort one-line summary of what was diagnosed, from the sibling run_log.md's
    RECOVERY blocks (data/<run>/raw/run_plan.json -> data/<run>/run_log.md). Empty string
    if the log is absent or has no RECOVERY blocks -- this is a provenance nicety, not
    load-bearing, so failures here must never block the lock itself."""
    try:
        run_log = run_plan_path.parents[1] / "run_log.md"
        if not run_log.exists():
            return ""
        text = run_log.read_text(errors="ignore")
        headers = [ln.strip("# ").strip() for ln in text.splitlines()
                   if ln.strip().startswith("## RECOVERY")]
        if not headers:
            return ""
        return f"{len(headers)} recovery block(s) logged ({'; '.join(headers[:3])}{'...' if len(headers) > 3 else ''})"
    except OSError:
        return ""


def lock_from(run_plan_path: Path, polymer_class: str, rules_path: Path) -> dict:
    """--lock-from: patch guides/polymer_rules.json's class entry with a finished, fully-PASSed
    reasoned run's decided_params, backfilling the class-level starting-hypothesis scaffold
    every future reasoned plan for a novel SMILES in this class begins from.

    This is a class-default improvement only -- it does NOT validate any SMILES for the
    deterministic/critic-skip path. That is a per-exact-SMILES status
    (guides/system_characterization_cache.json[canonical_smiles].protocol_validated),
    stamped separately by protocol-locker.md after this run.

    Only ever writes SNAPSHOT_KEYS fields (the same list make_plan() reads) and one
    provenance note field (_protocol_locked_note) -- DOI citations, experimental_* targets,
    and every other hand-curated field in the class entry are left untouched.
    """
    plan = json.loads(run_plan_path.read_text())
    if plan.get("plan_mode") != "reasoned":
        raise SystemExit(
            f"--lock-from refuses: {run_plan_path} has plan_mode={plan.get('plan_mode')!r}, "
            "not 'reasoned' -- locking only comes from a diagnosed-and-perfected run, "
            "never from replaying a replay.")
    plan_class = (plan.get("polymer_class") or "").upper()
    if plan_class and plan_class != polymer_class.upper():
        raise SystemExit(
            f"--lock-from refuses: {run_plan_path} is polymer_class={plan_class!r}, "
            f"not the requested {polymer_class.upper()!r}.")

    rules = json.loads(rules_path.read_text())
    cls_entry = rules["classes"].get(polymer_class.upper())
    if cls_entry is None:
        raise SystemExit(f"--lock-from refuses: class {polymer_class.upper()!r} not found in "
                          f"{rules_path} -- create the class entry before locking a protocol.")

    finished_params = plan.get("decided_params", {})
    changes = {}
    for k in SNAPSHOT_KEYS:
        if k not in finished_params:
            continue
        new_val = finished_params[k]
        old_val = cls_entry.get(k)
        if old_val != new_val:
            changes[k] = {"was": old_val, "now": new_val}
            cls_entry[k] = new_val

    source_run = plan.get("run_name", "unknown")
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary = _recovery_summary(run_plan_path)
    note = f"Class defaults backfilled {date} from {source_run}."
    if summary:
        note += f" {summary}."
    if not changes:
        note += " No decided_params diverged from prior class defaults."
    cls_entry["_protocol_locked_note"] = note

    rules_path.write_text(json.dumps(rules, indent=2) + "\n")
    return {"status": "locked", "polymer_class": polymer_class.upper(),
            "source_run": source_run, "rules_path": str(rules_path),
            "changes": changes, "note": note}


def main():
    p = argparse.ArgumentParser(description="Emit a deterministic run_plan.json.")
    p.add_argument("--run_name")
    p.add_argument("--polymer_class", required=True)
    p.add_argument("--smiles", default=None)
    p.add_argument("--properties", default="all",
                   help="Comma-separated: density,tg,bulk_modulus or 'all'")
    p.add_argument("--out", default=None,
                   help="Output path; default data/<run_name>/raw/run_plan.json; '-' = stdout")
    p.add_argument("--lock-from", default=None, metavar="RUN_PLAN_JSON",
                   help="Patch guides/polymer_rules.json's class entry from a finished, "
                        "fully-PASSed reasoned run's decided_params, backfilling the "
                        "class-level starting-hypothesis scaffold, instead of generating "
                        "a new plan. See lock_from(). Does NOT validate any SMILES for "
                        "the deterministic path -- that's protocol-locker.md's separate "
                        "system_characterization_cache.json stamp.")
    p.add_argument("--rules-path", default=str(RULES_PATH),
                   help="polymer_rules.json to read/patch (default: guides/polymer_rules.json). "
                        "Override for --lock-from dry-runs against a scratch copy.")
    p.add_argument("--canonical_smiles", default=None,
                   help="Canonical SMILES (orchestration/scripts/canon_smiles.py). When this exact "
                        "SMILES has a frozen `protocol` block in system_characterization_cache.json, "
                        "the plan is built from what that molecule ACTUALLY RAN — resolved "
                        "equilibration step counts and the executed route — instead of from "
                        "polymer_rules.json class defaults.")
    p.add_argument("--no-chain", action="store_true",
                   help="Omit the resolved execution_chain from the plan.")
    args = p.parse_args()

    if args.lock_from:
        result = lock_from(Path(args.lock_from), args.polymer_class, Path(args.rules_path))
        print(json.dumps(result, indent=2))
        return

    if not args.run_name:
        p.error("--run_name required unless --lock-from is given")

    props_str = args.properties.strip().lower()
    properties = ({"density", "tg", "bulk_modulus"} if props_str == "all"
                  else {x.strip().lower() for x in props_str.split(",") if x.strip()})

    frozen = load_frozen_protocol(args.canonical_smiles) if args.canonical_smiles else {}
    plan = make_plan(args.run_name, args.polymer_class, args.smiles, properties,
                     frozen_protocol=frozen, with_chain=not args.no_chain)
    text = json.dumps(plan, indent=2)

    if args.out == "-":
        print(text)
        return
    out_path = (Path(args.out) if args.out
                else REPO_ROOT / "data" / args.run_name / "raw" / "run_plan.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(json.dumps({"status": "success", "run_plan": str(out_path),
                      "plan_mode": plan["plan_mode"], "confidence": plan["confidence"]}))


if __name__ == "__main__":
    main()
