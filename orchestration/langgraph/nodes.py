#!/usr/bin/env python3
"""The graph's nodes. Each one is a plain function of RunState -> partial RunState.

Two rules hold throughout and are worth stating once:

1. **Python writes every file.** The two model nodes return structured output and nothing
   else; no Write or Edit is ever granted. apply_adjudication touches exactly five keys of
   run_plan.json, so the "what may a critic change" restriction from SKILL.md step 5 is
   structural rather than prompt-enforced -- and testable with no model in the loop.

2. **Nothing here is authoritative.** run_plan.json, workflow_state.json and each attempt's
   executor_state.json stay the system of record. State fields that mirror them are re-read
   after every mutation rather than remembered, because materialize_plan rewrites the plan
   in place.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from chemistry_policy import consistency  # noqa: E402
from classify_cli import ClassificationError, classify_polymer  # noqa: E402
from rules_common import get_class_entry, load_rules  # noqa: E402
from headless_claude import HeadlessError, invoke, markdown_body, section  # noqa: E402

import guards  # noqa: E402
import schemas  # noqa: E402
from state import UNREVIEWED, VALID_CONFIDENCE  # noqa: E402

VENV_PY = REPO_ROOT / "mcp-servers" / ".venv" / "bin" / "python"
CRITIC_MD = REPO_ROOT / ".claude" / "agents" / "literature-grounding-worker.md"
SKILL_MD = REPO_ROOT / ".claude" / "skills" / "novel-run-plan" / "SKILL.md"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def event(kind: str, **fields: Any) -> dict:
    return {"event": kind, "at": _now_iso(), **fields}


def run_dir(state: dict) -> Path:
    return Path(state["repo_root"]) / "data" / state["run_name"]


def plan_path(state: dict) -> Path:
    return run_dir(state) / "raw" / "run_plan.json"


def _write_json(path: Path, payload: dict) -> None:
    """Atomic write, matching scientific_control._write_json's tmp+replace convention so a
    killed driver can never leave a half-written plan behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(tmp, path)


def _run(cmd: list[str], *, repo_root: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                          cwd=repo_root, timeout=timeout)


def _restore_artifacts(state: dict) -> dict:
    """Re-attach the artifacts a previous invocation already produced.

    Resuming re-enters mid-graph, so anything an earlier run computed and wrote is on disk
    but NOT in this process's state. Two of them are load-bearing and were being dropped:

      grounding_path   entry_resolve routes to `adjudicate` precisely BECAUSE
                       literature_grounding.json exists -- and then, without this, handed the
                       adjudicator "(none -- the critic returned no usable result)". It would
                       adjudicate blind, discarding a critique already paid for in both money
                       and minutes, and reach a worse decision than the first attempt would
                       have.
      chemistry        the pendant-group and melt-margin findings _chemistry_brief puts in
                       front of the adjudicator. Silently absent on resume, so a resumed run
                       weighed less evidence than a fresh one.

    Both are read back rather than recomputed: they are the artifacts of steps that already
    ran, and re-running them would cost another model call for no new information.
    """
    raw = run_dir(state) / "raw"
    out: dict = {}

    grounding = raw / "literature_grounding.json"
    if grounding.is_file():
        out["grounding_path"] = str(grounding)
        try:
            verdict = ((json.loads(grounding.read_text()).get("critique") or {})
                       .get("D-01_ff") or {}).get("verdict")
        except (json.JSONDecodeError, OSError):
            verdict = None
        out["critic_verdict"] = verdict

    classification = raw / "classification.json"
    if classification.is_file():
        try:
            doc = json.loads(classification.read_text())
        except (json.JSONDecodeError, OSError):
            return out
        out["classification_path"] = str(classification)
        if doc.get("chemistry_consistency"):
            out["chemistry"] = doc["chemistry_consistency"]
        if doc.get("polymer_class"):
            out.setdefault("polymer_class", doc["polymer_class"])
        if doc.get("class_source"):
            out["class_source"] = doc["class_source"]
    return out


def _plan_summary(path: Path) -> dict:
    """The plan fields the graph reports and guards on, re-read from disk.

    Always re-read, never remembered: materialize_plan rewrites run_plan.json in place, so
    a cached copy taken before it goes stale the moment it runs.
    """
    try:
        doc = json.loads(Path(path).read_text())
    except (json.JSONDecodeError, OSError):
        return {"plan_path": str(path)}
    estimate = doc.get("cost_estimate") or {}
    return {
        "plan_path": str(path),
        "polymer_class": doc.get("polymer_class"),
        "plan_mode": doc.get("plan_mode"),
        "confidence": doc.get("confidence"),
        "cost_gpu_hours": estimate.get("total_gpu_hours"),
        "cost_unpriced": [u.get("stage", u) if isinstance(u, dict) else u
                          for u in (estimate.get("unpriced_stages") or [])],
    }


