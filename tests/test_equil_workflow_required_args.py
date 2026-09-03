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

# The CORE chain's required args. The descent's knobs (cool_block_*, stage7_*, stage8_*) moved
# to generate_cooling_workflow with the stages they size -- COOLING_REQUIRED below.
REQUIRED = [
    "velocity_seed",
    "densify_ramp_steps",
    "densify_check_every_steps",
    "densify_steps_cap",
    "ff_activate_npt_steps",
    "anneal_heat_steps",
    "anneal_check_every_steps",
    "anneal_cap_steps",
    "melt_ramp_steps",
    "melt_hold_min_steps",
    "melt_hold_cap_steps",
    "nvt_melt_min_steps",
    "nvt_melt_cap_steps",
    "warmup_steps",
    "use_long_range",
]
REQUIRED_INTEGER = {"velocity_seed"}
REQUIRED_BOOLEAN = {"use_long_range"}
REQUIRED_FLOAT = set()

COOLING_REQUIRED = [
    "velocity_seed",
    "cool_block_dT_K",
    "cool_block_hold_steps",
    "cool_block_hold_cap_steps",
    "stage8_min_steps",
    "stage8_cap_steps",
    "use_long_range",
]


def _workflow_signature(name="generate_equilibration_workflow"):
    """The tool's parameters as {name: has_default}. Parsed rather than imported --
    server.py needs the `mcp` package, which the test interpreter does not have."""
    tree = ast.parse(SERVER_PY.read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef)
              and n.name == name)
    args = fn.args.args + fn.args.kwonlyargs
    defaults = ([None] * (len(fn.args.args) - len(fn.args.defaults)) + list(fn.args.defaults)
                + list(fn.args.kw_defaults))
    return {a.arg: d is not None for a, d in zip(args, defaults)}, fn


def test_every_step_count_and_the_seed_are_required():
    sig, _ = _workflow_signature()
    for name in REQUIRED:
        assert name in sig, f"{name} vanished from generate_equilibration_workflow"
        assert not sig[name], f"{name} has a default -- omitting it silently changes the deck"


def test_the_cooling_tool_requires_its_own_step_counts():
    """The same hazard, moved with the stages: a silently-defaulted cool_block_hold_steps is
    how two runs of the same system would cool at different rates."""
    sig, _ = _workflow_signature("generate_cooling_workflow")
    for name in COOLING_REQUIRED:
        assert name in sig, f"{name} vanished from generate_cooling_workflow"
        assert not sig[name], f"{name} has a default -- omitting it silently changes the deck"
    assert not sig["T_melt_hold_K"] and not sig["final_T_K"], (
        "the descent's endpoints must be passed explicitly, not defaulted")


def test_the_core_chain_no_longer_accepts_the_descents_knobs():
    """Pin the split itself: passing a cool_block knob to the core chain must be a TypeError,
    not a silently-ignored argument."""
    sig, _ = _workflow_signature()
    for name in ("cool_block_dT_K", "cool_block_hold_steps", "stage7_min_steps",
                 "stage8_min_steps", "final_T_K", "t_equil_K", "tg_start_T_K"):
        assert name not in sig, f"{name} is still accepted by the core chain"


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
                 "extend_only", "anneal_margin_K"):
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
    for name in REQUIRED_INTEGER:
        assert schema["properties"][name]["type"] == "integer"
    for name in REQUIRED_BOOLEAN:
        assert schema["properties"][name]["type"] == "boolean"
    for name in set(REQUIRED) - REQUIRED_INTEGER - REQUIRED_BOOLEAN - REQUIRED_FLOAT:
        types = {b["type"] for b in schema["properties"][name]["anyOf"]}
        assert types == {"integer", "null"}, name

    cooling = next(t for t in tools if t.name == "generate_cooling_workflow").inputSchema
    assert set(COOLING_REQUIRED) <= set(cooling["required"])
    assert {"T_melt_hold_K", "final_T_K"} <= set(cooling["required"])


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


def _kwargs_reaching(fn_name: str, tool_name: str) -> set:
    """Every argument name a submitter can put on a tool call: explicit keywords plus the keys
    of the shared `common` dict it splats. The three call sites (fresh / resume_from /
    extend_only) share that dict, which is exactly why the args cannot be read off one call."""
    tree = ast.parse((REPO_ROOT / "orchestration" / "scripts" / "run_campaign.py").read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == fn_name)
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == tool_name]
    assert calls, f"{fn_name} makes no {tool_name} call"
    names = {kw.arg for call in calls for kw in call.keywords if kw.arg}
    names |= {k.value for d in ast.walk(fn) if isinstance(d, ast.Dict)
              for k in d.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    names |= {kw.arg for c in ast.walk(fn) if isinstance(c, ast.Call)
              for kw in c.keywords if kw.arg}
    return names


def test_deterministic_executor_passes_every_required_arg():
    """Each submitter must name every required arg of its own tool, including the ones it
    passes as None."""
    equil = _kwargs_reaching("_submit_equil_chain", "generate_equilibration_workflow")
    assert set(REQUIRED) <= equil, f"missing {set(REQUIRED) - equil}"
    cool = _kwargs_reaching("_submit_cool_chain", "generate_cooling_workflow")
    assert set(COOLING_REQUIRED) <= cool, f"missing {set(COOLING_REQUIRED) - cool}"


def test_stage_seed_is_stable_across_resolutions_and_distinct_per_run():
    import stage_params

    class A:
        pass

    def seed(run_name, pinned=None):
        a = A()
        a.run_name, a.velocity_seed = run_name, pinned
        return stage_params._velocity_seed(a)

    assert seed("PEG1") == seed("PEG1")
    assert seed("PEG1") != seed("PEG2")
    assert 10000 <= seed("PEG1") <= 999_999
    assert seed("PEG1", pinned=4242) == 4242


# ── every kwarg the orchestrator passes must actually exist on the tool ────────

def _server_tool_params() -> dict:
    """{tool name: set of accepted parameter names} for every top-level def in server.py."""
    tree = ast.parse(SERVER_PY.read_text())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            a = node.args
            out[node.name] = {p.arg for p in a.posonlyargs + a.args + a.kwonlyargs}
            if a.kwarg:
                out[node.name] = None  # accepts **kwargs -- cannot be checked
    return out


def test_no_orchestrator_call_passes_an_argument_the_tool_does_not_accept():
    """The gap every in-process fake leaves open.

    tests/test_run_campaign.py's fakes take **kwargs, so a call passing a parameter the real
    MCP tool has never heard of type-checks green all the way through the suite and fails only
    on the first real run. That is exactly what happened when the equilibration/cooling split
    introduced `output_name=` (so the melt gate writes equilibration.json and the assessment
    gate writes cooling.json) without adding it to check_equilibration_comprehensive,
    extract_equilibrated_density or enforce_equilibration_gate.

    Only calls with purely explicit keywords are checked -- a `**common` splat is opaque here
    and is covered by test_deterministic_executor_passes_every_required_arg instead.
    """
    tools = _server_tool_params()
    tree = ast.parse((REPO_ROOT / "orchestration" / "scripts" / "run_campaign.py").read_text())
    problems = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        name = node.func.attr
        accepted = tools.get(name)
        if accepted is None or name not in tools:
            continue                      # not a server tool, or it takes **kwargs
        if any(kw.arg is None for kw in node.keywords):
            continue                      # has a ** splat -- opaque
        for kw in node.keywords:
            if kw.arg not in accepted:
                problems.append(f"{name}(...) passed {kw.arg!r}, which it does not accept")
    assert not problems, "\n".join(sorted(set(problems)))
