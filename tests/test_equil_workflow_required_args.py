"""Step counts and the velocity seed are required arguments, not defaults.

PEGCMP1 and PEGORE1 were generated from identical prompts carrying
`npt_prod_steps: 2000000`, and emitted `run 2000000` and `run 1000000` respectively:
one worker forwarded the argument, the other omitted it and took
`steps_npt // 2` from the atom-count tier. Every silently-defaulting step count is the
same hazard, and a null `velocity_seed` is worse -- `script_generator` then draws a
fresh `velocity all create` seed per stage, so the chain cannot be reproduced at all.

Omission is now a schema error. An explicit null is still accepted for the step counts
(it selects the documented tier default, a pure function of the .data file) because
that is a caller decision recorded on the call; only omission is ambiguous.
"""
import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

SERVER_PY = REPO_ROOT / "mcp-servers" / "mcp-lammps-engine" / "server.py"

REQUIRED = [
    "velocity_seed",
    "npt_prod_steps",
    "npt_cool_steps",
    "npt_cool300_steps",
    "melt_npt_steps",
    "extend_steps",
]


def _workflow_signature():
    """The tool's parameters as {name: has_default}. Parsed rather than imported --
    server.py needs the `mcp` package, which the test interpreter does not have."""
    tree = ast.parse(SERVER_PY.read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef)
              and n.name == "generate_equilibration_workflow")
    args = fn.args.args + fn.args.kwonlyargs
    defaults = ([None] * (len(fn.args.args) - len(fn.args.defaults)) + list(fn.args.defaults)
                + list(fn.args.kw_defaults))
    return {a.arg: d is not None for a, d in zip(args, defaults)}, fn


def test_every_step_count_and_the_seed_are_required():
    sig, _ = _workflow_signature()
    for name in REQUIRED:
        assert name in sig, f"{name} vanished from generate_equilibration_workflow"
        assert not sig[name], f"{name} has a default -- omitting it silently changes the deck"


def test_data_file_and_work_dir_stay_required():
    sig, _ = _workflow_signature()
    assert not sig["data_file"] and not sig["work_dir_base"]


def test_the_optional_knobs_keep_their_defaults():
    """Originally this also guarded `temp`, `use_pcff`, and `engine`, on the grounds that
    requiring them "would break every existing call site". A full trace of prompt ->
    tool-call threading found those call sites already pass all three, and that their
    defaults are the dangerous kind: `temp=300.0` builds a melt that never melts, and
    all three FF flags defaulting False emits GAFF2 styles against a class2 cell. They
    moved to required; see tests/test_tool_arg_threading.py, which owns that set now.
    What stays optional here is what stays harmless."""
    sig, _ = _workflow_signature()
    for name in ("polymer_name", "max_temp", "press", "max_press", "n_chains",
                 "add_melt_npt", "extend_only", "add_300k_production"):
        assert sig[name], f"{name} lost its default"


def test_null_seed_is_rejected_in_the_body():
    """A null seed passes the type check on a direct Python call, so the body has to
    refuse it -- that is the path that reaches script_generator's random.randint."""
    _, fn = _workflow_signature()
    src = ast.unparse(fn)
    assert "velocity_seed is None" in src
    assert "velocity_seed is required" in src


def test_mcp_schema_marks_them_required():
    """The AST check proves the Python signature; workers go through the JSON schema, and
    whether pydantic puts a no-default Optional in `required` is version-dependent. Skips
    unless run under the server's own interpreter (`mcp-servers/.venv/bin/python`)."""
    import asyncio

    pytest.importorskip("mcp")
    sys.path.insert(0, str(SERVER_PY.parent))
    import server

    tools = asyncio.run(server.mcp.list_tools())
    schema = next(t for t in tools if t.name == "generate_equilibration_workflow").inputSchema
    assert set(REQUIRED) <= set(schema["required"])
    # A null seed must fail at the schema, not just in the body.
    assert schema["properties"]["velocity_seed"]["type"] == "integer"
    for name in REQUIRED[1:]:
        types = {b["type"] for b in schema["properties"][name]["anyOf"]}
        assert types == {"integer", "null"}, name


def test_the_other_seed_drawing_tools_require_one_too():
    """`generate_script` (Tg staircase, deform, NEMD) and `run_bulk_modulus_series` drew their
    own seeds per call. The Tg prompt printed a `velocity_seed` the tool could not accept."""
    tree = ast.parse(SERVER_PY.read_text())
    for name in ("generate_script", "run_bulk_modulus_series"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == name)
        args = fn.args.args
        defaults = [None] * (len(args) - len(fn.args.defaults)) + list(fn.args.defaults)
        sig = {a.arg: d is not None for a, d in zip(args, defaults)}
        assert "velocity_seed" in sig, f"{name} still cannot be given a seed"
        assert not sig["velocity_seed"], f"{name}'s seed has a default"
        assert "velocity_seed is None" in ast.unparse(fn), f"{name} accepts a null seed"


