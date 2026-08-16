#!/usr/bin/env python3
"""
verify_protocol_replay.py — prove a run's recorded protocol is the protocol it actually ran, by
regenerating its LAMMPS decks from its own run_plan.json and diffing them against the decks the
run left on disk.

This is the gate that stops a DECORATIVE parameter from being frozen as protocol. The failure
mode is real and has shipped: cutoff_A was recorded as 12.0 in 32/36 runs while 9.5 actually ran.
Freezing that plan would give every replicate a faithful reproduction of a protocol that never
executed. A plan value that never reached a deck fails here, named, at lock time.

  python3 orchestration/scripts/verify_protocol_replay.py --run_dir data/<RUN> [--json]

Exit 0 = clean (only seeds and paths differ). Exit 1 = dirty or refused.

NORMALIZATION — differences that are expected and must not count as divergence:
  seeds        the whole point of a replicate is a different seed
  paths        the replay writes to a scratch dir, so absolute paths differ everywhere
  timestamps   generator banners

REFUSALS — a plan mutated mid-run has no single deck set corresponding to it. decided_params is
edited in place (PSU1 went nchain 20 -> 32 after an L/2Rg failure), so a plan carrying
`amendments` or `revision_history` describes a moving target: refuse rather than report a
misleading diff.
"""

import argparse
import difflib
import json
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from gen_prompt import apply_plan, resolve_hardware, resolve_stage_params  # noqa: E402
from hw_common import load_rules, get_class_entry  # noqa: E402
import execution_chain as ec  # noqa: E402

LAMMPS_ENGINE_DIR = REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"

# ── Normalization ────────────────────────────────────────────────────────────
_SUBS = [
    # `velocity all create <temp> <seed> ...` — the seed is the 4th token.
    (re.compile(r"(velocity\s+\S+\s+create\s+\S+\s+)(-?\d+)"), r"\1<SEED>"),
    # langevin / other explicit seed args
    (re.compile(r"(fix\s+\S+\s+\S+\s+langevin\s+\S+\s+\S+\s+\S+\s+)(-?\d+)"), r"\1<SEED>"),
    # Any path -> basename, so a scratch replay dir compares equal to the run dir. Relative
    # paths are matched too: a caller passing `data/RUN/...` instead of `/home/.../data/RUN/...`
    # otherwise leaves a phantom difference on every deck that includes a params file.
    (re.compile(r"(?<![\w.])(?:/|\.{0,2}/|[\w.\-]+/)[\w.\-/]*/([\w.\-]+\.[\w]+)"), r"<PATH>/\1"),
    (re.compile(r"(/[\w.\-/]+/)([\w.\-]+)"), r"<PATH>/\2"),
    (re.compile(r"^#.*\d{4}-\d{2}-\d{2}.*$", re.M), "# <DATE>"),
]


_NUM = re.compile(r"(?<![\w.])(-?\d+\.?\d*(?:[eE][-+]?\d+)?)(?![\w.])")


def _canon_numbers(line: str) -> str:
    """`timestep 1` and `timestep 1.0` are the same protocol. Canonicalize numeric tokens so
    formatting drift in the generator is not reported as a parameter divergence — while a genuine
    200000-vs-500000 difference still is."""
    def sub(m):
        try:
            v = float(m.group(1))
        except ValueError:
            return m.group(1)
        return str(int(v)) if v == int(v) else repr(v)
    return _NUM.sub(sub, line)


def normalize(text: str) -> list:
    for pat, rep in _SUBS:
        text = pat.sub(rep, text)
    return [_canon_numbers(ln.rstrip()) for ln in text.splitlines() if ln.strip()]


def _is_numeric_divergence(diff_lines) -> bool:
    """True when the two decks differ in a NUMBER (a protocol parameter), as opposed to a line
    existing in one and not the other (a generator feature added or removed since the run).
    Both are reported; only the former makes the verdict dirty, because only the former means the
    plan records a value the run did not execute."""
    added = [l[1:].strip() for l in diff_lines if l.startswith("+")]
    removed = [l[1:].strip() for l in diff_lines if l.startswith("-")]
    for a in added:
        stripped_a = _NUM.sub("#", a)
        for r in removed:
            if _NUM.sub("#", r) == stripped_a and a != r:
                return True   # same statement, different number
    return False


