"""Verdict arithmetic shared by both graders.

Deliberately free of numpy, RadonPy and MDAnalysis: radonpy_grader.py imports it inside the
`radonpy` conda env and polyjarvis_grader.py inside mcp-servers/.venv, and the default pytest
suite exercises it with neither installed.
"""
from __future__ import annotations

import math

PASS = "PASS"
FAIL = "FAIL"
UNEVALUABLE = "UNEVALUABLE"  # the criterion applies, but this window cannot compute it
UNMEASURED = "UNMEASURED"    # the input the criterion needs does not exist for this cell
NOT_GATED = "NOT_GATED"      # RadonPy defines the quantity but sets no threshold (crit None)
INCOMPLETE = "INCOMPLETE"    # nothing failed, but something that binds was never evaluated


def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def radonpy_criterion(value, mean, crit, relative: bool) -> dict:
    """One row of RadonPy's check_eq: FAIL when value > (|mean| * crit if relative else crit).

    check_eq compares with `>`, and every comparison against NaN is False, so a NaN sma_sd --
    which analyze_thermo returns whenever the log holds fewer than 2*width rows -- PASSES there
    without a word. Here it is UNEVALUABLE. That is the only departure from RadonPy's rule.
    """
    if crit is None:
        return {"status": NOT_GATED, "value": None if _missing(value) else value, "threshold": None}
    if _missing(value) or (relative and _missing(mean)):
        return {"status": UNEVALUABLE, "value": None if _missing(value) else value, "threshold": None}
    threshold = abs(mean) * crit if relative else crit
    return {"status": FAIL if value > threshold else PASS, "value": value, "threshold": threshold}


def combine(statuses) -> str:
    """FAIL beats everything; any criterion that binds but was not evaluated makes the verdict
    INCOMPLETE rather than PASS -- an empty or partial set is never a clean pass."""
    gated = [s for s in statuses if s != NOT_GATED]
    if FAIL in gated:
        return FAIL
    if not gated or UNEVALUABLE in gated or UNMEASURED in gated:
        return INCOMPLETE
    return PASS


def polyjarvis_verdict(failing, unmeasured) -> str:
    """enforce_gate.classify's binding failures and unmeasured binding gates, as one word."""
    if failing:
        return FAIL
    if unmeasured:
        return INCOMPLETE
    return PASS
