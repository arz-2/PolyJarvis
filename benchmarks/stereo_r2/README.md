# stereo_r2 — 7 systems × 3 seeded replicates

Fixed-protocol, independent-seed replicate campaign for the manuscript revision. 21 run
directories under `data/`, every plan materialized and verified, **nothing executed**.

    python3 benchmarks/stereo_r2/build_matrix.py     # (re)build the 21 run dirs
    python3 benchmarks/stereo_r2/verify_matrix.py    # 6 pre-GPU checks, claims no GPU

`MANIFEST.json` is the campaign definition: SMILES, class, stereochemistry, every pinned
experimental value with its source, and each system's known limitations. `matrix.json` is
generated — the 21 run names, their seeds, and their priced cost.

## Why this exists

Reviewer comment 1: the round-1 "replicates" varied cooling rate, chain length, chain count,
annealing cycles and pressure ladder, so stochastic uncertainty was conflated with protocol
and finite-size effects. Here `decided_params` are frozen per system and only two seeds move.
`verify_matrix.py`'s `identity` check asserts that mechanically — replicate plans differ in
`run_name`, `emc_seed`, `velocity_seed` and nothing else — and fails if a replicate shares a
seed, which would make it not a replicate.

## The set

| Run dirs | Polymer | Class | FF | Stereochemistry | GPU-h/run (priced) |
|---|---|---|---|---|---|
| `iPMMA_1..3` | PMMA | PACR | PCFF | isotactic | 10.33 |
| `aPS_1..3` | PS | PSTR | PCFF | atactic | 9.74 |
| `sPVC_1..3` | PVC | PVNL | PCFF | syndiotactic (dyad) | 7.55 |
| `PLLA_1..3` | PLA | PEST | PCFF | L-enantiopure | 10.34 |
| `PE_1..3` | PE | PHYC | **TraPPE-UA** | achiral | 2.25 |
| `PEEK_1..3` | PEEK | PKTN | PCFF | achiral | 11.47 |
| `PSU_1..3` | polysulfone | PSFO | PCFF | achiral | 10.62 |

Aliphatic apolar → chlorinated vinyl → aromatic vinyl → acrylic ester → aliphatic polyester →
aromatic ketone/ether → aromatic sulfone. Two electrostatics regimes (lj/cut + TraPPE-UA for
PE, PPPM + PCFF for the rest), four stereochemical states, PE rubbery at 300 K and the other
six glassy.