def _last_json_value(text: str):
    """The last complete JSON value in `text`, ignoring anything printed around it.

    Lifted from scientific_control._last_json_value deliberately rather than imported: this
    runs in the driver process, and reaching into the control plane for a five-line text
    utility would couple the two for no benefit.
    """
    decoder = json.JSONDecoder()
    for index in reversed([i for i, char in enumerate(text) if char in "[{"]):
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if not text[index + end:].strip():
            return value
    return None


def _stop(status: str, detail: str, **fields: Any) -> dict:
    return {"status": status, "detail": detail,
            "events": [event("stop", status=status, detail=detail, **fields)]}


# ---------------------------------------------------------------------------
# entry_resolve
# ---------------------------------------------------------------------------
def entry_resolve(state: dict) -> dict:
    """Where does this invocation pick up? Derived from data/<run>/ alone.

    There is no LangGraph checkpointer on purpose: adding one would put a second, parallel
    record of run progress next to workflow_state.json, and the two would drift. The run
    directory already knows everything needed.

    Two traps this must avoid, both learned from the control plane's actual behaviour:

      * `system_size.resolved_by` is NOT the discriminator it looks like -- run-plan
        already sets it on a scaffold, so testing it would send a never-materialized plan
        straight to execute. plan_mode is the real signal: run-plan writes "scaffold",
        make_plan_from_cache writes "deterministic", and only materialize_plan writes
        "reasoned".
      * control_state.json is NOT run state. After a dry-run materialize it reads
        status "complete" with session_ended_at set -- that describes the control-plane
        SESSION, not the campaign. Reading it here would send a half-planned run straight
        to execute. workflow_state.json is the only file consulted.
    """
    workflow_state = run_dir(state) / "workflow_state.json"
    if workflow_state.is_file():
        try:
            status = json.loads(workflow_state.read_text()).get("status")
        except (json.JSONDecodeError, OSError):
            status = None
        if status != "accepted":
            path = plan_path(state)
            out = {"entry_node": "execute",
                   "events": [event("resume", at_node="execute", workflow_status=status)]}
            if path.is_file():
                out.update(_plan_summary(path))
            out.update(_restore_artifacts(state))
            return out

    path = plan_path(state)
    if not path.is_file():
        return {"entry_node": "cache_probe", "events": [event("resume", at_node="cache_probe")]}

    try:
        plan = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return {"entry_node": "cache_probe",
                "events": [event("resume", at_node="cache_probe",
                                 note=f"unreadable plan, replanning: {exc}")]}

    confidence = plan.get("confidence")
    grounding = run_dir(state) / "raw" / "literature_grounding.json"
    if confidence == UNREVIEWED or confidence not in VALID_CONFIDENCE:
        node = "adjudicate" if grounding.is_file() else "critique"
        out = {"entry_node": node, "plan_path": str(path),
               "polymer_class": plan.get("polymer_class"),
               **_restore_artifacts(state),
               "events": [event("resume", at_node=node, confidence=confidence)]}
        return out

    if plan.get("plan_mode") not in ("reasoned", "deterministic"):
        return {"entry_node": "materialize", "plan_path": str(path),
                "polymer_class": plan.get("polymer_class"),
                "events": [event("resume", at_node="materialize")]}

    return {"entry_node": "execute", **_plan_summary(path), **_restore_artifacts(state),
            "events": [event("resume", at_node="execute")]}


