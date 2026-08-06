---
name: emc-binary-annual-expiry
description: EMC binaries expire ~1 yr after build date — every EMC job fails "Validity has run out" (exit 255); fix = swap bin/ only from a fresh SourceForge tarball, never the field/ tree
metadata:
  type: feedback
---

The EMC binary at `~/emc/bin/emc_linux_x86_64` is time-limited. Once past its validity
window, **every** `submit_emc_cell_job` fails instantly (exit 255, ~0.15 s) with:

```
Error: main:
       Validity has run out; please download a fresh version.
```

This is class/SMILES independent — do NOT diagnose it as a SMILES, `*`-placement, or
force-field problem, and do not retry with a smaller `dp`.

**Why:** upstream ships dated rebuilds of the same version (v9.4.4_20230801,
_20240801, _20250801, _20260701 ...). Hit on 2026-08-05 with the _20250801 build
installed (`data/PVDF1`, PHAL/PVDF).

**How to apply:**
1. Fetch the newest `emc_linux_x86_64_v9.4.4_<date>.tgz` from the SourceForge
   `montecarlo` project (`https://sourceforge.net/projects/montecarlo/files/`).
2. Replace **only** `v9.4.4/bin/emc_linux_x86_64` at the installed path
   (`smiles_to_emc.py` resolves `EMC_ROOT`/`EMC_BIN` at module scope, so an
   `EMC_ROOT` env override needs an MCP server restart; overwriting in place does not).
   Back the old binary up first.
3. **Never overwrite `~/emc/field/`, `~/emc/scripts/`, `~/emc/templates/`.** The field
   tree is the scientific surface every prior campaign run used, and the installed
   `field/opls/2024/opls-aa.{prm,top,define}` carry a **local PolyJarvis patch**
   (si4/o2h siloxane types for PSIL; `.bak` siblings hold the stock files). The
   upstream 2026 tarball ships `#EMC/FIELD/OPLS/2026` with real parameter changes
   (e.g. added `c3a5f` furan aromatic C) — pulling it in would silently break
   comparability and drop the PSIL patch.
4. Note the new binary build date in the run report — it differs from every prior run.

**STATUS 2026-08-05: fixed.** The orchestrator installed `v9.4.4` build `Jul 21 2026`
at `~/emc/bin/emc_linux_x86_64` (the params header prints the build date — the run
prompt called it "build 20260701", the binary self-reports Jul 21 2026; trust the
header). `data/PVDF1` PHAL/PVDF then built cleanly in 45 s (3620 atoms). The
`field/` tree was NOT replaced, so the local PSIL si4/o2h patch survives and no
field-version/parse error occurred against the newer binary. Do not re-diagnose an
expiry unless you actually see the "Validity has run out" string again — and if you
do, report it rather than downloading anything.

**Agent-level constraint:** in the sandbox both *executing* a freshly downloaded
binary and *writing* to `~/emc/bin/` are denied by the permission classifier.
Downloading, extracting, and diffing are allowed. So the builder can diagnose and
stage the fix but cannot apply it — emit the failure RESULT block with the exact
tarball URL and cp commands and let the human/orchestrator apply it. Do not reach for
`dangerouslyDisableSandbox`.
