#!/usr/bin/env python3
"""
gen_prompt.py — Generate fully-formed worker prompts for PolyJarvis orchestrator.

Usage:
  python3 scripts/gen_prompt.py --stage <STAGE> [options]

Stages: build | equil | tg | deform | born | analyze-tg | analyze-full

The script reads polymer_rules.json (for class defaults) and STAGE_INDEX.md
(for recovery thresholds and cross-stage rules) at runtime, so prompts always
reflect the current configuration without the orchestrator needing to read
either file directly.

Required for all stages:
  --run_name NAME
  --polymer_class CLASS   (e.g. PSTR, PACR, PHYC)

Optional overrides (defaults come from polymer_rules.json):
  --smiles SMILES
  --data_path PATH        input .data file (equil, tg, deform, analyze)
  --work_dir PATH         base directory for stage outputs
  --gpu_ids IDS           default: "0,1,2,3"
  --mpi_ranks N           default: 4
  --dp N                  degree of polymerisation override
  --nchain N              number of chains override
  --lammps_flags JSON     e.g. '{"use_pcff":true,"use_opls":false}'
  --is_glassy BOOL        true|false (deform + analyze-full)
  --tg_k FLOAT            Tg in K (analyze-full, from first analysis call)
  --tg_fit_quality STR    (analyze-full)
  --deform_log PATH       (analyze-full, glassy only)
  --npt_prod_log PATH     (analyze-full)
  --npt_prod_dump PATH    (analyze-full)
  --ff STR                force field string (analyze-full)
  --backbone_types JSON   atom type IDs as JSON list (analyze-full)
  --output_dir PATH       raw/ output directory

Physics knob overrides (all optional; defaults from polymer_rules.json):
  --npt_prod_ns FLOAT     Stage 7 NPT production time in ns (equil). Auto-sized by
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
                          Filters tasks: in analyze-full; orchestrator uses it for stage gating.
"""

import argparse
import json
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = REPO_ROOT / "guides" / "polymer_rules.json"
STAGE_INDEX_PATH = REPO_ROOT / "guides" / "STAGE_INDEX.md"

STAGE_GUIDES = {
    "build":        "STAGE_1_MOLECULAR_CONSTRUCTION.md",
    "equil":        "STAGE_2_EQUILIBRATION.md",
    "tg":           "STAGE_3_TG_MEASUREMENT.md",
    "analyze-tg":   "STAGE_4_ANALYSIS.md",
    "analyze-full": "STAGE_4_ANALYSIS.md",
    "deform":       "STAGE_5_PROPERTY_EXTRACTION.md",
    "born":         "STAGE_5_PROPERTY_EXTRACTION.md",
}


# ─── Loaders ──────────────────────────────────────────────────────────────────

def load_rules() -> dict:
    with open(RULES_PATH) as f:
        return json.load(f)


def load_stage_index() -> str:
    return STAGE_INDEX_PATH.read_text()


def load_stage_guide(stage: str) -> str:
    filename = STAGE_GUIDES.get(stage)
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


# ─── Helpers ──────────────────────────────────────────────────────────────────

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
    }


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
    exp = cls.get("experimental_density_gcm3")
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

