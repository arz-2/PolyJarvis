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
        "tg_data_file", "per_t_dump_file", "method_gap_exempt", "backbone_types",
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


# Worker-facing docs outside guides/ that carry their own literal call blocks. An agent .md
# loads before its guide, and recover.md is the recovery path's source of truth, so a block
# here that omits a required arg hard-fails that worker on its first call.
OTHER_CALLER_DOCS = (sorted((REPO_ROOT / ".claude" / "agents").glob("*.md"))
                     + [REPO_ROOT / ".claude" / "commands" / "recover.md",
                        REPO_ROOT / "orchestration" / "tracks" / "FOUNDATION.md"])

# recover.md's RE-ANNEAL block is a deliberate delta -- it shows only the arguments that
# change, and says so on the next line. Exempt the tool there, not the file.
DELTA_BLOCK_EXEMPT = {("recover.md", "generate_equilibration_workflow")}


@pytest.mark.parametrize("doc", OTHER_CALLER_DOCS, ids=lambda p: p.name)
def test_agent_and_recovery_docs_name_every_required_arg(doc):
    text = doc.read_text()
    for tool, (_srv, required, _g) in REQUIRED_ARGS.items():
        if (doc.name, tool) in DELTA_BLOCK_EXEMPT:
            continue
        for block in _call_blocks(text, tool):
            # Prose mentions like `tool(extend_only=True)` inside a table cell are not call
            # sites; a real block names at least the tool's own first positional arg.
            if len(block) < 40:
                continue
            missing = [n for n in required if not re.search(rf"\b{n}\s*=", block)]
            assert not missing, f"{doc.name}'s {tool} block omits {missing}"


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


def _stage_args(**overrides):
    """gen_prompt's argparse namespace with every flag at its default, as a stage function sees
    it when the orchestrator passes nothing but the basics."""
    class A:
        pass

    args = A()
    defaults = dict(
        run_name="PACR9", polymer_class="PACR", smiles="*CC(*)(C)C(=O)OC",
        data_path="/x/cell.data", work_dir=None, output_dir=None, dt_fs=None,
        gpu_ids="0", mpi_ranks=1, engine="kokkos", lammps_flags=None, nchain=None,
        dp=None, backbone_types=None, velocity_seed=None, emc_seed=None,
        density_initial=None, is_glassy=None, deform_rate_mode="primary",
        K_deform_rate_inv_s=None, K_strain_max=None, tg_rate_index=None,
        tg_t_high_K=None, tg_t_low_K=None, tg_t_step_K=None, tg_steps_per_t=None,
        tg_start_data=None, T_equil_K=None, T_anneal_high_K=None, npt_prod_ns=None,
        npt_cool_steps=None, npt_cool300_steps=None, add_melt_npt=False, phase="full",
        pending_cooldown_path=None, deform_log="/x/d.log", deform_log_slow=None,
        murnaghan_logs=None, npt_prod_log=None, npt_prod_dump=None, equil_data_path=None,
        enthalpy_col=None, exp_K_min=None, exp_K_max=None, exp_tg_K=None,
    )
    for k, v in {**defaults, **overrides}.items():
        setattr(args, k, v)
    return args


@pytest.mark.parametrize("stage,fields", [
    ("equil-check", ["cutoff_A", "ct_min_decay_melt", "dt_fs"]),
    ("analyze-bm", ["dt_fs", "strain_rate_per_fs", "K_strain_max", "npt_prod_log_path"]),
    ("analyze-tg", ["tg_data_file", "per_t_dump_file", "method_gap_exempt", "backbone_types"]),
    ("murnaghan", ["dt_fs", "npt_steps", "engine", "velocity_seed", "lammps_flags"]),
    ("deform", ["dt_fs", "engine", "gpu_ids", "mpi_ranks", "velocity_seed"]),
    ("build", ["dp", "nchain", "density_initial", "emc_seed"]),
])
def test_prompt_emits_the_value_the_tool_needs(stage, fields):
    """A required tool argument with no prompt field behind it is worse than an optional
    one: it turns a silent wrong number into a hard failure with nothing to pass."""
    import gen_prompt

    rules = gen_prompt.json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())
    cls = rules["classes"]["PACR"]
    text = gen_prompt.STAGE_MAP[stage](_stage_args(), cls)
    for name in fields:
        assert f"{name}:" in text, f"--stage {stage} prompt omits {name}"


def _agent_tools(doc: Path) -> set:
    """The bare tool names in an agent .md's `tools:` frontmatter list."""
    m = re.search(r"^tools:\n((?:\s*-\s.*\n)+)", doc.read_text(), re.M)
    if not m:
        return set()
    return {line.split("__")[-1].strip()
            for line in re.findall(r"^\s*-\s*(\S+)", m.group(1), re.M)}


