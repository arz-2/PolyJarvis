#!/usr/bin/env python3
"""
REAL (runtime) executors for the error-recovery benchmark (--execute path).

Unlike fault_catalog.py's --smoke surfaces (which inject a representative string or a
pre-flight check), these functions launch the *actual* tool (LAMMPS / EMC / extract_thermal)
on tiny, runtime-generated cells and capture the GENUINE error the tool emits, then apply the
prescripted recovery and verify it re-runs past the failure. The real strings were captured
2026-06-27 — see REAL_FAULT_CAPTURE.md.

Design choices:
  - Portable: the base cells are generated at runtime via build_cell (no dependence on the
    git-excluded data/CALIB_PCFF); the lmp binary is taken from $LAMBDA_LAMMPS (the same
    source the engine uses), falling back to a $USER-derived path then PATH.
  - CPU-serial: tiny cells run in seconds on one core, so no GPU claim and zero contention
    with concurrent GPU work. (A real LAMMPS runtime crash is the same on CPU or GPU.)
  - Honesty: F5/F6 are inferred — execute_recover returns None (agent resolves at launch),
    exactly as in the smoke catalog.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Pin system OpenMPI before any engine import resolves OpenMPI paths.
os.environ.setdefault("OPENMPI_PREFIX", "/usr")
os.environ.setdefault("OPENMPI_BIN", "/usr/bin")
os.environ.setdefault("OPENMPI_LIB", "/usr/lib/x86_64-linux-gnu")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "manuscript" / "recovery"))
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-emc-server"))
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"))

_LAMBDA_USER = os.environ.get("LAMBDA_USER", os.environ.get("USER", "arz2"))
LMP = (os.environ.get("LAMBDA_LAMMPS")
       or f"/home/{_LAMBDA_USER}/lammps-install/bin/lmp")

EXTRACT_THERMAL = (REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"
                   / "analysis_scripts" / "extract_thermal.py")

# Validated trigger SMILES (REAL_FAULT_CAPTURE.md).
SMILES_BASE = "*CC(C)(C(=O)OC)*"     # PMMA — generic pcff cell
SMILES_3STAR = "*CC*C*"              # F4: wrong * count
SMILES_PURA = "*NC(=O)NCCCCCC*"      # F5: polyurea, pcff lacks {n_2,hn}


# ---------------------------------------------------------------------------
@dataclass
class RealContext:
    work_dir: Path
    gpu_id: Optional[int] = None        # None -> CPU serial
    timeout: int = 360
    _base: Optional[tuple] = field(default=None, repr=False)
    _sparse: Optional[tuple] = field(default=None, repr=False)

    def base_cell(self) -> tuple:
        """(data, params) for a small dense-ish pcff cell. Cached."""
        if self._base is None:
            self._base = _build_cell(self.work_dir / "base", "base",
                                     SMILES_BASE, density=0.5, dp=5, nchains=2)
        return self._base

    def sparse_cell(self) -> tuple:
        """(data, params) for a sparse low-rho cell — F1's PPPM trigger. Cached."""
        if self._sparse is None:
            self._sparse = _build_cell(self.work_dir / "sparse", "sparse",
                                       SMILES_BASE, density=0.05, dp=5, nchains=4)
        return self._sparse


def _build_cell(out_dir: Path, name: str, smiles: str, density: float,
                dp: int, nchains: int) -> tuple:
    from smiles_to_emc import build_cell
    out_dir.mkdir(parents=True, exist_ok=True)
    data = build_cell(smiles=smiles, output_dir=str(out_dir), output_name=name,
                      field="pcff", density=density, dp=dp, nchains=nchains, seed=1001)
    return str(data), str(Path(data).with_suffix(".params"))


