#!/usr/bin/env python3
"""
fetch_matweb_refs.py — Scrape MatWeb for experimental property data for
the 7 PolyJarvis revision polymers (PE/PMMA/PLA/PVC/PSU/NR/PEEK).

Fetches: density (g/cm³ at RT), Young's modulus (GPa), Poisson's ratio,
Tg (K), shear modulus (GPa), bulk modulus (GPa) where available.

Output: data/matweb_refs.json
Next step: db/ingest_scripts/import_matweb.py reads this JSON and loads
the data into polymer_db.sqlite.

Usage:
  python3 db/ingest_scripts/fetch_matweb_refs.py [options]

Options:
  --dry-run         Print search URLs without making HTTP requests.
  --target PE,...   Comma-separated subset of polymer IDs (default: all 7).
  --cache-dir DIR   HTML cache directory (default: data/matweb_cache).
  --out FILE        Output JSON path (default: data/matweb_refs.json).
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("requests is required: pip install requests")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TODAY = date.today().isoformat()

BASE_URL = "https://www.matweb.com"
SEARCH_URL = BASE_URL + "/search/QuickText.aspx"
SHEET_URL  = BASE_URL + "/search/DataSheet.aspx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE_URL + "/",
}

# (polymer_id, poly_class, search_term, keyword_filters)
# keyword_filters: result name must contain at least one of these substrings
TARGETS = [
    ("PE",   "PHYC", "polyethylene low density",
     ["polyethylene", "low density", "ldpe"]),
    ("PMMA", "PACR", "poly methyl methacrylate",
     ["methyl methacrylate", "pmma"]),
    ("PLA",  "PEST", "polylactic acid amorphous",
     ["lactic acid", "poly(lactic", "polylactic", "plla", "pdlla", "pla"]),
    ("PVC",  "PVNL", "polyvinyl chloride unplasticized",
     ["vinyl chloride", "pvc", "upvc"]),
    ("PSU",  "PSFO", "polysulfone bisphenol",
     ["polysulfone", "udel", "bisphenol"]),
    ("NR",   "PDIE", "polyisoprene natural rubber",
     ["polyisoprene", "natural rubber", "cis-1,4"]),
    ("PEEK", "PKTN", "polyether ether ketone amorphous",
     ["ether ether ketone", "peek"]),
]

# Property name patterns → normalized key.  Order matters: more specific first.
_PROP_MAP = [
    (re.compile(r"bulk\s*modulus",         re.I), "K_GPa"),
    (re.compile(r"shear\s*modulus",        re.I), "G_GPa"),
    (re.compile(r"tensile\s*modulus|young",re.I), "E_GPa"),
    (re.compile(r"poisson",               re.I), "poisson"),
    (re.compile(r"glass\s*transition|Tg\b",re.I), "Tg_C"),
    (re.compile(r"^density$",              re.I), "density_gcm3"),
]

# Unit conversion factors → GPa
_TO_GPA = {"gpa": 1.0, "mpa": 1e-3, "kpa": 1e-6, "pa": 1e-9,
           "ksi": 6.895e-3, "psi": 6.895e-6}


# ---------------------------------------------------------------------------
# HTML parsers
# ---------------------------------------------------------------------------

class _LinkParser(HTMLParser):
    """Collect all (href, text) pairs from an HTML fragment."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._cur_href: str | None = None
        self._cur_text: str = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs = dict(attrs)
            self._cur_href = attrs.get("href", "")
            self._cur_text = ""

    def handle_endtag(self, tag):
        if tag == "a" and self._cur_href is not None:
            self.links.append((self._cur_href, self._cur_text.strip()))
            self._cur_href = None

    def handle_data(self, data):
        if self._cur_href is not None:
            self._cur_text += data


