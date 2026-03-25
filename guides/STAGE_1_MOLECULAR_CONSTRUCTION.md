# Stage 1: Molecular Construction
**Read when:** You have a SMILES string and need to produce a LAMMPS `.data` file
**Next stage:** `STAGE_2_EQUILIBRATION.md` — once you have a `.data` file ready to upload

---

## Critical Rules for This Stage

### Rule 0: classify_polymer is Always First

Before building a molecule, before choosing a force field, before anything else — call `classify_polymer(smiles)` and read its output. The returned `class_id` and `class_name` determine all downstream decisions (FF, charges, electrostatics) via the class table below.

```python
classification = classify_polymer(smiles="*CC*")
# → status: "success"
# → class_id: 1, class_name: "PHYC", description: "Polyhydrocarbon"
# → flags: {"PHYC": True, "PSTR": False, ...}
# → warning: "Pure hydrocarbon (PHYC): GAFF2_mod overestimates PE density ~24% and Tg ~80K. Use GAFF2 instead of GAFF2_mod."
```

If `class_id == 0` (UNKNOWN): stop. The SMILES is malformed or missing `[*]` attachment points. Fix before proceeding.

If `warning` is not None: read it, understand it, and record it in your SUMMARY_LOG.

If `co_occurring_groups` is non-empty: the polymer has multiple functional group motifs. This doesn't change the FF choice but may affect property accuracy — note it.

---

### Rule A: Force Field AFTER Polymerization
**This is the single most costly mistake in the entire workflow. Do not break it.**

```python
# ❌ WRONG — force field is lost during polymerization
ff = assign_forcefield(monomer, "GAFF2_mod")
poly = submit_polymerize_job(ff["file_modified"], 100)

# ✅ CORRECT
poly = submit_polymerize_job(monomer, 100)
ff = assign_forcefield(poly_output, "GAFF2_mod")
```

**Why:** RadonPy's async polymerization job does not preserve force field parameters assigned to the monomer. Violation causes LAMMPS to fail with "unknown atom type" — discovered after days of debugging in Dec 2025.

---

### Rule B: Verify Force Field Choice Against Literature Before Assigning

Do not default to GAFF2_mod blindly. Check what force field published MD studies use for your specific polymer.

| Use Case | Force Field | Notes |
|---|---|---|
| Pure hydrocarbons (PE, PP) | **GAFF2** | GAFF2_mod overestimates PE density by ~24% and Tg by ~80K |
| General / Tg screening | **GAFF2_mod** | Stable, consistent, accept systematic offset |
| Fluorinated polymers | **GAFF2_mod** | Designed for F-containing systems |
| Charged systems (PEO, PMMA, PS) | **GAFF2_mod** + RESP charges | PPPM required for electrostatics |

---

## Workflow

```
classify_polymer()
  └─ build_molecule_from_smiles()
       └─ [optional] submit_conformer_search_job() 
            └─ submit_assign_charges_job(c)
                 └─ submit_polymerize_job()
                      └─ assign_forcefield(ff) 
                           └─ submit_generate_cell_job()
                                └─ save_lammps_data()  → output: cell.data
```

---

## Tools

### `classify_polymer` *(sync — call first, always)*

```python
result = classify_polymer(smiles="*CC(c1ccccc1)*")  # PS
# Returns:
# {
#   "status": "success",
#   "class_id": 2,
#   "class_name": "PSTR",
#   "description": "Polystyrenic",
#   "flags": {"PHYC": False, "PSTR": True, "PVNL": True, ...},
#   "co_occurring_groups": [{"class_id": 3, "class_name": "PVNL", "description": "Polyvinyl"}],
#   "warning": None,
#   "message": "Class 2 (PSTR): Polystyrenic"
# }
```

**Output fields and how to use them:**

| Field | How to use |
|---|---|
| `status` | `"success"` or `"error"` — always check before reading other fields |
| `class_id` / `class_name` | Use the FF selection table below to set force field, charges, and electrostatics |
| `description` | Human-readable class name (e.g. "Polyhydrocarbon", "Polystyrenic") |
| `warning` | Log in SUMMARY_LOG; indicates known FF accuracy issues for this class |
| `co_occurring_groups` | Note in SUMMARY_LOG; no action required but affects uncertainty |
| `flags` | Full 21-group match dict `{class_name: bool}` — useful for complex copolymers |
| `class_id == 0` | Hard stop — SMILES is broken, fix before proceeding |

**Class ID complete reference** *(classify_polymer returns class_id and class_name; FF/charges/electrostatics are agent decisions based on these)*:

