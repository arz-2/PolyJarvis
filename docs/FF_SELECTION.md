# Force-field selection: measured coverage and what the domain check is worth

Findings from wiring COMPASS and pcff_ore and backtesting the domain check. Both results
contradict assumptions in the plan that produced them, so they are recorded here before anything
is built on top.

## The problem being addressed

Density against **authoritative amorphous** comparators from `guides/polymer_rules.json`:

| field | families | mean error | spread |
|---|---|---|---|
| TraPPE-UA | PE +0.5%, cis-PBD −0.2% | +0.2% | 0.7 pp |
| **PCFF** | PEEK −5.3%, PEG −5.5%, PMMA −6.2%, PS −6.5% | **−5.9%** | 1.1 pp |

16 of 21 classes route to PCFF. Replicate noise is 0.28 pp, so the deficit is ~20σ.

## Measured field coverage — the full matrix

Real builds, each family's actual SMILES. EMC fields via `smiles_to_emc.py --field` (dp=4,
nchains=2); GAFF via RadonPy `ff_assign`. `—` = not attempted (class not routed there).

| family | pcff | pcff_ore | compass | opls-aa '24 | opls-aa '12 | opls-ua | trappe-ua | trappe-eh | **GAFF2** |
|---|---|---|---|---|---|---|---|---|---|
| PE | OK | OK | OK | OK | OK | fail | OK | OK | **OK** |
| PEEK | OK | fail | fail | fail | fail | fail | — | fail | **OK** |
| PEG | OK | OK | OK | fail | fail | fail | — | fail | **OK** |
| PLA | OK | OK | fail | fail | fail | fail | — | fail | **OK** |
| PMMA | OK | OK | fail | OK | OK | fail | — | OK | **OK** |
| PS | OK | OK | OK | OK | fail | fail | — | OK | **OK** |
| PSU | OK | fail | fail | fail | fail | fail | — | fail | **OK** |
| PVC | OK | OK | fail | fail | OK | fail | — | fail | **OK** |
| cis-PBD | OK | OK | fail | fail | fail | fail | OK | OK | **OK** |

GAFF and GAFF2_mod match GAFF2 exactly — all three type all nine. **DREIDING also types all nine**,
but it is a coverage result, not a candidate: DREIDING is a generic hybridization-based field, and
RadonPy's implementation sets `pair_style: lj` — an LJ approximation to what is properly an exp-6
field, with no H-bond term (LAMMPS has `hbond/dreiding/*` available; RadonPy does not use it). Use
it to widen a cross-field spread, never as an accuracy candidate.

**Two fields achieve universal coverage with a defensible parameterization: PCFF and GAFF2.** That
is why 16 classes route to PCFF — it is a constraint, not a preference. GAFF2 is the only
alternative that reaches every family, and it is the only option at all for **PEEK and PSU**.
Caveat carried from the capability probe: on PEEK, GAFF2 is proven only to the *typing* step, while
PCFF is the only field proven to a runnable cell.

Alternatives available per deficit family:

| family | alternatives to PCFF |
|---|---|
| PEEK | GAFF2 only |
| PEG | compass, pcff_ore, GAFF2 |
| PMMA | opls-aa (2024 and 2012), trappe-eh, GAFF2 |
| PS | compass, opls-aa 2024, trappe-eh, GAFF2 |

So a cross-field density comparison (Leg 2) is feasible for **all four** deficit families, which
the plan assumed it was not.

### What GAFF2 costs, and what it is

Honest caveats before treating it as the answer:

- It is a **general small-molecule force field** (drug-like organics, solvation), not one
  parameterized for polymer condensed-phase thermomechanics the way COMPASS or PCFF were. RadonPy
  uses GAFF2_mod for exactly this purpose, so there is precedent, but its polymer density
  performance here is untested.
- It runs through the **RadonPy builder**, not EMC — a different pipeline branch. PURA already
  uses it (`GAFF2_mod`), so the plumbing exists and works.
- **It needs a QM charge step** (`submit_assign_charges_job`, RESP/AM1-BCC) per new chemistry.
  PCFF's bond-increment charges are free by comparison. This is the real per-run cost.
- `gaff2_mod` is itself a reparameterization of GAFF2 (adds `c3f`), so "GAFF2_mod" is not stock
  GAFF2 — the same labelling caution that applies to a rescaled PCFF applies here.

COMPASS fails with `Error: core/script/field/entry.c:651 ScriptFieldEntryApply: Missing force
field parameters` — the published/LAMMPS subset, 96 typing templates against pcff's 422.

