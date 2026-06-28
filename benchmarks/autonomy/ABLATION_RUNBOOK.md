# R1M7 3-arm foundation ablation — ready-to-fire runbook

Goal: for each system, produce three comparable `results/<sys>_<arm>.json` (process metrics)
plus a supplementary `<sys>_<arm>_accuracy.json` (300 K density vs exp). Arms, dumbest→smartest:
**stock** (generic EMC defaults) < **script** (curated `polymer_rules.json`) < **agent** (real orchestrator).

## Systems
- **PMMA / PACR** — on-table control (and the GPU go/no-go probe, below).
- **poly(propylene sulfide) / PSUL** — fresh, aliphatic, low-Tg (~225 K). Class-member
  *curation trap*: the SMILES is the aliphatic member, but PSUL is calibrated for aromatic
  polyphenylene sulfide (Tg 358 K, ρ 1.35). Stock and script inherit the wrong member's physics;
  only the **agent** arm escapes via `literature-grounding-worker` (PSUL is confidence=medium, so
  GROUND fires). The discriminating axis here is **agent vs. {stock, script}**, not stock-vs-script.
  SMILES (2 stars): `*CC(C)S*`. ⚠ aliphatic C–S–C in PCFF is untested — smoke-test the build first.

## Confirmed mechanism (CPU, 2026-06-27) — what actually differs between arms
The equil workflow always melts to `max_temp` via nvt_softheat, so stock does NOT skip the melt.
The real difference is the **production/equilibration regime**:
- **stock** (T_workflow=300 → 7-run): production at **300 K** — glassy/frozen for PC (Tg 422),
  no mobile-melt relaxation at 1 atm.
- **script/agent** (T_workflow=550 PMMA / 600 PC → 9-run): production at the **melt** (550/600 K,
  mobile, equilibrates), then npt_cool300 + npt_prod300 at **300 K**.
Both report density at **300 K** (stock: npt_production@300; curated: npt_prod300@300) — apples-to-apples
*after* the scripted_baseline fix that reads `wf["npt_production_dir"]` (points to npt_prod300 for the
glassy 9-run) instead of hardcoding npt_production (the melt). The gap grows with Tg, so PC is the
discriminating system; PMMA is the control.

## Expectation (set honestly)
Process metric (terminal_state/interventions) will most likely show **all arms complete** for both
systems — that's on-design. The discriminating foundation output is **accuracy** (curated/agent closer
to exp than stock). The *process-divergence* (recovery) story lives in the R1M11 recovery study, not here.

## GO/NO-GO GATE (do this FIRST when a GPU frees)
The whole premise = "does the stock regime gap move 300 K density measurably?" Test with ONE run:
run **stock-PMMA**, compare its 300 K density to an existing curated PMMA (data/PMMA1 or PMMA2).
- Meaningfully different (≳1–2%) → mechanism has signal → run the rest.
- Within noise → reconsider the floor before spending on PC.

## Commands
```bash
VENV=/home/arz2/PolyJarvis/mcp-servers/.venv/bin/python   # base python lacks `mcp`
cd /home/arz2/PolyJarvis
GPU=$(scripts/pick_gpu.py --json claim --run ABLATION --need 1 | python3 -c 'import sys,json;print(json.load(sys.stdin)["claimed"][0])')

# GATE: stock-PMMA first
$VENV benchmarks/autonomy/scripted_baseline.py --run PMMA_STOCK --arm stock \
  --polymer_class PACR --smiles "*CC(C)(C(=O)OC)*" --execute --gpu_ids $GPU --mpi 8 --seed 1001
$VENV benchmarks/autonomy/agent_metrics.py --run_dir data/PMMA2 --system PMMA_ref \
  --polymer_class PACR --accuracy   # curated reference density for the gate comparison

# If gate passes — remaining scripted arms (same seed 1001):
$VENV benchmarks/autonomy/scripted_baseline.py --run PMMA_CURATED --arm script \
  --polymer_class PACR --smiles "*CC(C)(C(=O)OC)*" --execute --gpu_ids $GPU --mpi 8 --seed 1001
# Build smoke-test FIRST (aliphatic C–S–C in PCFF is untested; blocks all three arms if it fails):
$VENV benchmarks/autonomy/scripted_baseline.py --run PROPSULFIDE_SMOKE --arm script \
  --polymer_class PSUL --smiles "*CC(C)S*" --smoke
$VENV benchmarks/autonomy/scripted_baseline.py --run PROPSULFIDE_STOCK --arm stock \
  --polymer_class PSUL --smiles "*CC(C)S*" --execute --gpu_ids $GPU --mpi 8 --seed 1001
$VENV benchmarks/autonomy/scripted_baseline.py --run PROPSULFIDE_CURATED --arm script \
  --polymer_class PSUL --smiles "*CC(C)S*" --execute --gpu_ids $GPU --mpi 8 --seed 1001

scripts/pick_gpu.py release --run ABLATION
```

## Agent arm (the third arm)
Not this driver — a real foundation-only orchestrator run on the SAME seed (1001), then parsed.
For poly(propylene sulfide) the prepared task lives at `data/PROPSULFIDE_AGENT/Task.txt` (run it in a
fresh orchestrator session). CRITICAL: the orchestrator must ground the **aliphatic** molecule —
polymer_name "poly(propylene sulfide)", never "polyphenylene sulfide"/"PPS" — or the trap closes.
```bash
$VENV benchmarks/autonomy/agent_metrics.py --run_dir data/<PMMA_AGENT_RUN> --system PMMA \
  --polymer_class PACR --seed 1001 --foundation-only --accuracy
$VENV benchmarks/autonomy/agent_metrics.py --run_dir data/PROPSULFIDE_AGENT --system PROPSULFIDE \
  --polymer_class PSUL --seed 1001 --foundation-only --accuracy
```
For clean parsing the orchestrator should emit per RECOVERIES block:
`<!-- RECOVERY: error_class=.. prescripted=.. outcome=.. attempts=.. -->`

## Notes
- mpi=8 (PCFF/class2 is charged — mpi≥4 required; mpi=1 starves the GPU run). engine="gpu" is
  hardcoded in `_dispatch_equil`; kokkos would be faster but gpu is fine for the small foundation cell.
- Hold the GPU claim across the whole arm; verify `release` returns a non-empty list.
- Accuracy exp band: PMMA 1.19 (PACR). For poly(propylene sulfide) do NOT hardcode a band — the
  point is that each arm grades against its OWN run_summary exp_range: stock/script inherit the
  aromatic-PPS band (~1.35, wrong member) while the agent's exp-lookup recovers the aliphatic
  band (~1.1). Raw 300 K MD density is FF-determined and likely ~1.1 for all arms, so the agent's
  edge surfaces as regime-correctness (rubbery 7-stage vs script's 560 K glassy path) and the
  correct accuracy verdict, not a better density number. Process metrics never include accuracy.
```