| class_id | class_name | Description | Example polymers | FF | Charges | Electrostatics |
|---|---|---|---|---|---|---|
| 0 | UNKNOWN | Unclassified | Bad SMILES | ❌ Stop | — | — |
| 1 | PHYC | Polyhydrocarbon | PE, PP, PIB | **GAFF2** | None | lj/cut |
| 2 | PSTR | Polystyrenic | PS | GAFF2_mod | RESP | pppm |
| 3 | PVNL | Polyvinyl | PVA, PAN | GAFF2_mod | RESP | pppm |
| 4 | PACR | Polyacrylic | PMMA, PAA | GAFF2_mod | RESP | pppm |
| 5 | PHAL | Polyhalogenated | PTFE, PVC | GAFF2_mod | RESP | pppm |
| 6 | PDIE | Polydiene | Polybutadiene, Polyisoprene | GAFF2_mod | RESP | pppm |
| 7 | POXI | Polyoxide/Polyether | PEO, PPO | GAFF2_mod | RESP | pppm |
| 8 | PSUL | Polythioether | Polythioether | GAFF2_mod | RESP | pppm |
| 9 | PEST | Polyester | PET, PLA, PCL | GAFF2_mod | RESP | pppm |
| 10 | PAMD | Polyamide | Nylon-6, Nylon-66 | GAFF2_mod | RESP | pppm |
| 11 | PURT | Polyurethane | PU | GAFF2_mod | RESP | pppm |
| 12 | PURA | Polyurea | Polyurea | GAFF2_mod | RESP | pppm |
| 13 | PIMD | Polyimide | Kapton, PI | GAFF2_mod | RESP | pppm |
| 14 | PANH | Polyanhydride | Polyanhydride | GAFF2_mod | RESP | pppm |
| 15 | PCBN | Polycarbonate | PC | GAFF2_mod | RESP | pppm |
| 16 | PIMN | Polyamine | Polyamine | GAFF2_mod | RESP | pppm |
| 17 | PSIL | Polysiloxane | PDMS | GAFF2_mod | RESP | pppm |
| 18 | PPHS | Polyphosphazene | Polyphosphazene | GAFF2_mod | RESP | pppm |
| 19 | PKTN | Polyketone/PEEK | PEEK | GAFF2_mod | RESP | pppm |
| 20 | PSFO | Polysulfone | Polysulfone | GAFF2_mod | RESP | pppm |
| 21 | PPNL | Polyphenylenevinylene | PPV | GAFF2_mod | RESP | pppm |

**Known warnings (exact strings returned by the tool):**
- **PHYC (class 1):** `"Pure hydrocarbon (PHYC): GAFF2_mod overestimates PE density ~24% and Tg ~80K. Use GAFF2 instead of GAFF2_mod."` — validated from December 2025 PE runs
- **PDIE (class 6):** `"Diene polymer: verify cis/trans geometry in SMILES — cis vs trans isomers can differ by ~60K in Tg."` — cis-PI vs trans-PI have Tg difference of ~60K

---

### `build_molecule_from_smiles`
```python
result = build_molecule_from_smiles(
    smiles="*CC*",        # * = polymerization attachment point
    add_hydrogens=True
)
# Returns: {"temp_file": "/tmp/...", "num_atoms": 8}
```

**SMILES tips:**
- Ethylene (PE): `*CC*`
- Propylene (PP): `*CC(C)*`
- Styrene (PS): `*CC(c1ccccc1)*`
- Ethylene glycol (PEG/PEO): `*COCCO*` or `*CCO*`

---

### `submit_conformer_search_job`
```python
job = submit_conformer_search_job(
    mol_file=result["temp_file"],
    ff="GAFF2",
    psi4_omp=10,           # Use psi4_omp, NOT omp
    work_dir="conformer_search"
)
# Async — poll with get_job_status(job["job_id"])
```

**Skip for:** PE, PP, and other simple linear monomers with no rotatable bonds.
**Use for:** PS, PMMA, PEO, any aromatic or branched monomer.

---

### `submit_assign_charges_job`
```python
job = submit_assign_charges_job(
    mol_file=optimized_file,
    charge_method="RESP",    # Gold standard. ESP is faster alternative.
    optimize_geometry=False,
    omp_psi4=10,
    work_dir="assign_charges"
)
```

**Charge method decision:**
- RESP: production runs
- ESP: acceptable for screening
- Gasteiger

---

### `submit_polymerize_job`
```python
job = submit_polymerize_job(
    mol_file=charged_monomer,
    degree_of_polymerization=100,  # 50=fast, 100=standard, 150=publication
    tacticity="atactic"            # atactic / isotactic / syndiotactic
)
# Runtime: 5-30 min
```

---

### `assign_forcefield`
```python
result = assign_forcefield(
    mol_file=polymer_output,   # From polymerize — NOT monomer
    forcefield="GAFF2_mod"     # See Rule B above for selection
)
# Synchronous — instant
# Returns: {"file_modified": "/path/to/polymer.json"}
```

