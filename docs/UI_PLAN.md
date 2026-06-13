# PolyJarvis Streamlit UI — Implementation Plan

> Status: **proposed / not yet implemented.** This document is the design spec for a
> web UI over PolyJarvis. No code has been written yet.

## 1. Context

PolyJarvis is today a pure-Python, MCP-driven agent with **no frontend at all** — no
JS, no web server, no HTML. All user interaction goes through the Claude Code
orchestrator, and the only user-facing "outputs" are files on disk:

- Each run's `data/[RUN]/run_log.md` — a markdown checkpoint with `SIMULATION STATE`,
  `RESULTS`, `DECISIONS`, `RECOVERIES`, and `TIMING` sections.
- Per-run analysis artifacts — JSON summaries (`tg_analysis.json`,
  `density_results.json`, `bulk_modulus.json`, aggregated `run_summary.json`), CSVs
  (`tg_density_bins.csv`), and static matplotlib PNGs (density-vs-T fit, RDF, MSD, Rg).
- The 21-class polymer database in `guides/polymer_rules.json`.

**Goal:** a clean Streamlit UI covering four areas — **monitor live runs, browse
results, launch new jobs, and browse the polymer DB** — at **read + light-control**
depth.

### Core design constraint

The UI must run with just `pip install streamlit pandas` and must **not** depend on the
heavy conda envs (RadonPy/LAMMPS) or run LAMMPS itself. Therefore the UI is
**file-first**: its source of truth is each run's local `run_log.md` + artifacts. Any
live backend call (`classify_polymer`, `get_run_status`) is an **optional,
feature-flagged enhancement that degrades gracefully** when those envs/servers are
absent. Launching a job means dropping a file-based request the orchestrator picks up;
the UI never drives the multi-agent pipeline directly.

### Grounding facts (confirmed during exploration)

- `data/*` is **gitignored** except `data/TEMPLATE/` (`.gitignore:22-23`). The queue
  folder and any seeded sample runs stay local; tracked test fixtures must live under
  `tests/fixtures/`.
- Server-side run state lives at a machine-specific, gitignored path
  (`mcp-lammps-engine/run_state.json`) — another reason to trust `run_log.md` as the
  portable source of truth.
- The orchestrator already writes a `## SIMULATION STATE` table to `run_log.md` before
  each Monitor call (`CLAUDE.md:75-85`) — the UI reads exactly this.

## 2. Approach

A new top-level **`ui/`** package, run with `streamlit run ui/app.py`. Streamlit
multipage layout (files in `pages/` auto-appear in the sidebar in numeric order).
File-only operation is always functional; live MCP calls are gated behind a `LIVE_MCP`
flag and wrapped so any failure silently falls back to file/manual mode.

### 2.1 Directory / file layout

```
ui/
  app.py                # Home/dashboard: run counts, capability banner, recent runs
  pages/
    1_Monitor.py        # live runs list + per-run live view (SIMULATION STATE, auto-refresh)
    2_Results.py        # per-run results: RESULTS table, PNGs, JSON/CSV, DECISIONS/TIMING
    3_Launch.py         # new-job form: classify/defaults preview → scaffold → enqueue
    4_Polymer_DB.py     # browse/search the 21 polymer_rules.json classes
  paths.py              # repo-root resolution; DATA_DIR, QUEUE_DIR, TEMPLATE, RULES_JSON; list_run_dirs()
  runlog_parser.py      # parse run_log.md → dicts/DataFrames (the core read primitive)
  rules.py              # load + index polymer_rules.json (cached); search_classes()
  artifacts.py          # discover/load a run's JSON, CSV, PNG artifacts (glob, absence-tolerant)
  backend.py            # adapter: pure-file ops always; optional live calls + capabilities()
  scaffold.py           # copy TEMPLATE, fill header, write REQUEST.json + queue pointer
  components.py         # shared widgets: status_badge, results_table, auto_refresh, kv_header
requirements-ui.txt     # streamlit, pandas (no rdkit/radonpy/lammps)
```

### 2.2 Key modules

**`paths.py`** — resolve repo root robustly (walk up from `__file__` until
`guides/polymer_rules.json` exists; allow `POLYJARVIS_ROOT` override). Exposes
`REPO_ROOT`, `DATA_DIR`, `QUEUE_DIR`, `TEMPLATE_RUNLOG`, `RULES_JSON`, and
`list_run_dirs()` (all `data/*/` except `TEMPLATE` and `queue`).

**`runlog_parser.py`** — `parse_run_log(path|text) -> dict`, the core read primitive.
Markdown is section-delimited by `## HEADERS`/`---`. Strategy:
1. Split on `## ` headers; keep the preamble (lines 1–3) as `header`.
2. Regex-extract the header line (`SMILES`, `FF`, `Charges`, `DP`, `Chains`, `GPU`),
   line 1 (`polymer_name`, `run_number`, dates), line 3 (seeds).
3. A generic `_md_table()` helper turns each markdown table into a DataFrame — reused for
   DECISIONS, SIMULATION STATE, TIMING, RESULTS.
