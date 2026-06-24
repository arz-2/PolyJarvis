# docs/

Reference and design documentation for PolyJarvis. (Operational, per-stage
workflow guides live in [`../guides/`](../guides/); this directory is the
higher-level reference material.)

| File | What it is |
|------|------------|
| [`PROPERTIES.md`](PROPERTIES.md) | The three reported properties (density, Tg, bulk modulus) — source logs, extraction tools, methods, and validation bands. The authoritative description of what the pipeline computes. |
| [`ROADMAP.md`](ROADMAP.md) | Feature roadmap — validation tracks, force-field work, additional properties, and the planner/critic architecture, with done/pending/blocked status. |
| [`specs/B4_runlog_miner_spec.md`](specs/B4_runlog_miner_spec.md) | Design spec for the `runlog_miner` learning loop (`../tools/runlog_miner/`): mine the `run_log.md` corpus → suggested rule deltas + recovery playbook + confidence calibration. |
