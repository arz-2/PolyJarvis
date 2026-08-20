#!/usr/bin/env python3
"""
hw_common.py — shared hardware-policy + rules access for the PolyJarvis CLI scripts.

Single source of truth for the small things several scripts each used to read their own
way (and drift on — e.g. pick_gpu.py once hardcoded 18 cores after the box moved to 32):
the polymer_rules.json loader, the hardware_policy accessor, physical-core detection, the
nvidia-smi GPU probe, and FF-family resolution.

stdlib only — importable by any orchestration/scripts/<x>.py (orchestration/scripts/ is on
sys.path[0] when run as a CLI; benchmark_hardware.py / calibrate_hardware.py also insert
orchestration/scripts/ explicitly).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RULES_PATH = REPO / "guides" / "polymer_rules.json"


def load_rules() -> dict:
    """Parse guides/polymer_rules.json."""
    with open(RULES_PATH) as f:
        return json.load(f)


def get_class_entry(rules: dict, polymer_class: str, warn_on_miss: bool = False) -> dict:
    """Class entry from polymer_rules, falling back to global_defaults on an unknown class."""
    entry = rules["classes"].get(polymer_class.upper())
    if entry is None:
        if warn_on_miss:
            print(f"WARNING: class '{polymer_class}' not found in polymer_rules.json; "
                  "using global_defaults", file=sys.stderr)
        entry = rules["global_defaults"]
    return entry


def hardware_policy(rules: dict | None = None) -> dict:
    """The hardware_policy block (loads rules if not supplied). {} if absent."""
    rules = rules if rules is not None else load_rules()
    return rules.get("hardware_policy", {})


def _phys_cores_probe() -> int:
    """Probe the box's physical-core count directly (lscpu, then os.cpu_count()),
    WITHOUT consulting hardware_policy. Used by host_matches(), which must compare the
    live machine against the saved fingerprint — trusting the policy value there would
    make phys_cores always "match" itself."""
    try:
        out = subprocess.run(["lscpu"], capture_output=True, text=True, timeout=10).stdout
        cps = sockets = None
        for ln in out.splitlines():
            if ln.startswith("Core(s) per socket:"):
                cps = int(ln.split(":")[1])
            elif ln.startswith("Socket(s):"):
                sockets = int(ln.split(":")[1])
        if cps and sockets:
            return cps * sockets
    except Exception:
        pass
    return os.cpu_count() or 8


def detect_phys_cores() -> int:
    """Physical-core count for this box. Prefer the calibrated hardware_policy host
    value, fall back to a direct probe. Replaces the old hardcoded 18 so callers scale
    to whatever box this clone runs on."""
    try:
        n = int(hardware_policy()["host"]["phys_cores"])
        if n > 0:
            return n
    except Exception:
        pass
    return _phys_cores_probe()


def gpu_status() -> list[dict]:
    """Return [{index, util, mem_used_mb}] from nvidia-smi, or [] if unavailable."""
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=index,utilization.gpu,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            gpus.append({"index": int(parts[0]),
                         "util": int(parts[1]),
                         "mem_used_mb": int(parts[2])})
    return gpus


def gpu_model() -> str:
    """The first GPU's marketing name from nvidia-smi (e.g. 'NVIDIA A800 40GB Active'),
    or 'unknown'. The model + count fingerprints the box for host-match gating."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=15).stdout
        names = [l.strip() for l in out.strip().splitlines() if l.strip()]
        if names:
            return names[0]
    except Exception:
        pass
    return "unknown"


def live_host() -> dict:
    """Best-effort fingerprint of the box this is running on: GPU count + model + a
    DIRECT physical-core probe (not the policy echo). Shape matches hardware_policy.host
    so host_matches() and calibrate_hardware can compare/write the same dict."""
    return {"gpus": len(gpu_status()), "gpu_model": gpu_model(),
            "phys_cores": _phys_cores_probe()}


