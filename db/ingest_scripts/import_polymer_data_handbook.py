"""
db/import_polymer_data_handbook.py

Import density, Tg, mechanical moduli, and thermal conductivity from
Polymer Data Handbook (Mark, J.E., ed., Oxford University Press, 1999).

PDF: literature/PolymerDataHandbook.pdf  (1102 pages)
Polymer data entries start at ~page 117.

Properties extracted (all others are skipped):
    density              → density_measurements
    glass transition T   → tg_measurements
    tensile/flexural/Young's modulus → mechanical_measurements (youngs_modulus)
    shear modulus        → mechanical_measurements (shear_modulus)
    bulk modulus         → mechanical_measurements (bulk_modulus)
    thermal/heat conductivity → thermal_conductivity_measurements

Run from project root:
    python -m db.import_polymer_data_handbook
    python -m db.import_polymer_data_handbook --verbose
"""

import os
import re
import sys

import pdfplumber

_HERE = os.path.dirname(__file__)
_ROOT = os.path.dirname(_HERE)
PDF_PATH = os.path.join(_ROOT, "literature", "PolymerDataHandbook.pdf")

SOURCE_KEY = "PolymerDataHandbook1999"
SOURCE_TITLE = "Mark, J.E. (ed.), Polymer Data Handbook, Oxford University Press, 1999"
SOURCE_YEAR = 1999

# Property type tokens
PROP_DENSITY = "density"
PROP_TG = "tg"
PROP_YOUNGS = "youngs_modulus"
PROP_SHEAR = "shear_modulus"
PROP_BULK = "bulk_modulus"
PROP_TC = "thermal_conductivity"

MECHANICAL_PROPS = {PROP_YOUNGS, PROP_SHEAR, PROP_BULK}

# Keywords → property type.  Sorted longest-first so longer prefixes match first.
_PROP_KW_RAW = [
    ("glasstransitiont",    PROP_TG),      # "Glasstransition temperature/temp"
    ("glasstransition",     PROP_TG),      # standalone "Glasstransition"
    ("glasstemperature",    PROP_TG),
    ("amorphousdensity",    PROP_DENSITY), # "Amorphousdensity gcm3 ..."
    ("crystallinedensity",  PROP_DENSITY), # "Crystallinedensity gcm3 ..."
    ("density",             PROP_DENSITY),
    ("flexuralmodulus",     PROP_YOUNGS),
    ("tensilemodulusemodulus", PROP_YOUNGS),  # catches "TensilemodulusE modulus" artifact
    ("tensilemodulus",      PROP_YOUNGS),
    ("youngmodulus",        PROP_YOUNGS),
    ("youngsmodulus",       PROP_YOUNGS),
    ("shearmodulus",        PROP_SHEAR),
    ("bulkmodulus",         PROP_BULK),
    ("thermalconductivity", PROP_TC),
    ("heatconductivity",    PROP_TC),
]
PROP_KEYWORDS = sorted(_PROP_KW_RAW, key=lambda x: -len(x[0]))

# First-word checks that indicate a CONTINUATION of the current property
# (not a new property boundary).
#
# EXACT set: phase/condition words that must match the full first word
#   (so "melt" matches but "meltflowrate" does NOT)
_CONTINUATION_EXACT: frozenset[str] = frozenset({
    "melt", "amorphous", "crystalline", "solid", "liquid", "rubber", "glassy",
    "above", "below", "low", "high", "medium", "pure", "commercial", "cast",
    "drawn", "quenched", "annealed", "crosslinked", "uncrosslinked", "sample",
    "specimen", "film", "fiber", "conventional",
})
# PREFIX set: words that may have suffixes (e.g. "isotacticpolymer", "orientedfilm")
_CONTINUATION_PREFIXES: tuple[str, ...] = (
    "temperature", "strength", "resistance", "ratio", "factor", "coefficient",
    "parameter", "index", "conductance", "constant", "isotactic", "syndiotactic",
    "atactic", "oriented", "unoriented",
)

