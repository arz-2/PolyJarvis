"""The guarantees that let one run's numbers be compared with another's.

PROPERTY INDEPENDENCE. `track_registry`'s `density` entry claims the 300 K density is
"comparable across every run because no property-conditional path reaches it", and cites a
`test_property_independence` that did not exist -- the guarantee was asserted in a docstring
and enforced nowhere. It is a real constraint: every run must hold its melt at the same
property-independent `T_melt_hold_K` regardless of what was requested, or two runs' densities
are measuring two different thermal histories.

ASSESSMENT TEMPERATURE. The second half is that `final_T_K` must actually BE the temperature
the run is assessed at, everywhere. Neither `final_T_K` nor `bm_temperature_K` is declared by
any polymer class, so both used to fall through to a bare 300.0 buried in `stage_params` --
the plan carried no record of its own assessment temperature, and overriding `final_T_K` moved
the cooling endpoint while the modulus, the regime call and the experimental lookup all stayed
at 300.
"""

import itertools
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import stage_params as sp  # noqa: E402
import track_registry  # noqa: E402
from make_deterministic_plan import SNAPSHOT_KEYS, make_plan  # noqa: E402
from rules_common import load_rules, get_class_entry  # noqa: E402
from scientific_control import (  # noqa: E402
    _bind_bm_temperature,
    _validate_protocol_relationships,
)

CLASS = "PACR"
SMILES = "*CC(*)(C)C(=O)OC"  # PMMA, exp Tg ~378 K -- glassy at 300, rubbery at 400


class _Args:
    """Every unset attribute is None, exactly like the campaign's argparse defaults."""

    def __getattr__(self, name):
        return None

    run_name = "PROPINDEP"
    smiles = SMILES
    polymer_class = CLASS


@pytest.fixture(scope="module")
def cls_entry():
    return get_class_entry(load_rules(), CLASS)


def _subsets():
    """Every non-empty subset of the requestable vocabulary, minus the contradictory ones.

    shear/Young's/Poisson pin mechanical_method="deformation"; that is a routing choice, not a
    thermal one, so it must not move the melt either -- they stay in.
    """
    props = sorted(track_registry.VALID_PROPERTIES)
    for size in range(1, len(props) + 1):
        for combo in itertools.combinations(props, size):
            yield frozenset(combo)


# ─── property independence ────────────────────────────────────────────────────────

def test_melt_hold_is_identical_for_every_requestable_property_subset(cls_entry):
    """No property-conditional path may reach the melt hold."""
    schedules = {}
    for props in _subsets():
        args = _Args()
        args.properties = ",".join(sorted(props))
        sched = sp.temperature_schedule(args, cls_entry)
        schedules[props] = (sched["T_melt_hold_K"], sched["T_anneal_high_K"])

    distinct = set(schedules.values())
    assert len(distinct) == 1, (
        f"T_melt_hold_K/T_anneal_high_K vary with the requested properties: {distinct}. "
        f"The melt hold is where every track starts; a property-conditional melt makes two "
        f"runs' densities incomparable."
    )


def test_requested_properties_never_pin_a_temperature(cls_entry):
    """forced_params_for is the ONLY channel by which a property pins a parameter."""
    for props in _subsets():
        pinned = track_registry.forced_params_for(props)
        thermal = {k for k in pinned if k.endswith("_K") or "temp" in k.lower()}
        assert not thermal, f"{sorted(props)} pins temperature keys {thermal}"


# ─── the assessment temperature is real ───────────────────────────────────────────

def test_plan_records_the_temperature_it_will_be_assessed_at():
    """No class declares final_T_K, so SNAPSHOT_KEYS alone copies nothing -- both keys must be
    derived explicitly or the plan has no record of its own assessment temperature."""
    plan = make_plan("PROPINDEP", CLASS, SMILES, {"bulk_modulus"})
    dp = plan["decided_params"]
    assert dp["final_T_K"] == 300.0
    assert dp["bm_temperature_K"] == dp["final_T_K"]


def test_bm_temperature_K_is_snapshotted_so_a_curated_class_value_is_honoured():
    assert "bm_temperature_K" in SNAPSHOT_KEYS


