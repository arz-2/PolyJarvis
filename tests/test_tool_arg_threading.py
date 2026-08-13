"""A protocol value a prompt emits must reach the tool call, on every path.

The failure it guards is silent in both directions. A worker (or the scripted executor)
omits an optional argument, the tool substitutes its own default, and the run records the
protocol it was told to use while executing a different one. Two confirmed instances:

  * `run_deterministic_replicate.py` resolved `cutoff_A` for equil-check and never passed
    it, disabling the minimum-image half (`L >= 2*cutoff_A`) of the finite-size gate.
  * The same call omitted `timestep_fs`. `dump_every` self-heals -- it is auto-detected
    from the dump header -- but `timestep_fs` does not, and `dt_ps = timestep_fs *
    dump_every / 1000`, so the two `dt_fs=2.0` classes reported `tau_relax_ps` and MSD at
    half their real values.

`generate_equilibration_workflow` fixed this once by making its step counts and seed
required-with-no-default, so omission became a schema error. `REQUIRED_ARGS` below extends
that to every argument whose default differs from the resolved value AND moves a reported
number or flips a binding gate. Arguments whose default is harmless -- `thermo_freq`,
`block_count`, `skip_frames`, `eq_fraction`, the `*_col` names -- deliberately stay
optional; widening to those would break call sites for no protocol gain.

A null is still legal for the nullable entries. Null is a caller decision recorded on the
call; omission is ambiguous. That distinction is the whole point.
"""
import ast
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

LAMMPS_SERVER = REPO_ROOT / "mcp-servers" / "mcp-lammps-engine" / "server.py"
EMC_SERVER = REPO_ROOT / "mcp-servers" / "mcp-emc-server" / "server.py"
EXECUTOR = REPO_ROOT / "orchestration" / "scripts" / "run_deterministic_replicate.py"

# tool -> (server file, required args, guide whose canonical call block must name them)
REQUIRED_ARGS = {
    "generate_equilibration_workflow": (LAMMPS_SERVER, [
        "velocity_seed", "npt_prod_steps", "npt_cool_steps", "npt_cool300_steps",
        "melt_npt_steps", "extend_steps", "temp", "use_pcff", "use_trappe", "use_opls",
        "engine",
    ], "EQUILIBRATION.md"),
    "run_lammps_chain": (LAMMPS_SERVER, ["engine"], "EQUILIBRATION.md"),
    "inspect_data_file": (LAMMPS_SERVER, [
        "lj_cutoff", "target_density_gcm3", "nchain",
    ], "EQUILIBRATION.md"),
    "check_equilibration_comprehensive": (LAMMPS_SERVER, [
        "timestep_fs", "ct_min_decay", "cutoff_A",
    ], "EQUIL_CHECK.md"),
    "extract_equilibrated_density": (LAMMPS_SERVER, ["target_temp"], "EQUIL_CHECK.md"),
    "enforce_equilibration_gate": (LAMMPS_SERVER, [
        "dp", "ct_gate_reliable", "exp_density_gcm3", "tg_K", "t_equil_K",
        "glass_data", "melt_data", "out_dir", "alpha_glass_per_K", "alpha_melt_per_K",
    ], None),  # call args live in gen_prompt's MECHANIZED GATE block, not a guide
    "extract_thermal": (LAMMPS_SERVER, [
        "tg_data_file", "per_t_dump_file", "method_gap_exempt",
    ], "THERMAL_ANALYSIS.md"),
    "run_bulk_modulus_series": (LAMMPS_SERVER, [
        "velocity_seed", "npt_steps", "dt_fs", "use_trappe", "use_pcff", "use_opls",
        "engine",
    ], "MURNAGHAN.md"),
    "extract_bulk_modulus_murnaghan": (LAMMPS_SERVER, ["npt_prod_log"], "BM_ANALYSIS.md"),
    "extract_bulk_modulus_deform": (LAMMPS_SERVER, [
        "strain_rate", "strain_max", "timestep", "log_file_2", "strain_rate_2",
    ], "BM_ANALYSIS.md"),
    "run_lammps_script": (LAMMPS_SERVER, ["engine"], ["DEFORM.md", "THERMAL_SWEEP.md"]),
    "submit_emc_cell_job": (EMC_SERVER, [
        "dp", "nchains", "density_initial", "seed",
    ], "MOLECULE_BUILDER.md"),
}

TOOLS = sorted(REQUIRED_ARGS)


