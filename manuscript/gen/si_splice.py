#!/usr/bin/env python3
"""Splice the generated SI tables into supporting_information.tex, one table at a time, by label.

Only the table environment carrying each label is replaced; surrounding prose is never touched.
Run si_tables.py first. `--check` reports which tables differ without writing.
"""
from __future__ import annotations

import sys
from pathlib import Path

GEN = Path(__file__).resolve().parent
SNIPPETS = GEN / "out" / "si_snippets"
SI = GEN.parent / "supporting_information_v3.tex"
# v3 dropped the per-run parameter and gate-disposition sections (author decision 2026-09-16).
TABLES = [("s7_rho_k", "tab:si_rho_k"), ("s7_tg", "tab:si_tg"), ("s7_struct", "tab:si_struct")]


def env_span(text: str, label: str) -> tuple[int, int]:
    i = text.index(r"\label{%s}" % label)
    for env in ("longtable", "table"):
        b = text.rfind(r"\begin{%s}" % env, 0, i)
        if b != -1 and text.find(r"\end{%s}" % env, b) > i:
            e = text.index(r"\end{%s}" % env, i) + len(r"\end{%s}" % env)
            return b, e
    raise ValueError(f"no table environment around {label}")


def main() -> int:
    check = "--check" in sys.argv
    si = SI.read_text()
    changed = []
    for snip, label in TABLES:
        new = (SNIPPETS / f"{snip}.tex").read_text()
        nb, ne = env_span(new, label)
        ob, oe = env_span(si, label)
        if si[ob:oe] != new[nb:ne]:
            changed.append(label)
            si = si[:ob] + new[nb:ne] + si[oe:]
    if not check and changed:
        SI.write_text(si)
    print(("differs: " if check else "spliced: ") + (", ".join(changed) or "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