def test_no_seed_is_drawn_at_random_once_one_is_given():
    """script_generator had three `random.randint` sites: the staircase reseed, the generic
    init_velocity, and the two NEMD Langevin thermostats. Each must consult the pinned seed
    first -- an unguarded draw is unreachable from the tools but still reproducible-looking."""
    src = (SERVER_PY.parent / "script_generator.py").read_text()
    for line in src.splitlines():
        if "random.randint" in line and not line.lstrip().startswith("#"):
            assert "_velocity_seed" in line or "else random.randint" in line, line


def test_prompts_for_every_seeded_stage_carry_one():
    import gen_prompt

    class A:
        pass

    args = A()
    for k, v in dict(
        run_name="PEGX1", polymer_class="POXI", data_path="/x/cell.data", work_dir=None,
        dt_fs=1.0, gpu_ids="0", mpi_ranks=1, engine="kokkos", lammps_flags=None,
        velocity_seed=None, is_glassy="false", deform_rate_mode="primary",
        K_deform_rate_inv_s=None, K_strain_max=None, tg_rate_index=0,
        tg_t_high_K=None, tg_t_low_K=None, tg_t_step_K=None, tg_steps_per_t=None,
        tg_rate_K_per_ns=None, tg_start_data=None, nchain=10, dp=50, output_dir=None,
        T_equil_K=None, T_anneal_high_K=None, npt_prod_ns=None, T_workflow_K=None,
    ).items():
        setattr(args, k, v)
    cls = {"experimental_tg_K": 206.0, "dt_fs": 1.0, "T_equil_K": 500.0}
    for prompt in (gen_prompt.tg_prompt, gen_prompt.deform_prompt, gen_prompt.murnaghan_prompt):
        text = prompt(args, cls)
        assert "velocity_seed:" in text, prompt.__name__
        assert "velocity_seed:     null" not in text, prompt.__name__


def test_deterministic_executor_passes_every_required_arg():
    """EVERY call site in run_deterministic_replicate must name all six, including the ones it
    passes as None -- the full chain, the EXTEND continuation, and --emit-decks. Asserted per
    call rather than against a fixed call count, so adding a call site cannot make this test
    fail for a reason unrelated to what it checks."""
    src = (REPO_ROOT / "orchestration" / "scripts" / "run_deterministic_replicate.py").read_text()
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr == "generate_equilibration_workflow"]
    assert calls, "no generate_equilibration_workflow call sites found"
    for call in calls:
        passed = {kw.arg for kw in call.keywords}
        assert set(REQUIRED) <= passed, f"missing {set(REQUIRED) - passed}"


def test_prompt_always_names_the_seed_and_every_step_count():
    """The prompt's old `npt_prod_ns: null` branch printed 'auto-sized by atom count',
    which reads as permission to omit the argument. Both branches must now spell out a
    value to pass."""
    import gen_prompt

    class A:
        pass

    for npt_prod_ns in (2.0, None):
        args = A()
        for k, v in dict(
            run_name="PEGX1", polymer_class="POXI", data_path="/x/cell.data",
            work_dir=None, dt_fs=1.0, T_equil_K=500.0, T_anneal_high_K=700.0,
            npt_prod_ns=npt_prod_ns, gpu_ids="0", mpi_ranks=1, engine="kokkos",
            lammps_flags=None, nchain=10, dp=50, backbone_types=None,
            velocity_seed=None, T_workflow_K=None,
        ).items():
            setattr(args, k, v)
        cls = {"experimental_tg_K": 206.0, "dt_fs": 1.0, "T_equil_K": 500.0}
        text = gen_prompt.equil_prompt(args, cls)
        for name in REQUIRED:
            assert f"{name}:" in text, f"{name} absent from the prompt (npt_prod_ns={npt_prod_ns})"
        assert "auto-sized by atom count" not in text
        assert "velocity_seed:     null" not in text


def test_prompt_seed_is_stable_across_regenerations_and_distinct_per_run():
    import gen_prompt

    class A:
        pass

    def seed(run_name, pinned=None):
        a = A()
        a.run_name, a.velocity_seed = run_name, pinned
        return gen_prompt._velocity_seed(a)

    assert seed("PEG1") == seed("PEG1")
    assert seed("PEG1") != seed("PEG2")
    assert 10000 <= seed("PEG1") <= 999_999
    assert seed("PEG1", pinned=4242) == 4242
