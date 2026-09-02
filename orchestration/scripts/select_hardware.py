#!/usr/bin/env python3
"""
select_hardware.py — D-08 hardware selection and the GPU-hours cost model that prices it.

These were two files until 2026-09-02, and they could not stop reaching into each other:
select_hardware imported cost_model at the top, and cost_model imported
select_hardware._monomer_atoms_and_mw from INSIDE plan_cost_estimate() because a top-level
import would have been circular. They are one question -- what will this run cost on what
hardware -- so they are now one file and the cycle is gone.

D-08 selection: `decision_policy.json:policies.hardware` remains the source of truth for the
numbers; the validator and runtime use this shared implementation instead of re-deriving
hardware thresholds. Runtime GPU allocation stays separate (pick_gpu.py).

The cost model prices every planning-stage decision that trades accuracy against compute
cost (D-04 system size, D-08 hardware, and plan-level budget reporting):

guides/polymer_rules.json's hardware_policy.directional_probe.size_points carries, per FF
family, 3 real measured (atoms, ns_per_day) points on this host at its shipped default
config (2026-08-24: ~3k, ~5k, ~15k atoms for pcff/opls/trappe -- gaff still has none).
Measuring a real range instead of one point mattered: a naive single-point linear
extrapolation from the original ~3k-atom point would have OVER-estimated pcff's cost at
15,040 atoms by >2x (predicted 8.5 ns/day, measured 17.4) and opls's by ~24% -- KOKKOS
full-offload (pcff/opls) has real fixed per-timestep overhead that a pure per-atom cost
model misses, while trappe (lj/cut, no kspace) IS close to linear. This module therefore
interpolates log-log between the two REAL points bracketing a target cell size (the common
case for the 5k-15k atom range novel systems are expected in) rather than assuming one
global exponent, and only falls back to a documented near-linear ASSUMPTION -- explicitly
flagged, never presented as a second measurement -- when extrapolating outside the
measured range, or for a family with no size_points at all.

Usage:
  python3 orchestration/scripts/select_hardware.py select --polymer_class PACR \
      --smiles "*CC(C)(C(=O)OC)*" [--dp_typical 60] [--nchain 15]
  python3 orchestration/scripts/select_hardware.py estimate --atoms 8000 --steps 1000000 \
      --ff_family pcff
  python3 orchestration/scripts/select_hardware.py plan --run_plan data/<RUN>/raw/run_plan.json
Prints JSON to stdout; `select` exits 1 on {"error": ...}, the other two always exit 0.
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules_common import load_rules, get_class_entry, hardware_policy, resolve_ff_family
from hw_common import host_matches
from mol_python import run_in_mol_env, RDKIT_CLI


# ===========================================================================
# COST MODEL — ns/day interpolation and GPU-hours
# ===========================================================================
IN_WINDOW_LOW, IN_WINDOW_HIGH = 0.5, 2.0  # single-point fallback's trust window (matches
                                          # select_hardware.py's own window)


def _benchmark_point(fam: str, hp: dict):
    """The one recommended_by_ff {ns_per_day, cell_atoms, engine, mpi, gpu} point for this
    FF family -- the single-point fallback used when no size_points exist."""
    rec = (hp.get("directional_probe", {}).get("recommended_by_ff", {}) or {}).get(fam)
    if not rec or not rec.get("ns_per_day") or not rec.get("cell_atoms"):
        return None
    return rec


def _size_points(fam: str, hp: dict):
    """Sorted [(atoms, ns_per_day), ...] from directional_probe.size_points[fam], or []
    when fewer than 2 real measured points exist for this family (not enough to
    interpolate -- the single-point fallback takes over)."""
    pts = (hp.get("directional_probe", {}).get("size_points", {}) or {}).get(fam) or []
    pairs = sorted(((p["atoms"], p["ns_per_day"]) for p in pts if p.get("atoms") and p.get("ns_per_day")),
                   key=lambda t: t[0])
    return pairs if len(pairs) >= 2 else []


def _loglog_interp(atoms: int, points: list) -> tuple:
    """(ns_per_day, in_range) via log-log linear interpolation/extrapolation between the
    two points bracketing `atoms` (or the two nearest points, for out-of-range
    extrapolation). Log-log rather than linear because throughput-vs-size is a power-law
    relationship here, not an additive one -- confirmed non-constant exponent BETWEEN
    families (trappe near -1, pcff/opls flatter) by the 2026-08-24 measurement, so this
    always reads the local slope from real neighboring points rather than assuming a
    single global one."""
    lo = max((p for p in points if p[0] <= atoms), key=lambda p: p[0], default=None)
    hi = min((p for p in points if p[0] >= atoms), key=lambda p: p[0], default=None)
    in_range = lo is not None and hi is not None
    if lo is None:
        lo, hi = points[0], points[1]
    elif hi is None:
        lo, hi = points[-2], points[-1]
    elif lo == hi:
        return lo[1], in_range
    la, lb = math.log(lo[0]), math.log(hi[0])
    na, nb = math.log(lo[1]), math.log(hi[1])
    t = (math.log(atoms) - la) / (lb - la)
    return math.exp(na + t * (nb - na)), in_range


def estimate_ns_per_day(atoms: int, ff_family: str, hp: dict = None, rules: dict = None) -> dict:
    """{"ns_per_day", "confidence", "basis"} for a cell of `atoms` atoms in `ff_family`.

    confidence:
      "high"   -- interpolated between two REAL measured points bracketing this atom
                  count (or an exact match to one), host-matched.
      "medium" -- interpolated/exact-matched but host does not match the measurement, or
                  values_are_benchmarked=false; or the single-point fallback's in-window
                  case with a host match.
      "low"    -- extrapolating beyond the measured range (size_points path), or the
                  single-point fallback's out-of-window case.
      "none"   -- no benchmark data exists for this family at all (e.g. gaff today).
    """
    rules = rules or load_rules()
    hp = hp if hp is not None else hardware_policy(rules)
    host_ok = bool(hp.get("values_are_benchmarked", False)) and host_matches(rules)

    points = _size_points(ff_family, hp)
    if points:
        ns_day, in_range = _loglog_interp(atoms, points)
        lo_a, hi_a = points[0][0], points[-1][0]
        if in_range and host_ok:
            confidence = "high"
        elif in_range:
            confidence = "medium"
        else:
            confidence = "low"
        basis = (f"log-log {'interpolated' if in_range else 'extrapolated'} between real "
                 f"measured points {points} -- {atoms} atoms is "
                 f"{'within' if in_range else 'outside'} the measured [{lo_a},{hi_a}] range"
                 + ("" if host_ok else "; host does not match the measurement or "
                    "values_are_benchmarked=false"))
        return {"ns_per_day": ns_day, "confidence": confidence, "basis": basis,
                "measured_points": points}

    # Single-point fallback (no size_points for this family, e.g. gaff today).
    point = _benchmark_point(ff_family, hp)
    if point is None:
        return {"ns_per_day": None, "confidence": "none",
                "basis": f"no benchmark data exists for {ff_family!r} at all"}
    bench_atoms, bench_ns_day = point["cell_atoms"], point["ns_per_day"]
    exact = (atoms == bench_atoms)
    in_window = IN_WINDOW_LOW * bench_atoms <= atoms <= IN_WINDOW_HIGH * bench_atoms
    scaled = bench_ns_day * (bench_atoms / atoms) if atoms > 0 else bench_ns_day
    ns_day = bench_ns_day if exact else scaled
    if exact and host_ok:
        confidence, basis = "high", (f"measured {bench_ns_day} ns/day at exactly "
                                     f"{bench_atoms} atoms, host-matched")
    elif in_window:
        confidence, basis = "medium", (
            f"single-point near-linear-in-atoms ASSUMPTION (not a fit) from "
            f"{bench_ns_day} ns/day at {bench_atoms} atoms to {atoms} atoms -- in-window "
            f"but only one measured point exists for {ff_family!r}, so this is not a real "
            "interpolation the way a size_points-covered family gets")
    else:
        confidence, basis = "low", (f"single-point near-linear-in-atoms ASSUMPTION extrapolated "
                                    f"from {bench_ns_day} ns/day at {bench_atoms} atoms to "
                                    f"{atoms} atoms, outside [{IN_WINDOW_LOW}x,{IN_WINDOW_HIGH}x] "
                                    f"of the benchmark cell -- only one measured point exists "
                                    f"for {ff_family!r}")
    return {"ns_per_day": ns_day, "confidence": confidence, "basis": basis}


def gpu_hours(atoms: int, steps: int, dt_fs: float, ff_family: str, gpu_per_run: int = 1,
             hp: dict = None, rules: dict = None) -> dict:
    """GPU-hours to run `steps` MD steps of timestep `dt_fs` (fs) on a cell of `atoms`
    atoms in force-field family `ff_family`, consuming `gpu_per_run` GPUs for the whole
    wall-clock duration -- GPU-hours (not wall-clock hours) is the resource-cost currency,
    so a 2-GPU job costs 2x a 1-GPU job of the same wall time."""
    if not atoms or not steps:
        return {"gpu_hours": 0.0, "confidence": "high",
                "basis": "zero atoms or zero steps -- no cost"}
    est = estimate_ns_per_day(atoms, ff_family, hp=hp, rules=rules)
    if est["ns_per_day"] is None:
        return {"gpu_hours": None, "confidence": "none", "basis": est["basis"]}
    simulated_ns = steps * dt_fs * 1e-6
    wall_days = simulated_ns / est["ns_per_day"]
    hours = wall_days * 24.0 * max(1, int(gpu_per_run or 1))
    return {"gpu_hours": round(hours, 4), "confidence": est["confidence"], "basis": est["basis"],
            "ns_per_day_used": round(est["ns_per_day"], 4), "simulated_ns": round(simulated_ns, 6)}


def _tg_sweep_total_steps(effective_class: dict) -> tuple:
    """(total_steps, note) summed over every configured tg_rates_K_per_ns entry -- the
    documented multi-rate protocol (decision_policy.json D-06's primary/alternative-rate
    reportability check needs more than one rate run). Reuses the exact
    n_steps_per_t = t_step / (rate * dt * 1e-6) arithmetic stage_params._resolve_tg_params
    already computes, rather than a second, driftable copy."""
    dt = effective_class.get("dt_fs", 1.0)
    t_step = effective_class.get("tg_t_step_K", 20)
    t_high = effective_class.get("tg_t_high_K", 600)
    t_low = effective_class.get("tg_t_low_K", 200)
    rates = effective_class.get("tg_rates_K_per_ns") or []
    floor = effective_class.get("tg_min_steps_per_T", 200000)
    if not rates or not t_step:
        return None, "no tg_rates_K_per_ns / tg_t_step_K configured -- cannot size the sweep"
    # Mirrors script_generator.py's actual temp-list construction (T_START down to T_END,
    # always force-appending T_END) rather than a closed-form round() -- confirmed against
    # PE1's real tg logs that round((t_high-t_low)/t_step) undercounts by 1 whenever the
    # range isn't an exact multiple of t_step (350/20=17.5 rounds to 18 T-bins; the real
    # generator always force-appends T_END, producing 19).
    temps: list[float] = []
    t = t_high
    while t > t_low + 1e-6:
        temps.append(t)
        t -= t_step
    if not temps or abs(temps[-1] - t_low) > 1e-6:
        temps.append(t_low)
    n_bins = max(1, len(temps))
    total = 0
    for rate in rates:
        n_steps_per_t = max(int(t_step / (rate * dt * 1e-6)), floor if floor else 0)
        total += n_bins * n_steps_per_t
    return total, (f"{len(rates)} rate(s) x {n_bins} T-bin(s), floor-checked against "
                    f"tg_min_steps_per_T={floor}")


def _murnaghan_total_steps(effective_class: dict) -> tuple:
    """(total_steps, note): one NPT run of bm_npt_steps*mechanical_sampling_factor per
    configured pressure point."""
    pressures = (effective_class.get("mechanical_resample_points")
                or effective_class.get("bm_pressures_atm") or [])
    if not pressures:
        return None, "no bm_pressures_atm configured -- cannot size the Murnaghan series"
    npt_steps = int(effective_class.get("bm_npt_steps", 500000)) * int(
        effective_class.get("mechanical_sampling_factor", 1))
    return len(pressures) * npt_steps, (f"{len(pressures)} pressure point(s) x "
                                        f"{npt_steps} npt_steps each")


def _deform_total_steps(effective_class: dict) -> tuple:
    """(total_steps, note): a single primary-direction leg. Deliberately a LOWER bound --
    a rate-sensitivity check or multi-axis anisotropy probe (documented for PLA2's three
    legs in decision_policy.json) would multiply this; this function has no way to know
    how many legs a given plan actually submits, so it prices exactly one and says so."""
    steps = int(effective_class.get("deform_eq_steps", 200000))
    return steps, "single primary-direction leg -- a lower bound, not a full multi-leg total"


def plan_cost_estimate(plan: dict, hp: dict = None, rules: dict = None) -> dict:
    """Per-stage + total GPU-hours for a materialized run_plan.json, reusing the exact
    step-count arithmetic that governs what actually gets submitted (never a second,
    driftable copy of stage-length logic). Stages whose length cannot be resolved from
    decided_params alone (equil's stage-length knobs mostly default to None, deferred to
    generate_equilibration_workflow's own atom-count-tiered default inside the MCP LAMMPS
    engine) are reported as unpriced rather than guessed -- the total is then an honest
    partial/lower-bound figure, not false precision.
    """
    rules = rules or load_rules()
    hp = hp if hp is not None else hardware_policy(rules)
    dp_dict = plan.get("decided_params", {}) or {}
    smiles = plan.get("smiles")
    polymer_class = plan.get("polymer_class")
    if not smiles or not polymer_class:
        return {"error": "plan is missing smiles/polymer_class -- cannot estimate cost"}

    cls = dict(get_class_entry(rules, polymer_class, warn_on_miss=False))
    effective_class = {**cls, **dp_dict}
    ff_raw = effective_class.get("preferred_ff") or effective_class.get("forcefield") or ""
    fam = resolve_ff_family(ff_raw, hp)
    dt_fs = effective_class.get("dt_fs", 1.0)
    dp = dp_dict.get("dp_typical") or effective_class.get("dp_typical")
    nchain = dp_dict.get("nchain") or effective_class.get("nchain")
    gpu_per_run = dp_dict.get("gpu_per_run") or hp.get("by_forcefield", {}).get(fam, {}).get(
        "gpu_per_run", 1)

    if not dp or not nchain:
        return {"error": "decided_params has no resolvable dp_typical/nchain"}

    try:
        is_ua = (fam == "trappe")
        atoms_per_monomer, _mw = _monomer_atoms_and_mw(smiles, is_ua)
    except Exception as e:  # noqa: BLE001 -- an RDKit failure must not crash cost estimation
        return {"error": f"atom-count estimate failed: {type(e).__name__}: {e}"}
    cell_atoms = atoms_per_monomer * dp * nchain

    planned_stage_names = {s.get("stage") for s in plan.get("planned_stages", [])}
    stages, unpriced = {}, []

    if "equil" in planned_stage_names:
        unpriced.append({"stage": "equil", "reason":
            "stage-length knobs default to None, deferred to generate_equilibration_"
            "workflow's own atom-count-tiered default inside the MCP LAMMPS engine -- "
            "not resolvable from decided_params alone; not priced here to avoid guessing"})

    if "tg" in planned_stage_names or "analyze-tg" in planned_stage_names:
        total_steps, note = _tg_sweep_total_steps(effective_class)
        if total_steps:
            stages["tg"] = gpu_hours(cell_atoms, total_steps, dt_fs, fam, gpu_per_run, hp, rules)
            stages["tg"]["steps"] = total_steps
            stages["tg"]["note"] = note
        else:
            unpriced.append({"stage": "tg", "reason": note})

    if "murnaghan" in planned_stage_names or "analyze-bm" in planned_stage_names:
        total_steps, note = _murnaghan_total_steps(effective_class)
        if total_steps:
            stages["murnaghan"] = gpu_hours(cell_atoms, total_steps, dt_fs, fam, gpu_per_run,
                                            hp, rules)
            stages["murnaghan"]["steps"] = total_steps
            stages["murnaghan"]["note"] = note
        else:
            unpriced.append({"stage": "murnaghan", "reason": note})

    # The deform fallback is never its own planned_stages entry -- build_planned_stages attaches
    # it as {"fallback": "deform"} on the murnaghan entry, and only for a glassy class. Gating on
    # the bare stage name (as this did until 2026-09-01) made the branch UNREACHABLE for every
    # deterministic plan, so the fallback went silently unpriced.
    #
    # Read the declaration, not track_registry.resolver_stages_for: the registry knows deform IS
    # murnaghan's fallback slot, but whether it attaches is a per-plan regime call. Pricing it
    # from the registry alone would charge every rubbery plan for a path it never has.
    deform_declared = any(s.get("fallback") == "deform"
                          for s in plan.get("planned_stages", []))
    if "deform" in planned_stage_names or deform_declared:
        total_steps, note = _deform_total_steps(effective_class)
        stages["deform"] = gpu_hours(cell_atoms, total_steps, dt_fs, fam, gpu_per_run, hp, rules)
        stages["deform"]["steps"] = total_steps
        stages["deform"]["note"] = note
        if deform_declared and "deform" not in planned_stage_names:
            stages["deform"]["note"] = (
                (note or "") + " [CONTINGENT: murnaghan's glassy fallback, charged only if "
                "BM_INADMISSIBLE routes to it -- included in worst-case, not in the base run]")

    priced = [s for s in stages.values() if s.get("gpu_hours") is not None]
    total = round(sum(s["gpu_hours"] for s in priced), 4) if priced else None
    conf_rank = {"high": 3, "medium": 2, "low": 1, "none": 0}
    overall_confidence = (min(priced, key=lambda s: conf_rank[s["confidence"]])["confidence"]
                         if priced else "none")

    return {
        "cell_atoms_estimate": cell_atoms, "ff_family": fam,
        "stages": stages, "unpriced_stages": unpriced,
        "total_gpu_hours": total, "confidence": overall_confidence,
        "note": ("Partial/lower-bound total -- see unpriced_stages for what is not "
                 "included (notably: equil-stage length, and any deform stage beyond "
                 "a single primary-direction leg).") if unpriced else
                 "All planned stages priced.",
    }


# ===========================================================================
# D-08 HARDWARE SELECTION
# ===========================================================================
def _monomer_atoms_and_mw(smiles: str, is_ua: bool, env: str = "radonpy",
                          timeout: int = 30) -> tuple:
    """(atom count, molar mass g/mol) for one repeat unit. Count is heavy-atom for UA FFs
    (e.g. TraPPE) or all-atom with H for all-atom FFs (PCFF/OPLS/GAFF); the mass is always
    all-atom. `*` connection-point atoms are discounted -- RDKit would otherwise count them
    as real (wildcard) atoms. Reaches RDKit via mol_python.run_in_mol_env(), the same seam
    canon_smiles.py's canonicalize() uses, invoking rdkit_cli.py's `monomer-info`."""
    args = ["monomer-info", "--smiles", smiles] + (["--ua"] if is_ua else [])
    r = run_in_mol_env(script_path=RDKIT_CLI, args=args, env=env, timeout=timeout)
    out = r.stdout.strip()
    if r.returncode != 0 or not out:
        raise RuntimeError(r.stderr.strip() or "empty output from RDKit atom-count")
    info = json.loads(out.splitlines()[-1])
    return int(info["n_atoms"]), float(info["mw_g_per_mol"])


def select_hardware(polymer_class: str, smiles: str, dp_typical: int | None,
                     nchain: int | None) -> dict:
    rules = load_rules()
    cls = get_class_entry(rules, polymer_class, warn_on_miss=True)
    hp = hardware_policy(rules)
    if not hp:
        return {"error": "guides/polymer_rules.json has no hardware_policy block"}

    ff_raw = cls.get("preferred_ff") or cls.get("forcefield") or ""
    fam = resolve_ff_family(ff_raw, hp)
    default = hp.get("by_forcefield", {}).get(fam, {})
    if not default:
        return {"error": f"no by_forcefield default for resolved FF family {fam!r} (ff_raw={ff_raw!r})"}

    dp = dp_typical if dp_typical is not None else cls.get("dp_typical", 50)
    nchain_v = nchain if nchain is not None else cls.get("nchain", 10)
    is_ua = (fam == "trappe")
    try:
        atoms_per_monomer, mw_per_monomer = _monomer_atoms_and_mw(smiles, is_ua)
    except Exception as e:
        return {"error": f"RDKit atom-count failed: {e}"}
    cell_atoms = atoms_per_monomer * dp * nchain_v
    cell_mass = mw_per_monomer * dp * nchain_v          # g/mol, end caps neglected

    # D-08's only priced candidate: `by_forcefield[fam]` IS the config
    # `recommended_by_ff`/`size_points` measured (same engine/mpi/gpu, per
    # polymer_rules.json:hardware_policy.directional_probe.size_points._note) -- there is no
    # second engine/mpi/gpu combination in this repo with its own real ns_per_day data to
    # argmin against (`_prev_gpu_package` fallbacks carry no throughput numbers at all, so
    # pricing them would be fabrication, not measurement). "Choosing hardware" here therefore
    # means: price this one candidate honestly at the plan's actual cell size and let the
    # confidence level reflect how much that price should be trusted -- using
    # this file's own multi-point log-log interpolation (size_points) instead of the old
    # script's old single-point in-window heuristic, which never read size_points at all.
    choice = {"engine": default.get("engine"), "gpu_per_run": default.get("gpu_per_run"),
              "mpi_ranks": default.get("mpi")}
    est = estimate_ns_per_day(cell_atoms, fam, hp=hp, rules=rules)
    confidence = est["confidence"]
    evidence = [{
        "claim": f"estimate_ns_per_day at this run's {cell_atoms}-atom estimate: "
                 f"{est['ns_per_day']} ns/day ({confidence} confidence)",
        "basis": est["basis"], "note": default.get("note"),
    }]

    # Size-scale floor: never let anything (probe or default) pin >=2 GPUs for a small cell.
    if cell_atoms < 10000 and choice.get("gpu_per_run", 1) and choice["gpu_per_run"] >= 2:
        choice["gpu_per_run"] = 1
        evidence.append({"claim": f"cell estimate {cell_atoms} atoms < 10k -- forced to 1 GPU "
                                   "regardless of probe/default gpu_per_run"})

    decision = {
        "id": "D-08_hardware", "choice": choice,
        "criteria_evaluated": ["forcefield_cost_structure", "atom_count", "concurrent_load",
                                "benchmark_evidence", "cell_size_vs_benchmark_cell", "host_match"],
        "evidence": evidence, "confidence": confidence, "alternatives": [],
    }

    decided_params_override = {}
    if choice != {"engine": default.get("engine"), "gpu_per_run": default.get("gpu_per_run"),
                  "mpi_ranks": default.get("mpi")}:
        decided_params_override = {"engine": choice["engine"], "gpu_per_run": choice["gpu_per_run"],
                                    "mpi_ranks": choice["mpi_ranks"]}

    uncertainties = []
    if confidence != "high":
        uncertainties.append({"name": "hardware_optimum", "dominant": False,
                              "reduction_probe": "hardware_benchmark"})

    return {
        "decision": decision,
        "decided_params_override": decided_params_override,
        "uncertainties": uncertainties,
        "cell_atoms_estimate": cell_atoms,
        "cell_mass_g_per_mol_estimate": round(cell_mass, 1),
        "ff_family": fam,
    }


# ===========================================================================
# CLI
# ===========================================================================
def _cmd_select(args) -> int:
    result = select_hardware(args.polymer_class, args.smiles, args.dp_typical, args.nchain)
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


def _cmd_estimate(args) -> int:
    try:
        result = gpu_hours(args.atoms, args.steps, args.dt_fs, args.ff_family, args.gpu_per_run)
    except Exception as e:  # noqa: BLE001 -- callers parse JSON, never a traceback
        result = {"error": f"{type(e).__name__}: {e}"}
    print(json.dumps(result, indent=2))
    return 0


def _cmd_plan(args) -> int:
    try:
        plan = json.loads(Path(args.run_plan).read_text())
        result = plan_cost_estimate(plan)
    except Exception as e:  # noqa: BLE001 -- callers parse JSON, never a traceback
        result = {"error": f"{type(e).__name__}: {e}"}
    print(json.dumps(result, indent=2))
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("select", help="D-08: resolve hardware for a class + SMILES")
    c.add_argument("--polymer_class", required=True)
    c.add_argument("--smiles", required=True, help="Repeat-unit SMILES with * connection points.")
    c.add_argument("--dp_typical", type=int, default=None)
    c.add_argument("--nchain", type=int, default=None)
    c.set_defaults(func=_cmd_select)

    c = sub.add_parser("estimate", help="price one (atoms, steps) combination")
    c.add_argument("--atoms", type=int, required=True)
    c.add_argument("--steps", type=int, required=True)
    c.add_argument("--dt_fs", type=float, default=1.0)
    c.add_argument("--ff_family", required=True, choices=["pcff", "opls", "trappe", "gaff"])
    c.add_argument("--gpu_per_run", type=int, default=1)
    c.set_defaults(func=_cmd_estimate)

    c = sub.add_parser("plan", help="price every stage of a materialized run_plan.json")
    c.add_argument("--run_plan", required=True)
    c.set_defaults(func=_cmd_plan)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
