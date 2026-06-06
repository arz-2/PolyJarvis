---
name: equilibration-check-quirks
description: Two recurring benign patterns in check_equilibration_comprehensive output for polyhydrocarbon (PE/PHYC) TraPPE-UA runs
metadata:
  type: project
ingested_at: 2026-06-05
---

`check_equilibration_comprehensive` produces two soft signals on PE/PHYC TraPPE-UA NPT production logs that look alarming but do not block PASS.

**1. Density gates labelled "N/A (NVT — fixed volume)" on a genuine NPT log.**
On PE4 (Stage 7, 07_npt_production) the D-05 markdown marked density drift and density block-SEM as "N/A (NVT — fixed volume)" even though the log is a real NPT run with a fluctuating Volume/Lx/Ly/Lz and a Density column. The tool still *computed* the density-drift (0.47%, p=0.096) and density-SEM (0.12%) numbers and they pass thresholds — only the label is wrong. Energy gates carry the verdict in that case.
**Why:** the tool's ensemble auto-detection appears to misclassify the production window as fixed-volume.
**How to apply:** trust the numeric density-drift/SEM values; do not treat the "N/A (NVT)" label as a failure or as evidence the run was NVT. Verify ensemble from the log header (presence of varying Lx/Ly/Lz/Volume) if it matters.

**2. C∞ "outside broad expected range [3,15]" warning is benign for PE with combined backbone types.**
PE4 with backbone_types=[1,2] (both backbone carbons, c4h2 + c4h3) and n_backbone_bonds=119 gave C∞=15.206, tripping the warning at the 15 boundary. This is a soft warning only; Rg CV (29.5%), MSID slope (1.178, R²=0.998), and P2 (0.023) all passed, confirming the chains are well-equilibrated Gaussian coils. The C∞ value just sits at the upper edge of the heuristic band.
**Why:** the [3,15] range is a broad heuristic; semicrystalline-tendency PE at high T legitimately lands near the top.
**How to apply:** for PE/PHYC, report the C∞ warning as INFO, not a defect, when the conformational gates (Rg CV, MSID, P2) pass.

Also note: PE production runs in this pipeline run hot (~550 K, above melt), so equilibrated density ~0.71 g/cm³ is correct for the melt — do not compare against the 300 K ~0.85 g/cm³ benchmark.