@pytest.mark.parametrize("final_t,expect_glassy", [(300.0, True), (400.0, False)])
def test_modulus_is_measured_at_the_assessment_temperature(cls_entry, final_t, expect_glassy):
    """The mechanical track measures on the cooling track's npt_final cell. Its temperature and
    its regime must both follow final_T_K, or the modulus re-thermostats a gated cell to a
    temperature nothing gated it at and labels it with the wrong phase."""
    effective = {**cls_entry, "final_T_K": final_t, "bm_temperature_K": final_t}
    args = _Args()

    murnaghan = sp.resolve_stage_params("murnaghan", args, effective)
    assert murnaghan["temp_K"] == final_t
    assert murnaghan["is_glassy"] is expect_glassy
    assert sp.assessment_temperature(args, effective) == final_t
    assert sp.assessment_regime(args, effective) == ("glassy" if expect_glassy else "rubbery")


def test_modulus_temperature_defaults_to_final_T_K_not_a_bare_300(cls_entry):
    """bm_temperature_K has no class default anywhere. Its fallback must be the assessment
    temperature, not a literal."""
    effective = {**cls_entry, "final_T_K": 425.0}
    assert "bm_temperature_K" not in effective
    assert sp.resolve_stage_params("murnaghan", _Args(), effective)["temp_K"] == 425.0


# ─── one assessment temperature per run ───────────────────────────────────────────

def test_a_modulus_temperature_the_cooldown_never_reaches_is_rejected():
    params = {"final_T_K": 300.0, "bm_temperature_K": 250.0}
    with pytest.raises(ValueError, match="must equal final_T_K"):
        _validate_protocol_relationships(params, {"bm_temperature_K"})


def test_moving_final_T_K_alone_carries_the_modulus_with_it():
    """The "assess at 400 K" request overrides final_T_K and nothing else; bm_temperature_K
    must follow rather than strand the plan in a state the validator rejects."""
    params = {"final_T_K": 400.0, "bm_temperature_K": 300.0}
    _bind_bm_temperature(params, {"final_T_K"})
    assert params["bm_temperature_K"] == 400.0
    _validate_protocol_relationships(params, {"final_T_K"})  # must not raise


def test_an_explicit_modulus_temperature_is_not_silently_overwritten():
    """Deliberately moving both is the caller's business; the follow rule must not clobber it,
    and the equality check still adjudicates."""
    params = {"final_T_K": 400.0, "bm_temperature_K": 400.0}
    _bind_bm_temperature(params, {"final_T_K", "bm_temperature_K"})
    assert params["bm_temperature_K"] == 400.0
    _validate_protocol_relationships(params, {"final_T_K", "bm_temperature_K"})


# ─── the registry must describe the artifacts that actually exist ─────────────────

def test_declared_summary_paths_are_real(tmp_path):
    """Every summary_path an observable declares must name a key generate_run_summary writes.

    summary_path has no consumer today, which is exactly why it drifted: three deformation
    observables declared ("results", "<name>", "value") and generate_run_summary has never
    written any of those keys. Dead metadata that lies is worse than none -- if a consumer is
    ever added it inherits the lie. This test is that consumer.
    """
    import json
    import subprocess

    script = (REPO_ROOT / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"
              / "generate_run_summary.py")
    (tmp_path / "cooling.json").write_text(json.dumps(
        {"density": {"plateau_density_mean": 1.18, "target_temp_K": 300.0},
         "gate": {"verdict": "PASS"}}))
    (tmp_path / "equilibration.json").write_text(json.dumps(
        {"density": {"plateau_density_mean": 1.04, "target_temp_K": 578.0},
         "gate": {"verdict": "PASS"}}))
    (tmp_path / "thermal.json").write_text(json.dumps({"Tg_K": 378.0, "r_squared": 0.99}))
    (tmp_path / "mechanical.json").write_text(json.dumps(
        {"status": "success", "method": "murnaghan", "B0_GPa": 3.4, "temperature_K": 300.0}))

    subprocess.run(
        [sys.executable, str(script), "--output_dir", str(tmp_path), "--run_name", "SPCHK",
         "--equilibration_path", str(tmp_path / "cooling.json"),
         "--melt_equilibration_path", str(tmp_path / "equilibration.json"),
         "--tg_path", str(tmp_path / "thermal.json"),
         "--mechanical_path", str(tmp_path / "mechanical.json")],
        check=True, capture_output=True)
    summary = json.loads((tmp_path / "run_summary.json").read_text())

    for obs in track_registry.OBSERVABLES.values():
        if not obs.summary_path:
            continue
        node = summary
        for key in obs.summary_path:
            assert isinstance(node, dict) and key in node, (
                f"{obs.name}.summary_path={obs.summary_path} does not resolve in "
                f"run_summary.json (stopped at {key!r})"
            )
            node = node[key]
        assert node is not None, f"{obs.name}.summary_path resolved to null"