# Compiled patterns
REF_PAT = re.compile(r"\(\s*\d+(?:\s*[,–]\s*\d+)*\s*\)\s*$")
CAS_PAT = re.compile(r"CHEMICALREGISTRYNUMBER\s*([\d-]+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def strip_cid(text: str) -> str:
    """Remove PDF CID encoding artifacts like '(cid:255)'."""
    return re.sub(r"\(cid:\d+\)", "", text)


def clean_for_kw(line: str) -> str:
    """Lowercase, remove spaces and CID codes — for keyword matching."""
    return strip_cid(line).replace(" ", "").lower()


def is_prop_header(line: str) -> bool:
    """True if this is the 'PROPERTY  UNITS  CONDITIONS  VALUE  REFERENCE' header row."""
    n = line.replace(" ", "").upper()
    return "PROPERTY" in n and "VALUE" in n and len(line) > 20


def classify_prop(clean_line: str) -> str | None:
    """Return property type if line starts with a known keyword, else None."""
    for kw, prop_type in PROP_KEYWORDS:
        if clean_line.startswith(kw):
            return prop_type
    return None


def _is_continuation_word(first_word: str) -> bool:
    return (first_word in _CONTINUATION_EXACT or
            any(first_word.startswith(p) for p in _CONTINUATION_PREFIXES))


def is_boundary(stripped: str) -> bool:
    """
    True if the line represents a non-target property (should reset current_prop).
    Heuristic: starts with uppercase, first word is not a continuation word,
    and is not one of our target keywords.
    """
    if not stripped or not stripped[0].isupper():
        return False  # lowercase / blank → continuation data
    clean = clean_for_kw(stripped)
    if classify_prop(clean) is not None:
        return False  # it IS a target keyword
    # Extract first word (split on digit / space / paren / punct)
    first_word = re.split(r"[\s\d\(\.\,\–\—\-]", clean)[0]
    return not _is_continuation_word(first_word)


def has_reference(line: str) -> bool:
    return bool(REF_PAT.search(line))


def extract_value(line: str) -> tuple[float | None, bool]:
    """
    Extract the last numeric value from a line before its trailing reference.

    Returns (value, is_celsius) where is_celsius=True means the text carries
    an embedded °C marker — the value should be skipped for K-declared properties.
    """
    # Celsius marker: digit immediately followed by '8C' (PDF encoding of °) or '°C'
    if re.search(r"\d(?:8C|°C)", line):
        return None, True

    line_no_ref = REF_PAT.sub("", line).strip()
    line_no_ref = strip_cid(line_no_ref)

    tokens = line_no_ref.split()
    for token in reversed(tokens):
        # Resolve range (en-dash only; regular hyphen may indicate negative)
        token_val = token.split("–")[0] if "–" in token else token
        token_val = token_val.rstrip(".,;:")
        try:
            val = float(token_val.replace(",", ""))
            if abs(val) < 1e9:
                return val, False
        except ValueError:
            continue
    return None, False


def detect_unit_factor(line: str) -> float:
    """Return GPa conversion factor from a mechanical-property line."""
    u = line.upper()
    if "GPA" in u:
        return 1.0
    if "MPA" in u:
        return 1e-3
    return 1e-3  # default: most handbook mechanical values are in MPa


def _parse_pa_value_GPa(line: str) -> float | None:
    """
    Handle 'MANTISSA×10^N Pa' mechanical property lines where × is CID-encoded.

    After CID stripping, '1,940 × 10⁶ Pa' becomes '1,940106 Pa'.
    Pattern: last digit of mantissa + '10' + exponent digit(s) at end of string.
    Returns value in GPa, or None if pattern not present or unit not bare Pa.
    """
    u = line.upper()
    if "GPA" in u or "MPA" in u or "KPA" in u or "BAR" in u:
        return None
    if "PA" not in u:
        return None

    ln = strip_cid(line)
    ln = re.sub(r"(\d):(\d)", r"\1.\2", ln)
    ln_no_ref = REF_PAT.sub("", ln).strip()

    m = re.search(r"(\d)(10)([0-9]{1,2})\s*$", ln_no_ref)
    if not m:
        return None

    exp = int(m.group(3))
    mantissa_region = ln_no_ref[: m.start(1) + 1]

    m_range = re.search(r"([\d,]+\.?\d*)\s*[–\-]\s*([\d,]+\.?\d*)\s*$", mantissa_region)
    if m_range:
        mantissa = (
            float(m_range.group(1).replace(",", ""))
            + float(m_range.group(2).replace(",", ""))
        ) / 2.0
    else:
        m_single = re.search(r"([\d,]+\.?\d*)\s*$", mantissa_region)
        if not m_single:
            return None
        mantissa = float(m_single.group(1).replace(",", ""))

    return mantissa * (10 ** exp) * 1e-9  # Pa → GPa


def extract_temp_K(line: str) -> float | None:
    """Try to extract a temperature in K from conditions text."""
    m = re.search(r"(\d+)\s*K\b", line)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+)\s*(?:8C|°C)", line)
    if m:
        return float(m.group(1)) + 273.15
    return None


