"""
import_mark2007.py — extract density equations and thermal conductivity from
Physical Properties of Polymers Handbook, 2nd ed. (Mark 2007, Springer).

Source PDF: literature/Physical_Properties_Polymers_Handbook_Mark2007.pdf

Tables extracted:
  7.1  Density equations above Tg (melt state)   → density_equations + density_measurements
  7.2  Density equations for glasses              → density_equations + density_measurements
  10.1 Thermal conductivity k (W/m K)             → thermal_conductivity_measurements

Tables skipped:
  7.3  Discrete density matrix — text layer is reversed/garbled in this PDF
  7.4  Thermal expansion — reversed text layer
  7.5/7.6  Tait equation parameters — not yet implemented
  9.1  Heat capacities — complex multi-column structure (future work)

PDF page mapping (0-indexed):
  Table 7.1   → page 102  (book page 94)
  Table 7.2   → page 103  (book page 95)
  Table 10.1  → pages 162–165  (book pages 156–159)

Run from the project root:
    python -m db.import_mark2007
"""

import math
import os
import re
import sys

import pdfplumber

_HERE = os.path.dirname(__file__)
_ROOT = os.path.dirname(_HERE)
PDF_PATH = os.path.join(_ROOT, "literature",
                        "Physical_Properties_Polymers_Handbook_Mark2007.pdf")

SOURCE_KEY = "Mark2007"
SOURCE_TITLE = ("Mark, J.E. (ed.), Physical Properties of Polymers Handbook, "
                "2nd ed., Springer, 2007")
SOURCE_DOI = "10.1007/978-0-387-69002-5"
SOURCE_YEAR = 2007

# PDF pages for each table (0-indexed)
PAGE_TABLE_71 = 102
PAGE_TABLE_72 = 103
PAGES_TABLE_101 = list(range(162, 166))  # pages 163-166 (1-indexed)


# ---------------------------------------------------------------------------
# CID / encoding helpers
# ---------------------------------------------------------------------------

def _decode_decimal(text: str) -> str:
    """Replace PDF's colon-as-decimal-point: '1:316' → '1.316'.

    Only replaces ':' between two digits to avoid touching polymer names.
    """
    return re.sub(r'(\d):(\d)', r'\1.\2', text)


def _cid_to_python(raw: str) -> str:
    """Convert a raw equation string (with CID codes) to a Python expression.

    CID mapping in this PDF:
      (cid:2) → minus sign (−)
      (cid:7) → multiplication (×)
    The plus sign uses the Latin character þ in this encoding.
    Exponents: t2 = t², t3 = t³ (superscripts flattened to ASCII by pdfplumber).
    """
    s = raw
    # Cubic t³ terms — must come before quadratic to avoid partial matches
    s = re.sub(r'\(cid:7\)10\(cid:2\)(\d+)t3',
               lambda m: f'*1e-{m.group(1)}*t**3', s)
    # Quadratic t² terms
    s = re.sub(r'\(cid:7\)10\(cid:2\)(\d+)t2',
               lambda m: f'*1e-{m.group(1)}*t**2', s)
    # Linear t terms (not followed by 2 or 3)
    s = re.sub(r'\(cid:7\)10\(cid:2\)(\d+)t(?![23\d])',
               lambda m: f'*1e-{m.group(1)}*t', s)
    # þ → +
    s = s.replace('þ', '+')
    # Remaining (cid:2) → minus
    s = s.replace('(cid:2)', '-')
    # Fix decimal points
    s = _decode_decimal(s)
    # exp() → math.exp() with multiplication from preceding coefficient
    s = re.sub(r'(\d)exp\(', r'\1*math.exp(', s)
    return s.strip()


def _cid_to_human(raw: str) -> str:
    """Convert raw equation to a human-readable Unicode string."""
    s = raw
    s = re.sub(r'\(cid:7\)10\(cid:2\)(\d+)t3',
               lambda m: f'×10⁻{m.group(1)}t³', s)
    s = re.sub(r'\(cid:7\)10\(cid:2\)(\d+)t2',
               lambda m: f'×10⁻{m.group(1)}t²', s)
    s = re.sub(r'\(cid:7\)10\(cid:2\)(\d+)t(?![23\d])',
               lambda m: f'×10⁻{m.group(1)}t', s)
    s = s.replace('þ', '+')
    s = s.replace('(cid:2)', '−')
    s = _decode_decimal(s)
    return s.strip()


