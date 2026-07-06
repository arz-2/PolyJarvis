---
name: kokkos-generate-script-correct
description: tg-sweep-worker must pass engine=kokkos+use_gpu=True to generate_script, not just run_lammps_script
metadata:
  type: feedback
---

**Rule:** Always thread `engine` and `use_gpu` parameters into the `generate_script()` call when using GPU-accelerated engines (kokkos, gpu).

**Why:** The template processor must emit the correct `package` directives (e.g., `-sf kk` for kokkos) into the deck. Without these flags at generation time, the compiled binary receives instructions for a different execution model (e.g., kokkos binary gets CPU-mode deck → instant hang/fail). Previous incident: PEG4 R-01 kokkos failure due to `package gpu` on kokkos binary.

**How to apply:** In Step 1 (generate_script), include both `engine` and `use_gpu` in the params dict:
```python
generate_script(
    template_name="npt_tg_step",
    data_file=...,
    output_script=...,
    params={
        ...,
        "engine": "kokkos",  # or "gpu" or "cpu"
        "use_gpu": true,     # must be True for engine=kokkos|gpu
        ...
    }
)
```
Then pass the same engine to `run_lammps_script()`.
