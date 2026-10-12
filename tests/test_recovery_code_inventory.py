"""Inventory of the recovery ladder: which blocking codes anything can actually produce,
and which of those any test actually drives.

WHAT THIS MEASURES, EXACTLY. Not reachability -- a string search. A code counts as
*produced* when some file outside `default_remedies()` itself names it as a string literal,
and as *tested* when some file under a tests/ directory does. That is weaker than proving a
run can reach it (a code assembled from a verdict token would read as unproduced) and
weaker than proving a test drives the remedy (naming a code is not firing it). It is strong
enough for the failure this exists to catch: the registry drifting away from the code that
feeds it, silently, in either direction.

WHY. `default_remedies()` routed 46 codes when this was written and 19 had no producer
anywhere in the repo -- the registry had been accumulating rows for verdicts that were
renamed, folded into a generic code, or never shipped. A dead row is not inert:
`RemedyRegistry.route` falls through to the `agent_only` catch-all for anything unrouted, so
a row that can never match reads as coverage the ladder does not have. Three whole remedies
were in that state and were deleted on 2026-09-07 (`safe_hardware`, `remove_noop`,
`unique_forcefield`, with their four codes); two more are half dead but still fire
(`transient_retry`, `continue_npt`). `.claude/commands/recover.md` lost its rows for the
same codes the same day -- this is the third part of that cleanup, as a standing check
rather than another one-off edit.

Both directions fail:
  - a code in UNREACHABLE that gains a producer -> the registry row is live again; drop it
    from the map here and confirm its remedy still does the right thing.
  - a code NOT in UNREACHABLE that loses its producer -> a remedy just went silent, and
    findings that used to route to it now land on the agent_only catch-all instead.
"""
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from workflow_engine import ACTIVE_BLOCKING_CODES, default_remedies  # noqa: E402

ENGINE = REPO_ROOT / "orchestration" / "scripts" / "workflow_engine.py"
SEARCH_ROOTS = ("orchestration", "mcp-servers", "guides", "hardware", "tools")

#: Codes no producer names, with what was checked on 2026-09-07. "No producer found" is the
#: honest entry where the reason was not established -- it is a search result, not a claim
#: that the code is unreachable by construction.
UNREACHABLE = {
    # run_campaign.py:2381 mints a generic PROCESS_FAILED for every stage; the per-stage
    # variants and the timeout code were never split back out.
    "PROCESS_TIMEOUT": "run_campaign.py:2381 mints generic PROCESS_FAILED",
    "BUILDER_PROCESS_FAILED": "run_campaign.py:2381 mints generic PROCESS_FAILED",
    "THERMAL_PROCESS_FAILED": "run_campaign.py:2381 mints generic PROCESS_FAILED",
    "MECHANICAL_POINT_PROCESS_FAILED": "run_campaign.py:2381 mints generic PROCESS_FAILED",
    # workflow_engine.py:1057-1059 escalates the ORIGINAL finding when a cap is hit -- it
    # never mints a code naming the exhaustion, so nothing can route on one.
    "REMEDY_EXHAUSTED": "workflow_engine.py:1057 escalates the original finding",
    "AUTOMATIC_REMEDY_CAP_REACHED": "workflow_engine.py:1059 escalates the original finding",
    "DEFORM_RATE_SENSITIVITY_PERSISTS": "no producer found 2026-09-07",
    # The equilibration gate reports EXTEND and its own verdicts; these three predate it.
    "EQUIL_DRIFT": "no producer in any gate script 2026-09-07",
    "EQUIL_SEM": "no producer in any gate script 2026-09-07",
    "EQUIL_N_EFF": "no producer in any gate script 2026-09-07",
    "FORCE_FIELD_TYPING_AMBIGUOUS": "no producer found 2026-09-07",
    "DETERMINISTIC_BUILD_FAILED": "no producer found 2026-09-07",
    "BM_INADMISSIBLE_UNSUPPORTED_REGIME": "no producer found 2026-09-07",
    "AMBIGUOUS_ORDERING": "no producer found 2026-09-07",
    "ARTIFACT_INTEGRITY_FAILED": "no producer found 2026-09-07",
}