def _eval_equation(py_expr: str, t: float) -> float | None:
    """Evaluate a density equation at temperature t (°C)."""
    try:
        return float(eval(py_expr, {'math': math, 't': t}))
    except Exception:
        return None


def _has_unclosed_paren(s: str) -> bool:
    return s.count('(') > s.count(')')


def _normalize_polymer_name(raw: str) -> str:
    """Best-effort normalization of PDF-extracted polymer names.

    pdfplumber drops inter-word spaces in typeset text.  We add:
    - space before capital letters that follow lowercase
    - space after commas not followed by space
    Leaves parenthetical expressions intact.
    """
    s = raw.strip()
    # Add spaces after commas
    s = re.sub(r',([^\s\)])', r', \1', s)
    # Add space before capital letter that follows lowercase (outside parens)
    s = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', s)
    return s


# ---------------------------------------------------------------------------
# Table 7.1 / 7.2 parser
# ---------------------------------------------------------------------------

_REF_PATTERN = re.compile(r'\[[\d,\s]+\]\s*$')
_RANGE_PATTERN = re.compile(
    r'(?:\(cid:2\))?(\d+)\s*[–\-]\s*(?:\(cid:2\))?(\d+)\s*$'
)


def _parse_temp_range(range_str: str) -> tuple[float, float] | None:
    """Parse '236–295' or '(cid:2)30–20' into (t_min, t_max) in °C."""
    m = re.match(
        r'(\(cid:2\))?(\d+(?:\.\d+)?)\s*[–\-]\s*(\(cid:2\))?(\d+(?:\.\d+)?)',
        range_str.strip()
    )
    if not m:
        return None
    t_min = -float(m.group(2)) if m.group(1) else float(m.group(2))
    t_max = -float(m.group(4)) if m.group(3) else float(m.group(4))
    return t_min, t_max


def _strip_ref_and_range(line: str):
    """Return (equation_and_name, t_min, t_max, ref) or None."""
    # Strip reference
    ref_m = _REF_PATTERN.search(line)
    if not ref_m:
        return None
    ref = ref_m.group(0).strip()
    rest = line[:ref_m.start()].strip()

    # Strip temp range
    range_m = _RANGE_PATTERN.search(rest)
    if not range_m:
        return None
    range_str = range_m.group(0).strip()
    t_range = _parse_temp_range(range_str)
    if not t_range:
        return None
    rest = rest[:range_m.start()].strip()

    return rest, t_range[0], t_range[1], ref


def _split_name_and_eq(rest: str) -> tuple[str | None, str]:
    """Split 'PolymerName  1:234...' into (name, equation_raw).

    Returns (None, equation_raw) for continuation lines.
    """
    # Equation always starts with digit:digit or digit.digit
    m = re.search(r'\s+(\d+[:.]\d+.+)$', rest)
    if m:
        name = _normalize_polymer_name(rest[:m.start()])
        eq_raw = m.group(1).strip()
        return name or None, eq_raw
    # Continuation line — starts directly with equation
    if re.match(r'^\d+[:.]\d+', rest) or rest.startswith('(cid:2)'):
        return None, rest.strip()
    return None, rest


def parse_table71(text: str) -> list[dict]:
    """Parse Table 7.1 text (density equations above Tg)."""
    results = []
    current_polymer = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip header / section lines (no reference bracket at end)
        parsed = _strip_ref_and_range(line)
        if not parsed:
            continue
        rest, t_min, t_max, ref = parsed

        name, eq_raw = _split_name_and_eq(rest)
        if name:
            current_polymer = name
        if not current_polymer:
            continue

        py_expr = _cid_to_python(eq_raw)
        human_eq = _cid_to_human(eq_raw)

        # Evaluate at 25°C; if out of range, evaluate at t_min
        if t_min <= 25 <= t_max:
            t_eval, extrapolated = 25.0, False
        else:
            t_eval, extrapolated = t_min, True

        density = _eval_equation(py_expr, t_eval)
        if density is None:
            continue

        results.append({
            'polymer': current_polymer,
            'equation': human_eq,
            'py_expr': py_expr,
            't_min_C': t_min,
            't_max_C': t_max,
            'phase': 'melt',
            'tg_C': None,
            'ref': ref,
            'density_gcm3': density,
            'T_eval_C': t_eval,
            'extrapolated': extrapolated,
        })

    return results