---

### `submit_generate_cell_job`
```python
job = submit_generate_cell_job(
    mol_file=result["file_modified"],
    num_chains=10,    # 6=fast/12k atoms, 10=standard/20k, 20=publication/40k
    density=0.05,     # ALWAYS 0.05 — prevents overlap, compressed during eq
    temperature=300
)
# Runtime: 10-30 min
```

---

### `save_lammps_data`
```python
result = save_lammps_data(
    mol_file=cell_output,
    output_path="./pe_cell.data",
    temp=300,
    include_velocities=True
)
# Synchronous — instant
# This file gets uploaded to Lambda in Stage 2
```

---

## Job Management Pattern (All Async Tools)

```python
job = submit_polymerize_job(...)      # or any submit_* call

while get_job_status(job["job_id"])["status"] != "completed":
    # status options: pending / running / completed / failed
    time.sleep(60)

output = get_job_output(job["job_id"])
# output["output_file"] = path to result JSON
```

---

## System Size Quick Reference

| Chains | Approx Atoms (100-mer) | Use For |
|---|---|---|
| 6 | ~12,000 | Fast screening |
| 10 | ~20,000 | Standard production |
| 20 | ~40,000 | Publication quality |

---

## Common Failures at This Stage

**`classify_polymer` returns `class_id == 0`:** SMILES is malformed or missing `[*]` polymerization attachment points. Check that your SMILES uses `*CC*` or `[*]CC[*]` notation, not bare SMILES without linkers.

**Wrong force field used despite classifier:** Agent defaulted to GAFF2_mod without checking class_name. For PHYC (class 1) this causes ~80K Tg error. Always use GAFF2 for PHYC; GAFF2_mod for everything else.

**"Unknown atom type" in LAMMPS later:** Force field was assigned before polymerization. Re-run from polymerize step.

**Conformer search crashes:** Check `psi4_omp` parameter (not `omp`). Confirm memory allocation is sufficient.

**Cell generation fails with overlap:** Density too high for initial packing. Always use `density=0.05`.

**Polymerization job hangs in "pending":** Check `list_all_jobs()` for stuck jobs from a previous session. Cancel if needed.

**`submit_polymerize_job` overwrites `mol_file` in place:** The polymerize tool writes its output back to the input path. If you built the monomer to `/tmp/foo.json`, the monomer is gone after polymerization completes. Always save checkpoints to distinct paths before running polymerize (see Checkpoint Saves below).

---

## Checkpoint Saves

Save the polymer JSON at each key stage so you can resume without re-running expensive QM steps:

```python
save_molecule(charged_monomer, "./checkpoints/01_charged_monomer.json", format="json")
save_molecule(polymer_output,  "./checkpoints/02_polymer.json",         format="json")
save_molecule(ff_output,       "./checkpoints/03_polymer_ff.json",      format="json")
save_molecule(cell_output,     "./checkpoints/04_cell.json",            format="json")
```

---

## Copolymer Construction

---

### Tool: `submit_copolymerize_job` — Alternating Copolymer

Builds an alternating (ABABAB…) chain. The `mol_files` list defines the repeating unit sequence; `degree_of_polymerization` is the number of full repeats.

```python
# Example: poly(ethylene-alt-propylene), (EP)₅₀
job = submit_copolymerize_job(
    mol_files=[
        "./checkpoints/ethylene_monomer.json",
        "./checkpoints/propylene_monomer.json"
    ],
    degree_of_polymerization=50,   # → 100 total monomer units
    output_file="./checkpoints/alt_ep_copolymer.json",
    tacticity="atactic"
)
# ← No force field on monomers before this step
# ← assign_forcefield() AFTER this job completes
```

**Notes:**
- Any number of monomer types: `[A, B, C]` with `n=30` → (ABC)₃₀
- `degree_of_polymerization` multiplies the entire monomer list — total units = n × len(mol_files)
- Runtime: same as homopolymer at equivalent total chain length

---

### Tool: `submit_random_copolymerize_job` — Statistical Copolymer

Inserts monomers in a random sequence obeying target mole fractions. `ratio` is auto-normalised — does not need to sum to 1.0.

```python
# Example: poly(styrene-stat-MMA), 70/30 mol%
job = submit_random_copolymerize_job(
    mol_files=[
        "./checkpoints/styrene_monomer.json",
        "./checkpoints/mma_monomer.json"
    ],
    ratio=[0.70, 0.30],
    degree_of_polymerization=100,  # total monomer units
    output_file="./checkpoints/stat_smma_copolymer.json",
    ratio_type="exact",            # 'exact' = enforce composition; 'choice' = probabilistic
    tacticity="atactic"
)
```