def extract_form(line: str) -> str | None:
    lo = line.lower()
    if "isotactic" in lo:
        return "isotactic"
    if "syndiotactic" in lo:
        return "syndiotactic"
    if "atactic" in lo:
        return "atactic"
    return None


def extract_phase(line: str) -> str:
    lo = line.lower()
    if "crystallin" in lo:
        return "crystalline"
    if "melt" in lo:
        return "melt"
    return "amorphous"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_or_create_polymer(conn, name: str, cas_no: str | None) -> int:
    """Return polymer id.  Inserts a new row if not present; merges CAS if useful."""
    if cas_no:
        row = conn.execute("SELECT id FROM polymers WHERE cas_no=?", (cas_no,)).fetchone()
        if row:
            return row[0]
    row = conn.execute("SELECT id FROM polymers WHERE name=?", (name,)).fetchone()
    if row:
        pid = row[0]
        if cas_no:
            conn.execute(
                "UPDATE polymers SET cas_no=? WHERE id=? AND cas_no IS NULL",
                (cas_no, pid),
            )
        return pid
    conn.execute("INSERT INTO polymers(name, cas_no) VALUES (?,?)", (name, cas_no))
    return conn.execute("SELECT id FROM polymers WHERE name=?", (name,)).fetchone()[0]


def _get_source_id(conn) -> int:
    return conn.execute("SELECT id FROM sources WHERE key=?", (SOURCE_KEY,)).fetchone()[0]


# ---------------------------------------------------------------------------
# Insertion
# ---------------------------------------------------------------------------

def _insert(prop: str, value: float, unit_factor: float, line: str,
            polymer_id: int, source_id: int, conn, stats: dict) -> None:
    notes = line[:300]

    if prop == PROP_DENSITY:
        if not (0.3 <= value <= 2.5):
            return
        T_K = extract_temp_K(line) or 298.15
        phase = extract_phase(line)
        conn.execute(
            "INSERT INTO density_measurements"
            "(polymer_id, density_gcm3, T_K, phase, source_id, notes)"
            " VALUES (?,?,?,?,?,?)",
            (polymer_id, value, T_K, phase, source_id, notes),
        )
        stats["density"] += 1

    elif prop == PROP_TG:
        tg_K = value
        if not (100.0 <= tg_K <= 1500.0):
            return
        # Known-bad: PVC (polymer_id=634) Tg=463 K is a PDF layout artifact —
        # the 463 K value belongs to PSU (Tg~459-463 K) on an adjacent page but
        # was parsed under the PVC entry. True PVC Tg ~354 K (PolymerHandbook4ed).
        if polymer_id == 634 and abs(tg_K - 463.0) < 1.0:
            return
        tg_C = tg_K - 273.15
        form = extract_form(line)
        conn.execute(
            "INSERT INTO tg_measurements"
            "(polymer_id, tg_C, tg_K, form, source_id, notes)"
            " VALUES (?,?,?,?,?,?)",
            (polymer_id, tg_C, tg_K, form, source_id, notes),
        )
        stats["tg"] += 1

    elif prop in MECHANICAL_PROPS:
        val_GPa = value * unit_factor
        if not (0.0 < val_GPa <= 50.0):
            return
        prop_col = {
            PROP_YOUNGS: "youngs_modulus",
            PROP_SHEAR: "shear_modulus",
            PROP_BULK: "bulk_modulus",
        }[prop]
        T_K = extract_temp_K(line) or 298.15
        conn.execute(
            "INSERT INTO mechanical_measurements"
            "(polymer_id, property, value_GPa, T_K, source_id, notes)"
            " VALUES (?,?,?,?,?,?)",
            (polymer_id, prop_col, val_GPa, T_K, source_id, notes),
        )
        stats["mech"] += 1

    elif prop == PROP_TC:
        if not (0.0 < value <= 500.0):
            return
        T_K = extract_temp_K(line)
        lo = line.lower()
        if "crystallin" in lo:
            phase = "crystalline"
        elif "amorphous" in lo:
            phase = "amorphous"
        elif "melt" in lo:
            phase = "melt"
        else:
            phase = None
        conn.execute(
            "INSERT INTO thermal_conductivity_measurements"
            "(polymer_id, k_WmK, T_K, phase, source_id, notes)"
            " VALUES (?,?,?,?,?,?)",
            (polymer_id, value, T_K, phase, source_id, notes),
        )
        stats["tc"] += 1