**This corrects the plan's premise.** COMPASS was expected to cover "exactly the four families
where the deficit was measured". It covers **two of them** (PEG, PS) — PMMA and PEEK fail. And
pcff_ore, expected to be a near-free drop-in, **fails on PEEK and PSU**, the aromatic
ether-ketone and sulfone chemistries.

So:
- COMPASS reaches 3 of 9 families and cannot address the majority of PCFF classes.
- pcff_ore reaches 7 of 9 but not the aromatic ether/sulfone ones.
- The COMPASS density test is still worth running, on **PEG and PS**, both of which have verified
  comparators (1.12, 1.05) and a measured PCFF deficit (−5.5%, −6.5%). Two families is weaker
  evidence than four, but if COMPASS lands near 0% where PCFF is −6%, that is direct evidence the
  deficit is PCFF parameterization rather than protocol.
- The only field that covers PCFF's whole range is **GAFF2**, via the RadonPy builder — see below.

## The domain check measures provenance, not accuracy

`orchestration/scripts/ff_domain.py` derives each field's validated type vocabulary from completed
runs and reports whether a new polymer's types fall inside it. PCFF's vocabulary is 15 types across
7 families; TraPPE-UA's is 3 across 2.

Backtested leave-one-family-out — would this family have been trusted if it were novel?

| family | extrapolated atom fraction | density error | K error |
|---|---|---|---|
| PE, PEG, PMMA, PS | 0% | +0.5, −5.5, −6.2, −6.5% | −14, +13, +23, −27% |
| PLA | 0.2% | no comparator | **+33.2%** |
| PEEK | 2.9% | −5.3% | +4.4% |
| PSU | 5.6% | no comparator | −10.1% |
| PVC | 16.6% | no comparator | −28.4% |
| cis-PBD | 49.8% | **−0.2%** | +9.3% |

**Extrapolation does not predict error, and the sign is backwards:**

- corr(extrapolated fraction, |K error|) = **−0.26**
- corr(extrapolated fraction, |density error|) = **−0.64** (n=6)

PLA extrapolates on 0.2% of its atoms and has the archive's worst K error; cis-PBD extrapolates on
49.8% and has among its best densities. The negative correlation is partly an artifact of the
leave-one-out construction — TraPPE-UA's small vocabulary makes its two accurate families look
maximally extrapolating — but either way the check has no demonstrated predictive power here.

**Consequence for the plan:** Leg 1 was specified to *gate* the other legs and "discard any field
that is extrapolating on this chemistry". On this evidence that would have discarded TraPPE-UA for
cis-PBD — the most accurate density in the archive. The check is retained as a **provenance
annotation only**, it returns `is_accuracy_prediction: false`, and `tests/test_ff_domain.py` locks
that so it cannot be re-sold as a gate.

This is the `feedback_gates_validity_not_accuracy` rule applied: the domain check is an
admissibility/provenance signal, and accuracy correlation is only valid evidence for agreement
gates. A provenance statement that does not predict error is still true and still worth reporting —
it just must not decide anything.

## What now carries the decision

With Leg 1 demoted and no installed field fixing PCFF generally, the weight falls on:

1. **Reference-free comparators** (Leg 3) — group-contribution density and the solubility
   parameter, the only absolute checks available for a polymer with no experimental value. These
   must first be calibrated against the families where experimental values *do* exist; if they
   cannot reproduce the known cases they cannot arbitrate unknown ones.
2. **Cross-field spread** (Leg 2) — for a novel polymer the field choice is the dominant unrecorded
   choice, and the spread across applicable fields is the honest uncertainty. Note the coverage
   table limits which polymers even *have* two applicable fields.
3. **σ rescaling** — now more likely to be needed than the plan assumed, since no standard
   installed field covers PCFF's 16 classes. Still the least attractive option: a rescaled PCFF is
   no longer PCFF.

## Can an EMC update add families? No — the limit is licensing, not version

Installed: **EMC v9.4.4, binary built Jul 21 2026, license valid to Jun 30 2027**. It was updated
on 2026-08-05 (`emc_linux_x86_64.20250801.bak` is the previous Jul 2025 build), so it is current.

EMC updates *do* add field coverage — 57 HISTORY entries mention adding fields, parameters or
typing rules. But that cannot fix COMPASS: **EMC ships the published COMPASS subset**, and full
COMPASS is commercial (BIOVIA), not redistributable. No future EMC release will include it. The
realistic gain from updates is incremental pcff/opls/trappe template additions.

