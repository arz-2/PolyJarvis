# Molecule Builder Memory Index

- [PEST routing](pest_routing.md) — PEST (PLA/PET/PCL)→EMC/PCFF, charge none, pppm; no co-occur/warning; use_pcff:true [ingested 2026-06-25]
- [PDIE routing + stereo trap](pdie_routing.md) — PDIE→EMC/TraPPE-UA (use_trappe:true); EMC ignores SMILES cis/trans → ~50:50 mixture; verify by torsion, not atom type
- [PKTN routing](pktn_routing.md) — PKTN (PEEK)→EMC/PCFF, charge none, pppm; co-occurs POXI+PPNL, ff_confidence low vs prompt's cited; coeffs live in emc_build.params