def parse_table72(text: str) -> list[dict]:
    """Parse Table 7.2 text (density equations for glassy polymers).

    Each line: [PolymerName]  Tg_C  equation  temp_range  [ref]
    Continuation lines: Tg_C  equation  temp_range  [ref]
    """
    results = []
    current_polymer = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parsed = _strip_ref_and_range(line)
        if not parsed:
            continue
        rest, t_min, t_max, ref = parsed

        # Try to extract Tg value: an integer before the equation
        # Equation starts at the first 'digit:digit' or 'digit.digit' pattern
        eq_m = re.search(r'(\d+[:.]\d+.*)$', rest)
        if not eq_m:
            continue
        eq_raw = eq_m.group(1).strip()
        before_eq = rest[:eq_m.start()].strip()

        # before_eq = "PolymerName TgC" or "TgC" (continuation) or "PolymerName"
        tg_m = re.search(r'\s+(\d+(?:\.\d+)?)\s*$', before_eq)
        if tg_m:
            tg_C = float(tg_m.group(1))
            name_part = before_eq[:tg_m.start()].strip()
        else:
            # Try: entire before_eq is integer (continuation, no polymer name)
            int_only = re.match(r'^(\d+)\s*$', before_eq)
            if int_only:
                tg_C = float(int_only.group(1))
                name_part = ''
            else:
                tg_C = None
                name_part = before_eq

        if name_part:
            current_polymer = _normalize_polymer_name(name_part)
        if not current_polymer:
            continue

        py_expr = _cid_to_python(eq_raw)
        human_eq = _cid_to_human(eq_raw)

        if t_min <= 25 <= t_max:
            t_eval, extrapolated = 25.0, False
        else:
            t_eval, extrapolated = max(t_min, 0.0), True

        density = _eval_equation(py_expr, t_eval)
        if density is None:
            continue

        results.append({
            'polymer': current_polymer,
            'equation': human_eq,
            'py_expr': py_expr,
            't_min_C': t_min,
            't_max_C': t_max,
            'phase': 'glass',
            'tg_C': tg_C,
            'ref': ref,
            'density_gcm3': density,
            'T_eval_C': t_eval,
            'extrapolated': extrapolated,
        })

    return results


# ---------------------------------------------------------------------------
# Table 10.1 parser (thermal conductivity)
# ---------------------------------------------------------------------------

# Known phase / grade sub-entry qualifiers — these appear as indented labels under a
# parent polymer and should NOT become new polymer names.
_PHASE_WORDS = {
    'moldings': 'moldings',
    'crystalline': 'crystalline',
    'amorphous': 'amorphous',
    'melt': 'melt',
    'rigid': 'rigid',
    'flexible': 'flexible',
    'chlorinated': 'chlorinated',
    'crosslinked': 'crosslinked',
    'oriented': 'oriented',
    'foam': 'foam',
    'foamed': 'foam',
    # Grade / processing type qualifiers
    'castinggrade': 'casting grade',
    'castingresin': 'casting resin',
    'cast': 'cast',
    'moldinggrade': 'molding grade',
    'extrusiongrade': 'extrusion grade',
    'injectionmoldinggrade': 'injection molding grade',
    # Vulcanizate qualifiers (rubber sub-entries)
    'carbonblackvulcanizate': 'carbon black vulcanizate',
    'carbonblackvulcanizates': 'carbon black vulcanizate',
    'puregumvulcanizate': 'pure gum vulcanizate',
    'puregumvulcanizates': 'pure gum vulcanizate',
    'puregunvculcanizate': 'pure gum vulcanizate',  # typo in PDF
    'unvulcanized': 'unvulcanized',
    # Generic qualifiers
    'elastomer': 'elastomer',
    'thermoplastic': 'thermoplastic',
    'at0.82atm': 'at 0.82 atm',
    # Density variants for polyethylene
    'highdensity': 'high density',
    'lowdensity': 'low density',
    'mediumdensity': 'medium density',
}