AGENT_DOCS = sorted((REPO_ROOT / ".claude" / "agents").glob("*.md"))


@pytest.mark.parametrize("doc", AGENT_DOCS, ids=lambda p: p.name)
def test_agent_md_arg_list_is_not_a_subset(doc):
    """An agent .md that names *some* of a tool's required arguments must name them all.

    The .md loads before its guide, and a worker follows the nearer instruction: tg-analysis-worker
    said "always pass output_dir and graphs_dir" while THERMAL_ANALYSIS.md's call block also named
    tg_data_file/per_t_dump_file, and the worker passed the .md's two. per_t_dump_file went unpassed
    on every run, the Tg sweep wrote per_t_structs.dump nobody read, and P2/Rg/Tg_dynamic_K were
    silently absent from tg_summary.json. A partial list is worse than no list -- an .md that
    delegates wholly to its guide names none of them and is fine."""
    lines = doc.read_text().splitlines()
    tools = _agent_tools(doc)
    for tool, (_srv, required, _g) in REQUIRED_ARGS.items():
        if tool not in tools:
            continue
        # Only prose that tells the worker what to pass *to this tool* competes with the guide.
        # A mention of an argument anywhere else in the .md does not.
        instructions = [ln for ln in lines
                        if re.search(r"\bpass(es|ing)?\b", ln, re.I) and tool in ln]
        params = set(_signature(_srv, tool))
        for ln in instructions:
            # Any parameter of this tool, not just a required one: the tg-analysis-worker line
            # that caused this named `output_dir` and `graphs_dir` only, and an enumeration that
            # stops before the required arguments is exactly the failure.
            named = {n for n in params if re.search(rf"`{n}[`=]|\b{n}\s*=", ln)}
            if not named:
                continue  # a general instruction, not an enumeration
            missing = sorted(set(required) - named)
            assert not missing, (
                f"{doc.name} tells the worker to pass {sorted(named)} to {tool} but not "
                f"{missing} -- a partial list overrides the guide's complete one:\n  {ln.strip()}")


def test_is_glassy_has_no_argparse_default():
    """The stage functions are tested through a namespace, which bypasses argparse entirely --
    so the derivation can be correct while the CLI still hands every caller a literal "true".
    That was the actual bug: `--is_glassy` defaulted to the string, so `_is_glassy`'s regime
    branch was unreachable from the command line."""
    tree = ast.parse((REPO_ROOT / "orchestration" / "scripts" / "gen_prompt.py").read_text())
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            continue
        if not (node.args and getattr(node.args[0], "value", None) == "--is_glassy"):
            continue
        default = next((k.value for k in node.keywords if k.arg == "default"), None)
        assert default is not None, "--is_glassy lost its explicit default=None"
        assert getattr(default, "value", "sentinel") is None, (
            "--is_glassy must default to None so the regime oracle decides; a string default "
            "makes every rubbery run's murnaghan/deform prompt claim glassy")
        return
    raise AssertionError("--is_glassy is no longer declared in gen_prompt.py")


# ── is_glassy: derived, never defaulted ───────────────────────────────────────
# `--is_glassy` defaulted to the string "true", so both consumers' `else` branches were dead code
# and every rubbery run's murnaghan/deform prompt claimed glassy. The regime oracle already knew
# better -- it drives the equil-check carve-out and the analyze-tg data path off the same
# T_workflow.

def _prompt(stage, polymer_class, is_glassy=None):
    import gen_prompt

    args = _stage_args(run_name="_probe", polymer_class=polymer_class, is_glassy=is_glassy)
    rules = gen_prompt.json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())
    return gen_prompt.STAGE_MAP[stage](args, rules["classes"][polymer_class])


@pytest.mark.parametrize("stage", ["murnaghan", "deform"])
@pytest.mark.parametrize("polymer_class,expected", [("POXI", "false"), ("PDIE", "false"),
                                                    ("PACR", "true"), ("PEST", "true")])
def test_is_glassy_follows_the_regime_when_the_flag_is_absent(stage, polymer_class, expected):
    assert f"is_glassy:         {expected}" in _prompt(stage, polymer_class)


def test_explicit_is_glassy_overrides_the_derivation():
    """The thermal track's value comes from this run's measured Tg and stays authoritative."""
    assert "is_glassy:         false" in _prompt("murnaghan", "PACR", is_glassy="false")
    assert "is_glassy:         true" in _prompt("murnaghan", "POXI", is_glassy="true")


