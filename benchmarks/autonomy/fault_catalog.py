#!/usr/bin/env python3
"""
Fault catalog for the error-recovery benchmark (R1M1 / M11).

Six deliberately-injected faults. Four have a pre-scripted recovery (a row in
.claude/commands/recover.md, Tier 1); two are generalization probes with NO
scripted fix (inferred / Tier 3 — the AGENT's job at the full launch).

Each fault provides:
  - inject(tmp_path) -> Signal: perturb a real input where cheaply possible
    (validator/ValueError/arithmetic) without launching LAMMPS/EMC; otherwise a
    representative error string LAMMPS/EMC emits, so the classifier can be scored.
  - recover(tmp_path) -> bool | None: apply the recover.md fix and verify it no
    longer triggers (prescripted faults); None for inferred faults.

Signal.kind:
  "log"     -> error text fed to error_classifier.classify_error
  "metric"  -> a condition (e.g. <4 Tg bins) detected from an analysis result
  "reject"  -> a pre-flight validator/ValueError rejection (build never proceeds)
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"))
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-emc-server"))

CALIB_PCFF = REPO_ROOT / "data" / "CALIB_PCFF" / "emc_build.data"

# Minimal complete atom_style=full cell that passes validate_data_file(lj_cutoff=1.0).
# Mirrors the engine's own CLEAN_DATA fixture (tests/test_data_file_utils.py) so F6's
# corruption is provably the cause: the clean copy validates, the corrupted copy does not.
CLEAN_DATA = """\
# test polymer data file
4 atoms
0 bonds
2 atom types

0.0 4.0 xlo xhi
0.0 4.0 ylo yhi
0.0 4.0 zlo zhi

Masses

1 1.008 # hc
2 12.011 # c3

Pair Coeffs

1 0.0157 2.6495
2 0.1094 3.3996

Atoms