# Known section headers (all caps or specific words)
_SECTION_HEADERS = {
    'polyamides', 'polycarbonates,polyesters,polyethers,andpolyketones',
    'epoxides', 'halogenatedolefinpolymers', 'hydrocarbonpolymers',
    'polyimides', 'phenolicresins', 'polysaccharides', 'polysiloxanes',
    'polysulfideandpolysulfones', 'polyurethanes', 'vinylpolymers',
    'others', 'polyesters', 'polyethers', 'reinforcedpolymers',
}

_TC_VALUE = re.compile(
    r'^(.+?)\s+'                    # label / polymer name
    r'(?:(\d{2,4})\s+)?'           # optional temperature K
    r'([\d.]+(?:[–\-][\d.]+)?)'    # k value or range
    r'\s+\[([\d,]+)\]\s*$'         # reference
)


def parse_table101(pages_text: str) -> list[dict]:
    """Parse Table 10.1 (thermal conductivity) from concatenated page text."""
    results = []
    current_polymer = None

    for line in pages_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r'(?i)(polymer|temperature|reference|table|chapter)', line):
            continue
        normalized = line.lower().replace(' ', '').replace(',', '')
        if normalized in _SECTION_HEADERS:
            continue

        m = _TC_VALUE.match(line)
        if not m:
            if not re.search(r'[\d.]+\s*\[', line):
                first_word = line.split()[0].lower() if line.split() else ''
                if first_word in _PHASE_WORDS:
                    pass  # sub-entry qualifier without measurement — keep current_polymer
                elif re.match(r'^\d', line):
                    pass  # composition qualifier (e.g. "23.5%Styrene") — skip
                elif (current_polymer and _has_unclosed_paren(current_polymer)
                      and re.match(r'^[a-z(]', line)):
                    # Continuation of multi-line polymer name
                    old_name = current_polymer
                    current_polymer = _normalize_polymer_name(
                        current_polymer + ' ' + line
                    )
                    # Patch any recently stored results that used the incomplete name
                    for r in reversed(results):
                        if r['polymer'] == old_name:
                            r['polymer'] = current_polymer
                        else:
                            break
                elif len(line) > 5:
                    current_polymer = _normalize_polymer_name(line)
            continue

        label = m.group(1).strip()
        temp_str = m.group(2)
        k_str = m.group(3)
        ref = f'[{m.group(4)}]'

        if 'dependence' in label.lower():
            continue
        # Skip range-valued entries (e.g. "0.24–0.34") — ambiguous
        if '–' in k_str or '-' in k_str:
            continue
        # Skip temperature-continuation rows (label is a bare integer like 273, 373)
        # and composition qualifiers starting with a digit (e.g. "35%Acrylonitrile")
        if re.match(r'^\d', label):
            continue

        try:
            k_val = float(k_str)
        except ValueError:
            continue

        T_K = float(temp_str) if temp_str else None

        # Strip trailing temperature values that the lazy regex captures as part of label
        # e.g. "Poly(ethylacrylate) 310.9" → "Poly(ethylacrylate)"
        label = re.sub(r'\s+\d+\.?\d*\s*$', '', label).strip()
        if not label:
            continue

        first_word = re.split(r'[\s,;:]+', label.lower())[0]
        if first_word in _PHASE_WORDS:
            phase = _PHASE_WORDS[first_word]
        else:
            current_polymer = _normalize_polymer_name(label)
            phase = None

        if not current_polymer:
            continue

        results.append({
            'polymer': current_polymer,
            'k_WmK': k_val,
            'T_K': T_K,
            'phase': phase,
            'ref': ref,
        })

    return results


# ---------------------------------------------------------------------------
# Database insertion helpers
# ---------------------------------------------------------------------------

def _get_or_create_polymer(conn, name: str) -> int:
    """Return polymer id, inserting a new row if needed."""
    row = conn.execute(
        "SELECT id FROM polymers WHERE name = ?", (name,)
    ).fetchone()
    if row:
        return row[0]
    conn.execute(
        "INSERT INTO polymers(name) VALUES (?)", (name,)
    )
    return conn.execute(
        "SELECT id FROM polymers WHERE name = ?", (name,)
    ).fetchone()[0]