class _TableParser(HTMLParser):
    """Extract all table rows as lists of cell text strings."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell: str = ""
        self._in_cell = False
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
        if tag in ("td", "th"):
            self._in_cell = True
            self._cell = ""

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._in_cell = False
            self._row.append(self._cell.strip())
        elif tag == "tr":
            if self._row:
                self.rows.append(self._row)
                self._row = []
        elif tag == "table":
            self._depth -= 1

    def handle_data(self, data):
        if self._in_cell:
            self._cell += data


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _fetch(session: "requests.Session", url: str, cache_path: Path,
           dry_run: bool) -> str | None:
    if dry_run:
        print(f"[dry-run] GET {url}")
        return None
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8", errors="replace")
    time.sleep(1.0)
    try:
        r = session.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as exc:
        print(f"  WARN: fetch failed for {url}: {exc}", file=sys.stderr)
        return None
    html = r.text
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8")
    return html


def _search_results(html: str, keywords: list[str]) -> list[tuple[str, str]]:
    """Return [(guid, material_name), ...] ranked by keyword match score."""
    parser = _LinkParser()
    parser.feed(html)
    candidates: list[tuple[int, str, str]] = []
    for href, text in parser.links:
        if "DataSheet.aspx" not in href or not text:
            continue
        m = re.search(r"MatGUID=([0-9a-fA-F]+)", href)
        if not m:
            continue
        guid = m.group(1)
        text_lower = text.lower()
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        # Penalise obvious composites / filled grades
        if re.search(r"\bfill|\bfib|\bcomp|\bglass\s+reinf|\bcarbon\s+reinf",
                     text_lower):
            score -= 10
        candidates.append((-score, text, guid))
    candidates.sort(key=lambda x: x[0])
    return [(guid, name) for _, name, guid in candidates]


def _parse_value_units(raw: str) -> tuple[float | None, str]:
    """Split '3.10 GPa' or '3100 MPa' or '0.1 - 0.3 g/cc' into (value, unit)."""
    raw = raw.strip()
    # Range: take midpoint
    m = re.match(r"([-\d.]+)\s*[-–]\s*([-\d.]+)\s*(\S*)", raw)
    if m:
        try:
            lo, hi = float(m.group(1)), float(m.group(2))
            return (lo + hi) / 2, m.group(3)
        except ValueError:
            pass
    # Single value + optional unit
    m = re.match(r"([-\d.eE+]+)\s*(.*)", raw)
    if m:
        try:
            return float(m.group(1)), m.group(2).strip()
        except ValueError:
            pass
    return None, ""


def _normalize(key: str, value: float, unit: str) -> float | None:
    """Convert value+unit to canonical units (GPa for moduli, K for Tg, g/cm³ for density)."""
    unit_lc = unit.lower().replace("/", "").replace("³", "3").replace("cc", "gcm3")
    if key in ("E_GPa", "G_GPa", "K_GPa"):
        factor = _TO_GPA.get(unit_lc, None)
        if factor is None:
            # Guess from magnitude: if > 100 it's likely MPa
            factor = 1e-3 if value > 100 else 1.0
        return round(value * factor, 4)
    if key == "poisson":
        return round(value, 4) if 0.0 <= value <= 0.5 else None
    if key == "Tg_C":
        # already in °C
        return round(value, 1)
    if key == "density_gcm3":
        # MatWeb reports density in g/cc (= g/cm³); some pages say kg/m³
        if "kgm3" in unit_lc or "kg/m" in unit_lc:
            return round(value / 1000, 4)
        return round(value, 4)
    return value


def _extract_properties(html: str) -> dict:
    """Parse a MatWeb DataSheet HTML page and return a property dict."""
    parser = _TableParser()
    parser.feed(html)
    props: dict[str, float] = {}
    for row in parser.rows:
        if len(row) < 2:
            continue
        prop_cell = row[0]
        # value may be in cell[1] alone ("0.855 g/cc") or cell[1]+cell[2]
        val_raw = row[1] if len(row) >= 2 else ""
        unit_raw = row[2] if len(row) >= 3 else ""
        if not val_raw or val_raw in ("N/A", "-", ""):
            continue

        # Identify property
        matched_key = None
        for pat, key in _PROP_MAP:
            if pat.search(prop_cell):
                matched_key = key
                break
        if not matched_key:
            continue

        # Try combined or separate value+unit
        if unit_raw:
            val, _ = _parse_value_units(val_raw)
            unit = unit_raw.strip()
        else:
            val, unit = _parse_value_units(val_raw)

        if val is None:
            continue
        norm = _normalize(matched_key, val, unit)
        if norm is None:
            continue
        if matched_key not in props:
            props[matched_key] = norm

    return props


def _material_name(html: str) -> str:
    """Extract the material title from a DataSheet page."""
    m = re.search(r"<title[^>]*>\s*MatWeb\s*[-–]\s*([^<]+)", html, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'<h1[^>]*>\s*([^<]{5,})', html)
    if m:
        return m.group(1).strip()
    return ""


# ---------------------------------------------------------------------------
# Main fetch logic
# ---------------------------------------------------------------------------

def fetch_polymer(polymer_id: str, poly_class: str, search_term: str,
                  keywords: list[str], session: "requests.Session",
                  cache_dir: Path, dry_run: bool) -> dict:
    print(f"\n[{polymer_id}] searching: {search_term!r}")
    record: dict = {
        "polymer_id":  polymer_id,
        "poly_class":  poly_class,
        "search_term": search_term,
        "accessed":    TODAY,
        "status":      "pending",
    }

    search_cache = cache_dir / f"{polymer_id}_search.html"
    url = f"{SEARCH_URL}?SearchText={urllib.parse.quote_plus(search_term)}"
    print(f"  GET {url}")
    html = _fetch(session, url, search_cache, dry_run)
    if html is None:
        record["status"] = "dry_run"
        return record

    candidates = _search_results(html, keywords)
    if not candidates:
        print(f"  WARN: no DataSheet links found in search results", file=sys.stderr)
        record["status"] = "no_results"
        return record

    # Try top candidates until we get a page with density
    for rank, (guid, name) in enumerate(candidates[:5]):
        sheet_cache = cache_dir / f"{polymer_id}_{guid}.html"
        sheet_url = f"{SHEET_URL}?MatGUID={guid}"
        print(f"  [{rank+1}] {name[:60]} → {guid[:8]}…")
        sheet_html = _fetch(session, sheet_url, sheet_cache, dry_run)
        if sheet_html is None:
            continue
        props = _extract_properties(sheet_html)
        if "density_gcm3" not in props and "E_GPa" not in props:
            print(f"       (no usable properties, skipping)")
            continue
        mat_name = _material_name(sheet_html) or name
        record.update({
            "material_name": mat_name,
            "matweb_guid":   guid,
            "url":           sheet_url,
            "status":        "ok",
            **props,
        })
        # Derive K from E + ν if K not found directly
        if "K_GPa" not in record and "E_GPa" in record and "poisson" in record:
            E, nu = record["E_GPa"], record["poisson"]
            if 0.0 < nu < 0.5:
                record["K_GPa_derived"] = round(E / (3 * (1 - 2 * nu)), 3)
        # Convert Tg °C → K
        if "Tg_C" in record:
            record["Tg_K"] = round(record["Tg_C"] + 273.15, 1)
        print(f"       density={record.get('density_gcm3')}  "
              f"E={record.get('E_GPa')} GPa  "
              f"Tg={record.get('Tg_K')} K")
        return record

    record["status"] = "no_properties"
    return record


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run",   action="store_true",
                    help="Print URLs without fetching")
    ap.add_argument("--target",    default="",
                    help="Comma-separated polymer IDs to fetch (default: all)")
    ap.add_argument("--cache-dir", default=str(REPO_ROOT / "data" / "matweb_cache"),
                    help="HTML cache directory")
    ap.add_argument("--out",       default=str(REPO_ROOT / "data" / "matweb_refs.json"),
                    help="Output JSON path")
    args = ap.parse_args()

    targets = [t for t in TARGETS
               if not args.target or t[0] in {x.strip() for x in args.target.split(",")}]
    if not targets:
        sys.exit(f"No matching targets for --target={args.target!r}")

    cache_dir = Path(args.cache_dir)
    out_path  = Path(args.out)

    session = requests.Session()
    results: dict[str, dict] = {}

    for polymer_id, poly_class, search_term, keywords in targets:
        rec = fetch_polymer(polymer_id, poly_class, search_term, keywords,
                            session, cache_dir, args.dry_run)
        results[polymer_id] = rec

    if not args.dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2))
        print(f"\nWrote {out_path}")
        ok = sum(1 for r in results.values() if r.get("status") == "ok")
        print(f"Summary: {ok}/{len(results)} polymers OK")
        for pid, rec in results.items():
            st = rec.get("status")
            if st != "ok":
                print(f"  WARN [{pid}]: status={st}")


if __name__ == "__main__":
    main()