**`ratio_type` choice:**
- `'exact'` — guaranteed composition (rounds to nearest integer count per monomer). Use for production.
- `'choice'` — each monomer drawn independently from probability distribution. Can deviate from target for short chains.

---

### Tool: `submit_block_copolymerize_job` — Block Copolymer

Connects blocks in the order specified. `mol_files` and `block_lengths` are parallel arrays.

```python
# Example: PEO₄₀-PS₃₀ diblock
job = submit_block_copolymerize_job(
    mol_files=[
        "./checkpoints/peo_monomer.json",
        "./checkpoints/ps_monomer.json"
    ],
    block_lengths=[40, 30],        # A₄₀-B₃₀, total 70 units
    output_file="./checkpoints/block_peo_ps.json",
    tacticity="atactic"
)

# Example: ABA triblock (pass same monomer twice)
job = submit_block_copolymerize_job(
    mol_files=[
        "./checkpoints/a_monomer.json",
        "./checkpoints/b_monomer.json",
        "./checkpoints/a_monomer.json"   # same file, second block
    ],
    block_lengths=[20, 30, 20],    # A₂₀-B₃₀-A₂₀
    output_file="./checkpoints/triblock_aba.json",
    tacticity="atactic"
)
```

**Note:** For large blocks (>50 per block), runtime can be significant. Estimate as ~1–5 min per 100 total monomers with `opt='rdkit'`.

---

### Copolymer Workflow (Complete)

```
build_molecule_from_smiles(smiles_A)  →  monomer_A.json
build_molecule_from_smiles(smiles_B)  →  monomer_B.json

# Charges on monomers first (before polymerization)
submit_assign_charges_job(monomer_A)  →  monomer_A_charged.json
submit_assign_charges_job(monomer_B)  →  monomer_B_charged.json

# Then polymerize (do NOT assign FF yet)
submit_block_copolymerize_job(
    mol_files=[monomer_A_charged.json, monomer_B_charged.json],
    block_lengths=[40, 30],
    output_file=copolymer.json
)

assign_forcefield(copolymer.json, "GAFF2_mod")   # ← FF here, not before

submit_generate_cell_job(copolymer_ff.json, num_chains=10)
save_lammps_data(cell.json, "copolymer.data")
```

---

## Polymer Blend / Mixture Cell

**Tool: `submit_generate_mixture_cell_job`**

Packs a periodic box from multiple distinct pre-built polymer chains. Each component is a fully prepared (polymerised + FF-assigned) polymer JSON.

```python
# Example: PS/PMMA 50:50 blend, 5 chains each
job = submit_generate_mixture_cell_job(
    mol_files=[
        "./checkpoints/ps_chain_ff.json",
        "./checkpoints/pmma_chain_ff.json"
    ],
    chains_per_component=[5, 5],   # 5 PS + 5 PMMA = 10 chains total
    output_file="./checkpoints/ps_pmma_blend_cell.json",
    density=0.05,                  # ALWAYS start low — same rule as homopolymer cell
    temperature=300.0
)
```

**Differences from `submit_generate_cell_job`:**
- Takes a list of *already-polymerised, FF-assigned* polymer JSONs (not a single chain)
- Each component can have different MW, architecture, or chemistry
- `chains_per_component[i]` controls the stoichiometry
- Output cell JSON contains the full mixture and can be exported directly to LAMMPS data

**Use cases:**
- Polymer blends (miscibility, phase behaviour)
- Block copolymer cells with multiple distinct chain lengths
- Polymer/solvent mixtures (add small molecule JSON as one component)

---

## Notes on `poly.polyinfo_classifier`

The `classify_polymer` MCP tool wraps `radonpy.core.poly.polyinfo_classifier` directly. You do not need to call it from Python — always use the MCP tool. The Python API is documented here for reference only.

```python
from radonpy.core import poly
class_id, flags = poly.polyinfo_classifier(smiles, return_flag=True)
```

**Note:** A bug in RadonPy 1.0b1 where `set_linker_flag` crashed on raw SMILES (missing `ff_type` property) was patched into the installed copy on 2026-03-09. If RadonPy is ever reinstalled, this patch must be reapplied — see line 3065 of `poly.py`.

**What `return_flag=True` gives you that `class_id` alone does not:**
The `flags` dict shows every functional group that matched, not just the winner. A polyurethane, for example, will have `PURT=True` (wins) but also `POXI=True` if it contains an ether linkage. The MCP tool surfaces these as `co_occurring_groups` in its response — always note them in SUMMARY_LOG.

**Caution:** The classifier is a SMARTS pattern matcher — it does not know if GAFF2_mod has been validated for your specific monomer. Always cross-check against literature for novel systems. Class 1 (PHYC) is the most common failure case in PolyJarvis (see Rule B above).

---

**→ When `cell.data` is saved, proceed to `STAGE_2_EQUILIBRATION.md`**
