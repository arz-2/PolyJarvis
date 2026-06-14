"""Confidence-calibration report for the run_log learning loop (P0c).

Checks each polymer class's stated ``confidence`` label (from polymer_rules.json)
against the outcomes the pipeline actually recorded in ``RESULTS``.

Design-critical: raw Tg error vs experiment is *expected* to be large (MD
over-predicts Tg by ~80–120 K), so calibration keys off the **✓/⚠ status** the agent
already recorded (which accounts for the expected offset) and off **density error**
(which is expected to be small) — never a naive zero-error Tg threshold.

See ``docs/specs/B4_runlog_miner_spec.md`` §2.3.
"""
from __future__ import annotations

import re
import statistics
from datetime import date

_PCT = re.compile(r"(-?\d+\.?\d*)\s*%")
_NUM = re.compile(r"(-?\d+\.?\d*)")


def _pct(s):
    m = _PCT.search(s or "")
    return float(m.group(1)) if m else None


def _num(s):
    m = _NUM.search(s or "")
    return float(m.group(1)) if m else None


def _ok(status):
    return "✓" in (status or "")


def _warn(status):
    return "⚠" in (status or "")


def calibrate(records, rules_classes) -> dict:
    """Return {class_id: {confidence, n, tg_ok, tg_warn, rho_err_mean, tg_spread, flags}}."""
    by_class: dict = {}
    for r in records:
        if r.polymer_class:
            by_class.setdefault(r.polymer_class, []).append(r)

    out: dict = {}
    for cid, runs in by_class.items():
        tg_rows = [r.results["Tg"] for r in runs if "Tg" in r.results and r.results["Tg"].filled]
        rho_rows = [r.results["rho"] for r in runs if "rho" in r.results and r.results["rho"].filled]
        if not tg_rows and not rho_rows:
            continue

        confidence = rules_classes.get(cid, {}).get("confidence", "?")
        tg_ok = sum(1 for x in tg_rows if _ok(x.status))
        tg_warn = sum(1 for x in tg_rows if _warn(x.status))
        rho_errs = [abs(e) for e in (_pct(x.error) for x in rho_rows) if e is not None]
        rho_err_mean = round(statistics.mean(rho_errs), 2) if rho_errs else None
        tg_vals = [v for v in (_num(x.computed) for x in tg_rows) if v is not None]
        tg_spread = round(statistics.pstdev(tg_vals), 1) if len(tg_vals) >= 2 else None

        flags: list = []
        total_tg = tg_ok + tg_warn
        if confidence == "high" and total_tg >= 1 and tg_warn > tg_ok:
            flags.append("over-confident: Tg ⚠ in majority of runs")
        if confidence == "low" and len(runs) >= 2 and total_tg >= 1 and tg_warn == 0:
            flags.append("could promote: all Tg within bounds")
        if confidence == "high" and rho_err_mean is not None and rho_err_mean > 5.0:
            flags.append(f"high ρ error ({rho_err_mean}%) for high-confidence class")
        if tg_spread is not None and tg_spread > 30.0:
            flags.append(f"high replica spread (σ={tg_spread} K)")

        out[cid] = {
            "confidence": confidence, "n": len(runs),
            "tg_ok": tg_ok, "tg_warn": tg_warn,
            "rho_err_mean": rho_err_mean, "tg_spread": tg_spread, "flags": flags,
        }
    return out


def build_calibration(records, rules) -> str:
    cal = calibrate(records, rules.get("classes", {}))
    lines = [
        "# Confidence Calibration",
        "",
        f"`runlog_miner` · {len(records)} runs · {len(cal)} classes with results · {date.today().isoformat()}",
        "",
    ]
    if not cal:
        lines += ["_No runs with filled results in the corpus yet._", ""]
        return "\n".join(lines) + "\n"

    lines += [
        "| Class | Confidence | n | Tg ✓/⚠ | mean ρ err | flag |",
        "|---|---|---|---|---|---|",
    ]
    for cid in sorted(cal):
        c = cal[cid]
        rho = f"{c['rho_err_mean']}%" if c["rho_err_mean"] is not None else "—"
        flag = "; ".join(c["flags"]) if c["flags"] else "—"
        lines.append(
            f"| {cid} | {c['confidence']} | {c['n']} | {c['tg_ok']}/{c['tg_warn']} | {rho} | {flag} |"
        )

    lines += [
        "",
        "_Note: raw Tg error vs experiment is reported but **not** flagged — MD systematically",
        "over-predicts Tg (~80–120 K), so calibration keys off the ✓/⚠ status the pipeline",
        "recorded (which accounts for the expected offset) and off density error._",
    ]
    return "\n".join(lines) + "\n"
