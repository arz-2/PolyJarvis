"""
db — PolyJarvis experimental polymer property database.

Stores real laboratory measurements only (DSC Tg, dilatometry density,
mechanical testing moduli). No MD simulation data.

Quick usage:
    from db import get_tg, get_property, get_thermal_conductivity, get_density_equation
    rows = get_tg(cas="9011-14-7")                       # PMMA Tg measurements
    rows = get_tg(name="Poly(styrene)")
    rows = get_property("density", name="Polyethylene")
    rows = get_property("bulk_modulus", cas="9003-53-6")
    rows = get_thermal_conductivity(name="Polystyrene")
    rows = get_density_equation(name="Polystyrene")
"""

import os
import sqlite3

_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(_DIR, "polymer_db.sqlite")
_SCHEMA = os.path.join(_DIR, "schema.sql")

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call repeatedly."""
    conn = _get_conn()
    with open(_SCHEMA) as f:
        conn.executescript(f.read())
    conn.commit()


def _polymer_id_clause(smiles, cas, name):
    """Build a WHERE fragment that matches any of the supplied identifiers."""
    if smiles:
        return "p.smiles = ?", smiles
    if cas:
        return "p.cas_no = ?", cas
    if name:
        return "p.name LIKE ?", f"%{name}%"
    raise ValueError("Provide at least one of: smiles, cas, name")


def get_tg(*, smiles=None, cas=None, name=None) -> list[dict]:
    """
    Return all experimental Tg measurements matching the identifier.

    Args:
        smiles: repeat-unit SMILES with * endpoints
        cas:    CAS registry number string
        name:   polymer name (substring match, case-insensitive via LIKE)

    Returns:
        List of dicts with keys: tg_C, tg_K, form, method, source_key, notes,
        handbook_ref, polymer_name, cas_no
    """
    clause, param = _polymer_id_clause(smiles, cas, name)
    sql = f"""
        SELECT t.tg_C, t.tg_K, t.form, t.method, t.notes, t.handbook_ref,
               s.key AS source_key,
               p.name AS polymer_name, p.cas_no
        FROM tg_measurements t
        JOIN polymers p ON p.id = t.polymer_id
        LEFT JOIN sources s ON s.id = t.source_id
        WHERE {clause}
        ORDER BY t.tg_K
    """
    rows = _get_conn().execute(sql, (param,)).fetchall()
    return [dict(r) for r in rows]


def get_property(property: str, *, smiles=None, cas=None, name=None) -> list[dict]:
    """
    Return experimental measurements for a given property.

    Args:
        property: one of 'density', 'bulk_modulus', 'youngs_modulus', 'shear_modulus'
        smiles / cas / name: polymer identifier (one required)

    Returns:
        List of dicts. Keys vary by property:
          density       → value (g/cm³), T_K, phase, source_key, notes
          *_modulus     → value (GPa), T_K, source_key, notes
    """
    clause, param = _polymer_id_clause(smiles, cas, name)

    if property == "density":
        sql = f"""
            SELECT d.density_gcm3 AS value, d.T_K, d.phase, d.notes,
                   s.key AS source_key,
                   p.name AS polymer_name, p.cas_no
            FROM density_measurements d
            JOIN polymers p ON p.id = d.polymer_id
            LEFT JOIN sources s ON s.id = d.source_id
            WHERE {clause}
            ORDER BY d.T_K
        """
    elif property in ("bulk_modulus", "youngs_modulus", "shear_modulus"):
        sql = f"""
            SELECT m.value_GPa AS value, m.T_K, m.notes,
                   s.key AS source_key,
                   p.name AS polymer_name, p.cas_no
            FROM mechanical_measurements m
            JOIN polymers p ON p.id = m.polymer_id
            LEFT JOIN sources s ON s.id = m.source_id
            WHERE {clause} AND m.property = '{property}'
            ORDER BY m.T_K
        """
    else:
        raise ValueError(
            f"Unknown property '{property}'. "
            "Valid: density, bulk_modulus, youngs_modulus, shear_modulus"
        )

    rows = _get_conn().execute(sql, (param,)).fetchall()
    return [dict(r) for r in rows]


def get_thermal_conductivity(*, smiles=None, cas=None, name=None) -> list[dict]:
    """
    Return experimental thermal conductivity measurements matching the identifier.

    Returns:
        List of dicts with keys: k_WmK, T_K, phase, source_key, notes,
        polymer_name, cas_no
    """
    clause, param = _polymer_id_clause(smiles, cas, name)
    sql = f"""
        SELECT tc.k_WmK, tc.T_K, tc.phase, tc.notes,
               s.key AS source_key,
               p.name AS polymer_name, p.cas_no
        FROM thermal_conductivity_measurements tc
        JOIN polymers p ON p.id = tc.polymer_id
        LEFT JOIN sources s ON s.id = tc.source_id
        WHERE {clause}
        ORDER BY tc.T_K
    """
    rows = _get_conn().execute(sql, (param,)).fetchall()
    return [dict(r) for r in rows]


def get_density_equation(*, smiles=None, cas=None, name=None) -> list[dict]:
    """
    Return analytical density equations matching the identifier (from Mark 2007).

    Returns:
        List of dicts with keys: equation (human-readable Unicode), py_expr
        (Python eval()-able with variable t in °C and math imported),
        t_min_C, t_max_C, phase ('melt' or 'glass'), tg_C,
        source_key, notes, polymer_name, cas_no
    """
    clause, param = _polymer_id_clause(smiles, cas, name)
    sql = f"""
        SELECT de.equation, de.py_expr, de.t_min_C, de.t_max_C,
               de.phase, de.tg_C, de.notes,
               s.key AS source_key,
               p.name AS polymer_name, p.cas_no
        FROM density_equations de
        JOIN polymers p ON p.id = de.polymer_id
        LEFT JOIN sources s ON s.id = de.source_id
        WHERE {clause}
        ORDER BY de.phase, de.t_min_C
    """
    rows = _get_conn().execute(sql, (param,)).fetchall()
    return [dict(r) for r in rows]