### Only four field families in this install can type a SMILES at all

EMC needs rule-based typing to build from SMILES. Checked:

| field | typing rules | builds `*CC*`? |
|---|---|---|
| pcff | `pcff_templates.dat` (422) | yes |
| pcff_ore | `pcff_ore_templates.dat` | yes |
| compass | `compass_templates.dat` (96) | yes |
| opls-aa / opls-ua | `.define` | yes (routed for PHAL, PSIL) |
| trappe-ua / trappe-eh | `.define` | yes |
| **charmm/c36a (CGenFF)** | none — only `.prm`/`.top` | **no** |
| **charmm/iff, cff, uff** | none | **no** |

CGenFF is by far the broadest file present (270 KB) but CHARMM types by **residue templates**, not
SMILES rules, so it cannot build an arbitrary novel polymer here — it failed on plain polyethylene,
as did IFF, CFF and UFF. The pipeline's reachable universe is therefore pcff, pcff_ore, compass,
opls, trappe, plus RadonPy's GAFF2/DREIDING via the other builder.

## Enabling COMPASS for more families: what it would actually take

The PMMA failure is **not** a typing failure — EMC typed the molecule fine and then could not find
torsion coefficients:

```
Warning: no torsion coefficients found for [c4:c43:c3':o1=*]
Warning: no torsion coefficients found for [c4:c44:c3':o2s]
Error: ScriptFieldEntryApply: Missing force field parameters.
```

After the `#equivalence` table substitutes (`c43,c44 → c4`; `o2s → o2`; `o1=* → o1=`), the two rows
needed are `c4 c4 c3' o1=` and `c4 c4 c3' o2`. Neither exists. What COMPASS *does* have is
revealing:

- `o1= c3' c4 h1` and `o2 c3' c4 h1` — the same torsions with an **H** on that carbon, both zero
- `c4 o2 c3' c4` = −2.5594 / 2.2013 / 0.0325 — the ether-side torsion, distinctly non-zero

So published COMPASS covers **simple esters** (ester carbon on a CH-bearing carbon) but not
**methacrylates**, where that carbon is quaternary. That is exactly PMMA's backbone.

Three ways to add them, none good:

1. **Set them to zero.** Physically wrong — ester rotation governs local packing and Tg, the very
   properties being measured — and the non-zero neighbour above shows they are not generically zero.
   This would silently degrade the measurement it is meant to improve.
2. **Take published COMPASS values** (Sun 1998, JPCB 102:7338, plus acrylate extensions). Legitimate,
   but needs literature retrieval and methacrylate torsions may simply never have been published in
   the open subset.
3. **Borrow from PCFF.** The nomenclatures are **disjoint** — PCFF uses `c, c1, c_1, o_1, o_2, cp,
   hc`; COMPASS uses `c4, c43, c44, c3', o1=, o2s` — so this is a hand type-mapping exercise, not a
   text copy. The result is a PCFF/COMPASS hybrid, which forfeits the "standard citable field"
   advantage that was the whole reason to prefer COMPASS.

And this repeats per chemistry: COMPASS has **49 atom types against PCFF's 138**, so most of the
pipeline's 21 classes would need their own parameter work.

**Recommendation: do not extend COMPASS.** Run it where it already works (PE, PEG, PS) purely for
the diagnostic value — whether the −5.9% PCFF deficit is parameterization or protocol. As a routing
option it is dead for 6 of 9 families and cannot be revived by an update. **GAFF2 is the field to
test for breadth**, since it is the only one besides PCFF that covers every family.

## Integration is not the constraint — typing is

Checked against the LAMMPS force-fields howto (`Howto.html#force-fields-howto` → `Howto_bioFF.html`)
and against the installed binary's own style list, not against documentation alone.

LAMMPS documents six organic force fields. **Five of the six run in the installed KOKKOS binary
today** — CHARMM, AMBER, COMPASS, DREIDING, OPLS — with every required `pair`/`bond`/`angle`/
`dihedral`/`improper` style present. Only ClassII-xe is missing (`angle_style class2xe` and
`dihedral_style class2xe` are absent from this LAMMPS 22 Jul 2025 CLASS2 package). Installed
packages: `CLASS2 EXTRA-COMPUTE EXTRA-DUMP EXTRA-MOLECULE EXTRA-PAIR KOKKOS KSPACE MANYBODY
MOLECULE REAXFF RIGID`.

