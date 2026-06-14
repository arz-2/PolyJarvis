"""Read-only summary report for a parsed run_log corpus (P0a).

Emits a markdown overview only — no suggestions, no edits. The suggestion engine
(P0b) and calibration/playbook artifacts (P0c) build on the same RunRecords.
"""
from __future__ import annotations


def _cell(s: str, dash: str = "—") -> str:
    s = (s or "").strip()
    return s if s else dash


def summarize(records: list) -> str:
    n = len(records)
    n_rec = sum(1 for r in records if r.has_recoveries)
    n_warn = sum(1 for r in records if r.warnings)

    lines = [
        "# run_log corpus summary",
        "",
        f"- runs parsed: **{n}**",
        f"- runs with recoveries: **{n_rec}**",
        f"- runs with parse warnings: **{n_warn}**",
        "",
        "## Runs",
        "",
        "| Run | Class | FF | DP×Chains | Atoms | D-05 | D-06 | #Rec | Tg (calc / exp / err) | ρ (calc) |",
        "|-----|-------|----|-----------|-------|------|------|------|-----------------------|----------|",
    ]
    for r in records:
        dpxc = f"{r.dp or '?'}×{r.n_chains or '?'}"
        tg = r.results.get("Tg")
        rho = r.results.get("rho")
        tg_cell = (
            f"{_cell(tg.computed)} / {_cell(tg.experimental)} / {_cell(tg.error)}"
            if tg else "—"
        )
        lines.append(
            f"| {r.run_name} | {_cell(r.polymer_class)} | {_cell(r.ff)} | {dpxc} | "
            f"{r.n_atoms or '—'} | {_cell(r.convergence)} | {_cell(r.fit_quality)} | "
            f"{len(r.recoveries)} | {tg_cell} | {_cell(rho.computed) if rho else '—'} |"
        )

    if n_rec:
        lines += ["", "## Recoveries", ""]
        for r in records:
            for rec in r.recoveries:
                lines.append(
                    f"- **{r.run_name}** [Stage {_cell(rec.stage)}] — "
                    f"{_cell(rec.diagnosis, 'no diagnosis recorded')}"
                )

    if n_warn:
        lines += ["", "## Parse warnings", ""]
        for r in records:
            for w in r.warnings:
                lines.append(f"- **{r.run_name}**: {w}")

    return "\n".join(lines) + "\n"