def test_the_bulk_modulus_extractor_json_is_the_file_the_extractor_writes():
    """extract_bulk_modulus_murnaghan writes mechanical.json, and generate_run_summary loads
    mechanical.json. The registry named bulk_modulus_murnaghan.json, which nothing writes."""
    murnaghan = (REPO_ROOT / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"
                 / "extract_bulk_modulus_murnaghan.py").read_text()
    declared = track_registry.observable("bulk_modulus").extractor_json
    assert f'"{declared}"' in murnaghan, (
        f"registry declares {declared!r} but the extractor never writes that filename")


def test_a_declared_observable_never_routes_a_track():
    """`declared` means routable in principle, resolver stages absent in fact. Planning one
    would emit a stage sequence no executor can run."""
    for obs in track_registry.OBSERVABLES.values():
        if obs.status != "declared" or not obs.legacy_property:
            continue
        assert obs.legacy_property not in track_registry.VALID_PROPERTIES or any(
            other.legacy_property == obs.legacy_property and other.status == "wired"
            for other in track_registry.OBSERVABLES.values()
        ), f"{obs.name} is declared but its legacy_property is requestable on its own"


# ─── the newly wired tracks ───────────────────────────────────────────────────────

def test_a_structural_request_costs_no_extra_md(cls_entry):
    """RDF and chain dimensions read the melt cell's data file and dump, both of which the
    foundation track writes anyway. Requesting either must add ONE analysis stage and no
    simulation -- in particular it must not pull in the cooldown."""
    for prop in ("chain_dimensions", "radial_distribution"):
        stages = track_registry.planned_stage_names({prop})
        assert stages == ["build", "equil", "equil-check", "analyze-structure",
                          "run-summary"], prop
        assert "cool" not in stages and "cool-check" not in stages, prop


def test_solubility_requires_the_cell_it_is_reported_at(cls_entry):
    """delta is quoted at the assessment temperature, and the CED subtraction reads the bulk
    npt_final log. So cohesive requires cooling for exactly the reason mechanical does."""
    stages = track_registry.planned_stage_names({"solubility_parameter"})
    assert stages == ["build", "equil", "equil-check", "cool", "cool-check",
                      "vacuum-build", "vacuum-chain", "analyze-solubility", "run-summary"]
    assert "cooling" in track_registry.tracks_for({"solubility_parameter"})


def test_the_vacuum_reference_matches_the_bulk_chains_in_everything_but_count(cls_entry):
    """E_inter = E_bulk - n_chains * E_intra only means anything if the reference chain IS one
    of the bulk chains: same SMILES, same field, same DP, same charge model. Only the chain
    COUNT and the density may differ."""
    effective = {**cls_entry, "preferred_ff": "pcff", "charge_method": "none",
                 "dp_typical": 40, "nchain": 20}
    args = _Args()
    bulk = sp.resolve_stage_params("build", args, effective)
    vac = sp.resolve_stage_params("vacuum-build", args, effective)

    for shared in ("smiles", "preferred_ff", "dp", "charge_method", "electrostatics",
                   "cutoff_A", "build_temperature_K"):
        assert vac[shared] == bulk[shared], shared
    assert vac["nchain"] == 1 and bulk["nchain"] == 20
    assert vac["density_initial_gcm3"] < bulk["density_initial_gcm3"]

    # ... and the subtraction must use the BULK count, not the reference's 1.
    assert sp.resolve_stage_params("analyze-solubility", args, effective)["n_chains"] == 20


def test_the_vacuum_chain_is_held_at_the_assessment_temperature(cls_entry):
    """The bulk log is npt_final's. A reference taken at another temperature subtracts the
    wrong intramolecular energy."""
    for final_t in (300.0, 400.0):
        effective = {**cls_entry, "preferred_ff": "pcff", "charge_method": "none",
                     "final_T_K": final_t, "bm_temperature_K": final_t}
        assert sp.resolve_stage_params(
            "vacuum-chain", _Args(), effective)["temp_K"] == final_t