def _signature(server_py: Path, fn_name: str):
    """{param: has_default}. Parsed rather than imported -- server.py needs the `mcp`
    package, which the plain test interpreter does not have."""
    tree = ast.parse(server_py.read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn_name)
    args = fn.args.args + fn.args.kwonlyargs
    defaults = ([None] * (len(fn.args.args) - len(fn.args.defaults)) + list(fn.args.defaults)
                + list(fn.args.kw_defaults))
    return {a.arg: d is not None for a, d in zip(args, defaults)}


@pytest.mark.parametrize("tool", TOOLS)
def test_signature_has_no_default(tool):
    server_py, required, _ = REQUIRED_ARGS[tool]
    sig = _signature(server_py, tool)
    for name in required:
        assert name in sig, f"{name} vanished from {tool}"
        assert not sig[name], (
            f"{tool}({name}=...) has a default -- omitting it silently changes the protocol")


def _load_server(server_py: Path):
    """Import a server module by path under a unique name. Both servers are called
    `server.py`, so a bare `import server` after a sys.path insert resolves to whichever
    landed first and leaves that wrong module cached in sys.modules for every later
    test in the session."""
    import importlib.util

    mod_name = f"_polyjarvis_{server_py.parent.name.replace('-', '_')}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    sys.path.insert(0, str(server_py.parent))
    try:
        spec = importlib.util.spec_from_file_location(mod_name, server_py)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(server_py.parent))


@pytest.mark.parametrize("tool", TOOLS)
def test_mcp_schema_marks_them_required(tool):
    """The AST check proves the Python signature; workers reach these through the JSON
    schema, and whether pydantic puts a no-default Optional in `required` is
    version-dependent. Skips unless run under a server interpreter that has `mcp`
    (`mcp-servers/.venv/bin/python -m pytest ...`)."""
    import asyncio

    pytest.importorskip("mcp")
    server_py, required, _ = REQUIRED_ARGS[tool]
    mod = _load_server(server_py)

    tools = asyncio.run(mod.mcp.list_tools())
    schema = next(t for t in tools if t.name == tool).inputSchema
    missing = set(required) - set(schema["required"])
    assert not missing, f"{tool} schema does not mark {sorted(missing)} required"


def test_harmless_optionals_keep_their_defaults():
    """The severity filter, encoded. An argument earns `required` only when its default
    differs from the resolved value AND that delta moves a number or flips a gate. These
    do not, and forcing them would break every call site for no protocol gain."""
    sig = _signature(LAMMPS_SERVER, "check_equilibration_comprehensive")
    for name in ("skip_frames", "dump_every", "eq_fraction", "block_count",
                 "temp_col", "density_col", "energy_col", "bond_length_A"):
        assert sig[name], f"{name} lost its default"
    bm = _signature(LAMMPS_SERVER, "run_bulk_modulus_series")
    for name in ("thermo_freq", "output_dir"):
        assert bm[name], f"{name} lost its default"


def test_dump_every_stays_optional_because_it_self_heals():
    """The asymmetry that makes timestep_fs required and dump_every not: the analysis
    script infers dump_every from consecutive timestep values in the dump header, so a
    wrong one corrects itself. Nothing infers timestep_fs."""
    src = (LAMMPS_SERVER.parent / "analysis_scripts"
           / "check_equilibration_comprehensive.py").read_text()
    assert "Auto-detected dump_every" in src


@pytest.mark.parametrize("tool", TOOLS)
def test_scripted_executor_passes_every_required_arg(tool):
    """The check that would have caught the cutoff_A bug: the deterministic path is a
    plain Python caller, so an omission there is invisible to any amount of prompt or
    guide wording."""
    _, required, _ = REQUIRED_ARGS[tool]
    tree = ast.parse(EXECUTOR.read_text())
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == tool]
    for call in calls:
        if any(k.arg is None for k in call.keywords):
            continue  # **kwargs splat -- can't resolve statically
        passed = {k.arg for k in call.keywords}
        missing = set(required) - passed
        assert not missing, f"{EXECUTOR.name}:{call.lineno} {tool} omits {sorted(missing)}"


def _call_blocks(text: str, tool: str):
    """Every `tool(...)` argument list in the markdown, by balanced parens -- the blocks
    close on their own line in some guides and inline in others."""
    blocks = []
    for m in re.finditer(rf"(?<![\w.]){tool}\(", text):
        i, depth = m.end(), 1
        while i < len(text) and depth:
            depth += (text[i] == "(") - (text[i] == ")")
            i += 1
        blocks.append(text[m.end():i - 1])
    return blocks