# ---------------------------------------------------------------------------
# cache_probe
# ---------------------------------------------------------------------------
def cache_probe(state: dict) -> dict:
    """Has this exact SMILES already got a frozen, validated protocol?

    A hit routes past classify, critique, adjudicate AND materialize, straight to execute.
    Skipping materialize is not an optimisation -- it is required for correctness.
    materialize_plan layers solve_system_size's recommended_params over decided_params, so
    running it on a cache replay would re-solve the cell and overwrite the very protocol
    make_plan_from_cache just replayed verbatim.

    Note guides/system_characterization_cache.json is `{}` on this branch, so this cannot
    fire until a first campaign is accepted and write_characterization_cache populates it.
    """
    from rules_common import canonicalize

    cache_file = Path(state["repo_root"]) / "guides" / "system_characterization_cache.json"
    try:
        canonical = canonicalize(state["smiles"])
    except Exception as exc:  # noqa: BLE001 -- an unreachable conda env is not fatal here
        return {"cache_hit": False, "canonical_smiles": None,
                "events": [event("cache_probe", hit=False, note=f"canonicalization failed: {exc}")]}

    entry = {}
    if cache_file.is_file():
        try:
            entry = (json.loads(cache_file.read_text()) or {}).get(canonical) or {}
        except (json.JSONDecodeError, OSError):
            entry = {}

    hit = bool(entry.get("protocol_validated"))
    out = {"canonical_smiles": canonical, "cache_hit": hit,
           "events": [event("cache_probe", hit=hit, canonical_smiles=canonical)]}
    if hit:
        out["polymer_class"] = entry.get("polymer_class")
        out["class_source"] = "characterization_cache"
    return out


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------
def classify(state: dict) -> dict:
    """Assign polymer_class, and record the full chemical-group profile behind it.

    This is the step a live session did by hand (or via the mol-builder MCP tool), and it
    decides far more than a name: get_class_entry supplies charge_method, electrostatics,
    cutoff_A, dt_fs, T_equil_K, density_initial_gcm3, the per-member experimental bands and
    the tacticity default. An unresolved class therefore REFUSES rather than guessing.

    It also records the molecule's REAL chemistry -- every functional group, wherever it
    sits -- and checks it against the constants that class carries. polyinfo_classifier
    matches on the extracted mainchain, so a pendant hydroxyl, nitrile or ester never
    informed the label; 404 of PI1070's 1077 repeat units carry exactly that kind of group.
    Those findings are ADVISORY: they are written to classification.json and handed to the
    adjudicating critic as context, and they never rewrite a class constant here.
    """
    try:
        result = classify_polymer(state["smiles"])
    except ClassificationError as exc:
        return _stop("classify_error", str(exc), smiles=state["smiles"])

    polymer_class = result["polymer_class"]
    try:
        class_entry = get_class_entry(load_rules(), polymer_class)
    except Exception:  # noqa: BLE001 -- the class is already validated by make_plan
        class_entry = {}
    chemistry = consistency(result.get("chemistry", {}), class_entry)

    out_path = run_dir(state) / "raw" / "classification.json"
    _write_json(out_path, {**result, "chemistry_consistency": chemistry,
                           "generated_at": _now_iso(), "run_name": state["run_name"]})

    events = [event("classify", polymer_class=polymer_class,
                    class_source=result["class_source"],
                    polyinfo_class=result.get("polyinfo_class"),
                    co_occurring=result.get("co_occurring"),
                    polarity=chemistry.get("polarity_class"),
                    backbone_groups=chemistry.get("backbone_groups"),
                    pendant_groups=chemistry.get("pendant_groups"),
                    chemistry_verdict=chemistry.get("verdict"))]
    events += [event("chemistry_finding", code=f["code"], severity=f["severity"],
                     detail=f["detail"]) for f in chemistry.get("findings", ())]
    return {
        "polymer_class": polymer_class,
        "class_source": result["class_source"],
        "classification_path": str(out_path),
        "chemistry": chemistry,
        "events": events,
    }


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------
def plan(state: dict) -> dict:
    """make_deterministic_plan run-plan — the deterministic core of planning.

    Everything numeric in the plan comes from here: D-01 is resolved (with a real EMC probe
    when the moiety screen finds a blocker), the cell is sized, hardware is selected and the
    run is priced. What it deliberately does NOT do is sign off -- it stamps
    confidence "unreviewed", which is invalid, and that is the gate the critic/adjudicator
    (or --no-llm's baseline) exists to clear.
    """
    path = plan_path(state)
    cmd = [VENV_PY, SCRIPT_DIR / "make_deterministic_plan.py", "run-plan",
           "--run_name", state["run_name"],
           "--polymer_class", state["polymer_class"],
           "--smiles", state["smiles"],
           "--properties", ",".join(state["properties"]),
           "--with-ff-probe", "--force"]
    if state.get("no_llm"):
        # --baseline stamps confidence "low" instead of "unreviewed", which is exactly the
        # deterministic arm: a runnable plan with no model in the loop.
        cmd.append("--baseline")

    r = _run(cmd, repo_root=state["repo_root"], timeout=1800)
    if r.returncode != 0 or not path.is_file():
        return _stop("plan_error",
                     f"run-plan failed (rc={r.returncode}): "
                     f"{(r.stderr or r.stdout).strip()[:1500]}")

    doc = json.loads(path.read_text())
    estimate = doc.get("cost_estimate") or {}
    return {
        "plan_path": str(path),
        "plan_mode": doc.get("plan_mode"),
        "confidence": doc.get("confidence"),
        "d01_admissible": ((doc.get("decisions") or [{}])[0]).get("admissible"),
        "cost_gpu_hours": estimate.get("total_gpu_hours"),
        "cost_unpriced": [u.get("stage", u) if isinstance(u, dict) else u
                          for u in (estimate.get("unpriced_stages") or [])],
        "events": [event("plan", plan_mode=doc.get("plan_mode"),
                         confidence=doc.get("confidence"),
                         gpu_hours=estimate.get("total_gpu_hours"))],
    }