def _run_lmp(deck: Path, ctx: RealContext) -> tuple:
    """Run a real LAMMPS deck; return (returncode, combined_log). CPU-serial by default."""
    env = dict(os.environ)
    if ctx.gpu_id is None:
        env["CUDA_VISIBLE_DEVICES"] = ""
        cmd = [LMP, "-in", str(deck)]
    else:
        env["CUDA_VISIBLE_DEVICES"] = str(ctx.gpu_id)
        cmd = [LMP, "-sf", "gpu", "-pk", "gpu", "1", "-in", str(deck)]
    try:
        p = subprocess.run(cmd, cwd=str(deck.parent), env=env,
                           capture_output=True, text=True, timeout=ctx.timeout)
        return p.returncode, (p.stdout or "") + "\n" + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        return 124, ((e.stdout or "") if isinstance(e.stdout, str) else "") + "\nTIMEOUT"


def _gen_nvt(data: str, params: str, out: Path, extra: dict) -> Path:
    """Generate a correct PCFF nvt deck (CPU) with sane defaults, then return its path."""
    from script_generator import ScriptGenerator
    gen = ScriptGenerator(str(data))
    p = {"use_pcff": True, "params_file": str(params), "use_pppm": True, "use_gpu": False,
         "T_START": 300.0, "T_FINAL": 300.0, "T_DAMP": 100.0, "TIMESTEP": 1.0, "N_STEPS": 50,
         "LOG_FILE": out.stem + ".log", "DUMP_FILE": out.stem + ".dump",
         "WRITE_DATA_FILE": str(out.parent / (out.stem + "_out.data"))}
    p.update(extra)
    gen.generate("nvt", str(out), params=p)
    return out


def _to_npt_compress(deck_text: str, P_atm: float, T: float, dt: float, steps: int) -> str:
    """Turn a generated nvt deck into an aggressive NPT compress (text surgery)."""
    return (deck_text
            .replace("fix nvt_fix all nvt temp 300.0 300.0 100.0",
                     f"fix npt_fix all npt temp {T} {T} 100.0 iso 1.0 {P_atm} 100.0")
            .replace("unfix nvt_fix", "unfix npt_fix")
            .replace("timestep 1.0", f"timestep {dt}")
            .replace("run 50", f"run {steps}"))


def _sweep_deck(data: str, params: str, out: Path, temps: list, steps_each: int) -> Path:
    """Write a real multi-temperature NPT sweep deck (one plateau per temperature)."""
    blocks = []
    for T in temps:
        blocks.append(f"velocity all scale {T}\n"
                      f"fix m all npt temp {T} {T} 100.0 iso 1.0 1.0 1000.0\n"
                      f"run {steps_each}\nunfix m")
    body = "\n".join(blocks)
    out.write_text(f"""log {out.stem}.log
units real
atom_style full
boundary p p p
pair_style lj/class2/coul/long 9.5 9.5
kspace_style pppm 1e-6
bond_style class2
angle_style class2
dihedral_style class2
improper_style class2
special_bonds lj/coul 0 0 1
pair_modify mix sixthpower tail yes
neighbor 2.0 bin
neigh_modify delay 0 every 1 check yes one 4000
read_data {data}
include {params}
thermo_style custom step time temp press enthalpy etotal ke pe ebond eangle edihed eimp evdwl ecoul elong etail vol lx ly lz density pxx pyy pzz
thermo_modify flush yes
thermo 50
timestep 1.0
velocity all create {temps[0]} 12345 mom yes rot yes
{body}
print "STAGE COMPLETE: sweep {len(temps)} pts"
""")
    return out


