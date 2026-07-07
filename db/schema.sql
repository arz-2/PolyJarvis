-- PolyJarvis experimental polymer property database
-- Only real laboratory measurements (DSC, dilatometry, mechanical testing) — no MD data.
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS polymers (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    cas_no     TEXT,
    smiles     TEXT,      -- repeat-unit SMILES with * endpoints; populated separately
    poly_class TEXT,      -- PolyJarvis class code: PACR, PHYC, PEST, etc.
    category   TEXT,      -- handbook category string
    UNIQUE(name, cas_no)
);
CREATE INDEX IF NOT EXISTS idx_polymers_cas   ON polymers(cas_no);
CREATE INDEX IF NOT EXISTS idx_polymers_class ON polymers(poly_class);
CREATE INDEX IF NOT EXISTS idx_polymers_name  ON polymers(name);

CREATE TABLE IF NOT EXISTS sources (
    id    INTEGER PRIMARY KEY,
    key   TEXT UNIQUE NOT NULL,
    title TEXT,
    doi   TEXT,
    year  INTEGER
);

CREATE TABLE IF NOT EXISTS tg_measurements (
    id           INTEGER PRIMARY KEY,
    polymer_id   INTEGER NOT NULL REFERENCES polymers(id),
    tg_C         REAL,
    tg_K         REAL,
    form         TEXT,     -- isotactic / syndiotactic / atactic / conventional
    method       TEXT,     -- DSC / Mechanical method / Dilatometry / etc.
    source_id    INTEGER   REFERENCES sources(id),
    notes        TEXT,
    handbook_ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_tg_polymer ON tg_measurements(polymer_id);

CREATE TABLE IF NOT EXISTS density_measurements (
    id           INTEGER PRIMARY KEY,
    polymer_id   INTEGER NOT NULL REFERENCES polymers(id),
    density_gcm3 REAL NOT NULL,
    T_K          REAL NOT NULL DEFAULT 298.15,
    phase        TEXT NOT NULL DEFAULT 'amorphous',
    source_id    INTEGER REFERENCES sources(id),
    notes        TEXT
);
CREATE INDEX IF NOT EXISTS idx_density_polymer ON density_measurements(polymer_id);

CREATE TABLE IF NOT EXISTS mechanical_measurements (
    id         INTEGER PRIMARY KEY,
    polymer_id INTEGER NOT NULL REFERENCES polymers(id),
    property   TEXT NOT NULL,   -- bulk_modulus / youngs_modulus / shear_modulus
    value_GPa  REAL NOT NULL,
    T_K        REAL NOT NULL DEFAULT 298.15,
    source_id  INTEGER REFERENCES sources(id),
    notes      TEXT
);
CREATE INDEX IF NOT EXISTS idx_mech_polymer   ON mechanical_measurements(polymer_id);
CREATE INDEX IF NOT EXISTS idx_mech_property  ON mechanical_measurements(property);

-- Analytical density equations (Tables 7.1, 7.2 of Mark 2007).
-- The py_expr column is eval()-able with t in °C and math imported.
CREATE TABLE IF NOT EXISTS density_equations (
    id         INTEGER PRIMARY KEY,
    polymer_id INTEGER NOT NULL REFERENCES polymers(id),
    equation   TEXT NOT NULL,   -- human-readable: "1.0865 − 6.19×10⁻⁴t + 0.136×10⁻⁶t²"
    py_expr    TEXT NOT NULL,   -- Python-evaluable: "1.0865 - 6.19e-4*t + 0.136e-6*t**2"
    t_min_C    REAL NOT NULL,
    t_max_C    REAL NOT NULL,
    phase      TEXT NOT NULL DEFAULT 'melt',  -- melt or glass
    tg_C       REAL,            -- glass-equation Tg (°C); NULL for melt equations
    source_id  INTEGER REFERENCES sources(id),
    notes      TEXT
);
CREATE INDEX IF NOT EXISTS idx_deq_polymer ON density_equations(polymer_id);

CREATE TABLE IF NOT EXISTS thermal_conductivity_measurements (
    id         INTEGER PRIMARY KEY,
    polymer_id INTEGER NOT NULL REFERENCES polymers(id),
    k_WmK      REAL NOT NULL,
    T_K        REAL,            -- NULL if temperature not specified in source
    phase      TEXT,            -- amorphous / crystalline / melt / moldings
    source_id  INTEGER REFERENCES sources(id),
    notes      TEXT
);
CREATE INDEX IF NOT EXISTS idx_tc_polymer ON thermal_conductivity_measurements(polymer_id);
