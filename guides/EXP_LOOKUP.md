# Experimental Lookup Guide
**Read when:** You are `exp-lookup-worker` querying the experimental DB for a completed simulation run.
**Scope:** Run `db/query_best_match.py` once. Return `exp_lookup.json` path and extracted ranges. No simulation tools.

---

## What the DB contains

`db/polymer_db.sqlite` — real laboratory measurements only (no MD data):

| Table | Rows | Key fields |
|-------|------|------------|
| `tg_measurements` | ~2,400 | `tg_K`, `form` (atactic/isotactic/…), `method` (DSC/Dilatometry/…) |
| `density_measurements` | ~220 | `density_gcm3`, `T_K`, `phase` (amorphous/glass/melt) |
| `mechanical_measurements` | ~103 | `value_GPa`, `property` (bulk_modulus/youngs_modulus/shear_modulus), `T_K` |

**Known gaps (not in schema):** cooling rate, strain rate, system size, MW/DP. Matching is on structured fields only.

**No SMILES in DB** — matching is name-based. Provide `--polymer_name` as explicitly as possible.

---

## Matching priority

The script tries in order:

1. `--polymer_name` exact then LIKE (copolymers auto-excluded) → `match_confidence=high`
2. `--polymer_class` → class canonical representative → `match_confidence=medium`
3. No match → writes `{match_method: "none"}`, exits 0

If `match_method="none"`: set all range fields to `null` in RESULT — the orchestrator falls back to `polymer_rules.json` ranges.

---

## Running the script

```bash
python3 /home/alexzhao/PolyJarvis/db/query_best_match.py \
  --polymer_name "Poly(methyl methacrylate)" \
  --polymer_class PACR \
  --T_sim_K 300.0 \
  --is_glassy true \
  --properties tg,density,bulk_modulus \
  --output_path /home/alexzhao/PolyJarvis/data/<run_name>/raw/exp_lookup.json
```

All args:

| Arg | Type | Default | Notes |
|-----|------|---------|-------|
| `--polymer_name` | str | None | Canonical IUPAC name for DB lookup; prefer over class fallback |
| `--polymer_class` | str | None | PolyJarvis class code; used as fallback |
| `--T_sim_K` | float | 300.0 | Simulation temperature; picks closest density row |
| `--is_glassy` | bool str | "true" | Flags K unit context; does not filter rows |
| `--properties` | str | "tg,density,bulk_modulus" | Comma-separated; omit properties not requested |
| `--output_path` | str | required | Absolute path for output JSON |

---

## Reading the output

```json
{
  "match_method": "name_match | class_representative | none",
  "match_confidence": "high | medium | none",
  "polymer_id": 211,
  "polymer_name": "Poly(methyl methacrylate)",
  "tg": {
    "agg_median_K": 379.1,
    "agg_range_K": [378.1, 380.1],
    "n_rows": 4,
    "form_filter": "atactic/conventional",
    "preferred_method": null
  },
  "density": {
    "value_gcm3": 1.17,
    "T_K": 298.15,
    "phase": "amorphous",
    "all_range_gcm3": [1.17, 1.188]
  },
  "bulk_modulus": {
    "agg_median_GPa": 4.591,
    "agg_range_GPa": [4.082, 5.1],
    "n_rows": 2,
    "T_K_ref": 298.15
  }
}
```

**Deriving RESULT ranges from the JSON:**

| RESULT field | JSON source |
|---|---|
| `exp_tg_min_K` | `tg.agg_range_K[0]` |
| `exp_tg_max_K` | `tg.agg_range_K[1]` |
| `exp_density_min_gcm3` | `density.all_range_gcm3[0]` if present, else `density.value_gcm3` |
| `exp_density_max_gcm3` | `density.all_range_gcm3[1]` if present, else `density.value_gcm3` |
| `exp_K_min_GPa` | `bulk_modulus.agg_range_GPa[0]` |
| `exp_K_max_GPa` | `bulk_modulus.agg_range_GPa[1]` |

If a property key is missing entirely from the JSON (not in DB), set the corresponding range fields to `null` in RESULT.

---

## RESULT format

```
RESULT:
  run_name: <run_name>
  exp_lookup_path: /abs/path/to/raw/exp_lookup.json
  match_method: name_match | class_representative | none
  match_confidence: high | medium | none
  exp_tg_min_K: <value or null>
  exp_tg_max_K: <value or null>
  exp_density_min_gcm3: <value or null>
  exp_density_max_gcm3: <value or null>
  exp_K_min_GPa: <value or null>
  exp_K_max_GPa: <value or null>
  n_sources: <count of distinct source_keys across all properties, or 0>
  notes: <one sentence on match quality, or "no match — caller should use polymer_rules.json">
```

On script failure:
```
RESULT:
  error: <concise description>
  step_failed: query_best_match.py
  action_needed: <what caller should do — typically fall back to polymer_rules.json>
```
