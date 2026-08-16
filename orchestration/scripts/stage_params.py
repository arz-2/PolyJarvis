"""Deterministic protocol parameter resolution.

This module is executable policy: it converts a run plan and polymer-class rules into
concrete tool arguments. It contains no agent prompts or simulation execution.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from hw_common import load_rules, resolve_ff_family, get_class_entry, host_matches, live_host
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_PATH = REPO_ROOT / 'guides' / 'polymer_rules.json'

def load_plan(plan_path: str) -> dict:
    with open(plan_path) as f:
        return json.load(f)

def apply_plan(cls: dict, plan: dict, args) -> dict:
    """Overlay an approved run_plan.json's decided_params onto the class entry.

    The plan carries the scientific agent's decisions (FF, system size, T-schedule,
    property knobs); runtime wiring (paths, gpu_ids, mpi_ranks) stays in CLI args. For a
    class-default scaffold, decided_params is a subset of cls with identical values. For a
    reasoned plan, decided_params may differ and those values take effect here.

    Also backfills --smiles and --properties from the plan when not given on the CLI, so
    the plan artifact is a self-contained source of truth.
    """
    effective = {**cls, **plan.get('decided_params', {})}
    if args.smiles is None and plan.get('smiles'):
        args.smiles = plan['smiles']
    if (args.properties is None or args.properties == 'all') and plan.get('properties'):
        args.properties = ','.join(plan['properties'])
    _apply_plan_hardware(args, plan.get('decided_params', {}))
    return effective

def _apply_plan_hardware(args, dp: dict) -> None:
    """Honor a reasoned plan's D-08_hardware override (engine / gpu_per_run / mpi_ranks in
    decided_params) when the CLI omitted the value. Precedence: CLI > plan > policy — the CLI
    stays authoritative, and resolve_hardware() fills anything still unset from hardware_policy.
    Deterministic plans never carry these keys (make_deterministic_plan.SNAPSHOT_KEYS excludes
    them), so the no-plan path stays byte-identical (tests/test_plan_reproducibility.py)."""
    if args.mpi_ranks is None and dp.get('mpi_ranks') is not None:
        args.mpi_ranks = dp['mpi_ranks']
    if getattr(args, 'engine', None) is None and dp.get('engine') is not None:
        args.engine = dp['engine']
    if args.gpu_ids is None and ('engine' in dp or 'gpu_per_run' in dp):
        (engine, gpu_n) = (dp.get('engine'), dp.get('gpu_per_run'))
        if engine == 'cpu' or gpu_n == 0:
            args.gpu_ids = ''
        elif gpu_n:
            args.gpu_ids = ','.join((str(i) for i in range(int(gpu_n))))
    if getattr(args, 'emc_seed', None) is None and dp.get('emc_seed') is not None:
        args.emc_seed = dp['emc_seed']
    if getattr(args, 'velocity_seed', None) is None and dp.get('velocity_seed') is not None:
        args.velocity_seed = dp['velocity_seed']

def resolve_hardware(args, cls: dict, rules: dict) -> None:
    """Fill mpi_ranks / gpu_ids from the FF×size hardware_policy when the CLI omits
    them, so a run can never default to the mpi=1 anti-pattern. Explicit CLI values
    always win (keeps deterministic-plan output byte-identical — runtime wiring stays
    CLI-authoritative per apply_plan's contract). Specific gpu_ids remain runtime;
    use orchestration/pick_gpu.py to claim a non-colliding GPU at submit time."""
    hp = rules.get('hardware_policy')
    if not hp:
        return
    if not hp.get('values_are_benchmarked') or not host_matches(rules):
        saved = hp.get('host') or {}
        saved_desc = f"{saved.get('gpus', '?')}x {saved.get('gpu_model', '?')} / {saved.get('phys_cores', '?')} cores" if saved else '(never calibrated)'
        live = live_host()
        live_desc = f"{live['gpus']}x {live['gpu_model']} / {live['phys_cores']} cores"
        print(f"INFO: hardware_policy was benchmarked on {saved_desc}; you are on {live_desc} (values_are_benchmarked={hp.get('values_are_benchmarked', False)}). Run /calibrate-hardware once to host-match the per-FF engine defaults.", file=sys.stderr)
    ff_raw = cls.get('preferred_ff') or cls.get('forcefield') or ''
    fam = resolve_ff_family(ff_raw, hp)
    pol = hp.get('by_forcefield', {}).get(fam, {})
    if getattr(args, 'engine', None) is None:
        args.engine = pol.get('engine')
    if args.engine != 'kokkos':
        args.engine = 'gpu'
    if args.mpi_ranks is None:
        args.mpi_ranks = pol.get('mpi', 8)
        print(f"INFO: mpi_ranks not given — derived {args.mpi_ranks} from hardware_policy[{fam}] (engine={pol.get('engine')})", file=sys.stderr)
    if args.gpu_ids is None:
        if pol.get('engine') == 'cpu':
            args.gpu_ids = ''
        else:
            n = max(1, int(pol.get('gpu_per_run', 1) or 1))
            args.gpu_ids = ','.join((str(i) for i in range(n)))
        print(f'INFO: gpu_ids not given — derived "{args.gpu_ids}" from hardware_policy[{fam}]; claim free GPU(s) with orchestration/pick_gpu.py', file=sys.stderr)

def _pick(arg_val, cls: dict, key: str, default):
    """CLI flag takes precedence over polymer_rules.json; rules over hard default."""
    return arg_val if arg_val is not None else cls.get(key, default)

def _lammps_flags(flags_json: str | None, cls: dict) -> dict:
    if flags_json:
        return json.loads(flags_json)
    ff = cls.get('preferred_ff', '').lower()
    class_ii = 'pcff' in ff or ff in ('compass', 'pcff_ore')
    return {'use_pcff': class_ii, 'use_opls': 'opls' in ff, 'use_trappe': 'trappe' in ff}

def _exp_tg_range(cls: dict, run_name: str | None=None) -> list:
    tg = cls.get('experimental_tg_K')
    if isinstance(tg, dict):
        if run_name:
            for (key, val) in tg.items():
                if isinstance(val, (int, float)) and run_name.upper().startswith(key.upper()):
                    return [round(val - 20), round(val + 20)]
        vals = sorted((v for v in tg.values() if isinstance(v, (int, float))))
        if vals:
            mid = vals[len(vals) // 2]
            return [round(mid - 20), round(mid + 20)]
    if isinstance(tg, (int, float)):
        return [round(tg - 20), round(tg + 20)]
    return ['<exp_tg_min>', '<exp_tg_max>']

def _exp_tg_point(cls: dict, run_name: str | None=None):
    """Point exp_tg_K value (not a ±20 band) for assess_cooling_contraction's tg_K arg.
    Mirrors _exp_tg_range's member-resolution logic (fixes the class-mean-averaging bug
    for multi-member classes)."""
    tg = cls.get('experimental_tg_K')
    if isinstance(tg, dict):
        if run_name:
            for (key, val) in tg.items():
                if isinstance(val, (int, float)) and run_name.upper().startswith(key.upper()):
                    return val
        vals = sorted((v for v in tg.values() if isinstance(v, (int, float))))
        return vals[len(vals) // 2] if vals else None
    if isinstance(tg, (int, float)):
        return tg
    return None

def _exp_density_point(cls: dict, run_name: str | None=None):
    """Point exp_density_gcm3 value (not a ±5% band) for assess_cooling_contraction."""
    exp = cls.get('experimental_density_gcm3')
    if isinstance(exp, dict):
        if run_name:
            for (key, val) in exp.items():
                if isinstance(val, (int, float)) and run_name.upper().startswith(key.upper()):
                    return val
        vals = sorted((v for v in exp.values() if isinstance(v, (int, float))))
        return vals[len(vals) // 2] if vals else None
    if isinstance(exp, (int, float)):
        return exp
    return None

def _exp_K_range(cls: dict) -> list:
    exp = cls.get('exp_K_GPa')
    if isinstance(exp, dict) and 'min' in exp and ('max' in exp):
        return [exp['min'], exp['max']]
    return [None, None]

def _db_exp_lookup(cls_id: str, polymer_name: str | None=None) -> dict:
    """Query polymer_db.sqlite for polymer-specific experimental values.

    Priority in callers:
      --exp_tg_K (CLI)  >  this function (DB)  >  polymer_rules.json median
    Returns dict with tg_median_K, density_gcm3, K_range_GPa (any may be None).
    Never raises — a broken or missing DB just returns all-None.
    """
    try:
        import sys as _sys
        _repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if _repo_root not in _sys.path:
            _sys.path.insert(0, _repo_root)
        from db.query_best_match import _connect, find_polymer_ids, get_tg_data, get_density_data, get_bulk_modulus_data
        conn = _connect()
        (ids, _method, _conf) = find_polymer_ids(conn, polymer_name, cls_id)
        if not ids:
            return {'tg_median_K': None, 'density_gcm3': None, 'K_range_GPa': None}
        tg = get_tg_data(conn, ids)
        dens = get_density_data(conn, ids, 300.0)
        bm = get_bulk_modulus_data(conn, ids, is_glassy=True)
        return {'tg_median_K': tg['agg_median_K'] if tg else None, 'density_gcm3': dens.get('value_gcm3') if dens else None, 'K_range_GPa': bm['agg_range_GPa'] if bm else None}
    except Exception:
        return {'tg_median_K': None, 'density_gcm3': None, 'K_range_GPa': None}

def _exp_density_range(cls: dict) -> list:
    exp = cls.get('experimental_density_gcm3')
    if isinstance(exp, dict):
        vals = sorted((v for v in exp.values() if isinstance(v, (int, float))))
        if vals:
            mid = vals[len(vals) // 2]
            return [round(mid * 0.95, 3), round(mid * 1.05, 3)]
    if isinstance(exp, (int, float)):
        return [round(exp * 0.95, 3), round(exp * 1.05, 3)]
    d0 = cls.get('density_initial_gcm3', 0.6)
    implied_rt = d0 / 0.55
    return [round(implied_rt * 0.85, 3), round(implied_rt * 1.15, 3)]

def _resolve_build_params(args, cls: dict) -> dict:
    """Resolve deterministic molecule-builder arguments."""
    return {'smiles': args.smiles, 'work_dir': args.work_dir or f'{REPO_ROOT}/data/{args.run_name}/lammps', 'preferred_builder': cls.get('preferred_builder', 'emc'), 'preferred_ff': cls.get('preferred_ff', 'gaff2_mod'), 'dp': args.dp or cls.get('dp_typical', 50), 'nchain': args.nchain or cls.get('nchain', 10), 'density_initial_gcm3': _pick(args.density_initial, cls, 'density_initial_gcm3', 0.6), 'build_temperature_K': cls.get('build_temperature_K', 300.0), 'emc_seed': args.emc_seed if getattr(args, 'emc_seed', None) is not None else None, 'charge_method': cls.get('charge_method', 'am1bcc').lower(), 'electrostatics': cls.get('electrostatics', 'pppm'), 'cutoff_A': cls.get('cutoff_A', 12.0), 'dt_fs': cls.get('dt_fs', 1.0), 'phal_patch': args.polymer_class.upper() == 'PHAL', 'lammps_flags': _lammps_flags(args.lammps_flags, cls), 'ff_confidence': 'cited' if cls.get('ff_justification_doi') else 'uncited'}

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
                for (k, v) in _tg_dict.items():
                    if isinstance(v, (int, float)) and _run.upper().startswith(k.upper()):
                        exp_tg = v
                        break
            if exp_tg is None:
                _vals = sorted((v for v in _tg_dict.values() if isinstance(v, (int, float))))
                exp_tg = _vals[len(_vals) // 2] if _vals else None
        else:
            exp_tg = _tg_dict
    if 'T_workflow_K' in cls:
        return cls['T_workflow_K']
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
    return 'rubbery' if _resolve_t_workflow(args, cls) <= 300.0 else 'glassy'

def _is_glassy(args, cls: dict) -> bool:
    """Whether the BM stages treat this cell as glassy. The orchestrator's `--is_glassy`, set from
    the thermal track's measured Tg, wins; with the flag absent the regime oracle decides. An
    argparse default cannot: it applies to every class alike, so a rubbery run silently reads as
    glassy and takes the Murnaghan/deform glassy branch."""
    flag = getattr(args, 'is_glassy', None)
    if flag is not None:
        return str(flag).lower() not in ('false', '0', 'no')
    return _regime(args, cls) == 'glassy'

def _velocity_seed(args) -> int:
    """The equilibration chain's `velocity all create` seed. generate_equilibration_workflow
    rejects a null seed, so resolve one here: the plan's pinned value if it has one, else a
    value derived from run_name — stable across retries, distinct per replicate."""
    pinned = getattr(args, 'velocity_seed', None)
    if pinned is not None:
        return int(pinned)
    digest = hashlib.sha256(args.run_name.encode()).hexdigest()
    return 10000 + int(digest, 16) % 989999

def _resolve_equil_params(args, cls: dict) -> dict:
    """Resolve deterministic equilibration-chain arguments."""
    dt = _pick(args.dt_fs, cls, 'dt_fs', 1.0)
    T_equil = _pick(args.T_equil_K, cls, 'T_equil_K', 600.0)
    npt_prod_ns_val = _pick(args.npt_prod_ns, cls, 'npt_prod_ns', None)
    npt_prod_steps = int(npt_prod_ns_val * 1000000.0 / dt) if npt_prod_ns_val is not None else None
    t_equil_ns = cls.get('t_equil_ns', 5.0)
    nvt_prod_steps = int(t_equil_ns * 1000000.0 / dt)
    npt_prod300_ns = cls.get('npt_prod300_ns', 2.0)
    npt_prod300_steps = int(npt_prod300_ns * 1000000.0 / dt)
    anneal_cycle_ns = cls.get('anneal_cycle_ns')
    anneal_cycle_steps = (int(anneal_cycle_ns * 1000000.0 / dt)
                          if anneal_cycle_ns is not None else None)
    T_workflow = _resolve_t_workflow(args, cls)
    add_melt_npt = (getattr(args, 'add_melt_npt', False) or
                    bool(cls.get('add_melt_npt', False)) or T_workflow <= 300.0)
    remedy_melt_ns = (getattr(args, 'melt_hold_ns', None) or cls.get('melt_hold_ns') or
                      getattr(args, 'melt_only_continuation_ns', None) or
                      cls.get('melt_only_continuation_ns'))
    melt_npt_ns_val = (remedy_melt_ns if remedy_melt_ns is not None else
                       (_pick(None, cls, 'melt_npt_ns', None) if add_melt_npt else None))
    melt_npt_steps = int(melt_npt_ns_val * 1000000.0 / dt) if add_melt_npt and melt_npt_ns_val is not None else None
    phase = getattr(args, 'phase', 'full') or 'full'
    if T_workflow <= 300.0:
        phase = 'full'
    return {
        'data_path': args.data_path,
        'phase': phase,
        'pending_cooldown_path': getattr(args, 'pending_cooldown_path', None),
        'lammps_flags': _lammps_flags(args.lammps_flags, cls),
        'use_long_range_electrostatics': cls.get('electrostatics', 'pppm') == 'pppm',
        'work_dir': args.work_dir or f'{REPO_ROOT}/data/{args.run_name}/lammps/equil',
        'dt_fs': dt,
        'T_equil_K': T_equil,
        'T_anneal_high_K': _pick(args.T_anneal_high_K, cls, 'annealing_T_high_K', 700.0),
        'T_workflow_K': T_workflow,
        'P_equil_atm': cls.get('P_equil_atm', 1.0),
        'compression_max_pressure_atm': cls.get('compression_max_pressure_atm', 50000.0),
        't_equil_ns': t_equil_ns,
        'nvt_prod_steps': nvt_prod_steps,
        'npt_prod300_ns': npt_prod300_ns,
        'npt_prod300_steps': npt_prod300_steps,
        'eq_annealing_cycles': int(cls.get('eq_annealing_cycles', 0)),
        'anneal_cycle_ns': anneal_cycle_ns,
        'anneal_cycle_steps': anneal_cycle_steps,
        'thermostat_damp_fs': cls.get('thermostat_damp_fs', 100.0),
        'barostat_damp_fs': cls.get('barostat_damp_fs', 1000.0),
        'npt_cool_steps': _pick(getattr(args, 'npt_cool_steps', None), cls,
                                'npt_cool_steps', None),
        'npt_cool300_steps': _pick(getattr(args, 'npt_cool300_steps', None), cls,
                                   'npt_cool300_steps', None),
        'npt_prod_ns': npt_prod_ns_val,
        'npt_prod_steps': npt_prod_steps,
        'add_melt_npt': add_melt_npt,
        'add_300k_production': bool(cls.get('add_300k_production', True)),
        'melt_npt_ns': melt_npt_ns_val,
        'melt_npt_steps': melt_npt_steps,
        'gpu_ids': args.gpu_ids,
        'mpi_ranks': args.mpi_ranks,
        'engine': args.engine,
        'velocity_seed': _velocity_seed(args),
        'cutoff_A': cls.get('cutoff_A', 12.0),
        'nchain': args.nchain or cls.get('nchain', 10),
        'exp_density_gcm3': _exp_density_point(cls, args.run_name),
    }

def _resolve_tg_rate(args, cls: dict):
    """Resolve the selected cooling rate + a per-rate output-dir suffix for multi-rate
    Tg sweeps. Returns (selected_rate | None, rate_suffix). When --tg_rate_index is unset,
    suffix is "" so the single-rate path stays byte-identical to the legacy pipeline."""
    tg_rates = cls.get('tg_rates_K_per_ns', [])
    rate_idx = getattr(args, 'tg_rate_index', None)
    if rate_idx is not None and tg_rates and (rate_idx < len(tg_rates)):
        selected_rate = tg_rates[rate_idx]
        return (selected_rate, f'_r{int(selected_rate)}')
    return (None, '')

def _resolve_tg_params(args, cls: dict) -> dict:
    """Resolve deterministic single-rate Tg sweep arguments."""
    dt = _pick(args.dt_fs, cls, 'dt_fs', 1.0)
    tg_rates = cls.get('tg_rates_K_per_ns', [])
    rate_idx = getattr(args, 'tg_rate_index', None)
    (selected_rate, rate_suffix) = _resolve_tg_rate(args, cls)
    t_step = _pick(args.tg_t_step_K, cls, 'tg_t_step_K', 20)
    floor = cls.get('tg_min_steps_per_T', 200000)
    if selected_rate is not None:
        n_steps_per_t = int(t_step / (selected_rate * dt * 1e-06))
    else:
        n_steps_per_t = _pick(args.tg_steps_per_t, cls, 'tg_steps_per_t', 500000)
    work_dir = args.work_dir or f'{REPO_ROOT}/data/{args.run_name}/lammps/thermal'
    return {'lammps_flags': _lammps_flags(args.lammps_flags, cls), 'use_long_range_electrostatics': cls.get('electrostatics', 'pppm') == 'pppm', 'work_dir': work_dir, 'dt_fs': dt, 'tg_rates_K_per_ns': tg_rates, 'tg_rate_index': rate_idx, 'selected_rate_K_per_ns': selected_rate, 'tg_sweep_dir': f'{work_dir}/tg_sweep{rate_suffix}', 'T_start_K': _pick(args.tg_t_high_K, cls, 'tg_t_high_K', 600), 'T_end_K': _pick(args.tg_t_low_K, cls, 'tg_t_low_K', 200), 'T_step_K': t_step, 'n_steps_per_t': n_steps_per_t, 'tg_min_steps_per_T': floor, 'below_steps_floor': selected_rate is not None and n_steps_per_t < floor, 'pressure_atm': cls.get('P_equil_atm', 1.0), 'thermostat_damp_fs': cls.get('thermostat_damp_fs', 100.0), 'barostat_damp_fs': cls.get('barostat_damp_fs', 1000.0), 'equil_data_path': getattr(args, 'tg_start_data', None) or args.data_path, 'gpu_ids': args.gpu_ids, 'mpi_ranks': args.mpi_ranks, 'engine': args.engine, 'velocity_seed': _velocity_seed(args)}

def _resolve_deform_params(args, cls: dict) -> dict:
    """Resolve deterministic deformation arguments."""
    return {'deform_rate_mode': args.deform_rate_mode, 'equil_data_path': args.data_path, 'lammps_flags': _lammps_flags(args.lammps_flags, cls), 'work_dir': args.work_dir or f'{REPO_ROOT}/data/{args.run_name}/lammps/mechanical', 'is_glassy': _is_glassy(args, cls), 'K_deform_rate_inv_s': _pick(args.K_deform_rate_inv_s, cls, 'K_deform_rate_inv_s', 100000000.0), 'K_deform_rate_slow_inv_s': cls.get('K_deform_rate_slow_inv_s', 'null'), 'K_strain_max': _pick(args.K_strain_max, cls, 'K_strain_max', 0.03), 'deform_eq_steps': int(cls.get('deform_eq_steps', 200000)), 'deform_strain_start': cls.get('deform_strain_start', 0.002), 'deform_avg_window': int(cls.get('deform_avg_window', 2000)), 'thermostat_damp_fs': cls.get('thermostat_damp_fs', 100.0), 'dt_fs': _pick(args.dt_fs, cls, 'dt_fs', 1.0), 'gpu_ids': args.gpu_ids, 'mpi_ranks': args.mpi_ranks, 'engine': args.engine, 'velocity_seed': _velocity_seed(args)}

def _resolve_analyze_tg_params(args, cls: dict) -> dict:
    """Resolve deterministic per-rate Tg analysis arguments."""
    (selected_rate, rate_suffix) = _resolve_tg_rate(args, cls)
    raw_suffix = f'tg_r{int(selected_rate)}/' if selected_rate is not None else ''
    output_dir = args.output_dir or f'{REPO_ROOT}/data/{args.run_name}/raw/{raw_suffix}'
    graphs_dir = output_dir.replace('/raw/', '/graphs/').replace('/raw', '/graphs')
    lammps_base = f'{REPO_ROOT}/data/{args.run_name}/lammps'
    tg_log = args.data_path or f'{lammps_base}/thermal/tg_sweep{rate_suffix}/tg_sweep.log'
    if _regime(args, cls) == 'rubbery':
        default_equil_data = f'{lammps_base}/equil/npt_production/npt_production_out.data'
    else:
        default_equil_data = f'{lammps_base}/equil/npt_prod300/npt_prod300_out.data'
    equil_data = args.equil_data_path or default_equil_data
    per_t_dump = f'{lammps_base}/thermal/tg_sweep{rate_suffix}/per_t_structs.dump'
    return {'selected_rate_K_per_ns': selected_rate, 'tg_rate_index': args.tg_rate_index, 'tg_log_path': tg_log, 'tg_data_file': equil_data, 'per_t_dump_file': per_t_dump, 'enthalpy_col': getattr(args, 'enthalpy_col', None) or 'Enthalpy', 'backbone_types': args.backbone_types or cls.get('backbone_types'), 'output_dir': output_dir, 'graphs_dir': graphs_dir, 'method_gap_exempt': bool(cls.get('tg_slope_gate_fallback') == 'slowest_rate')}

def _resolve_analyze_tg_multirate_params(args, cls: dict) -> dict:
    """Resolve deterministic multirate Tg aggregation arguments."""
    output_dir = args.output_dir or f'{REPO_ROOT}/data/{args.run_name}/raw/'
    script = str(REPO_ROOT / 'mcp-servers/mcp-lammps-engine' / 'analysis_scripts/extract_tg_multirate.py')
    return {'output_dir': output_dir, 'script': script, 'dsc_equiv_rate_K_per_ns': cls.get('dsc_equiv_rate_K_per_ns', 1.6667e-10), 'mr_rates': (args.mr_rates or '').replace(',', ' ').strip(), 'mr_tg_values': (args.mr_tg_values or '').replace(',', ' ').strip(), 'polymer_name': args.run_name, 'regime': _regime(args, cls)}

def _resolve_equil_check_params(args, cls: dict) -> dict:
    """Resolve deterministic equilibration validation arguments."""
    output_dir = args.output_dir or f'{REPO_ROOT}/data/{args.run_name}/raw/'
    graphs_dir = output_dir.replace('/raw/', '/graphs/').replace('/raw', '/graphs')
    ct_decay = cls.get('ct_min_decay_melt', 0.1) if cls.get('ct_gate_reliable', True) else None
    lammps_base = f'{REPO_ROOT}/data/{args.run_name}/lammps'
    T_workflow = _resolve_t_workflow(args, cls)
    phase = getattr(args, 'phase', 'full') or 'full'
    if T_workflow <= 300:
        phase = 'full'
    if phase == 'melt' or T_workflow <= 300:
        (prod, npt_prod_temp) = ('npt_production', T_workflow)
    else:
        (prod, npt_prod_temp) = ('npt_prod300', 300.0)
    return {'output_dir': output_dir, 'phase': phase, 'graphs_dir': graphs_dir, 'exp_density_range': _exp_density_range(cls), 'ct_min_decay_melt': ct_decay, 'cutoff_A': cls.get('cutoff_A'), 'npt_prod_log_path': args.npt_prod_log or f'{lammps_base}/equil/{prod}/{prod}.log', 'npt_prod_data_path': args.data_path or f'{lammps_base}/equil/{prod}/{prod}_out.data', 'melt_dump_path': args.npt_prod_dump or f'{lammps_base}/equil/nvt_production/nvt_production.dump', 'melt_data_path': f'{lammps_base}/equil/npt_production/npt_production_out.data', 'npt_prod_temp_K': npt_prod_temp, 'T_workflow_K': T_workflow, 'exp_tg_point_K': _exp_tg_point(cls, args.run_name), 'exp_density_point_gcm3': _exp_density_point(cls, args.run_name), 'is_glassy': T_workflow > 300, 'regime': _regime(args, cls), 'dp': getattr(args, 'dp', None) or cls.get('dp_typical'), 'ct_gate_reliable': cls.get('ct_gate_reliable', True), 'alpha_glass_per_K': cls.get('alpha_glass_per_K', 'null'), 'alpha_melt_per_K': cls.get('alpha_melt_per_K', 'null'), 'backbone_types': args.backbone_types or cls.get('backbone_types'), 'dt_fs': _pick(args.dt_fs, cls, 'dt_fs', 1.0)}

def _resolve_murnaghan_params(args, cls: dict) -> dict:
    """Resolve deterministic Murnaghan bulk-modulus arguments."""
    lammps_base = f'{REPO_ROOT}/data/{args.run_name}/lammps'
    sampling_factor = int(cls.get('mechanical_sampling_factor', 1))
    return {'lammps_flags': _lammps_flags(args.lammps_flags, cls), 'work_dir': args.work_dir or f'{REPO_ROOT}/data/{args.run_name}/lammps/mechanical', 'is_glassy': _is_glassy(args, cls), 'bm_pressures_atm': cls.get('mechanical_resample_points') or cls.get('bm_pressures_atm', None), 'dt_fs': _pick(args.dt_fs, cls, 'dt_fs', 1.0), 'equil_data_path': args.data_path or f'{lammps_base}/equil/npt_production/npt_production_out.data', 'temp_K': cls.get('bm_temperature_K', 300.0), 'npt_steps': int(cls.get('bm_npt_steps', 500000)) * sampling_factor, 'thermo_freq': int(cls.get('bm_thermo_freq', 100)), 'thermostat_damp_fs': cls.get('thermostat_damp_fs', 100.0), 'barostat_damp_fs': cls.get('barostat_damp_fs', 1000.0), 'mechanical_sampling_factor': sampling_factor, 'gpu_ids': args.gpu_ids, 'mpi_ranks': args.mpi_ranks, 'engine': args.engine, 'velocity_seed': _velocity_seed(args)}

def _resolve_analyze_bm_params(args, cls: dict) -> dict:
    """Resolve deterministic bulk-modulus extraction arguments."""
    output_dir = args.output_dir or f'{REPO_ROOT}/data/{args.run_name}/raw/'
    graphs_dir = output_dir.replace('/raw/', '/graphs/').replace('/raw', '/graphs')
    lammps_base = f'{REPO_ROOT}/data/{args.run_name}/lammps'
    _k_from_cls = _exp_K_range(cls)
    exp_K = [args.exp_K_min if args.exp_K_min is not None else _k_from_cls[0], args.exp_K_max if args.exp_K_max is not None else _k_from_cls[1]]
    K_deform_rate_slow_inv_s = cls.get('K_deform_rate_slow_inv_s', None)
    return {'output_dir': output_dir, 'graphs_dir': graphs_dir, 'npt_prod_log_path': args.npt_prod_log or f'{lammps_base}/equil/npt_prod300/npt_prod300.log', 'exp_K_range': exp_K, 'bm_pressures_atm': cls.get('bm_pressures_atm', None), 'strain_rate_per_fs': cls.get('K_deform_rate_inv_s', 100000000.0) * 1e-15, 'strain_rate_slow_per_fs': K_deform_rate_slow_inv_s * 1e-15 if K_deform_rate_slow_inv_s is not None else None, 'K_strain_max': cls.get('K_strain_max', 0.03), 'deform_eq_steps': int(cls.get('deform_eq_steps', 200000)), 'deform_strain_start': cls.get('deform_strain_start', 0.002), 'deform_avg_window': int(cls.get('deform_avg_window', 2000)), 'deform_log_path': getattr(args, 'deform_log', None), 'deform_log_path_slow': getattr(args, 'deform_log_slow', None), 'murnaghan_log_files': getattr(args, 'murnaghan_logs', None), 'dt_fs': _pick(args.dt_fs, cls, 'dt_fs', 1.0)}

def _resolve_run_summary_params(args, cls: dict) -> dict:
    """Resolve deterministic run-summary arguments.

    Every field is derived from CLI flags + the (plan-overlaid) class defaults + the
    deterministic output_dir convention — NOT from the plan's decisions[] list or the --plan
    path — so a deterministic plan still produces byte-identical output to the no-plan path
    The plan provenance is carried by reading raw/run_plan.json at the convention path below.
    """
    output_dir = args.output_dir or f'{REPO_ROOT}/data/{args.run_name}/raw/'
    graphs_dir = output_dir.replace('/raw/', '/graphs/').replace('/raw', '/graphs')
    run_plan = f"{output_dir.rstrip('/')}/run_plan.json"
    _db = _db_exp_lookup(args.polymer_class, getattr(args, 'polymer_name', None))
    (_tg_min, _tg_max) = (getattr(args, 'exp_tg_min', None), getattr(args, 'exp_tg_max', None))
    _tg_override = getattr(args, 'exp_tg_K', None)
    if _tg_min is not None and _tg_max is not None:
        exp_tg = [_tg_min, _tg_max]
    elif _tg_override is not None:
        exp_tg = [round(_tg_override - 20), round(_tg_override + 20)]
    elif _db.get('tg_median_K') is not None:
        exp_tg = [round(_db['tg_median_K'] - 20), round(_db['tg_median_K'] + 20)]
    else:
        exp_tg = _exp_tg_range(cls, run_name=args.run_name)
    (_dens_min, _dens_max) = (getattr(args, 'exp_density_min', None), getattr(args, 'exp_density_max', None))
    if _dens_min is not None and _dens_max is not None:
        exp_density = [_dens_min, _dens_max]
    elif _db.get('density_gcm3') is not None:
        _d = _db['density_gcm3']
        exp_density = [round(_d * 0.95, 3), round(_d * 1.05, 3)]
    else:
        exp_density = _exp_density_range(cls)
    _k_from_cls = _exp_K_range(cls)
    _k_from_db = _db.get('K_range_GPa')
    if _k_from_db and _k_from_db[1] - _k_from_db[0] < 0.01:
        _k_from_db = None
    exp_K = [args.exp_K_min if args.exp_K_min is not None else _k_from_db[0] if _k_from_db else _k_from_cls[0], args.exp_K_max if args.exp_K_max is not None else _k_from_db[1] if _k_from_db else _k_from_cls[1]]
    dp = args.dp if args.dp is not None else cls.get('dp_typical')
    nchain = args.nchain if args.nchain is not None else cls.get('nchain')
    charge_method = args.charge_method or cls.get('charge_method')
    ff = args.ff or cls.get('preferred_ff', 'pcff')
    d01 = args.d01 or ff
    d02 = args.d02 or charge_method
    d03 = args.d03 or cls.get('electrostatics')
    d04 = args.d04 or (f'DP={dp}, {nchain} chains' if dp and nchain else None)
    _slope_gate = getattr(args, 'slope_gate_pass', None)
    tg_path_label = 'single-rate fallback (slope_gate=False; class fallback rate — plan tg_slope_gate_fallback, default highest)' if _slope_gate is False else 'slowest-rate folder (slope_gate=True or N/A)'
    return {'output_dir': output_dir, 'graphs_dir': graphs_dir, 'run_plan': run_plan, 'exp_tg_range': exp_tg, 'exp_density_range': exp_density, 'exp_K_range': exp_K, 'dp': dp, 'nchain': nchain, 'charge_method': charge_method, 'ff': ff, 'd01_ff': d01, 'd02_charges': d02, 'd03_electrostatics': d03, 'd04_system_size': d04, 'slope_gate_pass': _slope_gate, 'tg_path_label': tg_path_label}
_STAGE_RESOLVERS = {'build': _resolve_build_params, 'equil': _resolve_equil_params, 'tg': _resolve_tg_params, 'deform': _resolve_deform_params, 'analyze-tg': _resolve_analyze_tg_params, 'analyze-tg-multirate': _resolve_analyze_tg_multirate_params, 'equil-check': _resolve_equil_check_params, 'murnaghan': _resolve_murnaghan_params, 'analyze-bm': _resolve_analyze_bm_params, 'run-summary': _resolve_run_summary_params}

def resolve_stage_params(stage: str, args, cls: dict) -> dict:
    """Resolve routing and physics decisions into concrete tool arguments."""
    resolver = _STAGE_RESOLVERS.get(stage)
    if resolver is None:
        raise ValueError(f'resolve_stage_params: no resolver for stage {stage!r} (valid: {sorted(_STAGE_RESOLVERS)})')
    return resolver(args, cls)