@pytest.mark.parametrize("tool", TOOLS)
def test_guide_call_block_names_every_required_arg(tool):
    """Closes the subagent link. A worker copies the guide's canonical call block, so an
    argument missing there reproduces itself on every run no matter what the tool schema
    says."""
    _, required, guides = REQUIRED_ARGS[tool]
    if guides is None:
        pytest.skip(f"{tool}'s call args are specified in gen_prompt, not a guide")
    for guide in ([guides] if isinstance(guides, str) else guides):
        text = (REPO_ROOT / "guides" / guide).read_text()
        blocks = _call_blocks(text, tool)
        assert blocks, f"{guide} has no canonical {tool}(...) call block"
        for name in required:
            assert any(re.search(rf"\b{name}\s*=", b) for b in blocks), (
                f"{guide}'s {tool} block omits {name}= -- workers copy this block verbatim")


def test_no_guide_still_instructs_conditional_omission():
    """`if x is not None: kwargs[...]` and 'do NOT pass' were how the omission got
    written down in the first place. Under required-and-nullable the instruction is
    always 'pass the null'."""
    offenders = []
    for path in sorted((REPO_ROOT / "guides").glob("*.md")):
        text = path.read_text()
        for pattern in (r"do NOT pass\s+`?\w+`?\s+to", r"Deliberately OMIT",
                        r"kwargs\[[\"']\w+[\"']\]\s*="):
            for m in re.finditer(pattern, text):
                offenders.append(f"{path.name}: {m.group(0)!r}")
    assert not offenders, "guides still instruct omission: " + "; ".join(offenders)


def test_gen_prompt_melt_gate_passes_explicit_nulls():
    """The phase=melt branch used to say 'Deliberately OMIT exp_density_gcm3/tg_K/
    glass_data/melt_data'. Those are now required, so the branch has to name them as
    nulls or every glassy run hard-fails at the melt gate."""
    src = (REPO_ROOT / "orchestration" / "scripts" / "gen_prompt.py").read_text()
    assert "Deliberately OMIT" not in src
    melt = src[src.index('if p["phase"] == "melt"'):src.index("def _resolve_murnaghan_params")]
    for name in ("exp_density_gcm3", "tg_K", "t_equil_K", "glass_data", "melt_data",
                 "alpha_glass_per_K", "alpha_melt_per_K"):
        assert re.search(rf"{name}\s+= null", melt), f"melt gate block omits {name} = null"


@pytest.mark.parametrize("stage,fields", [
    ("equil-check", ["cutoff_A", "ct_min_decay_melt", "dt_fs"]),
    ("analyze-bm", ["dt_fs", "strain_rate_per_fs", "K_strain_max", "npt_prod_log_path"]),
    ("analyze-tg", ["tg_data_file", "per_t_dump_file", "method_gap_exempt"]),
    ("murnaghan", ["dt_fs", "npt_steps", "engine", "velocity_seed", "lammps_flags"]),
    ("deform", ["dt_fs", "engine", "gpu_ids", "mpi_ranks", "velocity_seed"]),
    ("build", ["dp", "nchain", "density_initial", "emc_seed"]),
])
def test_prompt_emits_the_value_the_tool_needs(stage, fields):
    """A required tool argument with no prompt field behind it is worse than an optional
    one: it turns a silent wrong number into a hard failure with nothing to pass."""
    import gen_prompt

    class A:
        pass

    args = A()
    for k, v in dict(
        run_name="PACR9", polymer_class="PACR", smiles="*CC(*)(C)C(=O)OC",
        data_path="/x/cell.data", work_dir=None, output_dir=None, dt_fs=None,
        gpu_ids="0", mpi_ranks=1, engine="kokkos", lammps_flags=None, nchain=None,
        dp=None, backbone_types=None, velocity_seed=None, emc_seed=None,
        density_initial=None, is_glassy="true", deform_rate_mode="primary",
        K_deform_rate_inv_s=None, K_strain_max=None, tg_rate_index=None,
        tg_t_high_K=None, tg_t_low_K=None, tg_t_step_K=None, tg_steps_per_t=None,
        tg_start_data=None, T_equil_K=None, T_anneal_high_K=None, npt_prod_ns=None,
        npt_cool_steps=None, npt_cool300_steps=None, add_melt_npt=False, phase="full",
        pending_cooldown_path=None, deform_log="/x/d.log", deform_log_slow=None,
        murnaghan_logs=None, npt_prod_log=None, npt_prod_dump=None, equil_data_path=None,
        enthalpy_col=None, exp_K_min=None, exp_K_max=None, exp_tg_K=None,
    ).items():
        setattr(args, k, v)
    rules = gen_prompt.json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())
    cls = rules["classes"]["PACR"]
    text = gen_prompt.STAGE_MAP[stage](args, cls)
    for name in fields:
        assert f"{name}:" in text, f"--stage {stage} prompt omits {name}"