# ---------------------------------------------------------------------------
# Page parser
# ---------------------------------------------------------------------------

_STOP_WORDS = re.compile(
    r"^(?:REFERENCES?|Synthesis|PolymerDataHandbook|Polymer\s+Data\s+Handbook)\b",
    re.IGNORECASE,
)
_PAGE_FOOTER = re.compile(r"^\d{2,4}\s+Polymer")


def parse_page(text: str, polymer_id: int, source_id: int, conn, stats: dict) -> None:
    """Parse one page of property tables and insert relevant rows."""
    raw_lines = text.splitlines()
    lines = [strip_cid(l).rstrip() for l in raw_lines]

    # Find first PROPERTY header; skip pages with none
    start_idx = None
    for i, l in enumerate(lines):
        if is_prop_header(l):
            start_idx = i + 1
            break
    if start_idx is None:
        return

    current_prop: str | None = None
    unit_factor: float = 1.0

    for line in lines[start_idx:]:
        stripped = line.strip()
        if not stripped:
            continue
        if _STOP_WORDS.match(stripped) or _PAGE_FOOTER.match(stripped):
            break
        # Secondary PROPERTY header resets state (multiple tables on same page)
        if is_prop_header(stripped):
            current_prop = None
            continue

        clean = clean_for_kw(stripped)

        # --- Check for a target property keyword ---
        new_prop = classify_prop(clean)
        if new_prop is not None:
            current_prop = new_prop
            unit_factor = detect_unit_factor(stripped) if new_prop in MECHANICAL_PROPS else 1.0
            if has_reference(stripped):
                # For bare-Pa lines (e.g. "1,940×10⁶ Pa" CID-encoded as "1,940106 Pa"),
                # the standard extract_value + unit_factor path produces the wrong result.
                # Try the specialized Pa parser first for mechanical properties.
                inserted = False
                if new_prop in MECHANICAL_PROPS:
                    pa_val = _parse_pa_value_GPa(stripped)
                    if pa_val is not None and 0.0 < pa_val <= 50.0:
                        _insert(new_prop, pa_val, 1.0, stripped,
                                polymer_id, source_id, conn, stats)
                        inserted = True

                if not inserted:
                    val, is_c = extract_value(stripped)
                    if is_c and new_prop == PROP_TG:
                        pass  # skip Celsius Tg values
                    elif val is not None and val > 0:
                        _insert(new_prop, val, unit_factor, stripped,
                                polymer_id, source_id, conn, stats)
                # Mechanical properties: don't continue into next lines
                # (avoids capturing temperature-coefficient rows like "dE/dT MPa/K")
                if new_prop in MECHANICAL_PROPS:
                    current_prop = None
            continue

        # --- Non-target property boundary → reset ---
        if is_boundary(stripped):
            current_prop = None
            continue

        # --- Continuation line (Tg and density only, after resetting mech) ---
        if current_prop is not None and has_reference(stripped):
            val, is_c = extract_value(stripped)
            if is_c and current_prop == PROP_TG:
                continue
            if val is not None and val > 0:
                _insert(current_prop, val, unit_factor, stripped,
                        polymer_id, source_id, conn, stats)
            # After inserting a continuation for mechanical props, stop
            if current_prop in MECHANICAL_PROPS:
                current_prop = None


# ---------------------------------------------------------------------------
# Entry detection
# ---------------------------------------------------------------------------

def is_entry_start(text: str) -> bool:
    return "CLASS" in text and (
        "MAJOR APPLICATIONS" in text or "MAJORAPPLICATIONS" in text
    )