4. Strip HTML-comment examples (`<!-- ... -->`) so the template's examples don't leak.
5. Treat any `[...]`-only cell as "unfilled" (real logs are often partial).
6. Normalize SIMULATION STATE `status` (`pending/submitted/monitoring/done/failed/
   UNRESOLVED`) and RESULTS `✓/⚠/—` glyphs into enums for badge coloring.
7. RECOVERIES: detect the literal `None` sentinel → empty; else return raw block,
   best-effort split on `[Stage N]` markers.

`derive_overall_status()` collapses SIMULATION STATE into one dashboard status
(`queued/building/equilibrating/tg-sweep/analysis/done/failed/unresolved`). Pure-Python
(`re`); pandas only at the page layer.

**`backend.py`** — the decoupling layer.
- Pure-file (always): `list_runs()` (cached, short TTL), `get_run(run_id)`,
  `validate_smiles()` (RDKit-free heuristic — balanced brackets, legal chars, a `*`
  polymerization marker — warns, never blocks).
- Live (optional, `LIVE_MCP`, default off): `classify_polymer_live()`,
  `get_run_status_live()` shell into the MCP servers; on any failure return
  `{"available": False, "reason": ...}`.
- `capabilities()` probes once so the sidebar shows "live backend connected" vs
  "file-only mode".

**`rules.py`** — cached `load_rules()` over `guides/polymer_rules.json`; `classes()`,
`search_classes(query)` (matches name/examples/notes/class_id), accessors for
`global_defaults`/`electrostatics_decision_guide`/`tg_protocol_reference`/`_metadata`.
Powers both the DB browser and the Launch defaults preview. No RDKit.

**`artifacts.py`** — `discover(run_dir)` returns a manifest `{json:{name:path},
csv:[...], png:[...], runlog:path}` by glob so pages render only what exists.

**`scaffold.py`** — the launch action, all plain file ops, gated behind a confirm
button: `next_run_id()`, `scaffold_run()` (mkdir `data/[RUN]/`, copy
`data/TEMPLATE/run_log.md`, fill header tokens it can, seed a `## SIMULATION STATE` row
with status `queued` so the run shows up immediately), `write_request()` (write
`REQUEST.json` into the run dir **and** a pointer `data/queue/{run_id}.json` for the
orchestrator to watch). The UI only ever writes files it owns — never a run's
`run_log.md` after scaffolding — avoiding write races with the orchestrator.

**`components.py`** — `status_badge(status)`, `results_table(results)` (✓/⚠ colors),
`auto_refresh(seconds)` (uses `streamlit-autorefresh` if present, else a manual button +
`st.rerun`), `kv_header(header_dict)`.

### 2.3 Pages

- **`1_Monitor.py`** — dashboard DataFrame from `list_runs()` with status badges;
  per-run live view shows parsed SIMULATION STATE + partial RESULTS + latest RECOVERIES;
  `auto_refresh` (default 15 s, slider). Optional "enrich with live status" button when
  `capabilities().live_status`. Empty-state message when no runs exist.
- **`2_Results.py`** — run picker (default to done runs); RESULTS table with ✓/⚠ colors,
  PNG plots (`st.image`), JSON summaries (`st.json`, `run_summary.json` first),
  `tg_density_bins.csv` as a table + density-vs-T line chart, and
  DECISIONS/RECOVERIES/TIMING. Everything guarded "if present" so partial runs render.
- **`3_Launch.py`** — SMILES input (inline `validate_smiles` warnings) → classification
  preview (live if available, else manual dropdown of the 21 class_ids) → defaults from
  `rules.py` (FF, charge method, DP, nchain, density, Tg targets, citations) → editable
  params → preview the assembled `REQUEST.json` → **Confirm & enqueue** → links to
  Monitor. Idempotent (warn on existing run_id).
- **`4_Polymer_DB.py`** — search box → `search_classes`; selectable class list; detail
  panel with all per-class fields, `experimental_tg_K` table, citations/notes, confidence
  badge; tabs for global_defaults / electrostatics guide / tg_protocol / metadata.

### 2.4 Run-request schema (`REQUEST.json` + `data/queue/{run_id}.json`)

```json
{
  "schema_version": "1.0",
  "run_id": "PSTR_03",
  "created_at": "2026-06-13T16:40:00",
  "created_by": "arz2@andrew.cmu.edu",
  "status": "queued",
  "source": "streamlit-ui",
  "smiles": "*CC(*)c1ccccc1",
  "classification": {
    "method": "manual | classify_polymer",
    "class_id": "PSTR",
    "class_name": "Polystyrene-type",
    "confidence": "user-selected"
  },
  "params": {
    "force_field": "TraPPE-UA",
    "charge_method": "embedded in FF",
    "dp": 50,
    "n_chains": 10,
    "density_initial_gcm3": 0.55,
    "gpu_ids": "0",
    "overrides": {}
  },
  "analysis_tasks": ["check_equilibration_comprehensive","extract_tg","extract_density","extract_bulk_modulus"],
  "notes": "free text"
}
```

Status lifecycle owned by the orchestrator after pickup: `queued → claimed → running →
done|failed`. The UI only ever writes `queued`. `run_id` is the join key to
`data/[run_id]/`.

