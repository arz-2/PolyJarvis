# Planner Memory Index

- [PHYC cooling-rate API gap](phyc_cooling_rate_gap.md) — melt->300 K cool rate not expressible via decided_params; add_melt_npt only ~1.28x partial; pair with density-detection gate [ingested 2026-06-20]
- [Reasoned override on high-confidence class](reasoned_override_confidence.md) — corrected-protocol override flips plan_mode to reasoned, keeps class confidence=high; verify keys are threaded before encoding
- [Multi-member class exp Tg resolution](multimember_class_exp_tg_resolution.md) — make_deterministic_plan.py picks wrong experimental_tg_K for multi-member classes (PVNL etc); pin the specific member's Tg + density [ingested 2026-06-20]
- [PSFO DP floor resolution](psfo_dp_floor_resolution.md) — PSFO default dp_typical=15 violates DP>=20 Fox-Flory hard floor; use DP=20/nchain=8; justify K on glassy local-elastic physics not entanglement MW
- [PKTN rigid-backbone screening](pktn_rigid_backbone_screening.md) — PEEK melt C(t) never decays in MD; accept screening-grade equil on static+density, demote C(t)/MSD advisory; narrow Tg window not drop slow rate; amorphous density ref ~1.263 not 1.32 [ingested 2026-06-20]
- [PSTR reasoned plan](pstr_reasoned_plan.md) — PSTR confidence=medium->reasoned (has class temps, skip group-contrib); PS exp Tg=373 not 374, density 1.05, ~6.4k atoms/1 GPU; K screening-grade (DP40<Me160) via Born
- [PHYC high-DP static equil acceptance](phyc_highdp_static_equil_acceptance.md) — high-DP PE/PDIE melt C(t) never decorrelates (entanglement); accept on static chain stats, neutralize BOTH overall_pass+equil_verdict gates; gate C_inf vs temperature-matched finite-N ideal (~6.7) NOT asymptotic 8.2 [ingested 2026-06-20]