So **no force field on the list needs installing to be runnable.** All twelve fields in the
registry integrate. The binding constraint is entirely the front end: something has to type the
SMILES and emit parameters. CHARMM/CGenFF is the clean illustration — fully runnable in LAMMPS,
and EMC cannot type a single monomer against it, because CHARMM assigns types from residue
templates where EMC needs rules. That is a typer problem, not a LAMMPS problem, and the only fix
is an external typer (the CGenFF program / ParamChem), which carries registration and licensing.

### GPU cost differs by field, and it is not free

A style with no `/kk` variant runs host-side under KOKKOS and forces a host↔device copy every
timestep. What matters is the styles a field's **EMC-generated cell actually emits**, not the styles
the field could in principle use — those differ, and reading the field definition instead of the
build is what produced the earlier wrong entry for OPLS-AA. Measured against the binary:

| field | integrates | fully KOKKOS | host-side styles |
|---|---|---|---|
| pcff, pcff_ore, compass | yes | **yes** | — |
| charmm/c36a | yes | **yes** | — |
| trappe-ua, trappe-eh | yes | **yes** | — |
| opls-aa 2024, opls-aa 2012 | yes | **yes** | — |
| dreiding | yes | no | `improper_style umbrella` |
| gaff, gaff2, gaff2_mod | yes | no | `dihedral_style fourier`, `improper_style cvff` |

OPLS-AA carries no GPU penalty: EMC emits `dihedral_style multi/harmonic`, which has a `/kk`
variant, and **no impropers at all** — `opls-aa.prm`'s `ITEM IMPROPER` section holds three entries,
all on `c3=` alkene centers, so the field defines none for ester carbonyls or aromatics. A PMMA or
PS cell therefore has no improper term to run host-side. Its pair style is also `9.5 9.5`, the same
as PCFF's, so an OPLS-AA arm is cutoff-matched to a PCFF anchor by construction.

GAFF2 — the only universal alternative — remains the least accelerated, and that cost belongs in
the decision. Measure it on one short run before planning a sweep.

### MLIPs are a rebuild, not a download

`ML-PACE ML-SNAP ML-POD ML-UF3 ML-HDNNP ML-IAP ML-QUIP` are all present in the source tree
(`/home/arz2/lammps/src`), unbuilt. This corrects the earlier "no ML packages" framing: the LAMMPS
side is a recompile. It does not change the conclusion, because none of these ships a pretrained
polymer potential — they are potentials you *fit*, so the real cost is generating DFT training
data, on top of the Turing-class throughput problem already measured.

## What the literature says — and where it contradicts us

From `docs/ff_selection_literature.json` (12 DOI-verified sources). The valuable findings are the
contradictions, and there are three that bear directly on this plan:

1. **COMPASS has the wrong sign.** In the only located same-polymer multi-field benchmark that
   included COMPASS (PDMS, `10.1021/acs.jpcb.4c08471`), COMPASS was the **worst** of five fields
   (density RMSE 0.178 g/cm³) and **over**-predicted density. The premise for testing COMPASS was
   that a condensed-phase-optimized Class II field should fix an under-density. One polymer is not
   a refutation, but it removes the mechanism that made COMPASS the leading candidate.
2. **GAFF2 is not a clean fallback.** Its only large-scale amorphous-bulk validation (RadonPy,
   `10.1038/s41524-022-00906-4`, >1000 polymers) **admits its own systematic density bias** and
   applies an ML correction on top. Swapping a biased field for a differently-biased one is not an
   improvement, and no located source validates GAFF2 on aromatic backbones (PEEK, polysulfone) at
   all — for or against. That is precisely where it is our only option.
3. **Our PMMA deficit is 3× the literature's.** A PMMA/PIB review reports Class II fields
   reproducing amorphous density within 2%; we measure −6.2%. The literature agent's reading is
   that our deficit may be **protocol-specific rather than inherent to PCFF**.

Also recorded: no source corroborates the −5.9% class-wide magnitude, PCFF is comparatively
**under**-benchmarked in the open literature relative to COMPASS and OPLS-AA
(`10.1021/acs.macromol.5c01166`), and the transferability-predicts-error question our domain check
backtested has simply never been tested quantitatively in the published field — so our negative
result is neither corroborated nor contradicted, and stays an internal-archive result.

### Reconciling contradiction 3 with our own data

The protocol reading is the one that would redirect this whole effort, so it deserves the
counter-evidence rather than deference:

- **TraPPE-UA runs share the entire protocol and show no deficit.** PE and cis-PBD go through the
  same builder, equilibration chain, gate and extraction code and land at **+0.2%**, against
  −5.9% for the PCFF families. A protocol that under-densifies would have to act only on the
  all-atom Class II runs.
