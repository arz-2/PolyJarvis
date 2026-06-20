#!/usr/bin/env python3
"""
gen_prompt.py — Generate fully-formed worker prompts for PolyJarvis orchestrator.

Usage:
  python3 scripts/gen_prompt.py --stage <STAGE> [options]

Workers: build | equil | tg | deform | born | murnaghan | analyze-tg | equil-check | analyze-bm | run-summary

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
  --npt_prod_dump PATH    NPT production dump (equil-check)
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
import re
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = REPO_ROOT / "guides" / "polymer_rules.json"
CLAUDE_MD_PATH = REPO_ROOT / "CLAUDE.md"

WORKER_GUIDES = {
    "build":        "MOLECULE_BUILDER.md",
    "equil":        "EQUILIBRATION.md",
    "tg":           "THERMAL_SWEEP.md",
    "analyze-tg":   "THERMAL_ANALYSIS.md",
    "equil-check":  "EQUIL_CHECK.md",
    "analyze-bm":   "BM_ANALYSIS.md",
    "deform":       "DEFORM.md",
    "born":         "BORN_MATRIX.md",
    "murnaghan":    "MURNAGHAN.md",
    "run-summary":  None,
}


# ─── Loaders ──────────────────────────────────────────────────────────────────

def load_rules() -> dict:
    with open(RULES_PATH) as f:
        return json.load(f)


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
    return effective


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
    ff_raw = cls.get("preferred_ff") or cls.get("forcefield") or ""
    fam = hp.get("ff_aliases", {}).get(ff_raw) or hp.get("ff_aliases", {}).get(ff_raw.upper())
    if fam is None:
        fl = ff_raw.lower()
        fam = ("pcff" if "pcff" in fl else "opls" if "opls" in fl
               else "trappe" if "trappe" in fl else "gaff")
    pol = hp.get("by_forcefield", {}).get(fam, {})
    if args.mpi_ranks is None:
        args.mpi_ranks = pol.get("mpi", 8)
        print(f"INFO: mpi_ranks not given — derived {args.mpi_ranks} from "
              f"hardware_policy[{fam}] (engine={pol.get('engine')})", file=sys.stderr)
    if args.gpu_ids is None:
        args.gpu_ids = "" if pol.get("engine") == "cpu" else "0"
        print(f"INFO: gpu_ids not given — derived \"{args.gpu_ids}\" from "
              f"hardware_policy[{fam}]; claim a free GPU with scripts/pick_gpu.py",
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


def _nondegenerate(lo, hi, frac: float = 0.05) -> list:
    """Guard against a zero-width [x, x] band, which can never PASS. A single
    experimental anchor must become a ±frac tolerance band, not min==max."""
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo == hi:
        return [round(lo * (1 - frac), 3), round(hi * (1 + frac), 3)]
    return [lo, hi]


def _exp_tg_range(cls: dict) -> list:
    tg = cls.get("experimental_tg_K")
    if isinstance(tg, dict):
        vals = [v for k, v in tg.items() if isinstance(v, (int, float))]
        if vals:
            mid = sum(vals) / len(vals)
            return [round(mid - 20), round(mid + 20)]
    if isinstance(tg, (int, float)):
        return [round(tg - 20), round(tg + 20)]
    return ["<exp_tg_min>", "<exp_tg_max>"]


def _exp_K_range(cls: dict) -> list:
    exp = cls.get("exp_K_GPa")
    if isinstance(exp, dict) and "min" in exp and "max" in exp:
        return [exp["min"], exp["max"]]
    return [None, None]


def _exp_density_range(cls: dict) -> list:
    # Accept both the rules key (experimental_density_gcm3) and the plan's
    # decided_params scalar key (exp_density_gcm3) — a key mismatch here was the
    # cause of the zero-width [0.9,0.9] density band in cis-PBD1.
    exp = cls.get("experimental_density_gcm3")
    if exp is None:
        exp = cls.get("exp_density_gcm3")
    if isinstance(exp, dict):
        vals = [v for k, v in exp.items() if isinstance(v, (int, float))]
        if vals:
            mid = sum(vals) / len(vals)
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
    work_dir = args.work_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps"
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


def equil_prompt(args, cls: dict, cross_track_rules: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps/equil"
    guide = load_worker_guide("equil")
    dt = _pick(args.dt_fs, cls, 'dt_fs', 1.0)
    T_equil = _pick(args.T_equil_K, cls, 'T_equil_K', 600.0)
    T_anneal = _pick(args.T_anneal_high_K, cls, 'annealing_T_high_K', 700.0)
    npt_prod_ns_val = _pick(args.npt_prod_ns, cls, 'npt_prod_ns', None)
    if npt_prod_ns_val is not None:
        npt_prod_steps = int(npt_prod_ns_val * 1e6 / dt)
        npt_prod_line = (
            f"t_npt_prod_ns:     {npt_prod_ns_val}\n"
            f"npt_prod_steps:    {npt_prod_steps}  "
            f"# pass as npt_prod_steps= to generate_equilibration_workflow"
        )
    else:
        npt_prod_line = "t_npt_prod_ns:     null  # auto: steps_npt // 2 by atom-count tier"
    exp_tg_override = getattr(args, 'exp_tg_K', None)
    if exp_tg_override is not None:
        exp_tg = exp_tg_override
    else:
        exp_tg = cls.get('experimental_tg_K')
        if isinstance(exp_tg, dict):
            vals = sorted(v for v in exp_tg.values() if isinstance(v, (int, float)))
            exp_tg = vals[len(vals) // 2]  # median: avoids low-Tg outliers (e.g. PCL in PEST)
    if "T_workflow_K" in cls:
        T_workflow = cls["T_workflow_K"]
    else:
        T_workflow = 300.0 if isinstance(exp_tg, (int, float)) and exp_tg < 300 else T_equil
    add_melt_npt = getattr(args, 'add_melt_npt', False) or False
    melt_npt_ns_val = _pick(None, cls, 'melt_npt_ns', None) if add_melt_npt else None
    if add_melt_npt and melt_npt_ns_val is not None:
        melt_npt_steps = int(melt_npt_ns_val * 1e6 / dt)
        melt_npt_line = (
            f"add_melt_npt:      true\n"
            f"t_equil_K:         {T_equil}  # melt isothermal stage temperature\n"
            f"melt_npt_ns:       {melt_npt_ns_val}\n"
            f"melt_npt_steps:    {melt_npt_steps}  "
            f"# pass as melt_npt_steps= to generate_equilibration_workflow"
        )
    elif add_melt_npt:
        melt_npt_line = (
            f"add_melt_npt:      true\n"
            f"t_equil_K:         {T_equil}  # melt isothermal stage temperature"
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
T_workflow_K:      {T_workflow}   # 300.0 if rubbery (exp_Tg<300 K), else T_equil_K — pass as temp= to generate_equilibration_workflow
P_equil_atm:       {cls.get('P_equil_atm', 1.0)}
t_equil_ns:        {cls.get('t_equil_ns', 5.0)}
T_anneal_high_K:   {T_anneal}
anneal_cycles:     {cls.get('eq_annealing_cycles', 5)}
dt_fs:             {dt}
{npt_prod_line}
{melt_npt_line}
gpu_ids:           "{args.gpu_ids}"
mpi_ranks:         {args.mpi_ranks}

--- Worker Guide (EQUILIBRATION) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def tg_prompt(args, cls: dict, cross_track_rules: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps/thermal"
    guide = load_worker_guide("tg")
    dt = _pick(args.dt_fs, cls, 'dt_fs', 1.0)

    # Multi-rate support: pick the rate at tg_rate_index if provided
    tg_rates = cls.get('tg_rates_K_per_ns', [])
    rate_idx = getattr(args, 'tg_rate_index', None)
    if rate_idx is not None and tg_rates and rate_idx < len(tg_rates):
        selected_rate = tg_rates[rate_idx]
        # Compute n_steps_per_t for this rate: rate = T_step / (n_steps * dt * 1e-6)
        t_step = _pick(args.tg_t_step_K, cls, 'tg_t_step_K', 20)
        n_steps_for_rate = int(t_step / (selected_rate * dt * 1e-6))
        n_steps_per_t = n_steps_for_rate
        rate_line = (
            f"tg_rate_index:     {rate_idx}  # rate {selected_rate} K/ns\n"
            f"  cooling_rate:    {selected_rate} K/ns  # one of {tg_rates}"
        )
    else:
        n_steps_per_t = _pick(args.tg_steps_per_t, cls, 'tg_steps_per_t', 500000)
        rate_line = f"tg_rate_index:     null  # standard single-rate run"
        if tg_rates:
            rate_line += f"\n  all_rates_K_per_ns: {tg_rates}  # use --tg_rate_index N for multi-rate"

    tg_sweep_dir = f"{work_dir}/tg_sweep"
    return f"""\
