#!/usr/bin/env python3
"""
hw_common.py — live host and GPU probing.

What box is this, how many physical cores and GPUs does it have, and does it match the
hardware_policy.host fingerprint the per-FF benchmark defaults were measured on. Single
source of truth for probes several scripts each used to do their own way and drift on
(pick_gpu.py once hardcoded 18 cores after the box moved to 32).

The polymer_rules.json loader and class/member resolution that used to share this file moved
to rules_common.py on 2026-09-02 -- they were never about hardware. hardware_policy() is
imported from there; the dependency runs one way.

stdlib only -- importable by any orchestration/scripts/<x>.py (orchestration/scripts/ is on
sys.path[0] when run as a CLI; benchmark_hardware.py / calibrate_hardware.py also insert
orchestration/scripts/ explicitly).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules_common import hardware_policy  # noqa: E402


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
