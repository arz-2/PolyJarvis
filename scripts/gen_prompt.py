#!/usr/bin/env python3
"""
gen_prompt.py — Generate fully-formed worker prompts for PolyJarvis orchestrator.

Usage:
  python3 scripts/gen_prompt.py --stage <STAGE> [options]

Workers: build | equil | tg | deform | murnaghan | analyze-tg | equil-check | analyze-bm | run-summary

The script reads polymer_rules.json (for class defaults) and cross-track rules
from CLAUDE.md at runtime, so prompts always reflect the current configuration
without the orchestrator needing to read either file directly.

Required for all workers:
  --run_name NAME
  --polymer_class CLASS   (e.g. PSTR, PACR, PHYC)

Optional overrides (defaults come from polymer_rules.json):
  --smiles SMILES
  --data_path PATH        input .data file (equil, tg, deform, analyze)
  --work_dir PATH         base directory for worker outputs
  --gpu_ids IDS           comma-separated GPU IDs, e.g. "0" or "0,1"; if omitted,
                          derived from polymer_rules.json hardware_policy by FF
  --mpi_ranks N           MPI processes per run; if omitted, derived from
                          hardware_policy (never mpi=1 for PPPM classes)
  --dp N                  degree of polymerisation override
  --nchain N              number of chains override
  --lammps_flags JSON     e.g. '{"use_pcff":true,"use_opls":false}'
  --is_glassy BOOL        true|false (deform, born, murnaghan, analyze-bm)
  --tg_k FLOAT            Tg in K (from tg-analysis-worker RESULT)
  --tg_fit_quality STR    Tg fit quality (run-summary + analyze-bm)
  --deform_log PATH       npt_deform log (analyze-bm, glassy deform fallback)
  --murnaghan_logs JSON   JSON list of log paths (analyze-bm, rubbery+pressures path)
  --d05 STR               equil_verdict from equil-checker RESULT (run-summary worker)
  --npt_prod_log PATH     NPT production log (equil-check, analyze-bm)
  --npt_prod_dump PATH    structural-check dump override (equil-check); defaults to the
                          melt nvt_production.dump — NOT the production NPT dump
  --ff STR                force field string (run-summary, analyze-bm)
  --backbone_types JSON   atom type IDs as JSON list (equil-check only)
  --enthalpy_col STR      LAMMPS thermo column name for enthalpy (analyze-tg; default "Enthalpy")
  --output_dir PATH       raw/ output directory

Physics knob overrides (all optional; defaults from polymer_rules.json):
  --npt_prod_ns FLOAT     NPT production time in ns (equil). Auto-sized by
                          atom count when omitted. Converted to npt_prod_steps and
                          passed to generate_equilibration_workflow.
  --T_equil_K FLOAT       Equilibration temperature — maps to temp= in generate_equilibration_workflow
  --T_anneal_high_K FLOAT Peak annealing temperature — maps to max_temp=
  --tg_t_high_K FLOAT     Tg sweep start temperature (K)
  --tg_t_low_K FLOAT      Tg sweep end temperature (K)
  --tg_t_step_K FLOAT     Tg sweep temperature step (K); halve for BORDERLINE recovery
  --tg_steps_per_t INT    MD steps per temperature window; increase for better statistics
  --K_strain_max FLOAT    Max engineering strain for uniaxial deformation
  --K_deform_rate_inv_s FLOAT  Engineering strain rate (s⁻¹)
  --dt_fs FLOAT           MD timestep (fs); set 0.5 for "lost atoms" recovery
  --properties LIST       Comma-separated: density,tg,bulk_modulus or 'all' (default).
                          Orchestrator uses it for track gating.
"""

import argparse
import json
import os
import re
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hw_common import (load_rules, resolve_ff_family,  # shared rules/FF-family access
                       host_matches, live_host)

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = REPO_ROOT / "guides" / "polymer_rules.json"
CLAUDE_MD_PATH = REPO_ROOT / "CLAUDE.md"

WORKER_GUIDES = {
    "build":        "MOLECULE_BUILDER.md",
    "equil":        "EQUILIBRATION.md",
    "tg":           "THERMAL_SWEEP.md",
    "analyze-tg":   "THERMAL_ANALYSIS.md",
    "analyze-tg-multirate": "THERMAL_ANALYSIS.md",
    "equil-check":  "EQUIL_CHECK.md",
    "analyze-bm":   "BM_ANALYSIS.md",
    "deform":       "DEFORM.md",
    "born":         "BORN_MATRIX.md",
    "murnaghan":    "MURNAGHAN.md",
    "run-summary":  None,
}


# ─── Loaders ──────────────────────────────────────────────────────────────────
# load_rules() is imported from hw_common (single source of truth).