def _get_source_id(conn, key: str) -> int:
    return conn.execute(
        "SELECT id FROM sources WHERE key = ?", (key,)
    ).fetchone()[0]


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(pdf_path: str = PDF_PATH, db_path: str | None = None) -> None:
    import db as polymer_db  # noqa: PLC0415
    if db_path:
        polymer_db.DB_PATH = db_path
    polymer_db.init_db()

    conn = polymer_db._get_conn()

    # Upsert source
    conn.execute(
        "INSERT OR IGNORE INTO sources(key, title, doi, year) VALUES (?,?,?,?)",
        (SOURCE_KEY, SOURCE_TITLE, SOURCE_DOI, SOURCE_YEAR),
    )
    conn.commit()
    source_id = _get_source_id(conn, SOURCE_KEY)

    eq_rows = 0
    density_rows = 0
    tc_rows = 0

    with pdfplumber.open(pdf_path) as pdf:
        # --- Tables 7.1 and 7.2 ---
        text_71 = pdf.pages[PAGE_TABLE_71].extract_text() or ""
        text_72 = pdf.pages[PAGE_TABLE_72].extract_text() or ""

        for record in parse_table71(text_71):
            pid = _get_or_create_polymer(conn, record['polymer'])
            conn.execute(
                """INSERT INTO density_equations
                   (polymer_id, equation, py_expr, t_min_C, t_max_C,
                    phase, tg_C, source_id, notes)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (pid, record['equation'], record['py_expr'],
                 record['t_min_C'], record['t_max_C'],
                 'melt', None, source_id,
                 f"Table 7.1 ref {record['ref']}")
            )
            eq_rows += 1
            notes = (f"Evaluated from Mark2007 Table 7.1 equation at "
                     f"t={record['T_eval_C']:.0f}°C"
                     + (" (extrapolated)" if record['extrapolated'] else ""))
            conn.execute(
                """INSERT INTO density_measurements
                   (polymer_id, density_gcm3, T_K, phase, source_id, notes)
                   VALUES (?,?,?,?,?,?)""",
                (pid, record['density_gcm3'],
                 record['T_eval_C'] + 273.15,
                 'melt', source_id, notes)
            )
            density_rows += 1

        for record in parse_table72(text_72):
            pid = _get_or_create_polymer(conn, record['polymer'])
            conn.execute(
                """INSERT INTO density_equations
                   (polymer_id, equation, py_expr, t_min_C, t_max_C,
                    phase, tg_C, source_id, notes)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (pid, record['equation'], record['py_expr'],
                 record['t_min_C'], record['t_max_C'],
                 'glass', record['tg_C'], source_id,
                 f"Table 7.2 ref {record['ref']}")
            )
            eq_rows += 1
            notes = (f"Evaluated from Mark2007 Table 7.2 equation at "
                     f"t={record['T_eval_C']:.0f}°C"
                     + (" (extrapolated)" if record['extrapolated'] else ""))
            conn.execute(
                """INSERT INTO density_measurements
                   (polymer_id, density_gcm3, T_K, phase, source_id, notes)
                   VALUES (?,?,?,?,?,?)""",
                (pid, record['density_gcm3'],
                 record['T_eval_C'] + 273.15,
                 'glass', source_id, notes)
            )
            density_rows += 1

        # --- Table 10.1 ---
        tc_text = '\n'.join(
            pdf.pages[p].extract_text() or "" for p in PAGES_TABLE_101
        )
        for record in parse_table101(tc_text):
            pid = _get_or_create_polymer(conn, record['polymer'])
            conn.execute(
                """INSERT INTO thermal_conductivity_measurements
                   (polymer_id, k_WmK, T_K, phase, source_id, notes)
                   VALUES (?,?,?,?,?,?)""",
                (pid, record['k_WmK'], record['T_K'],
                 record['phase'], source_id,
                 f"Table 10.1 ref {record['ref']}")
            )
            tc_rows += 1

    conn.commit()
    print(f"density_equations:               {eq_rows} rows")
    print(f"density_measurements (evaluated): {density_rows} rows")
    print(f"thermal_conductivity:             {tc_rows} rows")

    # Quick sanity check
    n_poly = conn.execute("SELECT COUNT(*) FROM polymers").fetchone()[0]
    print(f"Total polymers in DB:             {n_poly}")


if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else PDF_PATH
    run(pdf)