**How the FF column was resolved.** `forcefield.select_by_moiety(smiles, class_prior)` is the
selector -- "which force field this SMILES should BUILD with, and what was actually measured."
SMARTS from `guides/ff_moiety_rules.json` (3 rules, measured over 982 real EMC trial builds on
RadonPy's PI1070) narrow the candidates; a real EMC trial build decides among them. Three
outcomes: no blocker -> the class `ff_accuracy_prior` stands; a blocker matched -> probe ranked
candidates and take whichever field actually types the repeat unit, which can move the field off
the prior; nothing types it -> `field=None`, `D-01 admissible: []`, refuse. The class supplies a
prior, not the answer.

Measured for these seven (2026-09-08): every one cleared the screen with `blockers: []`,
`unscreened: False`, so each `D-01.choice` is its class prior and `resolved_by` records that.
The chemistry was checked and cleared in all seven cases; none exercises the branch where
chemistry moves the field OFF the prior, or the refusal. That branch is reachable -- nylon-6 and
an aromatic imide both trip `carbonyl_adjacent_N` -- so a set that demonstrates FF override
rather than FF confirmation would need a PAMD, PIMD, PURT or PURA member.

Stereochemistry varies **across** systems, never within one — so a system's three runs measure
seed variance alone, and the stereo capability is demonstrated without being confounded with it.

## Three findings from building it

**A PVC dyad classifies as the wrong class.** RadonPy's `polyinfo_classifier` returns `PVNL`
for the 1-mer `*CC(*)Cl` but `PHAL` for *any* 2-mer dyad — `*CC(Cl)CC(Cl)*` and both stereo
variants. It is a repeat-unit-cut artifact of matching on the extracted mainchain, not a stereo
effect. `PHAL` routes to OPLS-AA, which is a recorded EMC build failure for PVC, so unattended
this swaps the entire protocol. Syndiotactic requires a dyad (a 1-mer can only build all-same,
i.e. isotactic), so it is unavoidable. The class is therefore stated per system rather than
classified; `guides/class_overrides.json` is not the right home, because its own scope rule
admits only molecules curated in `member_smiles`.

**That same miss silently flipped PVC's thermal regime.** The dyad matches no `PVNL`
`member_smiles`, so `resolve_member_value` refused, `_regime_exp_tg` fell through to a
group-contribution estimate (196 K + 80 K uncertainty), and `workflow_reference_temperature`
collapsed `T_workflow_K` from 530 to 300 — which made `stage_params._regime` call glassy PVC
**rubbery** at `final_T_K=300` and dropped the deform fallback from its mechanical stage. Caught
by comparing scaffolds: sPVC came out at 300.0 where every other glassy system sat at its class
`T_equil_K`. Pinning `experimental_tg_K` alone does not fix it — `materialize_plan` only rewrites
`T_workflow_K` when `T_equil_K` is overridden — so both are pinned.

**Stereo variants need their own experimental targets.** Every `experimental_tg_K` in
`polymer_rules.json` is the atactic/commercial value. Isotactic PMMA's is 319 K, not PACR's 378 K
— graded against the class default, a correct i-PMMA run would score as a ~60 K failure. Every
pinned value here comes from `db/experimental_db.sqlite`, never from a class median: iPMMA 319 K
(the DB's own `form='isotactic'` rows, 311–325 K), sPVC 371 K (PolymerHandbook4ed's syndiotactic
note plus a DSC row), amorphous PLLA density 1.248 (Garlotta2001 citing Mikos 1994), PSU density
1.235 (Mark 2007 Table 7.2 glass equation evaluated at the run's own 300 K). Three of the seven
classes — PEST, PVNL, PSFO — curate no `experimental_density_gcm3` at all, so without these pins
density would have had no comparator.

## Cost

186.9 GPU-h priced across the 21 runs. `select_hardware` never prices equilibration; the melt
chain's own step floors add ~113 GPU-h, so **~300 GPU-h is the floor**, before adaptive extends
or any recovery. At four concurrent runs that is ~3 days minimum. PEEK and PSU carry the
wall-time risk (`T_equil` 770 K and 700 K).

## Before launching

1. **Disk.** `/` is at 96%, 37 GB free. Equilibration dumps run ~3.3 GB per attempt; the seven
   pilots alone need ~23 GB before a single retry, all 21 need 70+ GB. ENOSPC kills the
   orchestrator's chains *and* Bash stdout. Free space first.
2. **Pilot before the seeds.** Run replicate 1 of all seven, gate each, and only then launch
   replicates 2 and 3. Two systems have open protocol questions: PS shows `MELT_STAGE_DEFICIT`
   on all four round-1 replicates (slower re-cooling provably cannot fix it), and PEEK carries an
   `eq_annealing_cycles` 8→12 change that no completed run has validated.
3. **Execute with `resume`, never `start`.** `agent_api.py resume <RUN>` calls
   `run_campaign_workflow` directly and does not re-materialize — no re-solve of system size, no
   re-probe of D-01, no re-read of the class table. Re-materializing per replicate is exactly the
   drift vector round 1 suffered from.
4. **All 21 plans already exist, deliberately.** `make_deterministic_plan`'s `_try_cache` replays
   `guides/system_characterization_cache.json` keyed by isomeric canonical SMILES; once a
   replicate completes, that cache is populated and a later `run-plan` for the same SMILES would
   replay it instead of planning. Generating every plan before any execution avoids that.
5. **Seeds are pinned before first execution, on purpose.** `workflow_state.json`'s `plan_hash`
   is written on the first real run; a seed edit after that invalidates stage state.

## Launching

`run_campaign` claims and releases GPUs itself (`gpu_claim(run_name, gpu_per_run)`, released on
exit even on exception), so do NOT pre-claim with `hardware_runtime.py` -- just check nothing else
holds the box:

    mcp-servers/.venv/bin/python orchestration/scripts/hardware_runtime.py --json status

Six of the seven systems are PPPM and `hardware_policy.concurrency_rule` allows one PPPM run per
GPU, so **4 concurrent runs** on this box, one GPU each.

Launch one run (multi-hour; `$!` is the launcher under `setsid nohup`, so capture a pidfile):

    RUN=iPMMA_1
    mkdir -p data/$RUN/raw
    setsid nohup mcp-servers/.venv/bin/python orchestration/scripts/agent_api.py resume $RUN \
      > data/$RUN/raw/launch_$(date +%Y%m%d_%H%M%S).log 2>&1 &
    echo $! > data/$RUN/raw/launcher.pid

Watch it:

    mcp-servers/.venv/bin/python orchestration/scripts/agent_api.py inspect $RUN

**Use `mcp-servers/.venv/bin/python`, never bare `python3`.** `run_campaign_workflow` imports the
LAMMPS engine server module, which needs `mcp` -- system python dies instantly with
`ModuleNotFoundError: No module named 'mcp'` before claiming a GPU or writing any state. Note
`hardware_runtime.py` wants `--json` BEFORE the subcommand.

`resume` is deliberate: it calls `run_campaign_workflow` directly and does NOT re-materialize --
no re-solve of system size, no re-probe of D-01, no re-read of the class table. `start` would
re-derive per replicate, which is the drift this campaign exists to eliminate.

### Order

1. Free disk (below). 37 GB free is not enough for even the pilot.
2. Pilot: replicate 1 of all seven, 4 at a time.
3. Gate each pilot through `enforce_gate.py` before expanding. PS and PEEK carry open protocol
   questions and are the two most likely to need re-planning.
4. Only then launch replicates 2 and 3. Their plans already exist and do not change at this step.
5. After each run, assert the executed seeds match the pinned ones -- `emc_seed` in
   `attempts/build/<id>/executor_state.json`, `velocity_seed` in the equilibration attempt. Round 1
   never closed this loop.

### Disk

`/` is at 96%, 37 GB free; equilibration dumps run ~3.3 GB per attempt. The pilot needs ~23 GB
before a single retry, the full matrix 70+ GB. ENOSPC kills the orchestrator's chains *and* Bash
stdout, so this is a hard precondition, not a warning. Candidates for a retention pass live under
older `data/<run>/` trees; delete nothing without checking what it is first.

## Known limitations, carried into the grading

- sPVC's density comparator (1.391 g/cm³) is a commercial value whose own source note discloses
  11.3% crystallinity. It is an **upper bound** for a fully amorphous cell and the weakest target
  in the set. sPVC is primarily a capability member: fully syndiotactic PVC is crystalline
  experimentally, and the prior i-PVC1 run found iso-vs-atactic density and modulus consistent
  with no effect.
- PEST's `exp_K_GPa` band carries an explicit unverified-provenance warning; PLLA's bulk modulus
  is graded against it as indicative, not binding.
- PE, PEEK and PSU are semicrystalline or crystallisable in practice. All three are graded
  against amorphous-phase comparators, disclosed rather than hidden.
- PSU enters with a known PCFF bias from round 1 (density −4%, Tg +8%).
- **The built stereochemistry is not measured.** `run_campaign.py:390` says so outright, and
  `rdkit_cli.py` has no stereo subcommand. Until a dyad m/r-fraction tool exists, the stereo claim
  rests on the SMILES and on the i-PVC1 parity anchor, not on the built cell. This matters because
  EMC's chirality parity inverts if `*` sits inside the stereocentre's branch — which is why the
  literal SMILES strings here must never be replaced by an RDKit-canonical form.
