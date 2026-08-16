#!/usr/bin/env python3
"""
Protocol freezing: a novel run records the protocol it ACTUALLY RAN, so a replicate reproduces it
with different seeds.

Two properties carry the whole feature, and each has a live counterexample in this repo:

  1. Freezing binds on PHYSICAL VALIDITY, not agreement with experiment. PLA1's density sits
     2.2% below its experimental target while every foundation gate passes — it must freeze.
  2. A plan value that never reached a deck is not protocol. PLA1's plan records
     tg_steps_per_t=500000 while its sweep ran 200000 (rate=100 K/ns), a 2.5x cooling-rate
     error that would change Tg — its thermal track must NOT freeze.

Tests touching data/ are skipped when the run dir is absent (data/ is git-excluded).
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import execution_chain as ec                      # noqa: E402
import make_deterministic_plan as mdp             # noqa: E402
import run_deterministic_replicate as rdr         # noqa: E402
import verify_protocol_replay as vpr              # noqa: E402
from gen_prompt import apply_plan, resolve_hardware  # noqa: E402
from hw_common import load_rules, get_class_entry    # noqa: E402

DATA = REPO_ROOT / "data"


def _needs(run):
    if not (DATA / run / "raw" / "run_plan.json").exists():
        pytest.skip(f"{run} not present (data/ is git-excluded)")
    return DATA / run


# ── Field categories ─────────────────────────────────────────────────────────

def test_seeds_are_never_frozen():
    """A frozen seed would make every replicate reproduce the source run exactly — the opposite
    of a replicate."""
    for key in ("emc_seed", "velocity_seed"):
        assert key in mdp.NEVER_FREEZE
        assert key not in mdp.FREEZE_KEYS


def test_host_wiring_is_never_frozen():
    """Freezing these would tie the protocol to the box it was measured on and contradict
    /calibrate-hardware."""
    for key in ("engine", "mpi_ranks", "gpu_per_run", "gpu_ids"):
        assert key in mdp.NEVER_FREEZE
        assert key not in mdp.FREEZE_KEYS


def test_backbone_types_is_frozen():
    """The executor hard-halts BACKBONE_TYPES_UNRESOLVED without it, and it is molecule-specific
    so the class scaffold cannot supply it."""
    assert "backbone_types" in mdp.FREEZE_KEYS


def test_frozen_stage_params_are_physics_only():
    """A resolved stage dict also carries absolute output paths and the launch engine. Freezing
    either would pin the protocol to one run directory and one machine."""
    frozen = mdp.freeze_stage_params({
        "T_START": 700.0, "T_DAMP": 100.0, "P_DAMP": 1000.0, "N_STEPS": 1000000,
        "TIMESTEP": 1.0, "use_pcff": True,
        "LOG_FILE": "npt_cool.log", "DUMP_FILE": "npt_cool.dump",
        "WRITE_DATA_FILE": "/home/x/data/RUN/lammps/equil/npt_cool/npt_cool_out.data",
        "params_file": "/home/x/data/RUN/lammps/equil/emc_build.params",
        "engine": "kokkos", "use_gpu": True, "write_restart": True,
    })
    assert frozen == {"T_START": 700.0, "T_DAMP": 100.0, "P_DAMP": 1000.0,
                      "N_STEPS": 1000000, "TIMESTEP": 1.0, "use_pcff": True}


def test_cache_carries_no_paths_or_engine():
    cache = json.loads((REPO_ROOT / "guides" / "system_characterization_cache.json").read_text())
    for smiles, entry in cache.items():
        blob = json.dumps(entry.get("protocol") or {})
        assert "/home/" not in blob, f"{smiles}: absolute path frozen into protocol"
        for host_value in ("kokkos", "gpu_ids", "mpi_ranks"):
            assert f'"{host_value}"' not in blob, f"{smiles}: host wiring frozen into protocol"


def test_key_track_partition():
    assert mdp.key_track("tg_t_high_K") == "thermal"
    assert mdp.key_track("bm_pressures_atm") == "mechanical"
    assert mdp.key_track("K_deform_rate_inv_s") == "mechanical"
    assert mdp.key_track("cutoff_A") == "foundation"
    # The thermal track MEASURES alpha, but as a decided_param it is an INPUT to the foundation
    # cooling-contraction check.
    assert mdp.key_track("alpha_glass_per_K") == "foundation"


def test_partition_drops_never_freeze():
    out = mdp.partition_frozen_params(
        {"cutoff_A": 9.5, "tg_t_high_K": 600, "emc_seed": 42, "mpi_ranks": 8})
    assert out["foundation"]["cutoff_A"] == 9.5
    assert out["thermal"]["tg_t_high_K"] == 600
    flat = {k for track in out.values() for k in track}
    assert "emc_seed" not in flat and "mpi_ranks" not in flat


# ── Validity gates, not agreement ────────────────────────────────────────────

def test_validity_gates_read_from_run_artifacts():
    raw = _needs("PLA1") / "raw"
    gates = mdp.read_validity_gates(raw)
    assert gates["foundation"]["gates"]["finite_size_verdict"] == "SIZE_PASS"
    assert gates["foundation"]["gates"]["homogeneity_verdict"] == "HOMOG_PASS"


def test_unadjudicated_gate_is_not_a_pass():
    """`pass` must be None, never False->skip or True->freeze, when a verdict is simply absent."""
    gates = mdp.read_validity_gates(Path("/nonexistent"))
    for track in ("foundation", "thermal", "mechanical"):
        assert gates[track]["pass"] is None


def test_freeze_refuses_without_foundation():
    """Foundation is a prerequisite: no equilibration verdict means nothing is freezable."""
    run = _needs("PLA1")
    plan = json.loads((run / "raw" / "run_plan.json").read_text())
    protocol, _ = mdp.build_frozen_protocol(plan, Path("/nonexistent"), "X")
    assert protocol == {}


def test_density_off_experiment_still_freezes():
    """PLA1's density is ~2.2% below its experimental target. Under the OLD all-PASS agreement
    check that blocked the lock; under validity gates it must freeze, because the deficit is a
    force-field artifact a replicate should reproduce, not a protocol defect."""
    run = _needs("PLA1")
    gate = run / "raw" / "equilibration_gate_full.json"
    if not gate.exists():
        pytest.skip("equil gate verdict not backfilled for PLA1")
    plan = json.loads((run / "raw" / "run_plan.json").read_text())
    replay = vpr.verify(run)
    protocol, _ = mdp.build_frozen_protocol(plan, run / "raw", "PLA1", replay)

    density = json.loads((run / "raw" / "equilibrated_density.json").read_text())
    rho = density.get("plateau_density_mean")
    assert rho is not None and abs(rho - 1.248) / 1.248 > 0.01, "expected a real disagreement"
    assert "foundation" in protocol


# ── Deck-replay gate ─────────────────────────────────────────────────────────

def test_replay_refuses_amended_plan():
    """decided_params is mutated in place mid-run, so an amended plan has no single deck set
    corresponding to it — refuse rather than emit a misleading diff."""
    for run in ("PMMA1", "cis-PBD1"):
        d = DATA / run
        if not (d / "raw" / "run_plan.json").exists():
            continue
        result = vpr.verify(d)
        assert result["status"] == "refused"
        assert result["reason"] == "plan_amended_mid_run"


def test_replay_clean_run_verifies():
    run = _needs("PSU1")
    result = vpr.verify(run)
    assert result["status"] == "clean", result.get("dirty")
    assert result["tracks"]["foundation"]["verified"] is True


def test_replay_catches_decorative_parameter():
    """PLA1's plan says 500000 steps/T; its deck ran 200000. Freezing that would give every
    replicate a 2.5x slower cooling rate, hence a different Tg."""
    run = _needs("PLA1")
    result = vpr.verify(run)
    assert result["tracks"]["thermal"]["verified"] is False
    assert any("tg_sweep" in d["deck"] for d in result["dirty"])


def test_diverged_track_does_not_freeze():
    run = _needs("PLA1")
    if not (run / "raw" / "equilibration_gate_full.json").exists():
        pytest.skip("equil gate verdict not backfilled for PLA1")
    plan = json.loads((run / "raw" / "run_plan.json").read_text())
    protocol, _ = mdp.build_frozen_protocol(plan, run / "raw", "PLA1", vpr.verify(run))
    assert "foundation" in protocol
    assert "thermal" not in protocol, "a diverged deck must block its own track"
    assert protocol["foundation"]["verified_by_deck_replay"] is True


def test_formatting_drift_is_not_divergence():
    """`timestep 1` and `timestep 1.0` are the same protocol; 200000 vs 500000 is not."""
    assert vpr.normalize("timestep 1") == vpr.normalize("timestep 1.0")
    assert vpr.normalize("run 200000") != vpr.normalize("run 500000")


def test_seed_and_path_differences_are_normalized():
    a = "velocity all create 300.0 12345 mom yes\nread_data /a/b/cell.data"
    b = "velocity all create 300.0 99999 mom yes\nread_data /x/y/cell.data"
    assert vpr.normalize(a) == vpr.normalize(b)


def test_relative_paths_normalize_like_absolute():
    """A caller passing `data/RUN/...` rather than `/home/.../data/RUN/...` must not leave a
    phantom difference on every deck that includes a params file."""
    assert (vpr.normalize("include /home/u/repo/data/R/lammps/equil/emc_build.params")
            == vpr.normalize("include data/R/lammps/equil/emc_build.params"))


# ── Acceptance: same protocol, different seed ────────────────────────────────

def test_executor_and_chain_agree_on_pinned_steps():
    """The plan's execution_chain and the executor must resolve step counts the SAME way.
    They are two code paths (execution_chain._equil and _submit_equil_chain/_emit_decks); if only
    one consults the frozen equil_stages, the plan advertises a protocol the run does not execute
    — precisely the decorative-parameter failure this feature exists to prevent."""
    frozen_stages = [
        {"name": "npt_production", "params": {"N_STEPS": 500000}},
        {"name": "npt_cool", "params": {"N_STEPS": 1000000}},
        {"name": "npt_cool300", "params": {"N_STEPS": 1000000}},
    ]
    args = ec.base_args("X", "PEST", "<none>")
    args._frozen_protocol = {"foundation": {"equil_stages": frozen_stages}}
    resolver_values = {"npt_prod_steps": None, "nvt_prod_steps": None, "npt_cool_steps": None,
                       "npt_cool300_steps": None, "npt_prod300_steps": None, "melt_npt_steps": None,
                       "npt_anneal_cycles": None, "npt_anneal_cycle_steps": None}

    executor = rdr._pinned_steps(args, resolver_values)
    chain = ec._pin_steps_from_frozen(frozen_stages)

    assert executor["npt_prod_steps"] == chain["npt_production"] == 500000
    assert executor["npt_cool_steps"] == chain["npt_cool"] == 1000000
    assert executor["npt_cool300_steps"] == chain["npt_cool300"] == 1000000


def _plan_and_args():
    """Build a frozen deterministic plan in memory — no dependency on a leftover run dir, and no
    writes to guides/ or data/."""
    frozen = {"foundation": {
        "source_run_name": "SRC", "frozen_at": "2026-01-01T00:00:00+00:00",
        "verified_by_deck_replay": True,
        "decided_params": {"cutoff_A": 9.5},
        "equil_stages": [
            {"name": "npt_production", "params": {"N_STEPS": 500000}},
            {"name": "npt_cool", "params": {"N_STEPS": 1000000}},
            {"name": "npt_cool300", "params": {"N_STEPS": 1000000}},
        ],
        "route": {"is_glassy": True},
    }}
    plan = mdp.make_plan("CHAINCHK", "PEST", "*OC(=O)C(*)C", {"density", "tg"},
                         frozen_protocol=frozen)
    rules = load_rules()
    args = ec.base_args("CHAINCHK", "PEST", "<in-memory>")
    cls = apply_plan(get_class_entry(rules, "PEST"), plan, args)
    resolve_hardware(args, cls, rules)
    args._frozen_protocol = frozen
    return plan, args, cls


def test_chain_matches_what_the_executor_will_run():
    """The plan advertises an execution_chain and the executor then runs its own control flow.
    If they can disagree, the chain is decorative — the exact defect this feature exists to
    eliminate."""
    plan, args, cls = _plan_and_args()
    result = rdr._assert_chain_matches_execution(args, cls, plan)
    assert result["checked"] is True
    assert result["stages"] > 0


def test_stale_chain_halts_instead_of_running():
    plan, args, cls = _plan_and_args()
    stale = json.loads(json.dumps(plan))
    for step in stale["execution_chain"]:
        if step["tool"] == "generate_equilibration_workflow":
            step["args"]["npt_prod_steps"] = 999999
    with pytest.raises(SystemExit, match="step counts"):
        rdr._assert_chain_matches_execution(args, cls, stale)


def test_reordered_chain_halts():
    plan, args, cls = _plan_and_args()
    stale = json.loads(json.dumps(plan))
    stale["execution_chain"] = stale["execution_chain"][:-1]
    with pytest.raises(SystemExit, match="does not match"):
        rdr._assert_chain_matches_execution(args, cls, stale)


def test_pinned_steps_falls_back_without_a_freeze():
    args = ec.base_args("X", "PEST", "<none>")
    args._frozen_protocol = {}
    out = rdr._pinned_steps(args, {"npt_prod_steps": 7, "nvt_prod_steps": 11, "npt_cool_steps": 8,
                                   "npt_cool300_steps": 9, "npt_prod300_steps": 12,
                                   "melt_npt_steps": 10, "npt_anneal_cycles": 0,
                                   "npt_anneal_cycle_steps": None})
    assert out == {"npt_prod_steps": 7, "nvt_prod_steps": 11, "npt_cool_steps": 8,
                   "npt_cool300_steps": 9, "npt_prod300_steps": 12, "melt_npt_steps": 10,
                   "npt_anneal_cycles": 0, "npt_anneal_cycle_steps": None}


# ── Execution chain ──────────────────────────────────────────────────────────

def _chain(properties, frozen=None, run="PLA1", cls_name="PEST"):
    run_dir = _needs(run)
    plan = json.loads((run_dir / "raw" / "run_plan.json").read_text())
    rules = load_rules()
    args = ec.base_args("CHAINTEST", cls_name, str(run_dir / "raw" / "run_plan.json"))
    cls = apply_plan(get_class_entry(rules, cls_name), plan, args)
    resolve_hardware(args, cls, rules)
    return ec.build_execution_chain(args, cls, plan, properties, frozen)


def test_chain_covers_every_stage_in_order():
    chain = _chain({"density", "tg", "bulk_modulus"})
    stages = [s["stage"] for s in chain]
    assert stages[0] == "build"
    assert stages[-1] == "run-summary"
    for expected in ("equil", "equil-check", "tg", "analyze-tg", "murnaghan", "analyze-bm"):
        assert expected in stages


def test_chain_marks_seeds_and_hardware_as_not_frozen():
    chain = _chain({"density", "tg"})
    values = {v for s in chain for v in s["args"].values() if isinstance(v, str)}
    assert ec.VARY_EMC_SEED in values
    assert ec.VARY_VELOCITY_SEED in values
    assert ec.HOST_ENGINE in values


def test_frozen_protocol_pins_step_counts():
    """Unpinned, generate_equilibration_workflow resolves step counts from an atom-count tier
    (boundaries at 5,000/15,000 atoms) — so a replicate whose fresh packing crosses a boundary
    would silently run a different equilibration. PLA1 sits at 4,520 atoms."""
    frozen = {"foundation": {"equil_stages": [
        {"name": "npt_production", "params": {"N_STEPS": 500000}},
        {"name": "npt_cool", "params": {"N_STEPS": 1000000}},
        {"name": "npt_cool300", "params": {"N_STEPS": 1000000}},
    ]}}
    args = [s for s in _chain({"density"}, frozen)
            if s["tool"] == "generate_equilibration_workflow"][0]["args"]
    assert args["npt_prod_steps"] == 500000
    assert args["npt_cool_steps"] == 1000000
    assert args["npt_cool300_steps"] == 1000000

    unpinned = [s for s in _chain({"density"})
                if s["tool"] == "generate_equilibration_workflow"][0]["args"]
    assert unpinned["npt_prod_steps"] is None, "without a freeze the tier default applies"


def test_frozen_route_forces_deform():
    """A K from deform and a K from Murnaghan are different measurements, so the replicate
    reproduces the branch rather than re-deciding it."""
    frozen = {"mechanical": {"route": {"bm_method": "deform"}}}
    chain = _chain({"bulk_modulus"}, frozen)
    tools = [s["tool"] for s in chain]
    assert "run_bulk_modulus_series" not in tools
    assert "extract_bulk_modulus_deform" in tools

    default = [s["tool"] for s in _chain({"bulk_modulus"})]
    assert "run_bulk_modulus_series" in default


# ── Guards ───────────────────────────────────────────────────────────────────

def test_cis_lock_guard_blocks_plain_rebuild():
    """EMC does not honour SMILES double-bond stereo, so a plain rebuild of this SMILES yields a
    ~48:52 cis/trans mixture its cached numbers do not describe."""
    cache = REPO_ROOT / "guides" / "system_characterization_cache.json"
    entry = json.loads(cache.read_text()).get("*C/C=C\\C*") or {}
    if not entry.get("requires_cis_lock"):
        pytest.skip("cis-lock entry not present")
    assert rdr._cis_lock_guard({"smiles": "*C/C=C\\C*"})
    assert not rdr._cis_lock_guard({"smiles": "*OC(C)C(=O)*"})


def test_protocol_is_owned_by_the_lock_writer():
    """The characterization write must never clobber a frozen protocol."""
    import write_characterization_cache as wcc
    assert "protocol" in wcc.VALIDATED_KEYS