# ---------------------------------------------------------------------------
# cost guards
# ---------------------------------------------------------------------------
def _cost_gate(state: dict, *, check_d01: bool, priced: bool) -> dict:
    path = state.get("plan_path")
    if not path or not Path(path).is_file():
        return _stop("plan_error", f"no run_plan.json to price at {path!r}")
    doc = guards.read_plan(path)
    if check_d01:
        d01 = guards.check_d01_admissible(doc)
        if not d01["ok"]:
            # Before any model spend: an unbuildable chemistry must not cost a critic call.
            return _stop(d01["status"], d01["detail"])

    verdict = guards.check_cost(doc, max_gpu_hours=state.get("max_gpu_hours"),
                                allow_unpriced=state.get("allow_unpriced", False),
                                priced=priced)
    if not verdict["ok"]:
        return _stop(verdict["status"], verdict["detail"],
                     gpu_hours=verdict.get("gpu_hours"), unpriced=verdict.get("unpriced"))
    return {"cost_gpu_hours": verdict.get("gpu_hours"),
            "cost_unpriced": verdict.get("unpriced") or [],
            "events": [event("cost_admitted", gpu_hours=verdict.get("gpu_hours"),
                             ceiling=state.get("max_gpu_hours"),
                             unpriced=verdict.get("unpriced"), note=verdict.get("note"))]}


def cost_guard_pre(state: dict) -> dict:
    """After planning, before any model spend.

    Its real job is the D-01 refusal -- an unbuildable chemistry must not cost a critic
    call. The cost half is best-effort here (priced=False): a scaffold carries
    cost_estimate: null because materialize_plan is what prices a run, so only an
    already-over-ceiling number can refuse at this point.
    """
    return _cost_gate(state, check_d01=True, priced=False)


def cost_guard_post(state: dict) -> dict:
    """After materialize, before execute.

    Not redundant with the pre-gate: materialize_plan recomputes cost_estimate after the
    adjudicator's overrides are applied and after solve_system_size may have moved
    dp_typical/nchain, so this is the first time the number reflects what will actually run.
    It is therefore the BINDING gate, and the only one that refuses an unpriceable plan.
    """
    return _cost_gate(state, check_d01=False, priced=True)


# ---------------------------------------------------------------------------
# critique
# ---------------------------------------------------------------------------
def critique(state: dict) -> dict:
    """The literature critic, headless.

    The prompt is .claude/agents/literature-grounding-worker.md itself, read at runtime and
    passed as --append-system-prompt, so that file stays the single source of truth and the
    headless behaviour cannot drift from what a live subagent would do. Only two of its
    instructions are overridden: it has no Write tool here, and it returns structured output
    instead of a RESULT block.

    Advisory by design -- SKILL.md is explicit that a literature-search failure must not
    block -- so every failure path records critic_verdict and proceeds.
    """
    if state.get("no_llm"):
        return {"critic_verdict": "skipped",
                "events": [event("critique", verdict="skipped", note="--no-llm")]}

    out_path = run_dir(state) / "raw" / "literature_grounding.json"
    preamble = (
        "\n\n## Driver overrides (headless invocation)\n\n"
        "You are running headlessly with NO Write tool and NO MCP tools. Two changes to the "
        "instructions above, and nothing else:\n\n"
        "1. Do NOT write `output_path` yourself and do NOT run the protocol_evidence.py "
        "ingest step. Return the Output JSON schema object as your structured output; the "
        "driver writes it and runs the ingest, stamping `generated_at` and `plan_reviewed`.\n"
        "2. Emit no `RESULT:` block. The JSON object is the whole answer.\n\n"
        "Everything else -- DOI verification, trust tiering, PolyDatabase first, WebSearch "
        "only as fallback, and every prohibition -- applies unchanged.\n"
    )
    prompt = (
        f"Critique the force-field decision in this run plan.\n"
        f"  run_name:   {state['run_name']}\n"
        f"  smiles:     {state['smiles']}\n"
        f"  polymer_class: {state['polymer_class']}\n"
        f"  properties: {', '.join(state['properties'])}\n"
        f"  plan_path:  {state['plan_path']}\n"
        f"  classification: {state.get('classification_path')}\n"
        f"  output_path: {out_path} (the driver writes it -- do not)\n"
    )

    try:
        grounding = invoke(prompt, schemas.GROUNDING_SCHEMA,
                           allowed_tools=("Read", "Bash(python3:*)", "Bash(jq:*)",
                                          "Bash(cat:*)", "Bash(grep:*)", "Bash(ls:*)",
                                          "Bash(sqlite3:*)", "WebSearch", "WebFetch"),
                           max_budget_usd=3.0, timeout_s=1800, model="sonnet",
                           append_system_prompt=markdown_body(CRITIC_MD) + preamble,
                           cwd=state["repo_root"])
    except (HeadlessError, subprocess.TimeoutExpired) as exc:
        # Never fatal: the critique is advisory, and a search failure that halted the run
        # would make the whole driver hostage to network weather.
        return {"critic_verdict": "error",
                "events": [event("critique", verdict="error", detail=str(exc)[:500])]}

    grounding = {**grounding, "generated_at": _now_iso(), "plan_reviewed": state["plan_path"]}
    _write_json(out_path, grounding)

    ingest = _run([VENV_PY, SCRIPT_DIR / "protocol_evidence.py", "ingest", "--store", "ff",
                   "--from", out_path, "--run-name", state["run_name"]],
                  repo_root=state["repo_root"], timeout=300)

    verdict = ((grounding.get("critique") or {}).get("D-01_ff") or {}).get("verdict")
    return {
        "grounding_path": str(out_path),
        "critic_verdict": verdict,
        "events": [event("critique", verdict=verdict,
                         n_studies=len(grounding.get("md_studies") or []),
                         # 0 records added is advisory, never a failure: the critic may
                         # legitimately find nothing new to store.
                         ingest_rc=ingest.returncode,
                         ingest=(ingest.stdout or "").strip()[:300])],
    }