def test_the_new_stages_never_hash_as_build():
    """An unmapped decided_params key falls to "build" and would invalidate the whole pipeline
    back to the cell every time it moved. This is the lockstep rule stated for the keys the
    two new tracks introduced."""
    import workflow_engine as we
    for key in ("rdf_rmax_A", "rdf_nbins", "rdf_atom_type_pairs",
                "structure_skip_frames", "structure_max_frames"):
        assert we.PARAMETER_STAGE[key] == "structure", key
    for key in ("vacuum_density_gcm3", "vacuum_nvt_steps", "vacuum_box_margin_A",
                "vacuum_thermo_freq", "solubility_eq_fraction"):
        assert we.PARAMETER_STAGE[key] == "cohesive", key


def test_macro_stages_stay_a_stage_order_subsequence():
    """_dependencies and invalidate_from both require it, and adding two tracks is exactly when
    it breaks."""
    import workflow_engine as we
    props = sorted(track_registry.VALID_PROPERTIES)
    for size in (1, 2, len(props)):
        for combo in itertools.combinations(props, size):
            macros = track_registry.macro_stages_for(frozenset(combo))
            positions = [we.STAGE_ORDER.index(m) for m in macros]
            assert positions == sorted(positions), combo


# ─── the melt/production reference temperature ────────────────────────────────────

def test_workflow_reference_follows_the_assessment_temperature(cls_entry):
    """T_workflow_K is the melt/production REFERENCE, and its regime call must be made at the
    temperature the run is assessed at.

    PACR/PMMA has exp Tg 378 K. Assessed at 300 K it is glassy, so the reference is the melt
    temperature. Assessed at 400 K it is rubbery -- the run is produced and reported AT 400 --
    so the reference is 400. Written as `300.0 if exp_tg < 300` (in four places), the second
    case came out glassy and pointed the reference at the melt.
    """
    args = _Args()
    glassy = sp._resolve_t_workflow(args, {**cls_entry, "final_T_K": 300.0})
    rubbery = sp._resolve_t_workflow(args, {**cls_entry, "final_T_K": 400.0})

    assert rubbery == 400.0
    assert glassy == sp._pick(None, cls_entry, "T_equil_K", 600.0)
    assert glassy > 400.0, "the glassy reference must be the melt, above the assessment T"


def test_the_reference_rule_is_one_function_shared_by_plan_and_deck():
    """make_deterministic_plan resolves this at plan time and stage_params at execution time.
    They must not be two implementations -- a plan recording one reference while the deck runs
    another is the artifact-disagrees-with-the-run bug class."""
    import make_deterministic_plan as mdp
    assert mdp.workflow_reference_temperature is sp.workflow_reference_temperature

    # glassy -> the melt; rubbery -> the assessment temperature; unresolvable Tg -> the melt.
    assert sp.workflow_reference_temperature(378, 600.0, 300.0) == 600.0
    assert sp.workflow_reference_temperature(378, 600.0, 400.0) == 400.0
    assert sp.workflow_reference_temperature(None, 600.0, 300.0) == 600.0


def test_the_plan_records_the_reference_the_deck_will_run(cls_entry):
    """The invariant that matters: what the plan artifact records is what the resolver returns
    when the deck is built from that same plan."""
    from make_deterministic_plan import make_plan
    dp = make_plan("TWPLAN", CLASS, SMILES, {"density"})["decided_params"]

    # PMMA at the default 300 K assessment is glassy, so the reference is the melt.
    assert dp["final_T_K"] == 300.0
    assert dp["T_workflow_K"] == dp["T_equil_K"]

    # _resolve_t_workflow short-circuits on a pinned T_workflow_K, so strip it: the question is
    # whether the RULE reproduces the recorded value, not whether the lookup echoes it back.
    unpinned = {k: v for k, v in dp.items() if k != "T_workflow_K"}
    assert sp._resolve_t_workflow(_Args(), unpinned) == dp["T_workflow_K"]


def test_the_tg_free_fallback_reads_the_regime_back_out_of_the_reference(cls_entry):
    """resolve_regime_legacy is the only path left when no Tg resolves at all. It infers the
    regime from where T_workflow sits relative to the assessment temperature, so it has to move
    with final_T_K too -- its old form compared against a literal 300."""
    import enforce_gate as eg
    args = _Args()
    for final_t, expected in ((300.0, "glassy"), (400.0, "rubbery")):
        effective = {**cls_entry, "final_T_K": final_t}
        t_workflow = sp._resolve_t_workflow(args, effective)
        assert eg.resolve_regime_legacy(t_workflow, final_t) == expected, final_t
        # and it agrees with the Tg-based oracle it stands in for
        assert eg.resolve_regime_legacy(t_workflow, final_t) == sp.assessment_regime(
            args, effective)