- **LJ truncation is ruled out.** `pair_modify ... tail yes` is present in **636 of 637** archived
  run inputs, so a missing long-range LJ correction — the standard protocol cause of a systematic
  under-density — is not the mechanism. (The single exception,
  `manuscript/data/PSU1/lammps/mechanical/bm_series/bm_P0/bm_P0.in`, reads `pair_modify mix
  arithmetic` with no `tail yes`. Both are wrong under a Class II field, which needs `sixthpower`
  mixing — a real defect in one PSU1 bulk-modulus point, but far too narrow to explain a class-wide
  density effect.)
- **A single global scalar explains all four families.** One uniform 2.04% σ shrink fits PEEK, PEG,
  PMMA and PS with 0.20 pp scatter, LOO out-of-sample 5.87% → 0.65%. Per-atom-type parameter error
  would be chemistry-dependent; a single scalar working across four distinct chemistries points at
  something uniform.
- **Finite size does not track the deficit.** PE2 violates the finite-size gate (L/2Rg 0.96) and PE
  still lands at **+0.5%**. Under-sized cells are real in this archive, but they are not producing
  the under-density.

That third point cuts **both** ways and is the honest state of the question: a uniform effect is
equally consistent with a systematic protocol/state-point issue and with a uniform LJ-radius bias
in PCFF's Class II parameterization. Our data cannot yet separate them — but the shared-protocol
argument makes "it is purely our protocol" hard to sustain.

**The discriminator we would want does not exist in the archive.** Cleanly separating the two
readings needs an all-atom, non-Class-II family run under the same protocol with a verified density
comparator. TraPPE-UA is united-atom; PHAL and PSIL do run OPLS-AA but are not among the nine
families with experimental density values. That absence is why the free stratification below is the
*only* available test rather than merely the cheapest one — and why an OPLS-AA PMMA or PS density
run (experiment 2) doubles as the missing discriminator.

## Suggested order of experiments

Revised: the literature removed COMPASS's rationale and weakened GAFF2's, so the cheapest
discriminating test is no longer a force-field swap at all.

1. **Separate protocol from parameterization first — free, no new field.** Re-derive the four
   deficit densities against a size- and equilibration-quality-stratified split of the existing
   archive. If the deficit tracks cell size or equilibration quality it is protocol; if it is flat
   across both, it is the field. We already know several archived cells violate the finite-size
   gate (PEEK1 0.74, PSU4 0.78, PSU2 0.99, PE2 0.96), which makes this a live hypothesis and not a
   formality. **Do this before spending GPU time.**
2. **PMMA and PS under their alternatives** — the two deficit families with the most options
   (opls-aa, trappe-eh, GAFF2 for PMMA; compass, opls-aa, trappe-eh, GAFF2 for PS), both with
   verified comparators (1.19, 1.05) and large measured deficits (−6.2%, −6.5%). Still the cheapest
   *simulated* discriminator of PCFF-specific vs general.
3. **PEG and PS under COMPASS** — demoted. Now a check on the PDMS result rather than a candidate
   fix, and worth running mainly because COMPASS is free to build on these two.
4. **PEEK under GAFF2** — lowest priority despite the largest aromatic deficit, because GAFF2 has
   no located aromatic-polymer density validation and an admitted bias of its own. Treat any result
   as a spread contribution, not an answer.

A prior worth carrying into (2): `data/PMMA1/raw/run_plan.json` weighed an OPLS-AA↔PCFF swap and
recorded Tang2022 giving 481 K simulated vs 383 K experimental Tg for OPLS-AA PMMA — badly wrong on
Tg. Density is a different observable and the test is still worth running, but do not expect
OPLS-AA to be a general upgrade on the strength of a density result alone.

## Smart field selection for a novel polymer

The current mechanism is `_select_field(polymer_class)` — a static class→field map returning one
string, with no evidence recorded and no alternative considered. For a novel polymer that is the
largest unrecorded choice in the pipeline.

The replacement is **a ranked candidate set with recorded evidence**, not a different single
answer. Four stages, ordered by cost, and only the first is a gate:

**Stage 0 — Buildability. Hard gate, free, minutes.** `orchestration/scripts/ff_capability.py`:
does the installed LAMMPS have every style the field's functional form needs, and can a front end
actually type this SMILES? Both halves are *measured* — the typing half by running a real 4-mer
build, never by consulting a coverage table. This is the only hard gate in field selection, because
it is the only binary one. Output is a candidate set.