# ---------------------------------------------------------------------------
# adjudicate
# ---------------------------------------------------------------------------
def adjudicate(state: dict) -> dict:
    """Apply or decline the critique, and sign the plan off.

    The prompt is SKILL.md step 5 itself, sliced at runtime -- the earlier steps instruct an
    interactive session to run tools the graph has already run. The model returns a decision;
    apply_adjudication performs every edit.
    """
    if state.get("no_llm") or state.get("critic_verdict") == "skipped":
        return {"events": [event("adjudicate", skipped=True, note="--no-llm")]}

    from scientific_control import planning_parameter_contract

    grounding_path = state.get("grounding_path")
    prompt = (
        f"{section(SKILL_MD, '## 5.', '## 6.')}\n"
        "---\n\n"
        "You are running headlessly with NO Write or Edit tool. Return the decision as "
        "structured output; the driver applies it after re-validating every override "
        "against scientific_control.validate_overrides, stamps origin='critic' on the "
        "evidence entries itself, and re-runs plan validation.\n\n"
        f"  plan:           {state['plan_path']}\n"
        f"  grounding:      {grounding_path or '(none -- the critic returned no usable result)'}\n"
        f"  classification: {state.get('classification_path')}\n"
        f"{_chemistry_brief(state)}"
    )
    try:
        decision = invoke(prompt, schemas.adjudication_schema(planning_parameter_contract()),
                          allowed_tools=("Read", "Bash(cat:*)", "Bash(jq:*)", "Bash(grep:*)",
                                         "Bash(sed:*)"),
                          # 1.5 was below the call's real cost and every adjudication on
                          # this box exited 1 with EMPTY stderr, degrading silently to the
                          # deterministic baseline -- indistinguishable from --baseline,
                          # because that is exactly what _fall_back_to_baseline stamps.
                          # Measured 2026-09-08: this prompt + schema costs $1.97 (a bare
                          # "say hi" against the same schema is already $0.42 in cache
                          # creation). The ceiling is a runaway stop, not a tight budget.
                          max_budget_usd=6.0, timeout_s=900, cwd=state["repo_root"])
    except (HeadlessError, subprocess.TimeoutExpired) as exc:
        # The call itself failed -- no decision was made. Degrade to the deterministic
        # baseline exactly as an invalid decision does, rather than returning quietly: the
        # plan on disk still reads confidence "unreviewed", which is INVALID, so materialize
        # would then die with PLAN_AGENT_CONTRACT_ERROR and a transient network blip would
        # kill a run that had already paid for its critique.
        return _fall_back_to_baseline(state, f"adjudication call failed ({exc})")

    return apply_adjudication(state, decision)


