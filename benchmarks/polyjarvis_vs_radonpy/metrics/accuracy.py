"""Extracts the accuracy axis for both arms.

PolyJarvis side (shape verified live against data/PE1/attempts/summary/attempt-0001/raw/
run_summary.json): `results.density.value_g_cm3`, `results.bulk_modulus.{value_GPa,method}`,
`convergence.verdict`.

RadonPy side: `analyze/results.csv` written by `helper.IO_Helper.output_md_data` at the end
of sample_script/eq.py -- one row, DBID-indexed, columns include `density` (g/cm^3) and
`bulk_modulus` (Pa, per radonpy/sim/lammps.py's own ylabel 'Bulk modulus [Pa]' -- converted
to GPa here for comparability) plus `check_eq` (bool-as-string) as RadonPy's only gate verdict.

Reference bands: guides/polymer_rules.json's per-class `experimental_density_gcm3` /
`exp_K_GPa` dicts, keyed by class member name (e.g. POXI.experimental_density_gcm3.PEO).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

from .schema import AccuracyBlock

PA_PER_GPA = 1e9


def _latest_run_summary(run_dir: Path) -> Optional[dict]:
    matches = sorted((run_dir / "attempts" / "summary").glob("attempt-*/raw/run_summary.json"))
    if not matches:
        return None
    return json.loads(matches[-1].read_text())


def extract_polyjarvis_accuracy(run_dir: Path, exp_density_g_cm3: Optional[float] = None,
                                 exp_k_range_gpa: Optional[list] = None) -> AccuracyBlock:
    block = AccuracyBlock()
    summary = _latest_run_summary(run_dir)
    if summary is None:
        block.method_note = f"no run_summary.json found under {run_dir}/attempts/summary/"
        return block

    results = summary.get("results", {})
    block.density_g_cm3 = (results.get("density") or {}).get("value_g_cm3")
    bm = results.get("bulk_modulus") or {}
    block.bulk_modulus_GPa = bm.get("value_GPa")
    block.bulk_modulus_method = bm.get("method")  # e.g. "murnaghan"
    block.gate_verdict = (summary.get("convergence") or {}).get("verdict")
    block.density_exp_ref_g_cm3 = exp_density_g_cm3
    block.bulk_modulus_exp_ref_range_GPa = exp_k_range_gpa
    block.method_note = (
        f"bulk_modulus method={block.bulk_modulus_method!r} "
        "(volume-deformation/Murnaghan-EOS fitting)"
    )
    return block


def extract_radonpy_accuracy(harness_root: Path, polymer_name: str,
                              exp_density_g_cm3: Optional[float] = None,
                              exp_k_range_gpa: Optional[list] = None) -> AccuracyBlock:
    block = AccuracyBlock()
    results_csv = harness_root / polymer_name / "analyze" / "results.csv"
    if not results_csv.is_file():
        block.method_note = f"no results.csv found at {results_csv}"
        return block

    with open(results_csv) as f:
        reader = csv.DictReader(f)
        row = next(reader, None)
    if row is None:
        block.method_note = f"results.csv at {results_csv} has no data row"
        return block

    density = row.get("density")
    bulk_modulus_pa = row.get("bulk_modulus")
    check_eq = row.get("check_eq")

    block.density_g_cm3 = float(density) if density not in (None, "", "nan") else None
    block.bulk_modulus_GPa = (
        float(bulk_modulus_pa) / PA_PER_GPA if bulk_modulus_pa not in (None, "", "nan") else None
    )
    block.bulk_modulus_method = "npt_fluctuation"
    block.gate_verdict = f"check_eq={check_eq}"
    block.density_exp_ref_g_cm3 = exp_density_g_cm3
    block.bulk_modulus_exp_ref_range_GPa = exp_k_range_gpa
    block.method_note = "bulk_modulus method=npt_fluctuation (isothermal, NPT thermodynamic fluctuation)"
    return block