def test_rubbery_class_does_not_get_the_glassy_submit_assertion():
    """The assertion is imperative and sits above the guide, so a wrong is_glassy does not merely
    mislabel the prompt -- it orders the worker down the glassy branch."""
    assert "is_glassy=true → SUBMIT" not in _prompt("murnaghan", "POXI")
    assert "is_glassy=true → SUBMIT" in _prompt("murnaghan", "PACR")


# ── output_dir: never derived from an input file ──────────────────────────────

def test_no_tool_derives_output_dir_from_an_input_file():
    """Seven tools silently redirected a null output_dir into a subdirectory of their own input
    (<log dir>/bulk_analysis, <dump dir>/eq_comprehensive, ...). generate_run_summary reads only
    the flat output_dir, so those JSONs were written and never read -- confirmed on cis-PBD1.

    Scoped to input-file-derived paths on purpose: run_bulk_modulus_series defaults output_dir to
    its own work_dir, which is a caller-supplied run directory, not a guess."""
    src = LAMMPS_SERVER.read_text()
    offenders = re.findall(r"output_dir\s*=\s*str\(Path\([^)]*\)\.parent[^\n]*", src)
    assert not offenders, "output_dir derived from an input file: " + "; ".join(offenders)


# ── The params-dict hole ──────────────────────────────────────────────────────
# generate_script's own signature is fully required, but the deck's protocol values ride
# inside its `params` dict, where a missing key falls back to a template default and no
# JSON schema can see it. The npt_deform strain is the sharp case: the template renders
# `run {N_STEPS}` and has no STRAIN_MAX placeholder at all, so the strain actually reached
# is N_STEPS * STRAIN_RATE * TIMESTEP and nothing tied that product to the requested
# K_strain_max.

def _generator():
    sys.path.insert(0, str(LAMMPS_SERVER.parent))
    from script_generator import ScriptGenerator
    return ScriptGenerator


def _deform_steps(tmp_path, **params):
    # A path that does not exist: abspath still renders it into the deck, and the
    # data-file FF auto-detection is guarded by os.path.exists, so use_pcff below stands.
    data_file = str(tmp_path / "cell.data")
    gen = _generator()(data_file=data_file)
    out = tmp_path / "d.in"
    base = {"STRAIN_RATE": 1e-7, "TIMESTEP": 1.0, "use_pcff": True, "DUMP_FILE": ""}
    gen.generate(template_name="npt_deform", output_path=str(out),
                 params={**base, **params}, velocity_seed=42)
    # The deck runs twice: NVT pre-equilibration (N_EQ_STEPS) first, then the deformation.
    # Anchor on the fix that starts straining, not on the first `run` in the file.
    return int(re.search(r"fix def all deform[^\n]*\nrun (\d+)", out.read_text()).group(1))


def test_strain_max_drives_the_step_count(tmp_path):
    """PSTR deforms at 1e7 /s, a tenth of every other class. On the 300000-step default it
    reached 0.003 strain, not the 0.03 it asked for -- and the extractor then fit a
    0.002-0.03 window against data that stopped at 0.003."""
    assert _deform_steps(tmp_path, STRAIN_RATE=1e-8, STRAIN_MAX=0.03) == 3_000_000
    assert _deform_steps(tmp_path, STRAIN_RATE=1e-7, STRAIN_MAX=0.03) == 300_000
    # dt=2 fs halves the steps needed for the same strain
    assert _deform_steps(tmp_path, TIMESTEP=2.0, STRAIN_MAX=0.03) == 150_000


def test_inconsistent_strain_pair_is_refused(tmp_path):
    with pytest.raises(ValueError, match="strain mismatch"):
        _deform_steps(tmp_path, STRAIN_RATE=1e-8, STRAIN_MAX=0.03, N_STEPS=300000)


def test_every_class_reaches_its_requested_strain(tmp_path):
    """Both legs, every class that has a deform rate -- the slow leg is the one that was
    uniformly short, since it drops the rate ~10x while N_STEPS stayed put."""
    import json
    classes = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())["classes"]
    for name, cls in sorted(classes.items()):
        smax, dt = cls.get("K_strain_max"), cls.get("dt_fs", 1.0)
        if smax is None:
            continue
        for key in ("K_deform_rate_inv_s", "K_deform_rate_slow_inv_s"):
            rate = cls.get(key)
            if not rate:
                continue
            rate_fs = rate * 1e-15
            steps = _deform_steps(tmp_path, STRAIN_RATE=rate_fs, TIMESTEP=dt, STRAIN_MAX=smax)
            reached = steps * rate_fs * dt
            assert abs(reached - smax) / smax < 0.01, f"{name} {key}: reached {reached}"
