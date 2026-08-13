---
name: pktn-routing
description: PKTN (PEEK/PEK) routes to EMC/PCFF, charge none, pppm; classifier co-occurs POXI+PPNL and reports ff_confidence low; EMC data file carries no Pair Coeffs section
metadata:
  type: project
---

PKTN (class_id 19, Polyketone/PEEK) → EMC builder, PCFF field, `charge_method: none`,
`electrostatics: pppm`, `lammps_flags {"use_pcff": true, "use_opls": false}`.

**Why:** `classify_polymer` on PEEK (`*Oc1ccc(Oc2ccc(C(=O)c3ccc(cc3)*)cc2)cc1`) returns
PKTN with `co_occurring_groups = [POXI, PPNL]` (ether linkages + conjugated aryl) and
`ff_confidence: "low"` — no class-specific PCFF validation paper; the cited support is
COMPASS II on PEEK (10.3390/polym12051054). Orchestrator prompts have passed
`ff_confidence: cited`, which disagrees with the classifier's `low`.

**How to apply:** Build with PKTN/EMC/PCFF as planned; surface the POXI+PPNL co-occurrence
and the `cited` vs `low` confidence divergence to the orchestrator for run_log D-01 rather
than changing the route. EMC's `cell.data` for this class has Masses/Atoms/Bonds/Angles/
Dihedrals/Impropers but **no Pair/Bond Coeffs sections** — coefficients live in
`emc_build.params`, so a missing "Pair Coeffs # <style>" comment is not a build failure and
FF auto-detect downstream must read the params file. See [[pest_routing]] and
[[feedback_output_contract_footguns]].

**Chain-count sizing:** PEEK at dp=32 / nchain=8 (density_initial 0.66) builds a 57.1 A box
that equilibrates to L=46.71 A and fails the finite_size gate with SIZE_CHAIN_SELF_IMAGE
(2*Rg = 56.83 A). nchain=17 at the same dp/density gives 18,530 atoms and a 73.35 A build box
(~1.8x volume). Treat nchain>=17 as the floor for dp=32 PKTN unless the orchestrator
specifies otherwise.
