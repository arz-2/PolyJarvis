-- PolyDatabase: LLM-mined index of polymer MD-simulation-literature records.
-- Source: Paudel, Shakya, Nag, Karki & An, "A structured dataset of polymers in molecular
-- dynamics simulations extracted by LLM-assisted text mining", ChemRxiv,
-- https://doi.org/10.26434/chemrxiv.15000400/v1 (posted 2026-02-25). CC BY 4.0.
-- Public dataset: Zenodo record 17401439 (polydatabase_dataset_augmented.xlsx).
--
-- This is a candidate-DOI *lead* index for planning-stage literature grounding, not a
-- ground-truth source: it is LLM-extracted (precision/recall/F1 ~0.97/0.96/0.97 against a
-- 116-paper human-annotated subset, per the source paper), not exhaustive, and every
-- candidate DOI still requires WebFetch verification against the primary paper before any
-- value is cited. For real laboratory measurements, see db/schema.sql / db/experimental_db.sqlite.
--
-- One row per polymer-force-field-property triple (the dataset's own long format).
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS md_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polymer_name TEXT NOT NULL,
    abbreviation TEXT,
    force_field TEXT,
    force_field_type TEXT,      -- All Atom / United Atom / Coarse Grained
    property TEXT,               -- density / glass_transition_temp / radius_gyration /
                                  -- youngs_modulus / diffusion_coefficient / viscosity
    value REAL,
    unit TEXT,                   -- standardized unit for `property` (see import_polydatabase.py)
    doi TEXT,
    extra_info TEXT,             -- raw JSON: temperature, pressure, chain_length_or_molecular_weight,
                                  -- number_of_chains, ensemble_or_equilibration, system_type,
                                  -- material_morphology, composition, reported_value_original_unit
    source_monomer TEXT,
    common_trade_name TEXT,
    chain_structure TEXT,        -- linear / branched / crosslinked / network
    architecture TEXT,           -- homopolymer / copolymer / other
    thermal_type TEXT,           -- thermoplastic / thermosetting / elastomer
    origin_type TEXT             -- synthetic / natural / semi-synthetic / blend
);

CREATE INDEX IF NOT EXISTS idx_md_records_polymer_name ON md_records(polymer_name);
CREATE INDEX IF NOT EXISTS idx_md_records_abbreviation ON md_records(abbreviation);
CREATE INDEX IF NOT EXISTS idx_md_records_doi ON md_records(doi);
