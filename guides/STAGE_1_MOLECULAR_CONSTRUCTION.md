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

**Class ID complete reference** *(classify_polymer returns class_id and class_name)*:

> **Routing rule — which builder to use:**
> ```
> classify_polymer()
>   ├─ PCBN, PAMD, PKTN, PSFO, PIMD  →  EMC  (pcff)
>   ├─ PHAL                           →  EMC  (opls/2024/opls-aa)
>   ├─ PHYC, PDIE, PSTR               →  EMC  (trappe-ua)
>   └─ all other classes              →  RadonPy  (GAFF2_mod + QM charges)
> ```
> Use the **EMC path** section below for the first three rows. Use the **RadonPy path** (rest of this document) for all others.

| class_id | class_name | Description | Example polymers | **FF** | Builder | Electrostatics |
|---|---|---|---|---|---|---|
| 0 | UNKNOWN | Unclassified | Bad SMILES | ❌ Stop | — | — |
| 1 | PHYC | Polyhydrocarbon | PE, PP, PIB | **TraPPE-UA** | EMC | lj/cut |
| 2 | PSTR | Polystyrenic | PS, P2VP | **TraPPE-UA** | EMC | lj/cut |
| 3 | PVNL | Polyvinyl | PVA, PVC | **OPLS-AA** | RadonPy | pppm |
| 4 | PACR | Polyacrylic | PMMA, PAA | **OPLS-AA** | RadonPy | pppm |
| 5 | PHAL | Polyhalogenated | PVDF, PTFE | **OPLS-AA** | EMC | pppm |
| 6 | PDIE | Polydiene | PBD, PI | **TraPPE-UA** | EMC | lj/cut |
| 7 | POXI | Polyoxide/Polyether | PEO, PPO | **OPLS-AA** | RadonPy | pppm |
| 8 | PSUL | Polythioether | PPS | **OPLS-AA** | RadonPy | pppm |
| 9 | PEST | Polyester | PET, PLA | **OPLS-AA** | RadonPy | pppm |
| 10 | PAMD | Polyamide | Nylon-6 | **PCFF** | EMC | pppm |
| 11 | PURT | Polyurethane | PU | **OPLS-AA** | RadonPy | pppm |
| 12 | PURA | Polyurea | Polyurea | **OPLS-AA** | RadonPy | pppm |
| 13 | PIMD | Polyimide | Kapton | **PCFF** | EMC | pppm |
| 14 | PANH | Polyanhydride | Polyanhydride | **OPLS-AA** | RadonPy | pppm |
| 15 | PCBN | Polycarbonate | BPA-PC | **PCFF** | EMC | pppm |
| 16 | PIMN | Polyamine | PEI, epoxy | **OPLS-AA** | RadonPy | pppm |
| 17 | PSIL | Polysiloxane | PDMS | **OPLS-AA** | RadonPy | pppm |
| 18 | PPHS | Polyphosphazene | Polyphosphazene | **OPLS-AA** ⚠️ | RadonPy | pppm |
| 19 | PKTN | Polyketone/PEEK | PEEK | **PCFF** | EMC | pppm |
| 20 | PSFO | Polysulfone | PSU | **PCFF** | EMC | pppm |
| 21 | PPNL | Conjugated | PPV | **OPLS-AA** | RadonPy | pppm |

⚠️ PPHS: OPLS-AA has P=N backbone types but no polyphosphazene-specific validation. Low confidence — flag results.

*EMC charges: PCFF, OPLS-AA, and TraPPE-UA charges are embedded in the force field — no QM charge step needed.*

---

## EMC Path — PCBN, PAMD, PKTN, PSFO, PIMD, PHAL, PHYC, PDIE, PSTR

If `classify_polymer` returns one of these classes, skip the RadonPy workflow entirely and use the EMC server. EMC builds the amorphous cell and assigns all force field parameters in a single pipeline step — no conformer search, charge assignment, polymerization, or FF assignment steps.

**The force field is selected automatically from `polymer_class` — do not pass a `field` argument.**

### Workflow

```
classify_polymer(smiles)
  └─ class_name in EMC set?
       └─ submit_emc_cell_job(smiles, polymer_class, ...)  → job_id
            └─ get_emc_job_status(job_id)   → poll until "completed"
                 └─ get_emc_job_output(job_id)
                      → result["data_path"]      # LAMMPS .data file
                      → result["lammps_flags"]   # {use_pcff, use_opls} for Stage 2
                           └─ → Stage 2 — data_path is local; pass lammps_flags to generate_script()
```

### `submit_emc_cell_job`

```python
job = submit_emc_cell_job(
    smiles="*OC(=O)Oc1ccc(C(C)(C)c2ccc(*)cc2)cc1",  # BPA-PC
    polymer_class="PCBN",    # determines force field automatically
    dp=20,                   # repeat units per chain [20]
    density_initial=0.6,     # ~0.5× experimental; EMC packs at this density
    ntotal=3000,             # target total atom count; EMC sets nchains from this
    temperature=300.0,
    seed=-1,                 # -1 = random seed each run
    output_name="polymer",
)
# Returns immediately: {"status": "submitted", "job_id": "abc12345", "field": "pcff", ...}
```

### Polling and retrieving the result

```python
import time
while True:
    s = get_emc_job_status(job["job_id"])
    if s["status"] == "completed":
        break
    if s["status"] == "failed":
        raise RuntimeError(s)
    time.sleep(10)

out = get_emc_job_output(job["job_id"])
data_path    = out["result"]["data_path"]     # absolute path to LAMMPS .data file
lammps_flags = out["result"]["lammps_flags"]  # e.g. {"use_pcff": True, "use_opls": False}
# → data_path is local — pass directly to generate_equilibration_workflow() in Stage 2
# → pass **lammps_flags to generate_equilibration_workflow() in Stage 2
```