def _load(p: Path):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _load_server():
    """Import the engine server as a plain module — same technique (and same justification)
    run_deterministic_replicate.py uses: FastMCP's @mcp.tool() returns the original function."""
    import importlib.util, os
    old = os.getcwd()
    try:
        os.chdir(LAMMPS_ENGINE_DIR)
        sys.path.insert(0, str(LAMMPS_ENGINE_DIR))
        spec = importlib.util.spec_from_file_location("replay_engine",
                                                      str(LAMMPS_ENGINE_DIR / "server.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["replay_engine"] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.chdir(old)


# ── Deck comparison ──────────────────────────────────────────────────────────

def compare(original: Path, replayed: Path) -> dict:
    a, b = normalize(original.read_text()), normalize(replayed.read_text())
    if a == b:
        return {"deck": original.name, "clean": True}
    diff = [ln for ln in difflib.unified_diff(a, b, "executed", "replayed", lineterm="", n=0)
            if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]
    numeric = _is_numeric_divergence(diff)
    return {"deck": original.name, "clean": not numeric,
            "kind": "parameter_divergence" if numeric else "generator_drift",
            "diff": diff[:40], "n_differences": len(diff)}


def _newest(paths):
    """A stage re-run after a RECOVERY leaves more than one deck; the newest is the one that
    produced the run's final state."""
    ps = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)
    return ps[0] if ps else None


def deck_inputs(deck: Path) -> dict:
    """The .data and .params a retained deck actually read. Taken from the deck itself rather
    than guessed from directory layout: EMC runs copy the cell next to the decks, and an EMC cell
    carries no inline Coeffs, so replaying without its .params fails pre-flight for a reason that
    has nothing to do with protocol divergence."""
    out = {}
    for line in deck.read_text().splitlines():
        s = line.strip()
        if s.startswith("read_data ") and "data_file" not in out:
            out["data_file"] = s.split(None, 1)[1].strip()
        elif s.startswith("include ") and "params_file" not in out:
            out["params_file"] = s.split(None, 1)[1].strip()
    return out


def verify(run_dir: Path) -> dict:
    run_dir = run_dir.resolve()
    run_name = run_dir.name
    plan_path = run_dir / "raw" / "run_plan.json"
    plan = _load(plan_path)
    if plan is None:
        return {"status": "refused", "reason": "no_run_plan", "run": run_name}

    for key in ("amendments", "revision_history"):
        if plan.get(key):
            return {"status": "refused", "reason": "plan_amended_mid_run", "run": run_name,
                    "detail": f"run_plan.json carries `{key}` — decided_params was mutated "
                              "mid-run, so no single deck set corresponds to it. Not "
                              "replayable, and not eligible to freeze."}

    lammps_dir = run_dir / "lammps"
    if not lammps_dir.exists():
        return {"status": "refused", "reason": "no_retained_decks", "run": run_name}

    replay_dir = run_dir / "raw" / "replay"
    if replay_dir.exists():
        shutil.rmtree(replay_dir)
    replay_dir.mkdir(parents=True, exist_ok=True)

    rules = load_rules()
    args = ec.base_args(run_name, plan["polymer_class"], str(plan_path))
    cls = apply_plan(get_class_entry(rules, plan["polymer_class"]), plan, args)
    resolve_hardware(args, cls, rules)
    engine = _load_server()

    results, refusals = [], []

    # ── equilibration decks ──
    equil_orig = lammps_dir / "equil"
    if equil_orig.exists():
        p = resolve_stage_params("equil", args, cls)
        flags = p["lammps_flags"]
        # n_atoms from the run's OWN built cell, so the atom-count tier resolves the same way it
        # did originally — otherwise every step count would differ for a reason that is not a
        # protocol divergence.
        first_deck = _newest(list(equil_orig.glob("minimize/minimize.in"))) \
            or _newest(list(equil_orig.rglob("*.in")))
        inputs = deck_inputs(first_deck) if first_deck else {}
        src_data = inputs.get("data_file")
        if not src_data or not Path(src_data).exists():
            cell_dir = lammps_dir / "cell"
            src_data = str(_newest(list(cell_dir.glob("*.data")))) if cell_dir.exists() else None
        wf = engine.generate_equilibration_workflow(
            data_file=str(src_data), params_file=inputs.get("params_file", ""),
            work_dir_base=str(replay_dir / "equil"),
            polymer_name=run_name, temp=p["T_workflow_K"], max_temp=p["T_anneal_high_K"],
            press=p["P_equil_atm"], use_pcff=flags["use_pcff"], use_trappe=flags["use_trappe"],
            use_opls=flags["use_opls"], npt_prod_steps=p["npt_prod_steps"],
            nvt_prod_steps=p["nvt_prod_steps"],
            add_melt_npt=p["add_melt_npt"],
            t_equil_K=p["T_equil_K"] if p["add_melt_npt"] else None,
            melt_npt_steps=p["melt_npt_steps"], npt_cool_steps=p["npt_cool_steps"],
            npt_cool300_steps=p["npt_cool300_steps"], npt_prod300_steps=p["npt_prod300_steps"],
            npt_anneal_cycles=p["npt_anneal_cycles"],
            npt_anneal_cycle_steps=p["npt_anneal_cycle_steps"],
            extend_steps=None,
            engine=p["engine"], velocity_seed=p["velocity_seed"],
        )
        if wf.get("status") != "success":
            refusals.append({"stage": "equil", "reason": "regeneration_failed",
                             "detail": wf.get("error"), "validation": wf.get("validation_errors")})
        else:
            for stage in wf["stages"]:
                name = stage["name"]
                orig = _newest(list(equil_orig.glob(f"{name}/{name}.in")))
                new = Path(stage["work_dir"]) / f"{name}.in"
                if orig and new.exists():
                    results.append(compare(orig, new))
                elif new.exists():
                    # The plan's decided_params regenerate a stage this run never had on disk —
                    # a decided_param that changes the deck shape without the original run ever
                    # having executed it. Report it as divergence, not a silent skip: this is the
                    # same failure verify_protocol_replay exists to catch, just at the stage-count
                    # level instead of the per-line level.
                    results.append({
                        "deck": f"{name}.in", "clean": False, "kind": "extra_stage",
                        "diff": [f"+ (new stage, not present in original run at {equil_orig})"],
                        "n_differences": 1,
                    })

    # ── Tg sweep deck ──
    tg_orig = _newest(list((lammps_dir / "thermal").rglob("tg_sweep.in"))) \
        if (lammps_dir / "thermal").exists() else None
    if tg_orig is not None:
        p = resolve_stage_params("tg", args, cls)
        out = replay_dir / "thermal" / "tg_sweep.in"
        out.parent.mkdir(parents=True, exist_ok=True)
        params = {"LOG_FILE": "tg_sweep.log", "DUMP_FILE": "", "WRITE_PER_T_DUMP": True,
                  "PER_T_DUMP_FILE": "per_t_structs.dump", "T_START": p["T_start_K"],
                  "T_END": p["T_end_K"], "T_STEP": p["T_step_K"],
                  "N_STEPS_PER_T": p["n_steps_per_t"], "P_START": 1.0, "P_FINAL": 1.0,
                  "T_DAMP": 100.0, "TIMESTEP": p["dt_fs"],
                  "use_pppm": not p["lammps_flags"]["use_trappe"], "use_gpu": True,
                  "engine": p["engine"]}
        tg_inputs = deck_inputs(tg_orig)
        if tg_inputs.get("params_file"):
            params["params_file"] = tg_inputs["params_file"]
        elif p.get("emc_params_path"):
            params["params_file"] = p["emc_params_path"]
        params.update({f"use_{k.split('_')[1]}": v for k, v in p["lammps_flags"].items()})
        r = engine.generate_script(
            template_name="npt_tg_step",
            data_file=tg_inputs.get("data_file") or p["equil_data_path"],
            output_script=str(out), velocity_seed=p["velocity_seed"], params=params)
        if r.get("status") == "error":
            refusals.append({"stage": "tg", "reason": "regeneration_failed", "detail": r})
        elif out.exists():
            results.append(compare(tg_orig, out))

    dirty = [r for r in results if not r["clean"]]
    drift = [r for r in results if r["clean"] and r.get("kind") == "generator_drift"]
    status = "refused" if (refusals and not results) else ("dirty" if dirty else "clean")
    return {"status": status, "run": run_name,
            "decks_compared": len(results), "decks_clean": len(results) - len(dirty),
            "tracks": _track_verdicts(results, refusals),
            "dirty": dirty, "generator_drift": drift, "refusals": refusals,
            "replay_dir": str(replay_dir)}


def deck_track(deck_name: str) -> str:
    if deck_name.startswith("tg_sweep"):
        return "thermal"
    if deck_name.startswith(("05_deform", "bm_")):
        return "mechanical"
    return "foundation"


def _track_verdicts(results, refusals) -> dict:
    """Per-track replay verdict, so a divergence in one track's deck blocks only that track's
    freeze. None = no deck for this track was compared (nothing proven either way)."""
    tracks = {}
    for track in ("foundation", "thermal", "mechanical"):
        mine = [r for r in results if deck_track(r["deck"]) == track]
        blocked = [r["stage"] for r in refusals
                   if {"equil": "foundation", "tg": "thermal",
                       "deform": "mechanical"}.get(r["stage"]) == track]
        if not mine:
            tracks[track] = {"verified": None,
                             "reason": "regeneration_failed" if blocked else "no_deck_compared"}
        else:
            bad = [r["deck"] for r in mine if not r["clean"]]
            tracks[track] = {"verified": not bad, "decks": len(mine), "diverged": bad}
    return tracks


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--run_dir", required=True)
    ap.add_argument("--json", action="store_true", help="Emit the full result as JSON.")
    a = ap.parse_args()
    result = verify(Path(a.run_dir))
    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{result['run']}: {result['status'].upper()} "
              f"({result.get('decks_clean', 0)}/{result.get('decks_compared', 0)} decks clean)")
        for d in result.get("dirty", []):
            print(f"\n  {d['deck']} — {d['n_differences']} differences")
            for ln in d["diff"]:
                print(f"    {ln}")
        for r in result.get("refusals", []):
            print(f"  REFUSED {r['stage']}: {r['reason']} — {r.get('detail')}")
        if result["status"] == "refused" and not result.get("refusals"):
            print(f"  {result.get('reason')}: {result.get('detail', '')}")
    sys.exit(0 if result["status"] == "clean" else 1)


if __name__ == "__main__":
    main()