def _extract_thermal(log: Path, out_dir: Path) -> dict:
    """Run the real extract_thermal; return its parsed JSON (last JSON line of stdout)."""
    import json
    p = subprocess.run([sys.executable, str(EXTRACT_THERMAL),
                        "--log_file", str(log), "--output_dir", str(out_dir)],
                       capture_output=True, text=True, timeout=300)
    for line in reversed((p.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"status": "failed", "error": (p.stderr or "no JSON from extract_thermal")[-300:]}


# ---------------------------------------------------------------------------
# Per-fault REAL inject / recover. Each inject -> (error_text, triggered:bool).
# Each recover -> bool (prescripted, verified) or None (inferred — agent-left).
# ---------------------------------------------------------------------------

def f1_inject(ctx: RealContext):
    data, params = ctx.sparse_cell()
    deck = _gen_nvt(data, params, ctx.work_dir / "f1.in", {})
    deck.write_text(_to_npt_compress(deck.read_text(), 100000.0, 600.0, 4.0, 5000))
    rc, log = _run_lmp(deck, ctx)
    triggered = "out of range atoms" in log.lower() and "pppm" in log.lower()
    return _err_tail(log), triggered


def f1_recover(ctx: RealContext) -> bool:
    data, params = ctx.sparse_cell()
    deck = _gen_nvt(data, params, ctx.work_dir / "f1_fix.in", {})
    txt = _to_npt_compress(deck.read_text(), 100000.0, 600.0, 0.5, 5000)
    # recover.md:39 — drop PPPM, short-range Coulomb, larger skin.
    txt = (txt.replace("pair_style lj/class2/coul/long 9.5 9.5", "pair_style lj/cut/coul/cut 9.5")
              .replace("neighbor 2.0 bin", "neighbor 3.0 bin"))
    txt = "\n".join(l for l in txt.splitlines() if not l.startswith("kspace_style pppm"))
    deck.write_text(txt)
    rc, log = _run_lmp(deck, ctx)
    return rc == 0 and "out of range atoms" not in log.lower()


def f2_inject(ctx: RealContext):
    data, params = ctx.base_cell()
    deck = _gen_nvt(data, params, ctx.work_dir / "f2.in", {})
    # Wrong FF styles for a class2 cell (the wrong-FF-flag deck LAMMPS would render).
    txt = (deck.read_text()
           .replace("pair_style lj/class2/coul/long 9.5 9.5", "pair_style lj/cut/coul/long 9.5")
           .replace("bond_style class2", "bond_style harmonic"))
    deck.write_text(txt)
    rc, log = _run_lmp(deck, ctx)
    triggered = "incorrect args for" in log.lower() or "coeff" in log.lower() and rc != 0
    return _err_tail(log), bool(triggered)


def f2_recover(ctx: RealContext) -> bool:
    data, params = ctx.base_cell()
    deck = _gen_nvt(data, params, ctx.work_dir / "f2_fix.in", {"N_STEPS": 50})  # correct class2 styles
    rc, log = _run_lmp(deck, ctx)
    return rc == 0


def f3_inject(ctx: RealContext):
    data, params = ctx.base_cell()
    # A too-narrow / partial sweep: a single short setpoint -> extract_thermal can't fit.
    deck = _sweep_deck(data, params, ctx.work_dir / "f3_narrow.in", temps=[300.0], steps_each=150)
    _run_lmp(deck, ctx)
    res = _extract_thermal(ctx.work_dir / "f3_narrow.log", ctx.work_dir / "f3_out")
    status = res.get("status")
    nbins = res.get("n_temperature_bins")
    failed = status == "failed"
    invalid = bool(res.get("primary_fit_invalid")) or (res.get("fit_quality") == "POOR")
    text = (res.get("error") or
            f"extract_thermal: status={status} n_bins={nbins} fit_quality={res.get('fit_quality')} "
            f"primary_fit_invalid={res.get('primary_fit_invalid')} "
            "bilinear_curvefit failed — check temperature range and data quality")
    return text, bool(failed or invalid)


def f3_recover(ctx: RealContext) -> bool:
    data, params = ctx.base_cell()
    # recover.md:32 — widen the range / add points.
    deck = _sweep_deck(data, params, ctx.work_dir / "f3_wide.in",
                       temps=[450.0, 400.0, 350.0, 300.0, 250.0], steps_each=120)
    _run_lmp(deck, ctx)
    res = _extract_thermal(ctx.work_dir / "f3_wide.log", ctx.work_dir / "f3w_out")
    return res.get("status") == "success" and (res.get("n_temperature_bins") or 0) >= 4


def f4_inject(ctx: RealContext):
    from smiles_to_emc import build_cell
    try:
        build_cell(smiles=SMILES_3STAR, output_dir=str(ctx.work_dir / "f4"), output_name="bad",
                   field="pcff", density=0.5, dp=3, nchains=2, seed=1001)
        return "build_cell accepted a 3-star SMILES (unexpected)", False
    except Exception as e:
        return str(e), True


def f4_recover(ctx: RealContext) -> bool:
    from smiles_to_emc import build_cell
    try:
        d = build_cell(smiles="*CC*", output_dir=str(ctx.work_dir / "f4_fix"), output_name="good",
                       field="pcff", density=0.5, dp=3, nchains=2, seed=1001)
        return Path(d).exists()
    except Exception:
        return False


def f5_inject(ctx: RealContext):
    from smiles_to_emc import build_cell
    try:
        build_cell(smiles=SMILES_PURA, output_dir=str(ctx.work_dir / "f5"), output_name="pura",
                   field="pcff", density=0.5, dp=3, nchains=2, seed=1001)
        return "EMC built PURA with pcff (unexpected — increment now supported?)", False
    except Exception as e:
        s = str(e)
        triggered = "increment" in s.lower() and "not found" in s.lower()
        return _err_tail(s), triggered


def f6_inject(ctx: RealContext):
    data, params = ctx.base_cell()
    corrupt = ctx.work_dir / "f6_corrupt.data"
    lines = Path(data).read_text().splitlines()
    ai = next(i for i, l in enumerate(lines) if l.strip().startswith("Atoms"))
    j = ai + 2
    while j < len(lines) and lines[j].strip():
        j += 1
    del lines[j - 3:j]                    # drop 3 atom lines -> count < header
    corrupt.write_text("\n".join(lines) + "\n")
    deck = _gen_nvt(data, params, ctx.work_dir / "f6.in", {})
    deck.write_text(deck.read_text().replace(f"read_data {data}", f"read_data {corrupt}"))
    rc, log = _run_lmp(deck, ctx)
    triggered = "incorrect format" in log.lower() and "data file" in log.lower()
    return _err_tail(log), triggered


def _err_tail(text: str, n: int = 600) -> str:
    """Keep the most diagnostic lines (the actual error/abort cause), dropping low-value
    EMC import noise ('duplicate ... omitted') so the saved artifact shows the real cause."""
    keys = ("error", "increment", "not found", "incorrect", "aborted", "pppm",
            "bilinear", "missing force field", "cannot compute")
    noise = ("duplicate", "omitted")
    lines = [l for l in (text or "").splitlines()
             if any(k in l.lower() for k in keys) and not any(z in l.lower() for z in noise)]
    tail = "\n".join(lines[-8:]) if lines else (text or "")[-n:]
    return tail[-n:]


# fault_id -> (inject, recover|None). Recover=None => inferred (agent-left).
EXECUTORS = {
    "F1_pppm_out_of_range":          (f1_inject, f1_recover),
    "F2_ff_style_mismatch":          (f2_inject, f2_recover),
    "F3_tg_fit_too_narrow":          (f3_inject, f3_recover),
    "F4_emc_bad_smiles":             (f4_inject, f4_recover),
    "F5_emc_unsupported_increment":  (f5_inject, None),
    "F6_data_file_corruption":       (f6_inject, None),
}


def execute_one(fault, ctx: RealContext) -> dict:
    """Run one fault for REAL: trigger -> capture genuine error -> classify -> recover -> verify."""
    from error_classifier import classify_error
    inject, recover = EXECUTORS[fault.id]
    err_text, triggered = inject(ctx)
    cls = classify_error(err_text)
    classifier_ok = (cls["error_class"] == fault.expected_error_class
                     and cls["prescripted"] == fault.prescripted)
    if recover is None:
        resolved, note = False, "inferred — no scripted recovery (AGENT resolves at launch)"
    else:
        try:
            resolved = bool(recover(ctx))
        except Exception as e:
            resolved = False
            note = f"recovery raised: {e!r}"
        else:
            note = "recover.md fix applied and re-ran past the failure" if resolved else "recovery did not resolve"
    return {
        "id": fault.id,
        "description": fault.description,
        "mode": "execute",
        "real_error": err_text,
        "triggered": triggered,
        "expected_error_class": fault.expected_error_class,
        "classifier_error_class": cls["error_class"],
        "classifier_inferred_class": cls.get("inferred_class"),
        "classifier_ok": classifier_ok,
        "prescripted": fault.prescripted,
        "recover_md_line": fault.recover_md_line,
        "recovery_resolved": resolved,
        "recovery_note": note,
    }