### SMILES conventions for each EMC class

| class_name | FF | Polymer | Correct SMILES | Note |
|---|---|---|---|---|
| PCBN | pcff | BPA-PC | `*OC(=O)Oc1ccc(C(C)(C)c2ccc(*)cc2)cc1` | Full carbonate in repeat unit; `*` on aromatic C |
| PAMD | pcff | Nylon-6 | `*C(=O)NCCCCC*` | Amide N must be adjacent to C=O; wrong placement → `{c_1, na}` error |
| PKTN | pcff | PEEK | `*Oc1ccc(Oc2ccc(C(=O)c3ccc(*)cc3)cc2)cc1` | — |
| PSFO | pcff | PSU (Udel) | `*Oc1ccc(C(C)(C)c2ccc(Oc3ccc(S(=O)(=O)c4ccc(*)cc4)cc3)cc2)cc1` | — |
| PIMD | pcff | Kapton | `*c1ccc(n2c(=O)c3cc4c(cc3c2=O)c(=O)n(c5ccc(Oc6ccc(*)cc6)cc5)c4=O)cc1` | All imide ring atoms lowercase; uppercase N → `{na, c_1}` error |
| PHAL | opls-aa | PVDF | `*CC(F)(F)*` | — |
| PHAL | opls-aa | PTFE | `*C(F)(F)C(F)(F)*` | — |
| PHYC | trappe-ua | PE | `*CC*` | — |
| PHYC | trappe-ua | PP (atactic) | `*CC(C)*` | No chirality → atactic; use `*[C@@H](C)C*` for isotactic |
| PDIE | trappe-ua | cis-PBD | `*C/C=C\C*` | cis/trans microstructure must be encoded in SMILES |
| PSTR | trappe-ua | PS (atactic) | `*CC(c1ccccc1)*` | No chirality → atactic |

> **PCBN SMILES critical detail:** The carbonate group (`-O-C(=O)-O-`) must be fully contained within the repeat unit. If `*` is placed on the carbonyl oxygen, `oz`/`oo` PCFF templates fail silently and EMC exits with "Missing force field parameters." Always put `*` on the aromatic carbon at both chain ends.

> **PIMD SMILES critical detail:** All imide ring atoms must be lowercase (aromatic notation), including carbonyl carbons. Uppercase `N` → EMC assigns sp3 `na` type → no `c_1` increment pair.

> **TraPPE-UA tacticity note:** `[C@@H]`/`[C@H]` chirality notation works with OPLS-AA but **not** with TraPPE-UA (united-atom has no explicit H). For PHYC/PDIE/PSTR, atactic is the only option via TraPPE-UA. Use RadonPy with `tacticity="isotactic"` if stereospecific chains are required.

### Recommended density_initial by class

| class_name | density_initial | Experimental RT density |
|---|---|---|
| PCBN (BPA-PC) | 0.60 | 1.20 g/cm³ |
| PAMD (Nylon-6) | 0.57 | 1.14 g/cm³ |
| PKTN (PEEK) | 0.65 | 1.30 g/cm³ |
| PSFO (PSU) | 0.65 | 1.24 g/cm³ |
| PIMD (Kapton) | 0.70 | 1.42 g/cm³ |
| PHAL (PVDF) | 0.89 | 1.78 g/cm³ |
| PHAL (PTFE) | 1.05 | 2.17 g/cm³ |
| PHYC (PE/PP/PIB) | 0.48 | 0.91–0.97 g/cm³ |
| PDIE (PBD/PI) | 0.45 | 0.90–0.91 g/cm³ |
| PSTR (PS) | 0.53 | 1.05 g/cm³ |

Use ~0.5× experimental — low enough to avoid steric clashes; LAMMPS equilibration (Stage 2) compresses to full density.

### Decision IDs for run_log.md (EMC path)

| ID | Decision | Value |
|---|---|---|
| D-01 | Force field | auto-selected from polymer_class (see `lammps_flags` in output) |
| D-02 | Charge method | embedded in FF — no separate step |
| D-03 | Electrostatics | pppm (all except PHYC/PDIE/PSTR which use lj/cut) |
| D-04 | System size | dp and ntotal passed to submit_emc_cell_job |

---

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
# Pass this local path directly to Stage 2
```

---

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

### Copolymer Workflow (Complete)

```
build_molecule_from_smiles(smiles_A)  →  monomer_A.json
build_molecule_from_smiles(smiles_B)  →  monomer_B.json

# Charges on monomers first (before polymerization)
submit_assign_charges_job(monomer_A)  →  monomer_A_charged.json
submit_assign_charges_job(monomer_B)  →  monomer_B_charged.json

# Then polymerize (do NOT assign FF yet)
submit_copolymerize_job(
    mol_files=[monomer_A_charged.json, monomer_B_charged.json],
    degree_of_polymerization=50,
    output_file=copolymer.json
)

assign_forcefield(copolymer.json, "GAFF2_mod")   # ← FF here, not before

submit_generate_copolymer_cell_job(chain_files=[copolymer_ff.json], num_chains=10)
save_lammps_data(cell.json, "copolymer.data")
```

> **Statistical and block copolymers, and polymer blends, are not yet implemented.** See ROADMAP Track H.

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

**→ When `cell.data` is saved (local path), proceed to `STAGE_2_EQUILIBRATION.md`**