def extract_polymer_name(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "Polymer Data Handbook" in line or "PolymerDataHandbook" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        # Skip ALL-CAPS author lines (e.g., "SHAW LING HSU")
        if re.match(r"^[A-Z][A-Z\s\.,\-]+$", line) and len(line) < 80:
            continue
        return line
    return None


def extract_cas(text: str) -> str | None:
    m = CAS_PAT.search(text.replace(" ", ""))
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Compressibility → bulk modulus (second pass)
# ---------------------------------------------------------------------------

def parse_compress_to_K_GPa(raw_line: str) -> float | None:
    """
    Parse a compressibility line from PolymerDataHandbook1999 and return K_T in GPa.

    Two unit formats appear in the PDF:

    Format A — bar⁻¹  (PS, PVC, PEEK, …):
        raw: 'Compressibility bar(cid:255)1 ... MANTISSA(cid:2)10(cid:255)N (ref)'
        stripped: 'Compressibility bar1 ... MANTISSA10N (ref)'
        (cid:2)=× and (cid:255)=− are both removed, so '× 10⁻N' → '10N' appended to mantissa.
        κ [bar⁻¹] = mantissa × 10⁻ᴺ
        K [GPa]   = 10⁻⁴ / κ [bar⁻¹]     (since 1 bar = 10⁻⁴ GPa)

    Format B — Pa⁻¹×10⁻¹⁰  (cis-PBD, …):
        raw: 'Compressibility P(cid:255)1(cid:2)10(cid:255)10 ... VALUE (ref)'
        stripped: 'Compressibility P11010 ... VALUE (ref)'
        The exponent is in the unit field; VALUE is a plain float.
        κ [Pa⁻¹] = VALUE × 10⁻ᴱˣᴾ
        K [GPa]   = 10⁻⁹ / κ [Pa⁻¹]
    """
    ln = strip_cid(raw_line)
    # Normalise colon-as-decimal-point PDF artifact (e.g. "9:302" → "9.302")
    ln = re.sub(r"(\d):(\d)", r"\1.\2", ln)
    ln_no_ref = REF_PAT.sub("", ln).strip()

    upper = ln_no_ref.upper()

    # ---- Format A: bar⁻¹ ---------------------------------------------------
    if "BAR" in upper:
        # After CID stripping, the value looks like "MANTISSA10N" where N is the
        # single exponent digit.  Find the last occurrence of (digit)(10)(digit)$
        # to split mantissa from the exponent encoding.
        m = re.search(r"(\d)(10)([0-9])\s*$", ln_no_ref)
        if not m:
            return None
        neg_exp = int(m.group(3))
        # Everything up to (and including) m.group(1) is the mantissa region
        mantissa_region = ln_no_ref[: m.start(1) + 1]

        # Try range "A–B" first, take the arithmetic mean
        m_range = re.search(r"(\d+\.?\d*)\s*[–\-]\s*(\d+\.?\d*)\s*$", mantissa_region)
        if m_range:
            v1 = float(m_range.group(1))
            v2 = float(m_range.group(2))
            mantissa = (v1 + v2) / 2.0
        else:
            m_single = re.search(r"(\d+\.?\d*)\s*$", mantissa_region)
            if not m_single:
                return None
            mantissa = float(m_single.group(1))

        kappa_bar = mantissa * 10 ** (-neg_exp)
        if kappa_bar <= 0:
            return None
        return 1e-4 / kappa_bar  # K in GPa

    # ---- Format B: Pa⁻¹ with exponent in unit field ------------------------
    # Detect "P1" followed by "10" + two-digit exponent (e.g. "P11010" = Pa⁻¹×10⁻¹⁰)
    m_unit = re.search(r"P1\s*10(\d{1,2})\b", ln_no_ref)
    if m_unit:
        neg_exp = int(m_unit.group(1))
        # Value is a plain float; extract last number before the reference
        val, _ = extract_value(raw_line)
        if val is None or val <= 0:
            return None
        kappa_pa = val * 10 ** (-neg_exp)
        return 1e-9 / kappa_pa  # K in GPa

    return None


def _compress_pass(pdf_path: str, source_id: int, conn, verbose: bool = False) -> int:
    """
    Second-pass scan: find every 'Compressibility' line, compute K_T = 1/κ,
    and insert as bulk_modulus into mechanical_measurements.

    Uses only polymers already present in the DB (no new polymers inserted).
    Safe to run after the main run() — adds rows without touching existing ones.
    """
    n_inserted = 0
    current_polymer_id: int | None = None

    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            if verbose and i % 100 == 0:
                print(f"  [compress pass] page {i+1}/{n_pages} …")
            text = page.extract_text() or ""
            if not text.strip():
                continue

            if is_entry_start(text):
                name = extract_polymer_name(text)
                if name:
                    row = conn.execute(
                        "SELECT id FROM polymers WHERE name=?", (name,)
                    ).fetchone()
                    current_polymer_id = row[0] if row else None
                else:
                    current_polymer_id = None

            if current_polymer_id is None:
                continue

            for raw_line in text.splitlines():
                stripped = raw_line.strip()
                if not stripped.lower().replace(" ", "").startswith("compressib"):
                    continue
                if not has_reference(strip_cid(stripped)):
                    continue

                K_GPa = parse_compress_to_K_GPa(stripped)
                if K_GPa is None or not (0.1 < K_GPa < 100.0):
                    continue

                T_K = extract_temp_K(strip_cid(stripped)) or 298.15
                # Known-bad: PEEK (polymer_id=963) K=1.075 GPa is derived from
                # κ=9.30e-5 bar⁻¹ — a rubbery-state measurement (T>Tg_PEEK~418K)
                # that defaulted to T=298K. Glassy PEEK K is ~4-7 GPa. Skip.
                if current_polymer_id == 963 and abs(K_GPa - 1.075) < 0.01:
                    continue

                notes = (
                    f"K_T = 1/κ derived from compressibility. "
                    f"Source line: {strip_cid(stripped)[:220]}"
                )
                conn.execute(
                    "INSERT INTO mechanical_measurements"
                    "(polymer_id, property, value_GPa, T_K, source_id, notes)"
                    " VALUES (?,?,?,?,?,?)",
                    (current_polymer_id, "bulk_modulus", K_GPa, T_K, source_id, notes),
                )
                n_inserted += 1
                if verbose:
                    print(
                        f"    [{i+1}] polymer_id={current_polymer_id}  "
                        f"K={K_GPa:.3f} GPa  T_K={T_K}  "
                        f"| {strip_cid(stripped)[:70]}"
                    )

    conn.commit()
    return n_inserted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(pdf_path: str = PDF_PATH, db_path: str | None = None,
        verbose: bool = False) -> None:
    import db as polymer_db  # noqa: PLC0415

    if db_path:
        polymer_db.DB_PATH = db_path
    polymer_db.init_db()
    conn = polymer_db._get_conn()

    # Register source
    conn.execute(
        "INSERT OR IGNORE INTO sources(key, title, year) VALUES (?,?,?)",
        (SOURCE_KEY, SOURCE_TITLE, SOURCE_YEAR),
    )
    conn.commit()
    source_id = _get_source_id(conn)

    stats: dict[str, int] = {"density": 0, "tg": 0, "mech": 0, "tc": 0}
    n_entries = 0
    current_polymer_id: int | None = None

    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            if verbose and i % 100 == 0:
                print(f"  page {i+1}/{n_pages} …")
            text = page.extract_text() or ""
            if not text.strip():
                continue

            if is_entry_start(text):
                name = extract_polymer_name(text)
                if name:
                    cas = extract_cas(strip_cid(text))
                    current_polymer_id = _get_or_create_polymer(conn, name, cas)
                    n_entries += 1
                    if verbose:
                        print(f"    [{i+1}] {name}  CAS={cas}")
                else:
                    current_polymer_id = None

            if current_polymer_id is not None:
                parse_page(text, current_polymer_id, source_id, conn, stats)

    conn.commit()

    # Second pass: derive bulk modulus from compressibility lines
    n_bulk = _compress_pass(pdf_path, source_id, conn, verbose=verbose)

    n_poly_total = conn.execute("SELECT COUNT(*) FROM polymers").fetchone()[0]
    print(f"Polymer entries seen:      {n_entries}")
    print(f"Tg rows inserted:          {stats['tg']}")
    print(f"Density rows:              {stats['density']}")
    print(f"Mechanical property rows:  {stats['mech']}")
    print(f"Bulk modulus (1/κ) rows:   {n_bulk}")
    print(f"Thermal conductivity rows: {stats['tc']}")
    print(f"Total polymers in DB:      {n_poly_total}")


def run_compressibility_only(pdf_path: str = PDF_PATH, db_path: str | None = None,
                             verbose: bool = False) -> None:
    """Run only the compressibility second pass (no re-import of other properties)."""
    import db as polymer_db  # noqa: PLC0415

    if db_path:
        polymer_db.DB_PATH = db_path
    polymer_db.init_db()
    conn = polymer_db._get_conn()

    conn.execute(
        "INSERT OR IGNORE INTO sources(key, title, year) VALUES (?,?,?)",
        (SOURCE_KEY, SOURCE_TITLE, SOURCE_YEAR),
    )
    conn.commit()
    source_id = _get_source_id(conn)

    n = _compress_pass(pdf_path, source_id, conn, verbose=verbose)
    print(f"Bulk modulus rows inserted (from compressibility): {n}")


if __name__ == "__main__":
    _verbose = "--verbose" in sys.argv or "-v" in sys.argv
    if "--compressibility-only" in sys.argv:
        run_compressibility_only(verbose=_verbose)
    else:
        run(verbose=_verbose)