def _gpu_model_matches(live_model: str, saved_model: str) -> bool:
    """Loose GPU-model comparison: nvidia-smi's bare name (e.g. 'Quadro RTX 6000') and
    hardware_policy.host's saved name (e.g. 'Quadro RTX 6000 24GB') format the same card
    differently -- same principle as select_hardware.py's _host_matches_measured_on() token
    match. Match if either string is a substring of the other."""
    live_model = (live_model or "").strip()
    saved_model = (saved_model or "").strip()
    if not live_model or not saved_model:
        return False
    return live_model in saved_model or saved_model in live_model


def host_matches(rules: dict | None = None) -> bool:
    """True iff the live box matches hardware_policy.host (GPU model + count + phys cores).
    Used to decide whether the benchmarked per-FF defaults apply here or the user should
    re-run /calibrate-hardware. Missing/empty saved host → False (never benchmarked here)."""
    saved = hardware_policy(rules).get("host") or {}
    if not saved:
        return False
    live = live_host()
    return (_gpu_model_matches(live["gpu_model"], saved.get("gpu_model", ""))
            and live["gpus"] == saved.get("gpus")
            and live["phys_cores"] == saved.get("phys_cores"))


@lru_cache(maxsize=256)
def _canon_for_match(smiles: str) -> str | None:
    """Stereo-stripped canonical SMILES for member-identity matching. Distinct from
    guides/system_characterization_cache.json's canonical_smiles cache key, which stays
    isomeric -- a different stereo variant of the same molecule needs independent protocol
    validation there, but tacticity/stereo markers must not change which class member a
    SMILES resolves to.

    Memoized: canonicalize() shells into a conda env per call. None on any failure
    (unparseable SMILES, RDKit/conda unavailable, timeout) -- never raises."""
    if not smiles:
        return None
    from canon_smiles import canonicalize
    try:
        return canonicalize(smiles, isomeric=False)
    except (RuntimeError, subprocess.TimeoutExpired):
        return None


def resolve_member(cls: dict, field: str, smiles: str) -> str | None:
    """Which member of cls[field] (a {member_name: [canonical_smiles, ...]} table) this
    smiles resolves to, or None."""
    member_smiles = cls.get(field) or {}
    canon = _canon_for_match(smiles)
    if canon is None:
        return None
    for member, variants in member_smiles.items():
        if not isinstance(variants, list):
            continue  # skip a sibling "note" string key
        if canon in variants:
            return member
    return None


def resolve_member_value(cls: dict, value_field: str, smiles: str):
    """cls[value_field] resolved for this smiles: the bare value if value_field is a
    scalar (applies to the whole class), the matched member's entry if value_field is a
    dict and cls['member_smiles'] resolves this smiles to one of its keys, else None."""
    val = cls.get(value_field)
    if isinstance(val, (int, float)):
        return val
    if not isinstance(val, dict):
        return None
    member = resolve_member(cls, "member_smiles", smiles)
    if member is None:
        return None
    v = val.get(member)
    return v if isinstance(v, (int, float)) else None


def resolve_ff_family(ff_raw: str, hp: dict) -> str:
    """Map a class's preferred_ff string to a by_forcefield family key
    (pcff | opls | trappe | gaff) via hardware_policy.ff_aliases, with a substring
    fallback. Used by stage_params.resolve_hardware and any consumer keying on FF family."""
    fam = hp.get("ff_aliases", {}).get(ff_raw) or hp.get("ff_aliases", {}).get(ff_raw.upper())
    if fam is None:
        fl = ff_raw.lower()
        # compass shares pcff's class2 functional form and its hardware profile, but
        # contains neither "pcff" nor any other family token, so the substring chain
        # below would silently drop it into "gaff" -- a different engine and rank count.
        fam = ("pcff" if ("pcff" in fl or fl == "compass") else "opls" if "opls" in fl
               else "trappe" if "trappe" in fl else "gaff")
    return fam