def _chemistry_brief(state: dict) -> str:
    """The molecule's own chemistry, put in front of the adjudicator explicitly.

    polymer_class is a backbone taxonomy, so the constants it carries were chosen without
    seeing any pendant group. Where that matters -- a hydroxyl or nitrile hanging off an
    otherwise apolar backbone, an H-bond network, a group measured to correlate with EMC
    build failure -- the adjudicator is the right place to weigh it, because the remedy is
    an `overrides` entry and that is the only thing it is allowed to write.

    Advisory framing is deliberate and stated in the prompt: these findings come from SMARTS
    over one repeat unit, while the class constants are curated against real validation runs.
    """
    chemistry = state.get("chemistry") or {}
    findings = chemistry.get("findings") or []
    if not findings:
        return ""
    lines = [f"  chemistry:      polarity={chemistry.get('polarity_class')}, "
             f"backbone={chemistry.get('backbone_groups')}, "
             f"pendant={chemistry.get('pendant_groups')}",
             "",
             "Chemistry findings for this repeat unit (ADVISORY -- these come from SMARTS "
             "over one repeat unit, while the class constants are curated against real "
             "validation runs, so weigh them, do not simply apply them):"]
    for f in findings:
        lines.append(f"  - [{f['severity']}] {f['code']}: {f['detail']}")
        if f.get("suggested_override"):
            lines.append(f"      suggested override: {json.dumps(f['suggested_override'])}")
    return "\n".join(lines) + "\n"


def _fall_back_to_baseline(state: dict, reason: str) -> dict:
    """Sign the plan off at the deterministic baseline when adjudication cannot be trusted.

    confidence "unreviewed" is what make_deterministic_plan stamps and it is deliberately
    INVALID -- it is the one thing standing between a scaffold and execution. So a failed
    adjudication cannot just decline to write: it has to leave the plan in a state the
    control plane will accept, or the run dies two nodes later for a reason that has nothing
    to do with the failure. "low" is the honest value -- it is exactly what --baseline
    stamps for the no-LLM arm -- and dominant_uncertainty records why.
    """
    path = Path(state["plan_path"])
    doc = json.loads(path.read_text())
    doc["confidence"] = "low"
    doc["dominant_uncertainty"] = f"{reason}; running the deterministic baseline"[:200]
    _write_json(path, doc)
    return {"adjudication": {}, "confidence": "low",
            "events": [event("adjudicate", degraded=reason[:300],
                             note="fell back to the deterministic baseline")]}


def _apply_field_change(doc: dict, overrides: dict, state: dict) -> list[str]:
    """Let the critic move the FORCE FIELD, safely. Returns findings to append.

    Until now the adjudicator -- the one component that actually reads force-field
    literature -- was the one component that could not act on it. Setting
    overrides.preferred_ff wrote decided_params.preferred_ff while D-01_ff.choice kept the
    old field, and validate_run_plan.py's `ff_choice_not_applied` then failed the plan as
    structural. apply_recovery (scientific_control.py) has carried the correct handling for
    a field move all along; this is that logic on the adjudication path, plus the check
    recovery does not need.

    Two things happen, in order:

      1. BUILDABILITY IS MEASURED, not assumed. forcefield.select_by_moiety only probes when
         a moiety rule BLOCKS, so a SMILES that trips no rule reaches adjudication with its
         admissible set unmeasured -- the critic is reasoning about a field nobody has tried.
         A real EMC trial build (~5 s, dp=4/nchains=2) decides. Measured 2026-09-08: compass
         types 2 of this campaign's 7 repeat units, so an unchecked switch would plan a run
         that dies at the build stage. On failure the FIELD override alone is dropped and the
         rest of the critique still applies -- a bad field suggestion should not cost the
         evidence and the uncertainty statement that came with it.
      2. Everything the field implies moves with it: D-01_ff.choice, charge_method,
         electrostatics, and the hardware block. Without this the derivation disagrees with
         the field actually built -- the exact bug apply_recovery's own comment describes.
    """
    field = overrides.get("preferred_ff")
    decided = doc.get("decided_params") or {}
    if not field or field == decided.get("preferred_ff"):
        return []

    sys.path.insert(0, str(SCRIPT_DIR))
    import forcefield  # noqa: PLC0415 -- in-env import, same seam as validate_overrides above
    from make_deterministic_plan import _derived_from_field  # noqa: PLC0415
    from rules_common import load_rules  # noqa: PLC0415

    smiles = state.get("smiles") or doc.get("smiles")
    try:
        probe = forcefield.check_typing(smiles, field)
    except Exception as exc:  # noqa: BLE001 -- an unbuildable field is a result, not a crash
        probe = {"types_smiles": False, "typing_error": f"{type(exc).__name__}: {exc}"}
    if not probe.get("types_smiles"):
        overrides.pop("preferred_ff", None)
        return [f"Critic proposed preferred_ff={field!r}; DECLINED -- a real EMC trial build "
                f"could not type this repeat unit with it "
                f"({str(probe.get('typing_error'))[:200]}). The rest of the critique stands."]

    rules = load_rules()
    derived = _derived_from_field(field, rules)
    for row in doc.get("decisions") or []:
        if row.get("id") == "D-01_ff":
            row["choice"] = field
    for key in ("charge_method", "electrostatics"):
        if key not in overrides:
            overrides[key] = derived[key]
    doc["hardware"] = {k: derived[k] for k in ("engine", "mpi_ranks", "gpu_per_run", "ff_family")}
    return [f"Critic moved the force field to {field!r}; a real EMC trial build types this "
            f"repeat unit with it. D-01_ff.choice, charge_method, electrostatics and the "
            f"hardware block were re-derived to match."]