equil_data_path:   {_v(args.data_path)}
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
per_t_dump:
  enabled:         true
  file:            {tg_sweep_dir}/per_t_structs.dump   # one final frame per T step
  param_key:       WRITE_PER_T_DUMP=True, PER_T_DUMP_FILE=per_t_structs.dump
  note:            Pass these in generate_script params alongside T_START/T_END/etc.

--- Worker Guide (THERMAL_SWEEP) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def deform_prompt(args, cls: dict, cross_track_rules: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps/mechanical"
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
K_rate_comparison: {str(cls.get('K_deform_rate_slow_inv_s') is not None).lower()}
K_strain_max:      {_pick(args.K_strain_max, cls, 'K_strain_max', 0.03)}
dt_fs:             {_pick(args.dt_fs, cls, 'dt_fs', 1.0)}
gpu_ids:           "{args.gpu_ids}"
mpi_ranks:         {args.mpi_ranks}

--- Worker Guide (DEFORM) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def born_prompt(args, cls: dict, cross_track_rules: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps/mechanical"
    is_glassy = args.is_glassy.lower() not in ("false", "0", "no") if args.is_glassy else True
    dt_fs = _pick(args.dt_fs, cls, "dt_fs", 1.0)
    born_run_ns = args.born_run_ns if args.born_run_ns is not None else 4.0
    n_steps = int(born_run_ns * 1e6 / dt_fs)
    guide = load_worker_guide("born")
    return f"""\
equil_data_path:   {_v(args.data_path)}
lammps_flags:      {json.dumps(flags)}
polymer_class:     {args.polymer_class.upper()}
run_name:          {args.run_name}
work_dir:          {work_dir}
is_glassy:         {str(is_glassy).lower()}
born_run_ns:       {born_run_ns}
n_steps:           {n_steps}
dt_fs:             {dt_fs}
gpu_ids:           "{args.gpu_ids}"
mpi_ranks:         {args.mpi_ranks}

--- Worker Guide (BORN_MATRIX) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def analyze_tg_prompt(args, cls: dict, cross_track_rules: str) -> str:
    output_dir = args.output_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/raw/"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    lammps_base = f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps"
    tg_log = args.data_path or f"{lammps_base}/thermal/tg_sweep/tg_sweep.log"
    # equil_data_path: NPT 300 K production output — passed to extract_thermal as tg_data_file for ΔCp mass normalisation.
    # NOTE: this default is the GLASSY filename (npt_prod300). RUBBERY runs end at npt_production —
    # the orchestrator MUST pass --equil_data_path/--data_path explicitly for rubbery classes (PDIE/PHYC).
    equil_data = args.equil_data_path or f"{lammps_base}/equil/npt_prod300/npt_prod300_out.data"
    enthalpy_col = getattr(args, "enthalpy_col", None) or "Enthalpy"
    guide = load_worker_guide("analyze-tg")
    return f"""\
tg_log_path:       {tg_log}
tg_data_file:      {equil_data}    # LAMMPS .data input to the Tg sweep; required for ΔCp mass normalisation
enthalpy_col:      {enthalpy_col}  # LAMMPS thermo column for enthalpy (must match log output)
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
output_dir:        {output_dir}
graphs_dir:        {graphs_dir}
tasks:
  - extract_thermal  # tg_data_file required for ΔCp; enthalpy_col must match log thermo output

--- Worker Guide (THERMAL_ANALYSIS) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def equil_check_prompt(args, cls: dict, cross_track_rules: str) -> str:
    """Prompt for equilibration-checker (equil-check gate — equil check + density)."""
    output_dir = args.output_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/raw/"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    exp_density = _nondegenerate(*_exp_density_range(cls))
    ct_decay = cls.get("ct_min_decay_melt", 0.10)

    lammps_base = f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps"
    equil_log = f"{lammps_base}/equil/nvt_production/nvt_production.log"
    # GLASSY defaults (npt_prod300). RUBBERY runs end at npt_production — orchestrator
    # passes --npt_prod_log/--data_path explicitly for PDIE/PHYC (see CLAUDE.md equil-check gate).
    npt_log = args.npt_prod_log or f"{lammps_base}/equil/npt_prod300/npt_prod300.log"
    npt_dump = args.npt_prod_dump or f"{lammps_base}/equil/npt_prod300/npt_prod300.dump"
    npt_data = args.data_path or f"{lammps_base}/equil/npt_prod300/npt_prod300_out.data"

    guide = load_worker_guide("equil-check")
    return f"""\
equil_log_path:    {equil_log}
npt_prod_log_path: {npt_log}
npt_prod_dump_path: {npt_dump}
equil_data_path:   {npt_data}
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
backbone_types:    {args.backbone_types or '<FILL from parse_data_file or lammps_flags>'}
ct_min_decay_melt: {ct_decay}
exp_density_range: {exp_density}
output_dir:        {output_dir}
graphs_dir:        {graphs_dir}
tasks:
  - check_equilibration_comprehensive
  - extract_equilibrated_density

--- Worker Guide (EQUIL_CHECK) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def murnaghan_prompt(args, cls: dict, cross_track_rules: str) -> str:
    """Prompt for murnaghan-worker (rubbery BM pressure series submission)."""
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps/mechanical"
    # Murnaghan is the rubbery-only path: the orchestrator spawns born-worker (not
    # murnaghan) for glassy polymers, so is_glassy is always false here. Deriving it
    # from --is_glassy (which defaults "true") would emit is_glassy:true and trip the
    # worker's Rule B rubbery-abort on every run that forgets --is_glassy false.
    is_glassy = False
    bm_pressures_atm = cls.get("bm_pressures_atm", None)
    dt = _pick(args.dt_fs, cls, "dt_fs", 1.0)
    lammps_base = f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps"
    equil_data = args.data_path or f"{lammps_base}/equil/npt_production/npt_production_out.data"
    guide = load_worker_guide("murnaghan")
    return f"""\
equil_data_path:   {equil_data}
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

--- Worker Guide (MURNAGHAN) ---
{guide}
--- Cross-Track Rules ---
{cross_track_rules}
"""


def analyze_bm_prompt(args, cls: dict, cross_track_rules: str) -> str:
    """Prompt for bulk-modulus-extractor (BM extraction, all four routing paths)."""
    output_dir = args.output_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/raw/"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    lammps_base = f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps"
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

    born_log_line     = f"born_log_path:       {args.born_log}" if args.born_log else "born_log_path:       null"
    born_matrix_line  = f"born_matrix_file:    {args.born_matrix}" if args.born_matrix else "born_matrix_file:    null"
    born_n_atoms_line = f"born_n_atoms:        {args.born_n_atoms}" if args.born_n_atoms else "born_n_atoms:        null"
    deform_log_line   = f"deform_log_path:     {args.deform_log}" if getattr(args, 'deform_log', None) else "deform_log_path:     null"
    murnaghan_line    = f"murnaghan_log_files: {args.murnaghan_logs}" if getattr(args, 'murnaghan_logs', None) else "murnaghan_log_files: null"

    guide = load_worker_guide("analyze-bm")
    return f"""\
{born_log_line}
{born_matrix_line}
{born_n_atoms_line}
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
    """Prompt for run-summary-worker (always-terminal, calls generate_run_summary)."""
    output_dir = args.output_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/raw/"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    exp_tg = _nondegenerate(*_exp_tg_range(cls))
    exp_density = _nondegenerate(*_exp_density_range(cls))
    _k_from_cls = _exp_K_range(cls)
    exp_K = _nondegenerate(
        args.exp_K_min if args.exp_K_min is not None else _k_from_cls[0],
        args.exp_K_max if args.exp_K_max is not None else _k_from_cls[1],
    )
    return f"""\
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
smiles:            {_v(args.smiles)}
ff:                {args.ff or cls.get('preferred_ff', 'pcff')}
d05_verdict:       {getattr(args, 'd05', None) or '<FILL from equil-checker RESULT>'}
d06_tg_fit_quality: {_v(args.tg_fit_quality, 'N/A (not requested)')}
exp_tg_range:      {exp_tg}
exp_density_range: {exp_density}
exp_K_range:       {exp_K}
output_dir:        {output_dir}
graphs_dir:        {graphs_dir}
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
    "equil-check":  equil_check_prompt,
    "analyze-bm":   analyze_bm_prompt,
    "run-summary":  run_summary_prompt,
}


def main():
    p = argparse.ArgumentParser(
        description="Generate a fully-formed PolyJarvis worker prompt.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Workers: build | equil | tg | deform | born | murnaghan | analyze-tg | equil-check | analyze-bm | run-summary",
    )
    p.add_argument("--stage", required=True, choices=list(STAGE_MAP),
                   metavar="STAGE",
                   help="build|equil|tg|deform|born|murnaghan|analyze-tg|equil-check|analyze-bm|run-summary")
    p.add_argument("--run_name", required=True)
    p.add_argument("--polymer_class", required=True)
    p.add_argument("--plan",
                   help="Path to an approved run_plan.json. Overlays the plan's "
                        "decided_params onto the class defaults (scientific decisions); "
                        "runtime paths/gpu stay in the flags below. Deterministic plans "
                        "produce byte-identical output to the no-plan path.")
    p.add_argument("--smiles")
    p.add_argument("--data_path")
    p.add_argument("--work_dir")
    p.add_argument("--gpu_ids", required=False, default=None,
                   help='Comma-separated GPU IDs, e.g. "0" or "0,1". '
                        'If omitted, derived from polymer_rules.json hardware_policy by FF '
                        '("" for CPU engine). Claim a free GPU with scripts/pick_gpu.py.')
    p.add_argument("--mpi_ranks", type=int, required=False, default=None,
                   help="MPI processes per run. If omitted, derived from "
                        "hardware_policy by FF (never mpi=1 for PPPM classes).")
    p.add_argument("--dp", type=int)
    p.add_argument("--nchain", type=int)
    p.add_argument("--lammps_flags")
    p.add_argument("--is_glassy", default="true")
    p.add_argument("--tg_k", type=float)
    p.add_argument("--tg_fit_quality")
    p.add_argument("--born_log",
                   help="Path to nvt_born log (analyze-bm, glassy born path)")
    p.add_argument("--born_matrix",
                   help="Path to born_matrix.dat from fix ave/time (analyze-bm, glassy born path)")
    p.add_argument("--born_n_atoms", type=int,
                   help="Number of atoms in Born cell (analyze-bm, from born-worker RESULT)")
    p.add_argument("--deform_log",
                   help="Path to npt_deform log (analyze-bm, glassy deform fallback)")
    p.add_argument("--murnaghan_logs",
                   help="JSON list of absolute log paths from murnaghan-worker (analyze-bm, rubbery+pressures)")
    p.add_argument("--d05",
                   help="equil_verdict from equil-checker RESULT: PASS|EXTEND|FAIL (run-summary stage)")
    p.add_argument("--born_run_ns", type=float,
                   help="NVT-Born run length in ns (born stage, default 4.0)")
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
