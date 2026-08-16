#!/usr/bin/env python3
"""
select_hardware.py — D-08 hardware selection, mechanically, from decision_policy.json's
`policies.hardware` require/prefer clauses and polymer_rules.json's hardware_policy.

The validator and runtime use this shared policy implementation instead of re-deriving hardware
thresholds. `decision_policy.json:policies.hardware` remains the source of truth for the numbers;
runtime GPU allocation remains separate.

Usage:
  python3 orchestration/select_hardware.py --polymer_class PACR --smiles "*CC(C)(C(=O)OC)*" \
      [--dp_typical 60] [--nchain 15]     # default: class entry's own dp_typical/nchain
Prints a JSON object: {decision, decided_params_override, uncertainties, cell_atoms_estimate,
ff_family} to stdout (exit 0), or {"error": "..."} (exit 1).
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hw_common import load_rules, get_class_entry, hardware_policy, resolve_ff_family, live_host

_RDKIT_SNIPPET = """\
import os
from rdkit import Chem
from rdkit.Chem import Descriptors
smi = os.environ['SELECT_HW_SMILES']
ua = os.environ['SELECT_HW_UA'] == '1'
mol = Chem.MolFromSmiles(smi)
if mol is None:
    raise SystemExit('RDKit could not parse SMILES: ' + smi)
# The two `*` connection points parse as dummy atoms: discount them from the atom count
# rather than deleting them from the string, which would leave an empty branch `c(...)` ->
# `c()` and fail to parse for any SMILES whose `*` sits inside a branch.
dummies = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 0)
with_h = Chem.AddHs(mol)
n_atoms = (mol.GetNumAtoms() if ua else with_h.GetNumAtoms()) - dummies
# Dummy atoms carry zero mass, so this is the repeat unit's residue mass as it appears
# in the chain -- exactly what the cell-mass estimate needs.
print(n_atoms, Descriptors.MolWt(with_h))
"""


def _monomer_atoms_and_mw(smiles: str, is_ua: bool, env: str = "radonpy",
                          timeout: int = 30) -> tuple:
    """(atom count, molar mass g/mol) for one repeat unit. Count is heavy-atom for UA FFs
    (e.g. TraPPE) or all-atom with H for all-atom FFs (PCFF/OPLS/GAFF); the mass is always
    all-atom. `*` connection-point atoms are stripped first --
    RDKit would otherwise count them as real (wildcard) atoms. Same conda-activate
    subprocess pattern as canon_smiles.py's canonicalize() -- RDKit lives outside `base`."""
    import os
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(_RDKIT_SNIPPET)
        snippet_path = f.name
    try:
        script = (
            "source ~/miniforge3/etc/profile.d/conda.sh\n"
            f"conda activate {env}\n"
            f"python3 {snippet_path}\n"
        )
        run_env = dict(os.environ)
        run_env["SELECT_HW_SMILES"] = smiles
        run_env["SELECT_HW_UA"] = "1" if is_ua else "0"
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=timeout, env=run_env)
        out = r.stdout.strip()
        if r.returncode != 0 or not out:
            raise RuntimeError(r.stderr.strip() or "empty output from RDKit atom-count")
        n_atoms, mw = out.splitlines()[-1].split()
        return int(n_atoms), float(mw)
    finally:
        Path(snippet_path).unlink(missing_ok=True)


def _host_matches_measured_on(measured_on: str, live: dict) -> bool:
    """directional_probe.measured_on is free-text prose (e.g. '4x NVIDIA A800 40GB Active /
    32 phys cores (...)'), not a structured dict like hardware_policy.host -- extract the GPU
    model and phys_cores substrings and compare against the live host. Unparseable or absent
    -> treat as mismatched (conservative: never silently adopt a probe from an unknown host)."""
    if not measured_on:
        return False
    cores_match = re.search(r"(\d+)\s*phys\s*cores", measured_on)
    if not cores_match or int(cores_match.group(1)) != live.get("phys_cores"):
        return False
    gpu_model = live.get("gpu_model") or ""
    # Compare on the model's distinguishing token (e.g. "A800", "RTX 6000") rather than the
    # full string -- measured_on and hardware_policy.host format GPU names slightly differently.
    tokens = [t for t in re.split(r"[\s,/]+", gpu_model) if len(t) >= 3]
    return any(t in measured_on for t in tokens) if tokens else False


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

    dp_probe = hp.get("directional_probe", {})
    values_are_benchmarked = bool(hp.get("values_are_benchmarked", False))
    measured_on = dp_probe.get("measured_on")
    live = live_host()
    host_match = _host_matches_measured_on(measured_on, live)
    recommended = dp_probe.get("recommended_by_ff", {}).get(fam)

    cleanly_benchmarked = values_are_benchmarked and host_match and recommended is not None
    in_size_window = False
    if cleanly_benchmarked:
        probe_atoms = recommended.get("cell_atoms")
        if probe_atoms:
            in_size_window = (0.5 * probe_atoms <= cell_atoms <= 2.0 * probe_atoms)

    if cleanly_benchmarked and in_size_window:
        choice = {"engine": recommended["engine"], "gpu_per_run": recommended["gpu"],
                   "mpi_ranks": recommended["mpi"]}
        evidence = [{
            "claim": f"directional_probe.recommended_by_ff[{fam}] measured on this host, "
                     f"cell_atoms={recommended.get('cell_atoms')} within [0.5x,2x] of the "
                     f"planned estimate ({cell_atoms} atoms)",
            "ns_per_day": recommended.get("ns_per_day"),
            "measured_on": measured_on, "date": dp_probe.get("date"),
        }]
        confidence = "high"
    else:
        choice = {"engine": default.get("engine"), "gpu_per_run": default.get("gpu_per_run"),
                  "mpi_ranks": default.get("mpi")}
        reason = ("by_forcefield default; not yet cleanly benchmarked on this host"
                  if not cleanly_benchmarked else
                  f"by_forcefield default; directional_probe cell_atoms="
                  f"{recommended.get('cell_atoms')} outside [0.5x,2x] of the planned estimate "
                  f"({cell_atoms} atoms) -- probe is out of size range for this run")
        evidence = [{"claim": reason, "note": default.get("note")}]
        # cleanly_benchmarked-but-out-of-size-window still falls back to the by_forcefield
        # default (not the measured recommendation) -- "medium", not "high": the host/engine
        # choice is calibrated, but this specific cell size wasn't. "low" is reserved for no
        # clean sweep at all.
        confidence = "low" if not cleanly_benchmarked else "medium"

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
    if not cleanly_benchmarked:
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


def main():
    p = argparse.ArgumentParser(description="Mechanically select D-08 hardware from policy + benchmark evidence.")
    p.add_argument("--polymer_class", required=True)
    p.add_argument("--smiles", required=True, help="Repeat-unit SMILES with * connection points.")
    p.add_argument("--dp_typical", type=int, default=None)
    p.add_argument("--nchain", type=int, default=None)
    args = p.parse_args()

    result = select_hardware(args.polymer_class, args.smiles, args.dp_typical, args.nchain)
    print(json.dumps(result, indent=2))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