1 1 2 -0.12 1.0 1.0 1.0
2 1 1 0.06 2.0 1.0 1.0
3 1 1 0.06 1.0 2.0 1.0
4 1 2 0.00 2.0 2.0 1.0
"""


@dataclass
class Signal:
    kind: str           # "log" | "metric" | "reject"
    text: str           # error text (log) / condition description (metric/reject)
    triggered: bool     # did the injection actually fire?


@dataclass
class Fault:
    id: str
    description: str
    prescripted: bool
    expected_error_class: str       # what classify_error should return ("unknown" if inferred)
    recover_md_line: Optional[int]
    inject: Callable[[Path], Signal]
    recover: Callable[[Path], Optional[bool]]


# ---- F1: PPPM out of range (prescripted, recover.md:39) ------------------------
def _inject_pppm(tmp: Path) -> Signal:
    # Real surface: an npt_compress at very low density requesting PPPM. We assert the
    # script would request kspace/pppm at a sub-0.1 g/cm^3 cell (the trigger condition).
    from script_generator import ScriptGenerator
    gen = ScriptGenerator(str(CALIB_PCFF))
    out = tmp / "compress_pppm.in"
    gen.generate("npt_compress", str(out), params={"use_pppm": True, "P_TARGET": 50000.0})
    requested = "kspace_style pppm" in out.read_text().lower()  # active directive, not comments
    # The runtime failure this produces:
    log = "ERROR: Out of range atoms - cannot compute PPPM (src/KSPACE/pppm.cpp:1934)"
    return Signal("log", log, triggered=requested)


def _recover_pppm(tmp: Path) -> bool:
    from script_generator import ScriptGenerator
    gen = ScriptGenerator(str(CALIB_PCFF))
    out = tmp / "compress_fix.in"
    # recover.md:39 -> switch compress to short-range Coulomb (no PPPM).
    gen.generate("npt_compress", str(out), params={"use_pppm": False, "P_TARGET": 50000.0})
    txt = out.read_text().lower()
    return "kspace_style pppm" not in txt  # PPPM directive removed from the compress stage


# ---- F2: FF style mismatch (prescripted, recover.md:36) ------------------------
def _inject_ff_mismatch(tmp: Path) -> Signal:
    # Real surface: PCFF data file + a contradictory FF flag should be rejected.
    from script_generator import ScriptGenerator
    gen = ScriptGenerator(str(CALIB_PCFF))
    out = tmp / "mismatch.in"
    try:
        gen.generate("npt", str(out), params={"use_trappe": True, "use_pcff": False})
        # If it did not raise, the runtime failure would be a wrong style keyword:
        return Signal("log", "ERROR: Unknown pair_style lj/charmm", triggered=True)
    except (ValueError, RuntimeError) as e:
        # Feed the REAL exception text to the classifier (not a fabricated log) so the
        # prescripted/inferred boundary is scored against genuine tool output.
        return Signal("log", f"ERROR: {e}", triggered=True)


def _recover_ff_mismatch(tmp: Path) -> bool:
    from script_generator import ScriptGenerator
    gen = ScriptGenerator(str(CALIB_PCFF))
    out = tmp / "ff_fix.in"
    try:
        gen.generate("npt", str(out), params={"use_pcff": True})  # explicit correct flag
        return out.exists()
    except Exception:
        return False


# ---- F3: Tg fit too narrow (prescripted, recover.md:32) ------------------------
def _tg_bins(t_low, t_high, t_step):
    n = 0
    t = t_high
    while t > t_low + 1e-6:
        n += 1
        t -= t_step
    return n + 1


def _inject_tg_narrow(tmp: Path) -> Signal:
    n = _tg_bins(250, 350, 50)  # 3 bins -> below the 4-bin floor
    return Signal("metric", f"Tg sweep produced {n} temperature bins (<4)", triggered=n < 4)


def _recover_tg_narrow(tmp: Path) -> bool:
    # recover.md:32 -> widen range (T_start+50, T_end-50). Use a fuller grid.
    n = _tg_bins(150, 450, 25)
    return n >= 4


# ---- F4: EMC bad SMILES, wrong * count (prescripted, recover.md:35) -----------
def _inject_bad_smiles(tmp: Path) -> Signal:
    from smiles_to_emc import make_esh
    try:
        make_esh("*CC*C*", field="pcff")  # 3 stars
        return Signal("reject", "make_esh accepted 3-star SMILES (unexpected)", triggered=False)
    except ValueError as e:
        return Signal("reject", f"EMC build rejected SMILES: {e}", triggered=True)


def _recover_bad_smiles(tmp: Path) -> bool:
    from smiles_to_emc import make_esh
    try:
        esh = make_esh("*CC*", field="pcff")  # valid 2-star
        return bool(esh)
    except Exception:
        return False


# ---- F5: EMC unsupported increment, PURA (INFERRED — generalization probe) -----
def _inject_unsupported_increment(tmp: Path) -> Signal:
    # PURA polyurea: EMC pcff lacks the {n_2,hn} increment. No recover.md row fixes
    # this — it is the inferred case. Represented by EMC's field-error string.
    log = "EMC field error: increment 'n_2,hn' not found in pcff field (PURA urea N-H)"
    return Signal("log", log, triggered=True)


def _recover_unsupported_increment(tmp: Path):
    return None  # no scripted recovery — AGENT must reason a fix at the full launch


# ---- F6: data-file atom-count mismatch (INFERRED — generalization probe) -------
def _inject_data_corruption(tmp: Path) -> Signal:
    # Topology corruption: drop a Pair Coeffs entry so the force field is incomplete
    # (header declares 2 atom types, only 1 coeff present). The clean copy validates;
    # the corrupted copy must not — that delta proves the injection is the cause.
    from script_generator import ScriptGenerator
    gen = ScriptGenerator(str(CALIB_PCFF))
    clean_ok = gen.validate_data_file(content=CLEAN_DATA, lj_cutoff=1.0).get("valid")
    bad = CLEAN_DATA.replace("2 0.1094 3.3996\n", "", 1)
    res = gen.validate_data_file(content=bad, lj_cutoff=1.0)
    rejected = not res.get("valid", True)
    triggered = bool(clean_ok) and rejected  # corruption — not a pre-existing flaw
    detail = "; ".join(res.get("errors", [])) or "topology mismatch"
    return Signal("reject",
                  f"data-file validation failed (clean passes, corrupted rejected): {detail}",
                  triggered=triggered)


def _recover_data_corruption(tmp: Path):
    return None  # not a recover.md row — inferred


CATALOG = [
    Fault("F1_pppm_out_of_range", "PPPM out of range in npt_compress", True,
          "pppm_out_of_range", 39, _inject_pppm, _recover_pppm),
    Fault("F2_ff_style_mismatch", "Missing/contradictory FF flag", True,
          "ff_style_mismatch", 36, _inject_ff_mismatch, _recover_ff_mismatch),
    Fault("F3_tg_fit_too_narrow", "Tg sweep <4 temperature bins", True,
          "tg_fit_too_narrow", 32, _inject_tg_narrow, _recover_tg_narrow),
    Fault("F4_emc_bad_smiles", "EMC build, wrong * count", True,
          "missing_ff_parameters", 35, _inject_bad_smiles, _recover_bad_smiles),
    Fault("F5_emc_unsupported_increment", "EMC unsupported increment (PURA)", False,
          "unknown", None, _inject_unsupported_increment, _recover_unsupported_increment),
    Fault("F6_data_file_corruption", "Data-file topology mismatch (incomplete force field)", False,
          "unknown", None, _inject_data_corruption, _recover_data_corruption),
]
