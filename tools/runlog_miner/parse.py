"""Tolerant parser for PolyJarvis ``run_log.md`` files.

P0a of the B.4 learning-loop design: turns a
semi-structured, LLM-authored ``run_log.md`` into a structured :class:`RunRecord`.

Read-only — emits no suggestions. Parsing is deliberately *tolerant*: logs are
written by an agent in real time, so missing or placeholder (``[X]``) fields are
recorded as unfilled rather than raised, and a malformed section degrades to a
parse warning instead of crashing the whole record.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# ─── regexes ────────────────────────────────────────────────────────────────
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)          # strip instructional/example comments
_SECTION = re.compile(r"^##\s+(.+?)\s*$", re.M)
_DECISION_ROW = re.compile(r"^\|\s*D-0(\d)\b([^|]*)\|([^|]*)\|([^|]*)\|", re.M)
_RECOVERY_HEAD = re.compile(r"^\[\s*Stage\b([^\]]*)\]\s*(.*)$", re.M)
_KV = re.compile(r"^\s*(Diagnosis|Fix|Outcome)\s*:\s*(.*)$", re.I | re.M)
_RESULT_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", re.M)

# class ids are all P + 3 uppercase letters (PCBN, PSTR, PHYC, ...); exclude the
# PCFF force-field token which matches the same shape.
_CLASS_TOKEN = re.compile(r"\bP[A-Z]{3}\b")
_CLASS_RETURNED = re.compile(r"returned\s+([A-Z]{3,6})", re.I)
_NON_CLASS_TOKENS = {"PCFF"}

# property-name → canonical key for the RESULTS table
_RESULT_KEYS = {
    "tg": "Tg",
    "ρ": "rho", "rho": "rho", "density": "rho",
    "k": "K", "bulk modulus": "K",
    "cooling rate": "cooling_rate",
}


# ─── data model ─────────────────────────────────────────────────────────────
@dataclass
class Decision:
    value: str = ""
    rationale: str = ""
    filled: bool = False


@dataclass
class Recovery:
    stage: str = ""
    trigger: str = ""
    diagnosis: str = ""
    fix: str = ""
    outcome: str = ""


@dataclass
class ResultRow:
    computed: str = ""
    experimental: str = ""
    error: str = ""
    status: str = ""
    filled: bool = False


@dataclass
class RunRecord:
    run_name: str
    path: str = ""
    polymer_name: str = ""
    polymer_class: Optional[str] = None
    smiles: str = ""
    ff: str = ""
    charge_method: str = ""
    dp: Optional[int] = None
    n_chains: Optional[int] = None
    n_atoms: Optional[int] = None
    decisions: dict = field(default_factory=dict)   # "D-01".."D-06" -> Decision
    recoveries: list = field(default_factory=list)  # [Recovery]
    results: dict = field(default_factory=dict)     # "Tg"/"rho"/"K"/"cooling_rate" -> ResultRow
    warnings: list = field(default_factory=list)    # parse warnings (never fatal)

    @property
    def convergence(self) -> str:
        return self.decisions.get("D-05", Decision()).value

    @property
    def fit_quality(self) -> str:
        return self.decisions.get("D-06", Decision()).value

    @property
    def has_recoveries(self) -> bool:
        return bool(self.recoveries)

    def to_dict(self) -> dict:
        return asdict(self)


# ─── helpers ────────────────────────────────────────────────────────────────
def _is_placeholder(cell: str) -> bool:
    s = cell.strip()
    return (not s) or ("[" in s and "]" in s)


def _to_int(s: str) -> Optional[int]:
    m = re.search(r"\d[\d,]*", s or "")
    return int(m.group(0).replace(",", "")) if m else None


def _field_after(label: str, text: str) -> str:
    """Return the value after ``label:`` up to the next ``|`` or end of line."""
    m = re.search(rf"{label}\s*:\s*([^|\n]+)", text, re.I)
    return m.group(1).strip().strip("`").strip() if m else ""


def _split_sections(text: str):
    """Return (preamble, {SECTION_NAME_UPPER: body})."""
    parts = _SECTION.split(text)
    preamble = parts[0]
    sections = {}
    for i in range(1, len(parts), 2):
        sections[parts[i].strip().upper()] = parts[i + 1]
    return preamble, sections


def _extract_class(d01_rationale: str) -> Optional[str]:
    m = _CLASS_RETURNED.search(d01_rationale)
    if m and m.group(1).upper() not in _NON_CLASS_TOKENS:
        cand = m.group(1).upper()
        if _CLASS_TOKEN.fullmatch(cand) or len(cand) in (4, 5):
            return cand
    for tok in _CLASS_TOKEN.findall(d01_rationale):
        if tok not in _NON_CLASS_TOKENS:
            return tok
    return None


# ─── section parsers ────────────────────────────────────────────────────────
def _parse_decisions(body: str, rec: RunRecord) -> None:
    for m in _DECISION_ROW.finditer(body):
        key = f"D-0{m.group(1)}"
        value, rationale = m.group(3).strip(), m.group(4).strip()
        rec.decisions[key] = Decision(
            value=value, rationale=rationale, filled=not _is_placeholder(value)
        )
    if "D-04" in rec.decisions and rec.n_atoms is None:
        m = re.search(r"([\d,]+)\s*atoms", rec.decisions["D-04"].value)
        if m:
            rec.n_atoms = _to_int(m.group(1))


def _parse_recoveries(body: str, rec: RunRecord) -> None:
    if body.strip().lower().startswith("none"):
        return
    heads = list(_RECOVERY_HEAD.finditer(body))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        block = body[m.end():end]
        kv = {k.lower(): v.strip() for k, v in _KV.findall(block)}
        rec.recoveries.append(
            Recovery(
                stage=m.group(1).strip(),
                trigger=m.group(2).strip(),
                diagnosis=kv.get("diagnosis", ""),
                fix=kv.get("fix", ""),
                outcome=kv.get("outcome", ""),
            )
        )


def _parse_results(body: str, rec: RunRecord) -> None:
    for m in _RESULT_ROW.finditer(body):
        name = m.group(1).strip().lower()
        if name in ("property", "") or re.fullmatch(r"[-: ]+", name):
            continue
        key = _RESULT_KEYS.get(name)
        if not key:
            continue
        computed = m.group(2).strip()
        rec.results[key] = ResultRow(
            computed=computed,
            experimental=m.group(3).strip(),
            error=m.group(4).strip(),
            status=m.group(5).strip(),
            filled=not _is_placeholder(computed),
        )


# ─── public API ─────────────────────────────────────────────────────────────
def parse_text(text: str, run_name: str, path: str = "") -> RunRecord:
    """Parse run_log.md *content* into a :class:`RunRecord`. Never raises on
    malformed content — problems are appended to ``record.warnings``."""
    rec = RunRecord(run_name=run_name, path=path)
    text = _COMMENT.sub("", text)                      # drop example/instruction comments first
    preamble, sections = _split_sections(text)

    # title + header lines (preamble)
    title = re.search(r"^#\s+(.+)$", preamble, re.M)
    if title:
        rec.polymer_name = re.split(r"\s+Run\b", title.group(1).strip())[0].strip()
    rec.smiles = _field_after("SMILES", preamble)
    rec.ff = _field_after("FF", preamble)
    rec.charge_method = _field_after("Charges", preamble)
    rec.dp = _to_int(_field_after("DP", preamble))
    rec.n_chains = _to_int(_field_after("Chains", preamble))

    for name, parser in (
        ("DECISIONS", _parse_decisions),
        ("RECOVERIES", _parse_recoveries),
        ("RESULTS", _parse_results),
    ):
        if name in sections:
            try:
                parser(sections[name], rec)
            except Exception as exc:  # noqa: BLE001 — tolerant by design
                rec.warnings.append(f"{name} parse error: {exc}")
        else:
            rec.warnings.append(f"missing section: {name}")

    if "D-01" in rec.decisions:
        rec.polymer_class = _extract_class(rec.decisions["D-01"].rationale)
    if rec.polymer_class is None:
        rec.warnings.append("could not determine polymer_class from D-01")

    return rec


def parse_run_log(path) -> RunRecord:
    p = Path(path)
    return parse_text(p.read_text(encoding="utf-8"), run_name=p.parent.name, path=str(p))


def load_corpus(data_dir="data", glob="*/run_log.md") -> list:
    """Discover and parse every run_log under *data_dir*, skipping TEMPLATE."""
    records = []
    for p in sorted(Path(data_dir).glob(glob)):
        if p.parent.name.upper() == "TEMPLATE":
            continue
        records.append(parse_run_log(p))
    return records
