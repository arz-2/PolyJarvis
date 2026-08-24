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
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hw_common import load_rules, get_class_entry, hardware_policy, resolve_ff_family
import cost_model

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
    # cost_model.py's real multi-point log-log interpolation (size_points) instead of this
    # script's old single-point in-window heuristic, which never read size_points at all.
    choice = {"engine": default.get("engine"), "gpu_per_run": default.get("gpu_per_run"),
              "mpi_ranks": default.get("mpi")}
    est = cost_model.estimate_ns_per_day(cell_atoms, fam, hp=hp, rules=rules)
    confidence = est["confidence"]
    evidence = [{
        "claim": f"cost_model.estimate_ns_per_day at this run's {cell_atoms}-atom estimate: "
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