def apply_adjudication(state: dict, decision: dict) -> dict:
    """Write the adjudicator's decision into run_plan.json — the whole enforcement.

    Exactly five things change, so SKILL.md step 5's edit restriction is structural rather
    than a prompt the model might wander from:

      overrides                    replaced (not merged): materialize_plan copies this
                                   wholesale into decided_params, so a merge would silently
                                   keep a superseded key alive.
      preferred_ff                 if the critic moves the FIELD, the row it critiqued and
                                   everything the field implies move with it -- see
                                   _apply_field_change. Gated on a real EMC trial build.
      confidence                   the execution gate.
      dominant_uncertainty         scalar.
      decisions[0].evidence        APPEND ONLY, origin stamped 'critic' here. autofill
                                   entries are the deterministic baseline that
                                   benchmarks/.../llm_contribution.py measures against, so
                                   they can be neither retagged nor deleted.
      decisions[0].critique.findings   append only.

    On an invalid override the plan is left untouched and the run degrades to the
    deterministic baseline (confidence 'low') rather than halting -- a model hiccup should
    cost the critique, not the campaign.
    """
    from scientific_control import validate_overrides

    path = Path(state["plan_path"])
    doc = json.loads(path.read_text())
    overrides = dict(decision.get("overrides") or {})

    try:
        validate_overrides(overrides)
    except Exception as exc:  # noqa: BLE001 -- ValueError today, but never worth crashing on
        return _fall_back_to_baseline(state, f"adjudication rejected ({exc})")

    field_findings = _apply_field_change(doc, overrides, state)

    confidence = decision.get("confidence")
    if confidence not in VALID_CONFIDENCE:
        confidence = "low"

    doc["overrides"] = overrides
    doc["confidence"] = confidence
    if decision.get("dominant_uncertainty"):
        doc["dominant_uncertainty"] = decision["dominant_uncertainty"]

    decisions = doc.get("decisions") or []
    if decisions:
        row = decisions[0]
        evidence = list(row.get("evidence") or [])
        for item in decision.get("critic_evidence") or []:
            evidence.append({"claim": item.get("claim"),
                             "source_doi": item.get("source_doi"),
                             "citation": item.get("citation"),
                             "origin": "critic"})
        row["evidence"] = evidence
        findings = list((row.get("critique") or {}).get("findings") or [])
        findings.extend(decision.get("findings") or [])
        findings.extend(field_findings)
        row["critique"] = {**(row.get("critique") or {}), "findings": findings}

    _write_json(path, doc)

    validation = _run([VENV_PY, SCRIPT_DIR / "validate_run_plan.py", "--run_plan", path],
                      repo_root=state["repo_root"], timeout=300)
    return {
        "adjudication": {"overrides": overrides, "confidence": confidence},
        "confidence": confidence,
        "events": [event("adjudicate", confidence=confidence, overrides=overrides,
                         n_critic_evidence=len(decision.get("critic_evidence") or []),
                         validate_rc=validation.returncode)],
    }