**Stage 1 — Archive prior, weighted by chemical similarity. Free.** Among candidates, rank by
measured signed error on the *nearest validated family*, where nearness is atom-type vocabulary
overlap. This is the honest job for `ff_domain.py`'s data: **not** the in/out-of-domain verdict it
currently returns — backtesting showed that does not predict error — but the continuous
similarity underneath it, which is the right basis for deciding how much of an archive prior
transfers. Reframing that verdict as a similarity metric is the one change this design asks of
existing code.

**Stage 2 — Literature prior. Free.** `docs/ff_selection_literature.json`, and the
literature-grounding worker for chemistry-specific evidence. Note its own verdict on this stage:
high-throughput pipelines in the published field **fix one force field per campaign** and none
implements automated per-polymer selection, so there is no established method to copy here.

**Stage 3 — Cross-field spread. Costs build + equilibration per field.** Run the top-k survivors
and **report the disagreement as the uncertainty**. This does not identify the correct field; it
quantifies how much the answer depends on a choice that cannot be justified — which is the honest
number to publish for a novel polymer. Density is the precise observable (0.28 pp replicate noise),
so this needs foundation only: no Tg sweep, no pressure ladder.

The **reference-free comparators** (group-contribution density, solubility parameter / CED) are
what can turn a spread into a *choice*. The literature supports CED as an established but underused
validation observable — which is the strongest available argument for finishing that calibration.

Two rules the design must keep:

- **Never gate on domain coverage.** It would have discarded TraPPE-UA for cis-PBD, the archive's
  most accurate density.
- **Never report a novel-polymer property with only a fit-precision error bar.** For a novel
  polymer the field spread dominates; omitting it repeats the error of quoting Tg to ±8.9 K against
  a 45 K method gap.

## Plumbing added

`mcp-servers/mcp-emc-server/server.py`: `_resolve_field()` plus a `field_override` parameter on
`submit_emc_cell_job`, validated against an allow-list (`compass`, `pcff_ore`, `trappe-eh`,
`opls/2012/opls-aa` and the three defaults). **Class defaults are unchanged** — the override is
documented for comparison runs only, preserving the server's existing rule that normal builds take
the class default. `_lammps_flags` routes `pcff_ore` and `compass` to the class2 deck, which is
correct: pcff_ore *is* pcff, and COMPASS shares the 9-6 / quartic-bond functional form.

**Untested trap, still open:** `mechanical/bm_series/bm_P*.in` carry no `include` — they `read_data`
the equil restart and use the `Pair Coeffs` baked into it. Any field comparison must verify the
bulk-modulus runs actually carry the intended field's coefficients.

`orchestration/scripts/ff_capability.py` (+ `tests/test_ff_capability.py`): the Stage-0 hard gate.
`--integration-only` reports style availability and the KOKKOS gap without building; with a SMILES
it also runs the front end for real per field.

Run on **PMMA** and **PEEK**, it reproduces the hand-built matrix exactly, and distinguishes the two
failure modes — `FieldsApply: Missing rules` (cannot type the monomer at all) from
`ScriptFieldEntryApply: Missing force field parameters` (types fine, no parameters for the resulting
torsion). PMMA: `pcff`, `opls/2024/opls-aa`, `gaff2`, `dreiding` pass; `compass` fails on
parameters, `charmm/c36a` on typing. PEEK: `pcff`, `gaff2`, `dreiding` pass; `pcff_ore` fails on
parameters; `compass`, `opls/2024/opls-aa`, `trappe-eh`, `charmm/c36a` all fail on typing.

**Evidence is not uniform across front ends, and the output now says so.** EMC fields are built to a
runnable cell (`typing_evidence: built_cell`). RadonPy fields are only *typed* — `ff_assign` proves
atom types and bonded parameters, not a runnable system, because GAFF2 still needs its
per-chemistry QM charge step (`typing_evidence: typed_only`, with `further_steps_required`). On
PEEK that distinction is the whole result: **`pcff` is the only field proven to a runnable cell**,
and GAFF2's status as "PEEK's only alternative" is established at the typing step only.

Fields present in `~/emc/field` or RadonPy but deliberately excluded are listed with reasons in the
module's `EXCLUDED` dict. `polystyrene` is the one worth naming here since PS is a deficit family:
it is a **coarse-grained inverse-Boltzmann tabulated potential** (kT vs metres, no atom types, no
`.frc`), not an atomistic PS parameterization, so it cannot serve as a candidate field.