def load_cross_track_rules() -> str:
    text = CLAUDE_MD_PATH.read_text()
    m = re.search(r'<!-- CROSS_STAGE_RULES_START -->(.*?)<!-- CROSS_STAGE_RULES_END -->', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return "[Cross-track rules not found in CLAUDE.md — check CROSS_STAGE_RULES_START/END markers]"


def load_worker_guide(stage: str) -> str:
    filename = WORKER_GUIDES.get(stage)
    if not filename:
        return ""
    path = REPO_ROOT / "guides" / filename
    return path.read_text() if path.exists() else f"[Guide not found: {filename}]"


def get_class_entry(rules: dict, polymer_class: str) -> dict:
    entry = rules["classes"].get(polymer_class.upper())
    if entry is None:
        print(f"WARNING: class '{polymer_class}' not found in polymer_rules.json; using global_defaults", file=sys.stderr)
        entry = rules["global_defaults"]
    return entry


def load_plan(plan_path: str) -> dict:
    with open(plan_path) as f:
        return json.load(f)


def apply_plan(cls: dict, plan: dict, args) -> dict:
    """Overlay an approved run_plan.json's decided_params onto the class entry.

    The plan carries the Planner's *scientific decisions* (FF, system size, T-schedule,
    property knobs); runtime wiring (paths, gpu_ids, mpi_ranks) stays in CLI args. For a
    deterministic plan, decided_params is a subset of cls with identical values, so this
    overlay is an identity and worker prompts are byte-identical to the no-plan path
    (enforced by tests/test_plan_reproducibility.py). For a reasoned plan, decided_params
    may differ and those values take effect here.

    Also backfills --smiles and --properties from the plan when not given on the CLI, so
    the plan artifact is a self-contained source of truth.
    """
    effective = {**cls, **plan.get("decided_params", {})}
    if args.smiles is None and plan.get("smiles"):
        args.smiles = plan["smiles"]
    if (args.properties is None or args.properties == "all") and plan.get("properties"):
        args.properties = ",".join(plan["properties"])
    _apply_plan_hardware(args, plan.get("decided_params", {}))
    return effective


def _apply_plan_hardware(args, dp: dict) -> None:
    """Honor a reasoned plan's D-08_hardware override (engine / gpu_per_run / mpi_ranks in
    decided_params) when the CLI omitted the value. Precedence: CLI > plan > policy — the CLI
    stays authoritative, and resolve_hardware() fills anything still unset from hardware_policy.
    Deterministic plans never carry these keys (make_deterministic_plan.SNAPSHOT_KEYS excludes
    them), so the no-plan path stays byte-identical (tests/test_plan_reproducibility.py)."""
    if args.mpi_ranks is None and dp.get("mpi_ranks") is not None:
        args.mpi_ranks = dp["mpi_ranks"]
    if getattr(args, "engine", None) is None and dp.get("engine") is not None:
        args.engine = dp["engine"]          # plan's D-08 engine (gpu | kokkos | cpu)
    if args.gpu_ids is None and ("engine" in dp or "gpu_per_run" in dp):
        engine, gpu_n = dp.get("engine"), dp.get("gpu_per_run")
        if engine == "cpu" or gpu_n == 0:
            args.gpu_ids = ""                                  # CPU engine — hide GPUs
        elif gpu_n:                                            # explicit GPU count → placeholders
            args.gpu_ids = ",".join(str(i) for i in range(int(gpu_n)))
        # engine=="gpu" with no count → leave None; resolve_hardware fills from gpu_per_run policy
    # Fixed seeds for replication runs (deterministic plans pin these from REVISION_PARAMS.md).
    if getattr(args, "emc_seed", None) is None and dp.get("emc_seed") is not None:
        args.emc_seed = dp["emc_seed"]
    if getattr(args, "velocity_seed", None) is None and dp.get("velocity_seed") is not None:
        args.velocity_seed = dp["velocity_seed"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def resolve_hardware(args, cls: dict, rules: dict) -> None:
    """Fill mpi_ranks / gpu_ids from the FF×size hardware_policy when the CLI omits
    them, so a run can never default to the mpi=1 anti-pattern. Explicit CLI values
    always win (keeps deterministic-plan output byte-identical — runtime wiring stays
    CLI-authoritative per apply_plan's contract). Specific gpu_ids remain runtime;
    use scripts/pick_gpu.py to claim a non-colliding GPU at submit time."""
    hp = rules.get("hardware_policy")
    if not hp:
        return
    # Fresh-clone nudge: the per-FF engine defaults below were benchmarked on hp.host and
    # the crossover is hardware-dependent (KOKKOS wins PPPM but loses small UA cells on this
    # GPU; another GPU/core-count can flip it). If this box isn't the benchmarked one — or no
    # clean sweep has run here — the defaults are directional, not measured-for-you. Advisory
    # only: resolution proceeds unchanged (defaults still apply at D-08 confidence:low).
    if not hp.get("values_are_benchmarked") or not host_matches(rules):
        saved = hp.get("host") or {}
        saved_desc = (f"{saved.get('gpus','?')}x {saved.get('gpu_model','?')} / "
                      f"{saved.get('phys_cores','?')} cores" if saved else "(never calibrated)")
        live = live_host()
        live_desc = f"{live['gpus']}x {live['gpu_model']} / {live['phys_cores']} cores"
        print(f"INFO: hardware_policy was benchmarked on {saved_desc}; you are on {live_desc} "
              f"(values_are_benchmarked={hp.get('values_are_benchmarked', False)}). Run "
              f"/calibrate-hardware once to host-match the per-FF engine defaults.",
              file=sys.stderr)
    ff_raw = cls.get("preferred_ff") or cls.get("forcefield") or ""
    fam = resolve_ff_family(ff_raw, hp)
    pol = hp.get("by_forcefield", {}).get(fam, {})
    # Resolve the launch engine the worker forwards to the MCP run tools. Precedence:
    # CLI/plan (already on args) > policy by_forcefield[fam].engine > "gpu". Only "kokkos" opts
    # into full-offload; "cpu"/anything else normalizes to "gpu" so chain launches stay as today
    # (per-stage use_gpu still governs CPU-only stages inside the deck).
    if getattr(args, "engine", None) is None:
        args.engine = pol.get("engine")
    if args.engine != "kokkos":
        args.engine = "gpu"
    if args.mpi_ranks is None:
        args.mpi_ranks = pol.get("mpi", 8)
        print(f"INFO: mpi_ranks not given — derived {args.mpi_ranks} from "
              f"hardware_policy[{fam}] (engine={pol.get('engine')})", file=sys.stderr)
    if args.gpu_ids is None:
        if pol.get("engine") == "cpu":
            args.gpu_ids = ""
        else:
            # emit gpu_per_run placeholder ids (e.g. "0,1" for a 2-GPU run); the orchestrator
            # claims that many free GPUs via scripts/pick_gpu.py claim --need N at submit time.
            n = max(1, int(pol.get("gpu_per_run", 1) or 1))
            args.gpu_ids = ",".join(str(i) for i in range(n))
        print(f"INFO: gpu_ids not given — derived \"{args.gpu_ids}\" from "
              f"hardware_policy[{fam}]; claim free GPU(s) with scripts/pick_gpu.py",
              file=sys.stderr)


def _v(val, fallback="<FILL>"):
    return val if val is not None else fallback


def _pick(arg_val, cls: dict, key: str, default):
    """CLI flag takes precedence over polymer_rules.json; rules over hard default."""
    return arg_val if arg_val is not None else cls.get(key, default)


def _lammps_flags(flags_json: str | None, cls: dict) -> dict:
    if flags_json:
        return json.loads(flags_json)
    ff = cls.get("preferred_ff", "").lower()
    return {
        "use_pcff": ff == "pcff",
        "use_opls": ff in ("opls-aa", "opls"),
        "use_trappe": ff in ("trappe-ua", "trappe"),
    }


def _exp_tg_range(cls: dict, run_name: str | None = None) -> list:
    tg = cls.get("experimental_tg_K")
    if isinstance(tg, dict):
        if run_name:
            for key, val in tg.items():
                if isinstance(val, (int, float)) and run_name.upper().startswith(key.upper()):
                    return [round(val - 20), round(val + 20)]
        vals = sorted(v for v in tg.values() if isinstance(v, (int, float)))
        if vals:
            mid = vals[len(vals) // 2]
            return [round(mid - 20), round(mid + 20)]
    if isinstance(tg, (int, float)):
        return [round(tg - 20), round(tg + 20)]
    return ["<exp_tg_min>", "<exp_tg_max>"]


def _exp_K_range(cls: dict) -> list:
    exp = cls.get("exp_K_GPa")
    if isinstance(exp, dict) and "min" in exp and "max" in exp:
        return [exp["min"], exp["max"]]
    return [None, None]


def _db_exp_lookup(cls_id: str, polymer_name: str | None = None) -> dict:
    """Query polymer_db.sqlite for polymer-specific experimental values.

    Priority in callers:
      --exp_tg_K (CLI)  >  this function (DB)  >  polymer_rules.json median
    Returns dict with tg_median_K, density_gcm3, K_range_GPa (any may be None).
    Never raises — a broken or missing DB just returns all-None.
    """
    try:
        import sys as _sys
        _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _repo_root not in _sys.path:
            _sys.path.insert(0, _repo_root)
        from db.query_best_match import (
            _connect, find_polymer_ids, get_tg_data, get_density_data, get_bulk_modulus_data,
        )
        conn = _connect()
        ids, _method, _conf = find_polymer_ids(conn, polymer_name, cls_id)
        if not ids:
            return {"tg_median_K": None, "density_gcm3": None, "K_range_GPa": None}
        tg = get_tg_data(conn, ids)
        dens = get_density_data(conn, ids, 300.0)
        bm = get_bulk_modulus_data(conn, ids, is_glassy=True)
        return {
            "tg_median_K": tg["agg_median_K"] if tg else None,
            "density_gcm3": dens.get("value_gcm3") if dens else None,
            "K_range_GPa": bm["agg_range_GPa"] if bm else None,
        }
    except Exception:
        return {"tg_median_K": None, "density_gcm3": None, "K_range_GPa": None}


def _exp_density_range(cls: dict) -> list:
    exp = cls.get("experimental_density_gcm3")
    if isinstance(exp, dict):
        vals = sorted(v for v in exp.values() if isinstance(v, (int, float)))
        if vals:
            mid = vals[len(vals) // 2]  # median — avoids outliers skewing the comparison band
            return [round(mid * 0.95, 3), round(mid * 1.05, 3)]
    if isinstance(exp, (int, float)):
        return [round(exp * 0.95, 3), round(exp * 1.05, 3)]
    # Fallback: derive from density_initial (~0.5–0.6× RT density)
    d0 = cls.get("density_initial_gcm3", 0.6)
    implied_rt = d0 / 0.55
    return [round(implied_rt * 0.85, 3), round(implied_rt * 1.15, 3)]


# ─── Stage prompt builders ────────────────────────────────────────────────────

def build_prompt(args, cls: dict, cross_track_rules: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"{REPO_ROOT}/data/{args.run_name}/lammps"
    guide = load_worker_guide("build")
    return f"""\
smiles:            {_v(args.smiles)}
run_name:          {args.run_name}
work_dir:          {work_dir}/cell
polymer_class:     {args.polymer_class.upper()}
preferred_builder: {cls.get('preferred_builder', 'emc')}
preferred_ff:      {cls.get('preferred_ff', 'gaff2_mod')}
dp:                {args.dp or cls.get('dp_typical', 50)}
nchain:            {args.nchain or cls.get('nchain', 10)}
density_initial:   {_pick(args.density_initial, cls, 'density_initial_gcm3', 0.6)}
emc_seed:          {args.emc_seed if getattr(args, 'emc_seed', None) is not None else 'null'}   # null = builder draws + reports a random seed
charge_method:     {cls.get('charge_method', 'am1bcc').lower()}
electrostatics:    {cls.get('electrostatics', 'pppm')}
cutoff_A:          {cls.get('cutoff_A', 12.0)}
dt_fs:             {cls.get('dt_fs', 1.0)}
phal_patch:        {str(args.polymer_class.upper() == 'PHAL').lower()}
ff_confidence:     {cls.get('confidence', 'low')}

--- Worker Guide (MOLECULE_BUILDER) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def _resolve_t_workflow(args, cls: dict) -> float:
    """Equilibration workflow temperature (K). Plan's T_workflow_K wins; otherwise 300 K for
    rubbery (exp_Tg < 300) and T_equil_K for glassy. Mirrors generate_equilibration_workflow,
    whose chain ends at npt_production when T ≤ 300 (rubbery, 7-run) and appends npt_prod300
    when T > 300 (glassy, 9-run)."""
    exp_tg_override = getattr(args, 'exp_tg_K', None)
    if exp_tg_override is not None:
        exp_tg = exp_tg_override
    else:
        _tg_dict = cls.get('experimental_tg_K')
        if isinstance(_tg_dict, dict):
            _run = getattr(args, 'run_name', None)
            exp_tg = None
            if _run:
                for k, v in _tg_dict.items():
                    if isinstance(v, (int, float)) and _run.upper().startswith(k.upper()):
                        exp_tg = v
                        break
            if exp_tg is None:
                _vals = sorted(v for v in _tg_dict.values() if isinstance(v, (int, float)))
                exp_tg = _vals[len(_vals) // 2] if _vals else None
        else:
            exp_tg = _tg_dict
    if "T_workflow_K" in cls:
        return cls["T_workflow_K"]
    T_equil = _pick(getattr(args, 'T_equil_K', None), cls, 'T_equil_K', 600.0)
    return 300.0 if isinstance(exp_tg, (int, float)) and exp_tg < 300 else T_equil


def _regime(args, cls: dict) -> str:
    """Single regime oracle: 'rubbery' if the workflow produces above Tg, else 'glassy'.

    Defined as T_workflow ≤ 300 K (⇔ exp_Tg < 300, via _resolve_t_workflow) so it agrees by
    construction with which equilibration chain was built (rubbery = 7-run ending at
    npt_production; glassy = 9-run with npt_prod300) and with the property-track routing.
    Consumed by the equil-check carve-out (require_rubbery), the analyze-tg data path, the
    multirate slope-gate exemption, and rubbery-K routing — one definition, fed everywhere.
    NOTE: do NOT redefine as `T_workflow > exp_Tg + margin`; for a glassy polymer T_workflow is
    the melt-equilibration temperature (~T_equil), which would mis-label glassy melts as rubbery."""
    return "rubbery" if _resolve_t_workflow(args, cls) <= 300.0 else "glassy"


def equil_prompt(args, cls: dict, cross_track_rules: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"{REPO_ROOT}/data/{args.run_name}/lammps/equil"
    guide = load_worker_guide("equil")
    dt = _pick(args.dt_fs, cls, 'dt_fs', 1.0)
    T_equil = _pick(args.T_equil_K, cls, 'T_equil_K', 600.0)
    T_anneal = _pick(args.T_anneal_high_K, cls, 'annealing_T_high_K', 700.0)
    npt_prod_ns_val = _pick(args.npt_prod_ns, cls, 'npt_prod_ns', None)
    if npt_prod_ns_val is not None:
        npt_prod_steps = int(npt_prod_ns_val * 1e6 / dt)
        npt_prod_line = (
            f"t_npt_prod_ns:     {npt_prod_ns_val}\n"
            f"npt_prod_steps:    {npt_prod_steps}  # pass as npt_prod_steps="
        )
    else:
        npt_prod_line = "t_npt_prod_ns:     null  # auto-sized by atom count"
    T_workflow = _resolve_t_workflow(args, cls)
    add_melt_npt = getattr(args, 'add_melt_npt', False) or (T_workflow <= 300.0)
    melt_npt_ns_val = _pick(None, cls, 'melt_npt_ns', None) if add_melt_npt else None
    if add_melt_npt and melt_npt_ns_val is not None:
        melt_npt_steps = int(melt_npt_ns_val * 1e6 / dt)
        melt_npt_line = (
            f"add_melt_npt:      true\n"
            f"t_equil_K:         {T_equil}\n"
            f"melt_npt_ns:       {melt_npt_ns_val}\n"
            f"melt_npt_steps:    {melt_npt_steps}  # pass as melt_npt_steps="
        )
    elif add_melt_npt:
        melt_npt_line = (
            f"add_melt_npt:      true\n"
            f"t_equil_K:         {T_equil}"
        )
    else:
        melt_npt_line = "add_melt_npt:      false"
    return f"""\
data_path:         {_v(args.data_path)}
lammps_flags:      {json.dumps(flags)}
run_name:          {args.run_name}
work_dir:          {work_dir}
polymer_class:     {args.polymer_class.upper()}
T_equil_K:         {T_equil}
T_workflow_K:      {T_workflow}   # pass as temp=
P_equil_atm:       {cls.get('P_equil_atm', 1.0)}
t_equil_ns:        {cls.get('t_equil_ns', 5.0)}
T_anneal_high_K:   {T_anneal}
anneal_cycles:     {cls.get('eq_annealing_cycles', 5)}
dt_fs:             {dt}
{npt_prod_line}
{melt_npt_line}
gpu_ids:           "{args.gpu_ids}"
mpi_ranks:         {args.mpi_ranks}
engine:            "{args.engine}"
velocity_seed:     {args.velocity_seed if getattr(args, 'velocity_seed', None) is not None else 'null'}   # null = random; pin for reproducible trajectory

--- Worker Guide (EQUILIBRATION) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def _resolve_tg_rate(args, cls: dict):
    """Resolve the selected cooling rate + a per-rate output-dir suffix for multi-rate
    Tg sweeps. Returns (selected_rate | None, rate_suffix). When --tg_rate_index is unset,
    suffix is "" so the single-rate path stays byte-identical to the legacy pipeline."""
    tg_rates = cls.get('tg_rates_K_per_ns', [])
    rate_idx = getattr(args, 'tg_rate_index', None)
    if rate_idx is not None and tg_rates and rate_idx < len(tg_rates):
        selected_rate = tg_rates[rate_idx]
        return selected_rate, f"_r{int(selected_rate)}"
    return None, ""


def tg_prompt(args, cls: dict, cross_track_rules: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"{REPO_ROOT}/data/{args.run_name}/lammps/thermal"
    guide = load_worker_guide("tg")
    dt = _pick(args.dt_fs, cls, 'dt_fs', 1.0)

    # Multi-rate support: pick the rate at tg_rate_index if provided
    tg_rates = cls.get('tg_rates_K_per_ns', [])
    rate_idx = getattr(args, 'tg_rate_index', None)
    selected_rate, rate_suffix = _resolve_tg_rate(args, cls)
    tg_floor_warning = ""
    if selected_rate is not None:
        # Compute n_steps_per_t for this rate: rate = T_step / (n_steps * dt * 1e-6)
        t_step = _pick(args.tg_t_step_K, cls, 'tg_t_step_K', 20)
        n_steps_for_rate = int(t_step / (selected_rate * dt * 1e-6))
        n_steps_per_t = n_steps_for_rate
        rate_line = (
            f"tg_rate_index:     {rate_idx}  # rate {selected_rate} K/ns\n"
            f"  cooling_rate:    {selected_rate}"
        )
        # Backstop only — the plan-time feasibility filter should have rejected an infeasible
        # rate. Warn (never block) if this multirate point undershoots the per-T steps floor:
        # too few ps/T collapses the bilinear Tg fit (cis-PBD2 r400=50ps, PEEK2 r160/r400).
        floor = cls.get('tg_min_steps_per_T', 200000)
        if n_steps_per_t < floor:
            ps = n_steps_per_t * dt * 1e-3
            tg_floor_warning = (
                f"⚠ WARNING: rate {selected_rate} K/ns → {n_steps_per_t} steps/T = {ps:.0f} ps/T, "
                f"BELOW tg_min_steps_per_T={floor} ({floor * dt * 1e-3:.0f} ps). Bilinear Tg fit "
                f"likely DEGENERATE (cis-PBD2/PEEK2 failure mode). This rate is infeasible for "
                f"tg_t_step_K={t_step}, dt={dt}fs — the slope gate is the backstop; do NOT report "
                f"this rate's Tg as primary.\n\n"
            )
    else:
        n_steps_per_t = _pick(args.tg_steps_per_t, cls, 'tg_steps_per_t', 500000)
        rate_line = f"tg_rate_index:     null  # standard single-rate run"
        if tg_rates:
            rate_line += f"\n  all_rates_K_per_ns: {tg_rates}  # use --tg_rate_index N for multi-rate"

    # Per-rate output dir so concurrent/sequential multi-rate sweeps don't collide on
    # one tg_sweep/tg_sweep.log. Single-rate path keeps the legacy "tg_sweep" dir.
    tg_sweep_dir = f"{work_dir}/tg_sweep{rate_suffix}"
    # Rubbery: equil_data_path = npt_tg_prep_data (npt_melt at T_equil_K)
    # Glassy:  equil_data_path = npt_prod300_out.data
    # Orchestrator passes the correct cell via --tg_start_data (rubbery) or --data_path (glassy)
    _tg_cell = getattr(args, 'tg_start_data', None) or args.data_path
    return f"""\
{tg_floor_warning}equil_data_path:   {_v(_tg_cell)}
lammps_flags:      {json.dumps(flags)}
polymer_class:     {args.polymer_class.upper()}
run_name:          {args.run_name}
work_dir:          {work_dir}
tg_sweep_dir:      {tg_sweep_dir}
tg_params:
  T_start:         {_pick(args.tg_t_high_K, cls, 'tg_t_high_K', 600)}
  T_end:           {_pick(args.tg_t_low_K, cls, 'tg_t_low_K', 200)}
  T_step:          {_pick(args.tg_t_step_K, cls, 'tg_t_step_K', 20)}
  n_steps_per_t:   {n_steps_per_t}
{rate_line}
dt_fs:             {dt}
gpu_ids:           "{args.gpu_ids}"
mpi_ranks:         {args.mpi_ranks}
engine:            "{args.engine}"   # forward as engine= to run_lammps_chain / run_lammps_script / generate_equilibration_workflow
velocity_seed:     {args.velocity_seed if getattr(args, 'velocity_seed', None) is not None else 'null'}   # null = random; pin for reproducible/recovery trajectory
per_t_dump:
  enabled:         true
  file:            {tg_sweep_dir}/per_t_structs.dump   # one final frame per T step
  param_key:       WRITE_PER_T_DUMP=True, PER_T_DUMP_FILE=per_t_structs.dump
  note:            Pass these in generate_script params alongside T_START/T_END/etc.
generate_script:
  template_name:   npt_tg_step   # REQUIRED — the multi-temperature cooling staircase.
  WARNING:         NEVER use template "npt" for a Tg sweep — it renders a single-temperature
                   NPT (no cooling, no per-T dump) and is an invalid sweep.
  required_params: T_START={_pick(args.tg_t_high_K, cls, 'tg_t_high_K', 600)}, T_END={_pick(args.tg_t_low_K, cls, 'tg_t_low_K', 200)}, T_STEP={_pick(args.tg_t_step_K, cls, 'tg_t_step_K', 20)} (map from tg_params above).
                   generate_script RAISES if T_END/T_STEP are missing — verify the rendered .in
                   has a `variable temps index ...` loop before submitting.

--- Worker Guide (THERMAL_SWEEP) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def deform_prompt(args, cls: dict, cross_track_rules: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"{REPO_ROOT}/data/{args.run_name}/lammps/mechanical"
    is_glassy = args.is_glassy.lower() not in ("false", "0", "no") if args.is_glassy else True
    guide = load_worker_guide("deform")
    return f"""\
equil_data_path:   {_v(args.data_path)}
lammps_flags:      {json.dumps(flags)}
polymer_class:     {args.polymer_class.upper()}
run_name:          {args.run_name}
work_dir:          {work_dir}
is_glassy:         {str(is_glassy).lower()}
K_deform_rate_inv_s: {_pick(args.K_deform_rate_inv_s, cls, 'K_deform_rate_inv_s', 1e8)}
K_deform_rate_slow_inv_s: {cls.get('K_deform_rate_slow_inv_s', 'null')}
K_strain_max:      {_pick(args.K_strain_max, cls, 'K_strain_max', 0.03)}
dt_fs:             {_pick(args.dt_fs, cls, 'dt_fs', 1.0)}
gpu_ids:           "{args.gpu_ids}"
mpi_ranks:         {args.mpi_ranks}
engine:            "{args.engine}"

--- Worker Guide (DEFORM) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def born_prompt(args, cls: dict, cross_track_rules: str) -> str:
    raise SystemExit(
        "ERROR: --stage born is no longer supported. Born+NVT has been removed from the "
        "PolyJarvis pipeline (2026-06-21) due to PCFF+PPPM virial incompatibility (failed "
        "3/3 pipeline runs). Use --stage murnaghan for glassy bulk modulus. "
        "See guides/BORN_MATRIX.md for the removal rationale."
    )


def analyze_tg_prompt(args, cls: dict, cross_track_rules: str) -> str:
    selected_rate, rate_suffix = _resolve_tg_rate(args, cls)
    # Per-rate analysis dir so the three tg_summary.json files don't overwrite each other.
    # Single-rate (no --tg_rate_index) keeps the legacy raw/ output → reproducibility preserved.
    raw_suffix = f"tg_r{int(selected_rate)}/" if selected_rate is not None else ""
    output_dir = args.output_dir or f"{REPO_ROOT}/data/{args.run_name}/raw/{raw_suffix}"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    lammps_base = f"{REPO_ROOT}/data/{args.run_name}/lammps"
    tg_log = args.data_path or f"{lammps_base}/thermal/tg_sweep{rate_suffix}/tg_sweep.log"
    # equil_data_path: production NPT output — passed to extract_thermal as tg_data_file for ΔCp mass
    # normalisation. Phase-aware: glassy chains end at npt_prod300 (cooled to 300 K); rubbery chains
    # (7-run, since commit 5b640ff) have NO npt_prod300 stage — they end at npt_production at
    # T_equil_K. Defaulting to npt_prod300 on a rubbery chain points at a nonexistent file.
    if _regime(args, cls) == "rubbery":
        default_equil_data = f"{lammps_base}/equil/npt_production/npt_production_out.data"
    else:
        default_equil_data = f"{lammps_base}/equil/npt_prod300/npt_prod300_out.data"
    equil_data = args.equil_data_path or default_equil_data
    enthalpy_col = getattr(args, "enthalpy_col", None) or "Enthalpy"
    guide = load_worker_guide("analyze-tg")
    rate_line = (f"cooling_rate_K_per_ns: {selected_rate}  # tg_rate_index={args.tg_rate_index}; "
                 f"report this (rate, Tg_K) pair to the multirate registry\n"
                 if selected_rate is not None else "")
    return f"""\
tg_log_path:       {tg_log}
tg_data_file:      {equil_data}    # required for ΔCp mass normalisation
enthalpy_col:      {enthalpy_col}
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
{rate_line}output_dir:        {output_dir}
graphs_dir:        {graphs_dir}
tasks:
  - extract_thermal

--- Worker Guide (THERMAL_ANALYSIS) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def analyze_tg_multirate_prompt(args, cls: dict, cross_track_rules: str) -> str:
    """Aggregate per-rate (rate, Tg_MD) pairs: log-linear + VF fit, extrapolated to the
    DSC-equivalent rate. The orchestrator supplies --mr_rates / --mr_tg_values from the
    cross-replicate registry; the worker runs the emitted command verbatim."""
    output_dir = args.output_dir or f"{REPO_ROOT}/data/{args.run_name}/raw/"
    script = str(REPO_ROOT / "mcp-servers/mcp-lammps-engine"
                 / "analysis_scripts/extract_tg_multirate.py")
    dsc_rate = cls.get("dsc_equiv_rate_K_per_ns", 1.6667e-10)
    guide = load_worker_guide("analyze-tg-multirate")
    rates = (args.mr_rates or "").replace(",", " ").strip()
    tg_vals = (args.mr_tg_values or "").replace(",", " ").strip()
    polymer_name = args.run_name
    # regime exempts the slope-sign gate for rubbery polymers (T_workflow >> Tg): a negative
    # rate-dependence slope is scatter, not contamination, so no false-positive reroll.
    regime = _regime(args, cls)
    command = (
        f"python3 {script} \\\n"
        f"  --rates {rates or '<FILL: space-separated rates from registry, e.g. 40 160 400>'} \\\n"
        f"  --tg_values {tg_vals or '<FILL: matching Tg_MD values from registry>'} \\\n"
        f"  --slow_rate_ref {dsc_rate} \\\n"
        f"  --regime {regime} \\\n"
        f"  --polymer_name {polymer_name} \\\n"
        f"  --output_dir {output_dir}"
    )
    return f"""\
task:              extract_tg_multirate
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
output_dir:        {output_dir}
dsc_equiv_rate_K_per_ns: {dsc_rate}
mr_rates:          {rates or '<FILL from registry>'}
mr_tg_values:      {tg_vals or '<FILL from registry>'}
command: |
  {command}

--- Worker Guide (THERMAL_ANALYSIS) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def equil_check_prompt(args, cls: dict, cross_track_rules: str) -> str:
    """Prompt for equilibration-checker (equil-check gate — equil check + density)."""
    output_dir = args.output_dir or f"{REPO_ROOT}/data/{args.run_name}/raw/"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    exp_density = _exp_density_range(cls)
    # Aromatic main-chain classes (ct_gate_reliable=false) cannot have their backbone path defined
    # by atom-type selection, so C(t)/C∞ are unreliable — do NOT arm the hard gate (null = advisory).
    ct_decay = cls.get("ct_min_decay_melt", 0.10) if cls.get("ct_gate_reliable", True) else None

    lammps_base = f"{REPO_ROOT}/data/{args.run_name}/lammps"
    # Phase-aware NPT production files: rubbery (T_workflow ≤ 300) ends at npt_production (7-run
    # chain — no npt_prod300 exists); glassy (T_workflow > 300) appends npt_prod300. The melt-NVT
    # log (nvt_production.log) is present in both. CLI --npt_prod_log/--npt_prod_dump/--data_path
    # still override when given.
    T_workflow = _resolve_t_workflow(args, cls)
    # Production NPT (thermo/density): rubbery (T ≤ 300) ends at npt_production; glassy (T > 300)
    # at npt_prod300 (cooled to 300 K). The structural/chain-relaxation checks (C(t), MSD, Rg, R_ee)
    # must run on the MELT trajectory — nvt_production at T_workflow, where chains are mobile — NOT
    # the production NPT, which for a glassy polymer is below Tg and yields trapped dynamics by
    # construction. check_equilibration_comprehensive decouples thermo (log_file) from structural
    # (dump_file), so a single call covers both: log_file = production NPT log, dump_file = melt dump.
    if T_workflow <= 300:
        prod, npt_prod_temp = "npt_production", T_workflow
    else:
        prod, npt_prod_temp = "npt_prod300", 300.0
    npt_log = args.npt_prod_log or f"{lammps_base}/equil/{prod}/{prod}.log"
    npt_data = args.data_path or f"{lammps_base}/equil/{prod}/{prod}_out.data"
    melt_dump = args.npt_prod_dump or f"{lammps_base}/equil/nvt_production/nvt_production.dump"

    # is_glassy and dp enable the require_glassy carve-out in the checker:
    # when is_glassy=True AND dp>=30, chain C(t)/end-to-end diffusion gates are advisory only
    # (gate on density SEM/CV/P2 exclusively). Derived from T_workflow so no explicit CLI flag needed.
    is_glassy_equil = T_workflow > 300
    # regime oracle drives the require_rubbery carve-out (decision_policy.json): a rubbery polymer
    # (produced above Tg) has is_glassy=False, so require_glassy does NOT apply — but its terminal
    # chain-reptation metrics are unreachable at finite DP, so C(t)/MSD/Rg/τ_relax must be advisory
    # and the gate keys on density block-SEM + homogeneity + energy only. Without this line the
    # checker hard-gates reptation metrics on rubbery melts → unfixable EXTEND (PE/PBD/PEG).
    regime = _regime(args, cls)
    dp_val = getattr(args, 'dp', None) or cls.get('dp_typical')
    guide = load_worker_guide("equil-check")
    return f"""\
npt_prod_log_path: {npt_log}
melt_dump_path:    {melt_dump}
npt_prod_temp_K:   {npt_prod_temp}   # target_temp= for extract_equilibrated_density
equil_data_path:   {npt_data}
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
backbone_types:    {args.backbone_types or '<FILL from inspect_data_file>'}
ct_min_decay_melt: {ct_decay if ct_decay is not None else 'null'}   # ct_min_decay= ; null ⇒ aromatic main chain, C(t)/C∞ advisory only (do NOT pass ct_min_decay)
is_glassy:         {str(is_glassy_equil).lower()}   # True → require_glassy carve-out: C(t)/Rg/MSD gates are advisory; gate only on density SEM/CV/P2
regime:            {regime}   # if rubbery: require_rubbery carve-out applies — C(t)/MSD/Rg/τ_relax ADVISORY; verdict gates ONLY on density block-SEM<2% AND density-homogeneity CV<25% AND energy drift/SEM; do NOT EXTEND/FAIL on reptation metrics alone. If glassy: no carve-out from this line (see is_glassy for require_glassy).
dp:                {dp_val if dp_val is not None else 'null'}   # DP≥30 required for require_glassy carve-out to apply
exp_density_range: {exp_density}
output_dir:        {output_dir}
graphs_dir:        {graphs_dir}
tasks:
  - check_equilibration_comprehensive
  - extract_equilibrated_density

### D-05 REQUIREMENT (PEEK2 I-04): paste result["d05_markdown"] (also written to
### {output_dir}d05_block.md) VERBATIM into the run_log.md D-05 CONVERGENCE DETAIL section.
### It contains the real Rg/MSD/density/C(t)/R_ee values. Leaving any [X ± Y] / [X]% /
### [PASS / FAIL] placeholder in run_log.md is a FAILURE of this equil-check step — the tool
### already fills every field, so there is no reason to leave a placeholder.

--- Worker Guide (EQUIL_CHECK) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def murnaghan_prompt(args, cls: dict, cross_track_rules: str) -> str:
    """Prompt for murnaghan-worker (rubbery BM pressure series submission)."""
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"{REPO_ROOT}/data/{args.run_name}/lammps/mechanical"
    is_glassy = args.is_glassy.lower() not in ("false", "0", "no") if args.is_glassy else False
    bm_pressures_atm = cls.get("bm_pressures_atm", None)
    dt = _pick(args.dt_fs, cls, "dt_fs", 1.0)
    lammps_base = f"{REPO_ROOT}/data/{args.run_name}/lammps"
    equil_data = args.data_path or f"{lammps_base}/equil/npt_production/npt_production_out.data"
    guide = load_worker_guide("murnaghan")
    # Glassy polymers ALWAYS submit. The guide's Rule B rubbery null-return guard has been
    # mis-applied to glassy cells when Tg metadata was degraded (POOR fits / single-rate
    # fallback) → worker returned null instead of submitting (PEEK2 I-02). Assert imperatively,
    # above the guide, so this overrides Rule B at prompt-assembly time.
    glassy_assertion = (
        "### ASSERTION (overrides guide Rule B): is_glassy=true → SUBMIT the Murnaghan series "
        "NOW, regardless of bm_pressures_atm being null. The rubbery null-return guard does NOT "
        "apply to glassy cells. Do not return an all-null RESULT.\n\n"
    ) if is_glassy else ""
    return f"""\
{glassy_assertion}equil_data_path:   {equil_data}
lammps_flags:      {flags}
polymer_class:     {args.polymer_class.upper()}
run_name:          {args.run_name}
work_dir:          {work_dir}/bm_series
is_glassy:         {str(is_glassy).lower()}
bm_pressures_atm:  {bm_pressures_atm}
temp_K:            300.0
npt_steps:         500000
dt_fs:             {dt}
gpu_ids:           "{args.gpu_ids}"
mpi_ranks:         {args.mpi_ranks}
engine:            "{args.engine}"

--- Worker Guide (MURNAGHAN) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def analyze_bm_prompt(args, cls: dict, cross_track_rules: str) -> str:
    """Prompt for bulk-modulus-extractor (BM extraction, all four routing paths)."""
    output_dir = args.output_dir or f"{REPO_ROOT}/data/{args.run_name}/raw/"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    lammps_base = f"{REPO_ROOT}/data/{args.run_name}/lammps"
    npt_log = args.npt_prod_log or f"{lammps_base}/equil/npt_prod300/npt_prod300.log"
    _k_from_cls = _exp_K_range(cls)
    exp_K = [
        args.exp_K_min if args.exp_K_min is not None else _k_from_cls[0],
        args.exp_K_max if args.exp_K_max is not None else _k_from_cls[1],
    ]
    bm_pressures_atm = cls.get("bm_pressures_atm", None)
    # Deform extraction params
    strain_rate_per_fs = cls.get("K_deform_rate_inv_s", 1e8) * 1e-15
    K_strain_max = cls.get("K_strain_max", 0.03)

    deform_log_line   = f"deform_log_path:     {args.deform_log}" if getattr(args, 'deform_log', None) else "deform_log_path:     null"
    murnaghan_line    = f"murnaghan_log_files: {args.murnaghan_logs}" if getattr(args, 'murnaghan_logs', None) else "murnaghan_log_files: null"

    guide = load_worker_guide("analyze-bm")
    return f"""\
{deform_log_line}
{murnaghan_line}
npt_prod_log_path: {npt_log}
bm_pressures_atm:  {bm_pressures_atm}
exp_K_range:       {exp_K}
strain_rate_per_fs: {strain_rate_per_fs:.2e}
K_strain_max:      {K_strain_max}
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
output_dir:        {output_dir}
graphs_dir:        {graphs_dir}

--- Worker Guide (BM_ANALYSIS) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def run_summary_prompt(args, cls: dict, cross_track_rules: str) -> str:
    """Prompt for run-summary-worker (always-terminal, calls generate_run_summary).

    Threads run metadata and per-decision strings through to generate_run_summary so
    run_summary.json is fully populated. Every field is derived from CLI flags + the
    (plan-overlaid) class defaults + the deterministic output_dir convention — NOT from the
    plan's decisions[] list or the --plan path — so a deterministic plan still produces
    byte-identical output to the no-plan path (enforced by tests/test_plan_reproducibility.py).
    The plan provenance is carried by reading raw/run_plan.json (the convention path below).
    """
    output_dir = args.output_dir or f"{REPO_ROOT}/data/{args.run_name}/raw/"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    run_plan = f"{output_dir.rstrip('/')}/run_plan.json"

    # Priority: explicit CLI min/max (thread from exp-lookup-worker) > --exp_tg_K CLI > DB query
    #           > polymer_rules.json median. The explicit min/max path lets the orchestrator pass
    #           condition-matched experimental ranges from exp-lookup-worker instead of hand-entering
    #           a tight floor (which caused a 0.07% density false FAIL, PVC2).
    _db = _db_exp_lookup(args.polymer_class, getattr(args, 'polymer_name', None))
    _tg_min, _tg_max = getattr(args, 'exp_tg_min', None), getattr(args, 'exp_tg_max', None)
    _tg_override = getattr(args, 'exp_tg_K', None)
    if _tg_min is not None and _tg_max is not None:
        exp_tg = [_tg_min, _tg_max]
    elif _tg_override is not None:
        exp_tg = [round(_tg_override - 20), round(_tg_override + 20)]
    elif _db.get("tg_median_K") is not None:
        exp_tg = [round(_db["tg_median_K"] - 20), round(_db["tg_median_K"] + 20)]
    else:
        exp_tg = _exp_tg_range(cls, run_name=args.run_name)

    # Density: explicit CLI min/max > DB value ±5% > polymer_rules.json median ±5%
    _dens_min, _dens_max = getattr(args, 'exp_density_min', None), getattr(args, 'exp_density_max', None)
    if _dens_min is not None and _dens_max is not None:
        exp_density = [_dens_min, _dens_max]
    elif _db.get("density_gcm3") is not None:
        _d = _db["density_gcm3"]
        exp_density = [round(_d * 0.95, 3), round(_d * 1.05, 3)]
    else:
        exp_density = _exp_density_range(cls)

    # K: CLI override > DB range (if genuine range) > polymer_rules.json range
    # A DB range of [x, x] (single-point measurement) is treated as missing — it must not
    # override the polymer_rules class range, which covers all class members.
    _k_from_cls = _exp_K_range(cls)
    _k_from_db = _db.get("K_range_GPa")
    if _k_from_db and (_k_from_db[1] - _k_from_db[0]) < 0.01:
        _k_from_db = None  # degenerate single-point DB entry; fall through to polymer_rules
    exp_K = [
        args.exp_K_min if args.exp_K_min is not None else (
            _k_from_db[0] if _k_from_db else _k_from_cls[0]
        ),
        args.exp_K_max if args.exp_K_max is not None else (
            _k_from_db[1] if _k_from_db else _k_from_cls[1]
        ),
    ]

    dp = args.dp if args.dp is not None else cls.get("dp_typical")
    nchain = args.nchain if args.nchain is not None else cls.get("nchain")
    charge_method = args.charge_method or cls.get("charge_method")
    ff = args.ff or cls.get("preferred_ff", "pcff")
    d01 = args.d01 or ff
    d02 = args.d02 or charge_method
    d03 = args.d03 or cls.get("electrostatics")
    d04 = args.d04 or (f"DP={dp}, {nchain} chains" if dp and nchain else None)

    _slope_gate = getattr(args, 'slope_gate_pass', None)
    _tg_path_label = (
        "single-rate fallback (slope_gate=False; highest-rate folder)"
        if _slope_gate is False
        else "slowest-rate folder (slope_gate=True or N/A)"
    )
    return f"""\
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
smiles:            {_v(args.smiles)}
ff:                {ff}
charge_method:     {_v(charge_method, 'null')}
dp:                {_v(dp, 'null')}
n_chains:          {_v(nchain, 'null')}
n_atoms:           {_v(getattr(args, 'n_atoms', None), 'null')}
date_start:        {_v(args.date_start, 'null')}
date_end:          {_v(args.date_end, 'null')}
d01_ff:            {_v(d01, 'null')}
d02_charges:       {_v(d02, 'null')}
d03_electrostatics: {_v(d03, 'null')}
d04_system_size:   {_v(d04, 'null')}
d05_verdict:       {args.d05 or '<FILL from equil-checker RESULT>'}
d06_tg_fit_quality: {_v(args.tg_fit_quality, 'N/A (not requested)')}
run_plan:          {run_plan}   # always pass to generate_run_summary --run_plan (skip if file absent)
exp_tg_range:      {exp_tg}
exp_density_range: {exp_density}
exp_K_range:       {exp_K}
n_replicates:      {_v(getattr(args, 'n_replicates', None), 'N/A')}   # distinct replicates in the multi-rate Tg registry; pass to generate_run_summary --n_replicates
tg_path:           {_v(getattr(args, 'tg_path', None), 'null')}   # explicit canonical tg_summary.json path ({_tg_path_label}); pass to generate_run_summary --tg_path
slope_gate_pass:   {_v(_slope_gate, 'null')}   # False → single-rate fallback Tg; pass --tg_k with the fallback value
output_dir:        {output_dir}
graphs_dir:        {graphs_dir}

Forward every field above to generate_run_summary as its matching --flag (dp→--dp,
n_chains→--n_chains, n_atoms→--n_atoms, charge_method→--charge_method, date_start→--date_start,
date_end→--date_end, d01_ff→--d01, …, d05_verdict→--d05, d06_tg_fit_quality→--d06,
run_plan→--run_plan). Skip any field whose value is `null`.

# generate_run_summary returns {{"status":"submitted","run_id":...}} but it completes IN-PROCESS in
# seconds — do NOT poll with get_run_status (you have no such tool). After the call, Read
# {output_dir}run_summary.json directly and parse it.
"""


# ─── CLI ──────────────────────────────────────────────────────────────────────

STAGE_MAP = {
    "build":        build_prompt,
    "equil":        equil_prompt,
    "tg":           tg_prompt,
    "deform":       deform_prompt,
    "born":         born_prompt,
    "murnaghan":    murnaghan_prompt,
    "analyze-tg":   analyze_tg_prompt,
    "analyze-tg-multirate": analyze_tg_multirate_prompt,
    "equil-check":  equil_check_prompt,
    "analyze-bm":   analyze_bm_prompt,
    "run-summary":  run_summary_prompt,
}


def main():
    p = argparse.ArgumentParser(
        description="Generate a fully-formed PolyJarvis worker prompt.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Workers: build | equil | tg | deform | murnaghan | analyze-tg | analyze-tg-multirate | equil-check | analyze-bm | run-summary",
    )
    p.add_argument("--stage", required=True, choices=list(STAGE_MAP),
                   metavar="STAGE",
                   help="build|equil|tg|deform|murnaghan|analyze-tg|analyze-tg-multirate|equil-check|analyze-bm|run-summary (born is removed — raises error)")
    p.add_argument("--run_name", required=True)
    p.add_argument("--polymer_class", required=True)
    p.add_argument("--plan",
                   help="Path to an approved run_plan.json. Overlays the plan's "
                        "decided_params onto the class defaults (scientific decisions); "
                        "runtime paths/gpu stay in the flags below. Deterministic plans "
                        "produce byte-identical output to the no-plan path.")
    p.add_argument("--smiles")
    p.add_argument("--data_path")
    p.add_argument("--tg_start_data",
                   help="Tg sweep starting .data file (rubbery: npt_tg_prep_data = npt_melt at "
                        "T_equil_K). Overrides --data_path for the tg stage only. Glassy polymers "
                        "omit this flag and pass --data_path instead.")
    p.add_argument("--work_dir")
    p.add_argument("--gpu_ids", required=False, default=None,
                   help='Comma-separated GPU IDs, e.g. "0" or "0,1". '
                        'If omitted, derived from polymer_rules.json hardware_policy by FF '
                        '("" for CPU engine). Claim a free GPU with scripts/pick_gpu.py.')
    p.add_argument("--mpi_ranks", type=int, required=False, default=None,
                   help="MPI processes per run. If omitted, derived from "
                        "hardware_policy by FF (never mpi=1 for PPPM classes).")
    p.add_argument("--engine", required=False, default=None,
                   choices=["gpu", "kokkos"],
                   help="Execution engine the worker forwards to run_lammps_chain / "
                        "run_lammps_script / generate_equilibration_workflow. If omitted, "
                        "derived from the plan's decided_params.engine or hardware_policy "
                        "(kokkos = full-offload; anything else → gpu).")
    p.add_argument("--emc_seed", type=int, required=False, default=None,
                   help="Fixed EMC cell-packing seed (build stage). If omitted, the builder "
                        "generates a random seed and reports it. For replication studies pass the "
                        "fixed seed from guides/REVISION_PARAMS.md so the cell is reproducible.")
    p.add_argument("--velocity_seed", type=int, required=False, default=None,
                   help="Fixed `velocity all create` RNG seed (equil/tg stages). If omitted, the "
                        "tool draws a random seed. Pin it (REVISION_PARAMS.md) for a reproducible "
                        "trajectory, not just a reproducible initial cell.")
    p.add_argument("--dp", type=int)
    p.add_argument("--nchain", type=int)
    # run-summary metadata (else sourced from the plan; see run_summary_prompt)
    p.add_argument("--n_atoms", type=int)
    p.add_argument("--charge_method")
    p.add_argument("--date_start")
    p.add_argument("--date_end")
    p.add_argument("--d01", help="run-summary: D-01 force-field choice")
    p.add_argument("--d02", help="run-summary: D-02 charges choice")
    p.add_argument("--d03", help="run-summary: D-03 electrostatics choice")
    p.add_argument("--d04", help="run-summary: D-04 system-size choice")
    p.add_argument("--lammps_flags")
    p.add_argument("--is_glassy", default="true")
    p.add_argument("--tg_k", type=float)
    p.add_argument("--tg_fit_quality")
    p.add_argument("--born_log",
                   help="DEPRECATED — Born+NVT removed 2026-06-21. Argument kept for CLI compatibility but ignored.")
    p.add_argument("--born_matrix",
                   help="DEPRECATED — Born+NVT removed 2026-06-21. Argument kept for CLI compatibility but ignored.")
    p.add_argument("--born_n_atoms", type=int,
                   help="DEPRECATED — Born+NVT removed 2026-06-21. Argument kept for CLI compatibility but ignored.")
    p.add_argument("--deform_log",
                   help="Path to npt_deform log (analyze-bm, glassy deform fallback)")
    p.add_argument("--murnaghan_logs",
                   help="JSON list of absolute log paths from murnaghan-worker (analyze-bm, rubbery+pressures)")
    p.add_argument("--d05",
                   help="equil_verdict from equil-checker RESULT: PASS|EXTEND|FAIL (run-summary stage)")
    p.add_argument("--born_run_ns", type=float,
                   help="DEPRECATED — Born+NVT removed 2026-06-21 (PCFF+PPPM virial incompatibility). "
                        "Use --stage murnaghan. See guides/BORN_MATRIX.md.")
    p.add_argument("--npt_prod_log")
    p.add_argument("--npt_prod_dump")
    p.add_argument("--ff")
    p.add_argument("--backbone_types",
                   help="Atom type IDs as JSON list (equil-check only)")
    p.add_argument("--enthalpy_col", default="Enthalpy",
                   help="LAMMPS thermo column name for enthalpy (analyze-tg; default 'Enthalpy')")
    p.add_argument("--output_dir")
    p.add_argument("--equil_data_path",
                   help="Path to equilibrated .data file (LAMMPS .data input to Tg sweep; required for ΔCp mass normalisation in extract_thermal)")
    # Physics knob overrides (all optional; default None → falls back to polymer_rules.json)
    p.add_argument("--npt_prod_ns", type=float,
                   help="NPT production time (ns); auto-sized by atom count if omitted")
    p.add_argument("--add_melt_npt", action="store_true", default=False,
                   help="Inject 05b melt isothermal NPT stage for rubbery classes (FF validation only)")
    p.add_argument("--T_equil_K", type=float,
                   help="Equilibration temperature (K) → temp= in generate_equilibration_workflow")
    p.add_argument("--T_anneal_high_K", type=float,
                   help="Peak annealing temperature (K) → max_temp= in generate_equilibration_workflow")
    p.add_argument("--tg_t_high_K", type=float,
                   help="Tg sweep start temperature (K)")
    p.add_argument("--tg_t_low_K", type=float,
                   help="Tg sweep end temperature (K)")
    p.add_argument("--tg_t_step_K", type=float,
                   help="Tg sweep step (K); halve for BORDERLINE R² recovery")
    p.add_argument("--tg_steps_per_t", type=int,
                   help="MD steps per temperature window")
    p.add_argument("--tg_rate_index", type=int,
                   help="Index into tg_rates_K_per_ns list for multi-rate sweeps (0=slowest)")
    p.add_argument("--mr_rates",
                   help="analyze-tg-multirate: comma/space-separated cooling rates (K/ns) "
                        "from the cross-replicate registry, e.g. '40,160,400'")
    p.add_argument("--mr_tg_values",
                   help="analyze-tg-multirate: matching Tg_MD values (K), same order as --mr_rates")
    p.add_argument("--n_replicates", type=int,
                   help="run-summary: number of distinct replicates in the multi-rate Tg registry")
    p.add_argument("--K_strain_max", type=float,
                   help="Max engineering strain for uniaxial deformation")
    p.add_argument("--K_deform_rate_inv_s", type=float,
                   help="Engineering strain rate (s⁻¹)")
    p.add_argument("--dt_fs", type=float,
                   help="MD timestep (fs); set 0.5 for 'lost atoms' recovery")
    p.add_argument("--density_initial", type=float,
                   help="Initial packing density (g/cm³); use for ESCALATE recovery (class default − 0.05) or Energy-NaN recovery (class default − 0.10)")
    p.add_argument("--properties", default="all",
                   help="Comma-separated properties to extract: density,tg,bulk_modulus or 'all'")
    p.add_argument("--exp_K_min", type=float,
                   help="Experimental bulk modulus lower bound (GPa); overrides polymer_rules.json")
    p.add_argument("--exp_K_max", type=float,
                   help="Experimental bulk modulus upper bound (GPa); overrides polymer_rules.json")
    p.add_argument("--exp_tg_K", type=float,
                   help="Experimental Tg override (K) for T_workflow_K decision; use for specific polymer "
                        "within a multi-polymer class (e.g. --exp_tg_K 213 for PCL within PEST)")
    p.add_argument("--exp_tg_min", type=float,
                   help="Experimental Tg lower bound (K) for run-summary grading; overrides DB/rules. "
                        "Thread from exp-lookup-worker. Pass with --exp_tg_max.")
    p.add_argument("--exp_tg_max", type=float,
                   help="Experimental Tg upper bound (K) for run-summary grading; overrides DB/rules.")
    p.add_argument("--exp_density_min", type=float,
                   help="Experimental density lower bound (g/cm³) for run-summary grading; overrides "
                        "DB/rules. Thread from exp-lookup-worker rather than hand-entering a tight floor "
                        "(a too-tight floor caused a 0.07%% false FAIL, PVC2 2026-06-23). With --exp_density_max.")
    p.add_argument("--exp_density_max", type=float,
                   help="Experimental density upper bound (g/cm³) for run-summary grading; overrides DB/rules.")
    p.add_argument("--polymer_name", default=None,
                   help="Canonical DB name for experimental lookup (e.g. 'Poly(methyl methacrylate)'). "
                        "Enables polymer-specific exp ranges from polymer_db.sqlite. "
                        "When omitted, falls back to the class-representative canonical pattern.")
    p.add_argument("--tg_path", default=None,
                   help="Explicit path to the canonical tg_summary.json for run-summary. "
                        "Normally the slowest-rate folder (e.g. tg_r40/tg_summary.json). "
                        "When slope_gate_pass=False, pass the highest-rate folder instead "
                        "(e.g. tg_r400/tg_summary.json — the single-rate fallback).")
    p.add_argument("--slope_gate_pass", type=lambda x: x.lower() == 'true', default=None,
                   help="Multirate log-linear slope gate result (true/false). False means "
                        "slope<=0 (contaminated sweep); tg_path should point to the highest-rate "
                        "fallback folder, not the slowest-rate folder. Threaded to run-summary-worker.")

    args = p.parse_args()

    rules = load_rules()
    cross_track_rules = load_cross_track_rules()
    cls = get_class_entry(rules, args.polymer_class)

    if args.plan:
        cls = apply_plan(cls, load_plan(args.plan), args)

    resolve_hardware(args, cls, rules)

    prompt_fn = STAGE_MAP[args.stage]
    print(prompt_fn(args, cls, cross_track_rules))


if __name__ == "__main__":
    main()
