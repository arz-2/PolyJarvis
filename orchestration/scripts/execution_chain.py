#!/usr/bin/env python3
"""
execution_chain.py — build the ordered, fully-resolved stage chain a deterministic run plan
carries, so the protocol is inspectable in one artifact instead of being implicit in
run_deterministic_replicate.py's Python control flow.

Each entry is {stage, track, tool, args}, in execution order, with every physics argument already
resolved to a concrete value. Three placeholder kinds mark what is deliberately NOT frozen:

  "<VARY:emc_seed>"      seeds — a replicate MUST draw its own (that is the point of a replicate)
  "<VARY:velocity_seed>"
  "<HOST:gpu_ids>"       host wiring — re-derived from hardware_policy, never frozen, or the
  "<HOST:mpi_ranks>"     protocol stops being portable off the box it was measured on
  "<HOST:engine>"
  "<RUNTIME:...>"        a path produced by an earlier stage of this same run

Conditional control flow stays in the executor: the EXTEND retry loop and the Murnaghan->deform
fallback cannot be expressed as a static list. What the chain carries instead is the frozen ROUTE
(which branch the source run actually took), so the executor reproduces the branch rather than
re-deciding it from its own gate results.

Args come from gen_prompt.resolve_stage_params — the same resolver the worker prompts and the
scripted executor already share — so this is a declarative view of the real code path, never a
parallel reimplementation of it.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_prompt import resolve_stage_params  # noqa: E402


def base_args(run_name: str, polymer_class: str, plan_path: str) -> SimpleNamespace:
    """Neutral args namespace mirroring gen_prompt.py's argparse defaults — everything None so
    apply_plan/resolve_hardware/resolve_stage_params fill from the plan and hardware_policy.
    Shared by run_deterministic_replicate.py and the plan writer so there is one definition."""
    return SimpleNamespace(
        run_name=run_name, polymer_class=polymer_class, plan=str(plan_path),
        smiles=None, data_path=None, tg_start_data=None, work_dir=None,
        gpu_ids=None, mpi_ranks=None, engine=None, emc_seed=None, velocity_seed=None,
        dp=None, nchain=None, n_atoms=None, charge_method=None, date_start=None, date_end=None,
        d01=None, d02=None, d03=None, d04=None, lammps_flags=None, is_glassy=None,
        tg_k=None, tg_fit_quality=None, deform_log=None, deform_log_slow=None,
        deform_rate_mode="primary", murnaghan_logs=None, d05=None, npt_prod_log=None,
        npt_prod_dump=None, ff=None, backbone_types=None, enthalpy_col="Enthalpy",
        output_dir=None, equil_data_path=None, npt_prod_ns=None, add_melt_npt=False,
        T_equil_K=None, T_anneal_high_K=None, tg_t_high_K=None, tg_t_low_K=None,
        tg_t_step_K=None, tg_steps_per_t=None, tg_rate_index=None, mr_rates=None,
        mr_tg_values=None, n_replicates=1, bm_npt_steps=None,
        K_strain_max=None, K_deform_rate_inv_s=None,
        dt_fs=None, density_initial=None, properties="all", exp_K_min=None, exp_K_max=None,
        exp_tg_K=None, exp_tg_min=None, exp_tg_max=None, exp_density_min=None,
        exp_density_max=None, polymer_name=None, tg_path=None, slope_gate_pass=None,
    )

VARY_EMC_SEED = "<VARY:emc_seed>"
VARY_VELOCITY_SEED = "<VARY:velocity_seed>"
HOST_GPU = "<HOST:gpu_ids>"
HOST_MPI = "<HOST:mpi_ranks>"
HOST_ENGINE = "<HOST:engine>"


def _rt(name: str) -> str:
    return f"<RUNTIME:{name}>"


def _step(stage, track, tool, args, **extra):
    return {"stage": stage, "track": track, "tool": tool, "args": args, **extra}


def _build(p, polymer_class):
    return _step("build", "foundation", "submit_emc_cell_job", {
        "smiles": p["smiles"], "polymer_class": polymer_class.upper(),
        "dp": p["dp"], "nchains": p["nchain"],
        "density_initial": p["density_initial_gcm3"],
        "temperature": 300.0, "seed": VARY_EMC_SEED, "output_name": "polymer",
    })


def _equil(p, run_name, frozen_stages=None):
    flags = p["lammps_flags"]
    # Step counts: a frozen protocol pins the RESOLVED integers. Left null, generate_equilibration_
    # workflow falls back to an atom-count tier (server.py:1536-1553, boundaries at 5,000/15,000
    # atoms) -- and a replicate's fresh EMC packing can land on the other side of a boundary and
    # silently run a different equilibration. Pinning is the whole point of freezing this stage.
    pinned = _pin_steps_from_frozen(frozen_stages)
    gen_args = {
        "data_file": _rt("build.data_path"), "work_dir_base": p["work_dir"],
        "polymer_name": run_name, "temp": p["T_workflow_K"], "max_temp": p["T_anneal_high_K"],
        "press": p["P_equil_atm"], "use_pcff": flags["use_pcff"], "use_trappe": flags["use_trappe"],
        "use_opls": flags["use_opls"],
        "npt_prod_steps": pinned.get("npt_production", p["npt_prod_steps"]),
        "add_melt_npt": p["add_melt_npt"],
        "t_equil_K": p["T_equil_K"] if p["add_melt_npt"] else None,
        "melt_npt_steps": pinned.get("npt_melt", p["melt_npt_steps"]),
        "npt_cool_steps": pinned.get("npt_cool", p["npt_cool_steps"]),
        "npt_cool300_steps": pinned.get("npt_cool300", p["npt_cool300_steps"]),
        "engine": HOST_ENGINE, "velocity_seed": VARY_VELOCITY_SEED, "extend_steps": None,
    }
    run_args = {"stages": _rt("equil.workflow_stages"), "gpu_ids": HOST_GPU,
                "mpi": HOST_MPI, "data_file": _rt("build.data_path"), "engine": HOST_ENGINE}
    return [
        _step("equil", "foundation", "generate_equilibration_workflow", gen_args),
        _step("equil", "foundation", "run_lammps_chain", run_args),
    ]


def _pin_steps_from_frozen(frozen_stages):
    """Map a frozen protocol's equil_stages back onto generate_equilibration_workflow's step
    arguments, so the replicate reruns the counts that actually executed."""
    out = {}
    for s in (frozen_stages or []):
        n = (s.get("params") or {}).get("N_STEPS")
        if s.get("name") and n:
            out[s["name"]] = n
    return out


def _equil_check(p, polymer_class):
    return [
        _step("equil-check", "foundation", "check_equilibration_comprehensive", {
            "log_file": p["npt_prod_log_path"], "dump_file": p["melt_dump_path"],
            "data_file": p["npt_prod_data_path"], "backbone_types": p["backbone_types"],
            "ct_min_decay": p["ct_min_decay_melt"], "output_dir": p["output_dir"],
            "graphs_dir": p["graphs_dir"], "cutoff_A": p["cutoff_A"], "timestep_fs": p["dt_fs"],
        }),
        _step("equil-check", "foundation", "extract_equilibrated_density", {
            "log_file": p["npt_prod_log_path"], "target_temp": p["npt_prod_temp_K"],
            "output_dir": p["output_dir"],
        }),
        _step("equil-check", "foundation", "enforce_equilibration_gate", {
            "comprehensive_json": str(Path(p["output_dir"]) / "equilibration_comprehensive.json"),
            "regime": p["regime"], "dp": p["dp"], "ct_gate_reliable": p["ct_gate_reliable"],
            "exp_density_gcm3": p["exp_density_point_gcm3"], "tg_K": p["exp_tg_point_K"],
            "t_equil_K": p["T_workflow_K"], "glass_data": p["npt_prod_data_path"],
            "melt_data": p["melt_data_path"], "out_dir": p["output_dir"],
            "alpha_glass_per_K": p["alpha_glass_per_K"], "alpha_melt_per_K": p["alpha_melt_per_K"],
            "phase": "full", "polymer_class": polymer_class.upper(),
        }),
    ]


def _tg(p):
    params = {
        "LOG_FILE": "tg_sweep.log", "DUMP_FILE": "", "WRITE_PER_T_DUMP": True,
        "PER_T_DUMP_FILE": "per_t_structs.dump", "T_START": p["T_start_K"], "T_END": p["T_end_K"],
        "T_STEP": p["T_step_K"], "N_STEPS_PER_T": p["n_steps_per_t"], "P_START": 1.0,
        "P_FINAL": 1.0, "T_DAMP": 100.0, "TIMESTEP": p["dt_fs"],
        "use_pppm": not p["lammps_flags"]["use_trappe"], "use_gpu": True, "engine": HOST_ENGINE,
    }
    if p.get("emc_params_path"):
        params["params_file"] = p["emc_params_path"]
    params.update({f"use_{k.split('_')[1]}": v for k, v in p["lammps_flags"].items()})
    return [
        _step("tg", "thermal", "generate_script", {
            "template_name": "npt_tg_step", "data_file": p["equil_data_path"],
            "output_script": f"{p['tg_sweep_dir']}/tg_sweep.in",
            "velocity_seed": VARY_VELOCITY_SEED, "params": params,
        }),
        _step("tg", "thermal", "run_lammps_script", {
            "script": f"{p['tg_sweep_dir']}/tg_sweep.in", "work_dir": p["tg_sweep_dir"],
            "log_file": "tg_sweep_run.log", "gpu_ids": HOST_GPU, "mpi": HOST_MPI,
            "engine": HOST_ENGINE,
        }),
    ]


def _analyze_tg(p):
    return _step("analyze-tg", "thermal", "extract_thermal", {
        "log_file": p["tg_log_path"], "tg_data_file": p["tg_data_file"],
        "per_t_dump_file": p["per_t_dump_file"], "backbone_types": p["backbone_types"],
        "enthalpy_col": p["enthalpy_col"], "output_dir": p["output_dir"],
        "graphs_dir": p["graphs_dir"], "method_gap_exempt": p["method_gap_exempt"],
    })


def _murnaghan(p, run_name):
    return _step("murnaghan", "mechanical", "run_bulk_modulus_series", {
        "data_file": p["equil_data_path"], "work_dir": f"{p['work_dir']}/bm_series",
        "pressures_atm": p["bm_pressures_atm"], "temp_K": p["temp_K"], "run_name": run_name,
        "gpu_ids": HOST_GPU, "mpi": HOST_MPI, "velocity_seed": VARY_VELOCITY_SEED,
        "npt_steps": p["npt_steps"], "dt_fs": p["dt_fs"],
        "use_trappe": p["lammps_flags"]["use_trappe"], "use_pcff": p["lammps_flags"]["use_pcff"],
        "use_opls": p["lammps_flags"]["use_opls"], "engine": HOST_ENGINE,
    })


def _deform(p, mode):
    suffix = "" if mode == "primary" else "_slow"
    rate = p["K_deform_rate_inv_s"] if mode == "primary" else p["K_deform_rate_slow_inv_s"]
    if rate in (None, "null"):
        return []
    return [
        _step("deform", "mechanical", "generate_script", {
            "template_name": "npt_deform", "data_file": p["equil_data_path"],
            "output_script": f"{p['work_dir']}/05_deform{suffix}.in",
            "velocity_seed": VARY_VELOCITY_SEED,
            "params": {"LOG_FILE": f"05_deform{suffix}.log",
                       "STRAIN_RATE": float(rate) * 1e-15, "STRAIN_MAX": p["K_strain_max"],
                       "TIMESTEP": p["dt_fs"], "use_gpu": True, "engine": HOST_ENGINE,
                       **p["lammps_flags"]},
        }, deform_rate_mode=mode),
        _step("deform", "mechanical", "run_lammps_script", {
            "script": f"{p['work_dir']}/05_deform{suffix}.in", "work_dir": p["work_dir"],
            "log_file": f"05_deform{suffix}.log", "gpu_ids": HOST_GPU, "mpi": HOST_MPI,
            "engine": HOST_ENGINE,
        }, deform_rate_mode=mode),
    ]


def _analyze_bm(p, bm_method):
    if bm_method == "deform":
        return _step("analyze-bm", "mechanical", "extract_bulk_modulus_deform", {
            "log_file": _rt("deform.primary_log"), "output_dir": p["output_dir"],
            "graphs_dir": p["graphs_dir"], "strain_rate": p["strain_rate_per_fs"],
            "strain_max": p["K_strain_max"], "timestep": p["dt_fs"],
        })
    return _step("analyze-bm", "mechanical", "extract_bulk_modulus_murnaghan", {
        "log_files": _rt("murnaghan.log_files"), "pressures_atm": p["bm_pressures_atm"],
        "output_dir": p["output_dir"], "graphs_dir": p["graphs_dir"],
        "npt_prod_log": p["npt_prod_log_path"],
    })


def _run_summary(p, plan, polymer_class, run_name):
    return _step("run-summary", "summary", "generate_run_summary", {
        "output_dir": p["output_dir"], "graphs_dir": p["graphs_dir"], "run_name": run_name,
        "smiles": plan.get("smiles") or "", "polymer_class": polymer_class.upper(),
        "ff": p["ff"], "charge_method": p["charge_method"] or "", "dp": p["dp"],
        "n_chains": p["nchain"], "d01": p["d01_ff"], "d02": p["d02_charges"],
        "d03": p["d03_electrostatics"], "d04": p["d04_system_size"],
        "d05": _rt("equil-check.verdict"), "d06": _rt("analyze-tg.fit_quality"),
        "tg_path": _rt("analyze-tg.tg_summary_path"),
    })


def build_execution_chain(args, cls: dict, plan: dict, properties: set,
                          frozen_protocol: dict = None) -> list:
    """Ordered, fully-resolved chain for this plan. `frozen_protocol` (when the SMILES has one)
    pins the resolved equilibration step counts and selects the mechanical branch the source run
    actually took."""
    frozen_protocol = frozen_protocol or {}
    foundation = frozen_protocol.get("foundation") or {}
    mech_route = (frozen_protocol.get("mechanical") or {}).get("route") or {}
    bm_method = mech_route.get("bm_method")
    run_name, polymer_class = args.run_name, args.polymer_class

    chain = [_build(resolve_stage_params("build", args, cls), polymer_class)]
    chain += _equil(resolve_stage_params("equil", args, cls), run_name,
                    foundation.get("equil_stages"))
    chain += _equil_check(resolve_stage_params("equil-check", args, cls), polymer_class)

    if "tg" in properties:
        chain += _tg(resolve_stage_params("tg", args, cls))
        chain.append(_analyze_tg(resolve_stage_params("analyze-tg", args, cls)))

    if "bulk_modulus" in properties:
        # Force the frozen route. Only when nothing is frozen does this fall back to the
        # submit-Murnaghan-then-maybe-deform shape the executor decides at runtime.
        if bm_method == "deform":
            for mode in ("primary", "slow"):
                chain += _deform(resolve_stage_params("deform", _mode(args, mode), cls), mode)
        else:
            chain.append(_murnaghan(resolve_stage_params("murnaghan", args, cls), run_name))
        chain.append(_analyze_bm(resolve_stage_params("analyze-bm", args, cls), bm_method))

    chain.append(_run_summary(resolve_stage_params("run-summary", args, cls), plan,
                              polymer_class, run_name))
    return chain


def _mode(args, mode):
    args.deform_rate_mode = mode
    return args