#: Live codes that no test names. A ratchet, not a target: it may only shrink. A code
#: arriving here means a new remedy route shipped with nothing exercising it.
UNTESTED = {
    "BM_FALLBACK_DEFORM", "BM_INADMISSIBLE_NONMONOTONIC", "DEFORM_ANISOTROPIC",
    "DEFORM_INADMISSIBLE", "DEFORM_NEGATIVE_MODULUS", "DEFORM_RATE_SENSITIVE",
    "FINITE_SIZE_FAILED", "MECHANICAL_IDENTIFIABILITY_FAILED", "PLAN_AGENT_CONTRACT_ERROR",
    "PLAN_VALIDATION_FAILED", "UNEXPLAINED_STAGE_FAILURE", "UNSUPPORTED_BUILDER",
}


def _sources_excluding_the_registry() -> dict[str, str]:
    """Every production source, with `default_remedies()`'s own body cut out of the engine.

    The registry names all 46 codes by construction, so leaving it in makes every code look
    produced. Sliced by AST rather than line number so the other sessions editing this file
    cannot quietly shift the window.
    """
    lines = ENGINE.read_text().splitlines(keepends=True)
    node = next(item for item in ast.parse("".join(lines)).body
                if isinstance(item, ast.FunctionDef) and item.name == "default_remedies")
    sources = {"workflow_engine.py (minus the registry)":
               "".join(lines[:node.lineno - 1] + lines[node.end_lineno:])}
    for root in SEARCH_ROOTS:
        for path in (REPO_ROOT / root).rglob("*"):
            if (path.is_file() and path.suffix in (".py", ".json") and path != ENGINE
                    and ".venv" not in path.parts and "tests" not in path.parts):
                sources[str(path)] = path.read_text(errors="ignore")
    return sources


def _test_sources() -> dict[str, str]:
    return {str(p): p.read_text(errors="ignore")
            for p in REPO_ROOT.rglob("tests/**/*.py") if ".venv" not in p.parts}


def _named_in(sources: dict[str, str], code: str) -> list[str]:
    return sorted(p for p, text in sources.items()
                  if f'"{code}"' in text or f"'{code}'" in text)


def test_every_registry_code_is_either_produced_or_declared_unreachable():
    sources = _sources_excluding_the_registry()
    produced = {code for code in ACTIVE_BLOCKING_CODES if _named_in(sources, code)}
    assert produced == ACTIVE_BLOCKING_CODES - set(UNREACHABLE), (
        "registry/producer drift.\n"
        f"  newly unproduced (a remedy just went silent): "
        f"{sorted(ACTIVE_BLOCKING_CODES - set(UNREACHABLE) - produced)}\n"
        f"  newly produced (drop from UNREACHABLE): {sorted(produced & set(UNREACHABLE))}"
    )


def test_the_unreachable_map_only_lists_codes_the_registry_still_routes():
    """A stale entry here would hide the removal of the row it documents."""
    assert set(UNREACHABLE) <= ACTIVE_BLOCKING_CODES


def test_no_registered_remedy_is_wholly_unroutable():
    """safe_hardware, remove_noop and unique_forcefield each routed only unproduced codes
    and were deleted 2026-09-07. Nothing may take their place: a row every one of whose
    codes is unproduced can never match, and reads as ladder coverage the engine does not
    have. The two remedies that are PARTLY dead (transient_retry keeps PROCESS_FAILED and
    PROCESS_DEAD_NO_SENTINEL; continue_npt keeps EXTEND) stay -- they still fire."""
    fully_dead = sorted(remedy.remedy_id for remedy in default_remedies()
                        if remedy.codes and remedy.codes <= set(UNREACHABLE))
    assert fully_dead == []


def test_no_new_live_code_ships_without_a_test_naming_it():
    """A ratchet on the untested set: it may shrink, never grow."""
    tests = _test_sources()
    live = ACTIVE_BLOCKING_CODES - set(UNREACHABLE)
    untested = {code for code in live if not _named_in(tests, code)}
    assert untested <= UNTESTED, (
        f"live remedy codes with no test naming them: {sorted(untested - UNTESTED)}")