### 2.5 Orchestrator glue (one documented contract, no MCP-server code changes)

Add a short **"## Job Intake (UI-enqueued runs)"** section to `CLAUDE.md`: at session
start, check `data/queue/*.json` for `status == "queued"`; for each, set
`status:"claimed"`, then run the existing workflow (`CLAUDE.md:44-64`) using the
request's `smiles` + `params` instead of prompting the user (if `method == "manual"`,
use the provided `class_id` to look up `polymer_rules.json`; the run dir already exists,
so reuse the scaffolded `run_log.md` rather than re-copying TEMPLATE); update the queue
file `status` on completion. This is the only new contract — everything downstream is
unchanged.

## 3. Files to create / modify

- **Create** `ui/` (all modules + pages above) and `requirements-ui.txt`.
- **Modify** `CLAUDE.md` — add the Job Intake section.
- **Create** tracked tests: `tests/fixtures/sample_run_log.md`,
  `tests/test_ui_runlog_parser.py`, `tests/test_ui_scaffold.py`, `tests/test_ui_rules.py`
  (matching existing `tests/` style; lightweight env, no conda).
- **No changes** to the MCP `server.py` files.

### Reused existing assets

- `data/TEMPLATE/run_log.md` — scaffold source **and** the parser contract.
- `guides/polymer_rules.json` — DB browser + Launch defaults (read directly).
- `mcp-servers/mcp-lammps-engine/server.py` (`get_run_status`/`list_runs`) and
  `mcp-mol-builder-server/server.py` (`classify_polymer`) — signatures for the *optional*
  live adapter only.

## 4. Dependencies & running

`requirements-ui.txt`:

```
streamlit>=1.33
pandas>=2.0
# optional, auto-detected:
# streamlit-autorefresh   # smoother live refresh; falls back to a manual button
```

Deliberately **no rdkit, no radonpy, no lammps** — satisfies the `pip install streamlit
pandas` constraint. Matplotlib not needed (PNGs are pre-rendered; `st.image` reads them).

Run: `pip install -r requirements-ui.txt`, then `streamlit run ui/app.py`. Optionally set
`POLYJARVIS_ROOT` and `LIVE_MCP=1` to enable best-effort live calls.

## 5. Verification (works with zero real runs)

Seed a local sample run (untracked, allowed under `data/`): a dev-only
`ui/_dev/seed_sample_run.py` that builds `data/SAMPLE_PS_01/` from TEMPLATE with a filled
header, a populated SIMULATION STATE (one `done`, one `monitoring` row), a filled RESULTS
table (one ✓, one ⚠), plus dummy `run_summary.json`, `tg_density_bins.csv`, and a
placeholder PNG.

1. **Monitor** — `SAMPLE_PS_01` appears with the derived status badge; per-run view shows
   the SIMULATION STATE table; editing `run_log.md` by hand and waiting shows the refresh
   pick it up. Zero-run case shows an empty state, no crash.
2. **Results** — sample run renders the RESULTS table with ✓/⚠ colors and the seeded
   JSON/CSV/PNG; delete one artifact → page still renders the rest.
3. **Launch** — submit a SMILES in file-only mode: classification falls back to the manual
   dropdown; confirm `data/[RUN]/run_log.md` is scaffolded and `REQUEST.json` +
   `data/queue/{run_id}.json` are written per schema; the new run shows on Monitor as
   `queued`. Malformed SMILES (unbalanced parens) → warning, not block.
4. **Polymer DB** — all 21 classes load; search "styrene"/"PSTR" filters; detail panel
   shows experimental_tg_K, citations, notes.
5. **Unit tests** — `pytest tests/test_ui_*.py` green in the lightweight env: parser
   against `data/TEMPLATE/run_log.md` (placeholders → unfilled) and the tracked
   `tests/fixtures/sample_run_log.md` (values populate); `search_classes`; scaffold
   request-schema round-trip; `validate_smiles` cases.

## 6. Trade-offs / fallbacks

- **Source of truth = `run_log.md`, not `get_run_status`** — works anywhere, survives
  server restarts; cost is liveness only as fresh as the last orchestrator checkpoint
  (mitigated by optional live enrichment).
- **Classification without RDKit/RadonPy** — manual class selection fallback;
  `validate_smiles` is heuristic and never blocks.
- **Launch is fire-and-forget via files** — the UI only enqueues; queued runs sit as
  `queued` until a live orchestrator session honors the new CLAUDE.md contract. By design
  (the UI must not run LAMMPS).
- **Templated/partial logs** — parser tolerates `[PLACEHOLDER]` cells and comment
  examples, rendering "—/unfilled" rather than erroring.
- **`data/` gitignored** — seeded sample runs and queue files are local-only; shared
  fixtures for CI go under `tests/fixtures/` (tracked) instead.
- **Concurrency on `run_log.md`** — the orchestrator writes while the UI reads; the UI
  never writes a run's `run_log.md` after scaffolding (only `REQUEST.json`/queue files it
  owns), avoiding write races.
```