def build_prompt(args, cls: dict, stage_index: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps"
    stage_guide = load_stage_guide("build")
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

--- Stage Guide (STAGE_1_MOLECULAR_CONSTRUCTION) ---
{stage_guide}
--- Stage Index (error recovery & cross-stage rules) ---
{stage_index}
"""


def equil_prompt(args, cls: dict, stage_index: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps/equil"
    stage_guide = load_stage_guide("equil")
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

--- Stage Guide (STAGE_2_EQUILIBRATION) ---
{stage_guide}
--- Stage Index (error recovery & cross-stage rules) ---
{stage_index}
"""


def tg_prompt(args, cls: dict, stage_index: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps/tg"
    stage_guide = load_stage_guide("tg")
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

--- Stage Guide (STAGE_3_TG_MEASUREMENT) ---
{stage_guide}
--- Stage Index (error recovery & cross-stage rules) ---
{stage_index}
"""


def deform_prompt(args, cls: dict, stage_index: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps/prop"
    is_glassy = args.is_glassy.lower() not in ("false", "0", "no") if args.is_glassy else True
    stage_guide = load_stage_guide("deform")
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

--- Stage Guide (STAGE_5_PROPERTY_EXTRACTION) ---
{stage_guide}
--- Stage Index (error recovery & cross-stage rules) ---
{stage_index}
"""


def born_prompt(args, cls: dict, stage_index: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    work_dir = args.work_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps/prop"
    is_glassy = args.is_glassy.lower() not in ("false", "0", "no") if args.is_glassy else True
    dt_fs = _pick(args.dt_fs, cls, "dt_fs", 1.0)
    born_run_ns = args.born_run_ns if args.born_run_ns is not None else 4.0
    n_steps = int(born_run_ns * 1e6 / dt_fs)
    stage_guide = load_stage_guide("born")
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

--- Stage Guide (STAGE_5_PROPERTY_EXTRACTION) ---
{stage_guide}
--- Stage Index (error recovery & cross-stage rules) ---
{stage_index}
"""


def analyze_tg_prompt(args, cls: dict, stage_index: str) -> str:
    output_dir = args.output_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/raw/"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    lammps_base = f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps"
    tg_log = args.data_path or f"{lammps_base}/tg/tg_sweep/tg_sweep.log"
    tg_sweep_dir = f"{lammps_base}/tg/tg_sweep"
    per_t_dump = f"{tg_sweep_dir}/per_t_structs.dump"
    # equil_data_path is the .data file fed into the Tg sweep (Stage 7 NPT output)
    equil_data = args.equil_data_path or f"{lammps_base}/equil/09_npt_prod300/09_npt_prod300_out.data"
    backbone_types_line = (f"backbone_types:    {args.backbone_types}"
                           if args.backbone_types else
                           "backbone_types:    <FILL from parse_data_file or lammps_flags>")
    stage_guide = load_stage_guide("analyze-tg")
    return f"""\
tg_log_path:       {tg_log}
per_t_dump_file:   {per_t_dump}    # present if WRITE_PER_T_DUMP=True was used in tg sweep
tg_data_file:      {equil_data}    # LAMMPS .data input to the Tg sweep (for MDAnalysis topology)
{backbone_types_line}
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
output_dir:        {output_dir}
graphs_dir:        {graphs_dir}
tasks:
  - extract_tg     # pass per_t_dump_file + tg_data_file + backbone_types to enable structural analysis

--- Stage Guide (STAGE_4_ANALYSIS) ---
{stage_guide}
--- Stage Index (error recovery & cross-stage rules) ---
{stage_index}
"""


def analyze_full_prompt(args, cls: dict, stage_index: str) -> str:
    flags = _lammps_flags(args.lammps_flags, cls)
    output_dir = args.output_dir or f"/home/arz2/PolyJarvis/data/{args.run_name}/raw/"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    is_glassy = args.is_glassy.lower() not in ("false", "0", "no") if args.is_glassy else True
    exp_tg = _exp_tg_range(cls)
    exp_density = _exp_density_range(cls)
    _k_from_cls = _exp_K_range(cls)
    exp_K = [
        args.exp_K_min if args.exp_K_min is not None else _k_from_cls[0],
        args.exp_K_max if args.exp_K_max is not None else _k_from_cls[1],
    ]
    bm_pressures_atm = cls.get("bm_pressures_atm", None)
    bm_task = "extract_bulk_modulus_born" if is_glassy else (
        "run_bulk_modulus_series+extract_bulk_modulus_murnaghan"
        if bm_pressures_atm else "extract_bulk_modulus"
    )
    ct_decay = cls.get("ct_min_decay_melt", 0.10)

    lammps_base = f"/home/arz2/PolyJarvis/data/{args.run_name}/lammps"
    equil_log = f"{lammps_base}/equil/06_nvt_production/06_nvt_production.log"
    npt_log = args.npt_prod_log or f"{lammps_base}/equil/09_npt_prod300/09_npt_prod300.log"
    npt_dump = args.npt_prod_dump or f"{lammps_base}/equil/09_npt_prod300/09_npt_prod300.dump"
    npt_data = args.data_path or f"{lammps_base}/equil/09_npt_prod300/09_npt_prod300_out.data"
    born_log_line    = f"born_log_path:     {args.born_log}" if args.born_log else "born_log_path:     null"
    born_matrix_line = f"born_matrix_file:  {args.born_matrix}" if args.born_matrix else "born_matrix_file:  null"
    born_n_atoms_line = f"born_n_atoms:      {args.born_n_atoms}" if args.born_n_atoms else "born_n_atoms:      null"

    props_str = args.properties if args.properties else "all"
    if props_str.strip().lower() == "all":
        props = {"density", "tg", "bulk_modulus"}
    else:
        props = {p.strip().lower() for p in props_str.split(",")}

    task_lines = ["  - check_equilibration_comprehensive"]
    if "density" in props:
        task_lines.append("  - extract_density")
    if "bulk_modulus" in props:
        task_lines.append(f"  - {bm_task}")
    task_lines.append("  - generate_run_summary")
    tasks_block = "\n".join(task_lines)

    stage_guide = load_stage_guide("analyze-full")
    return f"""\
equil_log_path:    {equil_log}
npt_prod_log_path: {npt_log}
{born_log_line}
{born_matrix_line}
{born_n_atoms_line}
equil_data_path:   {npt_data}
npt_prod_dump_path: {npt_dump}
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
smiles:            {_v(args.smiles)}
ff:                {args.ff or cls.get('preferred_ff', 'pcff')}
d06_tg_fit_quality: {_v(args.tg_fit_quality, 'ACCEPTABLE')}
exp_tg_range:      {exp_tg}
exp_density_range: {exp_density}
exp_K_range:       {exp_K}
bm_pressures_atm:  {bm_pressures_atm}
output_dir:        {output_dir}
graphs_dir:        {graphs_dir}
is_glassy:         {str(is_glassy).lower()}
dt_fs:             {_pick(args.dt_fs, cls, 'dt_fs', 1.0)}
backbone_types:    {args.backbone_types or '<FILL from parse_data_file>'}
ct_min_decay_melt: {ct_decay}
tasks:
{tasks_block}

--- Stage Guide (STAGE_4_ANALYSIS) ---
{stage_guide}
--- Stage Index (error recovery & cross-stage rules) ---
{stage_index}
"""


# ─── CLI ──────────────────────────────────────────────────────────────────────

STAGE_MAP = {
    "build": build_prompt,
    "equil": equil_prompt,
    "tg": tg_prompt,
    "deform": deform_prompt,
    "born": born_prompt,
    "analyze-tg": analyze_tg_prompt,
    "analyze-full": analyze_full_prompt,
}


def main():
    p = argparse.ArgumentParser(
        description="Generate a fully-formed PolyJarvis worker prompt.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Stages: build | equil | tg | deform | born | analyze-tg | analyze-full",
    )
    p.add_argument("--stage", required=True, choices=list(STAGE_MAP),
                   metavar="STAGE",
                   help="build|equil|tg|deform|born|analyze-tg|analyze-full")
    p.add_argument("--run_name", required=True)
    p.add_argument("--polymer_class", required=True)
    p.add_argument("--smiles")
    p.add_argument("--data_path")
    p.add_argument("--work_dir")
    p.add_argument("--gpu_ids", default="0,1,2,3")
    p.add_argument("--mpi_ranks", type=int, default=4)
    p.add_argument("--dp", type=int)
    p.add_argument("--nchain", type=int)
    p.add_argument("--lammps_flags")
    p.add_argument("--is_glassy", default="true")
    p.add_argument("--tg_k", type=float)
    p.add_argument("--tg_fit_quality")
    p.add_argument("--born_log",
                   help="Path to nvt_born log (analyze-full, glassy)")
    p.add_argument("--born_matrix",
                   help="Path to born_matrix.dat from fix ave/time (analyze-full, glassy)")
    p.add_argument("--born_n_atoms", type=int,
                   help="Number of atoms in Born cell (from born-worker RESULT)")
    p.add_argument("--born_run_ns", type=float,
                   help="NVT-Born run length in ns (born stage, default 4.0)")
    p.add_argument("--npt_prod_log")
    p.add_argument("--npt_prod_dump")
    p.add_argument("--ff")
    p.add_argument("--backbone_types")
    p.add_argument("--output_dir")
    p.add_argument("--equil_data_path",
                   help="Path to equilibrated .data file (input to Tg sweep, used as topology for structural analysis)")
    # Physics knob overrides (all optional; default None → falls back to polymer_rules.json)
    p.add_argument("--npt_prod_ns", type=float,
                   help="Stage 7 NPT production time (ns); auto-sized by atom count if omitted")
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
    stage_index = load_stage_index()
    cls = get_class_entry(rules, args.polymer_class)

    prompt_fn = STAGE_MAP[args.stage]
    print(prompt_fn(args, cls, stage_index))


if __name__ == "__main__":
    main()