# ---------------------------------------------------------------------------
# materialize
# ---------------------------------------------------------------------------
def materialize(state: dict) -> dict:
    """scientific_control --dry-run: promote the signed-off plan to an executable one.

    This resolves every stage parameter, re-solves the cell, re-prices the run and rewrites
    run_plan.json IN PLACE (scaffold -> reasoned). It is also the reason cost_guard_post
    exists: this is where the estimate first reflects the adjudicator's overrides.

    --dry-run here means "do not execute", not "do not write" -- the control plane writes
    the plan and control_state.json on this path deliberately.
    """
    r = _run([VENV_PY, SCRIPT_DIR / "scientific_control.py",
              "--run-name", state["run_name"], "--goal", state["goal"],
              "--smiles", state["smiles"], "--properties", ",".join(state["properties"]),
              "--plan", state["plan_path"], "--dry-run"],
             repo_root=state["repo_root"], timeout=1800)
    if r.returncode != 0:
        return _stop("materialize_error",
                     f"materialize failed (rc={r.returncode}): "
                     f"{(r.stderr or r.stdout).strip()[:1500]}")

    doc = json.loads(Path(state["plan_path"]).read_text())
    estimate = doc.get("cost_estimate") or {}
    return {
        "plan_mode": doc.get("plan_mode"),
        "confidence": doc.get("confidence"),
        "cost_gpu_hours": estimate.get("total_gpu_hours"),
        "events": [event("materialize", plan_mode=doc.get("plan_mode"),
                         confidence=doc.get("confidence"),
                         gpu_hours=estimate.get("total_gpu_hours"),
                         resolved_by=(doc.get("system_size") or {}).get("resolved_by"))],
    }


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------
def execute(state: dict) -> dict:
    """Hand the campaign to agent_api and wait.

    Run as a SUBPROCESS under mcp-servers/.venv, the campaign_watchdog pattern, for three
    reasons: langgraph never enters the process that imports the LAMMPS/EMC server modules;
    the driver is not tied to that interpreter; and the progress poller has a separate
    process to observe.

    Recovery is the INNER path -- --recovery-agent-command hands recovery_agent_cli to
    WorkflowEngine, which escalates per stage under MAX_AGENT_DECISIONS=2 and records every
    call in workflow_state.agent_escalations. Whatever comes back is terminal; see
    state.EXIT_CODES for why re-entering would only burn GPU time.

    Under --no-llm that command is NOT passed. Until 2026-09-09 it was passed
    unconditionally, so the "deterministic arm" still consulted a model up to twice on any
    escalation -- `no_llm` reached critique() and adjudicate() but never workflow_engine,
    scientific_control or agent_api. That made the arm unusable as a baseline for measuring
    the LLM's incremental contribution, which is exactly what it exists for. With no command,
    WorkflowEngine._escalate returns escalation_required (exit 2) instead of calling out, so
    the arm halts where an LLM would have been consulted and the difference is measurable.
    """
    if state.get("dry_run"):
        return {"workflow_status": "skipped",
                "events": [event("execute", skipped=True, note="--dry-run")]}

    recovery = f"{VENV_PY} {SCRIPT_DIR / 'recovery_agent_cli.py'}"
    # An empty list, not a None argument: agent_api takes --recovery-agent-command or
    # nothing, and passing the flag with an empty value would hand WorkflowEngine a command
    # string that fails at exec time rather than an absent one it routes around.
    recovery_args = [] if state.get("no_llm") else ["--recovery-agent-command", recovery]
    resuming = (run_dir(state) / "workflow_state.json").is_file()
    if resuming:
        cmd = [VENV_PY, SCRIPT_DIR / "agent_api.py", "resume", state["run_name"],
               *recovery_args]
    else:
        cmd = [VENV_PY, SCRIPT_DIR / "agent_api.py", "start",
               "--run-name", state["run_name"], "--goal", state["goal"],
               "--smiles", state["smiles"], "--properties", ",".join(state["properties"]),
               "--plan", state["plan_path"], *recovery_args]

    r = _run(cmd, repo_root=state["repo_root"], timeout=state.get("execute_timeout_s", 604800))
    # Take the LAST JSON value off stdout rather than requiring the whole stream to be JSON,
    # the same convention DeterministicScriptChain.execute uses for validate_run_plan. It
    # matters more here than there: run_campaign_workflow loads the LAMMPS and EMC server
    # modules IN-PROCESS, so any one of them printing a line to stdout would otherwise make
    # a campaign that actually succeeded report as failed -- with workflow_state.json on disk
    # saying the opposite. Diagnostics go to stderr today; this is the guard for the day one
    # of them does not.
    result = _last_json_value(r.stdout)
    if not isinstance(result, dict):
        return _stop("failed",
                     f"agent_api returned no parsable result (rc={r.returncode}): "
                     f"{(r.stderr or r.stdout).strip()[:1500]}")

    status = result.get("status")
    finding = result.get("finding") or {}
    return {
        "execute_result": result,
        "workflow_status": status,
        "workflow_stage": result.get("stage"),
        "finding_code": finding.get("code"),
        "status": status if status in ("accepted", "escalation_required", "failed") else "failed",
        "detail": finding.get("details") or result.get("reason") or "",
        "events": [event("execute", status=status, stage=result.get("stage"),
                         finding=finding.get("code"), resumed=resuming)],
    }
