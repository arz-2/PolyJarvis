# molecule-builder Memory Index

- [PSIL now buildable](psil_now_buildable.md) — PDMS/PSIL builds fine via EMC opls/2024/opls-aa after the 2026-06-05 siloxane typing patch (si4 [Si](~O)(O)(C)(C), o2 bridge, o2h/h1o caps). Verified job f4c83340 (dp=80, 8020 atoms). Supersedes the old "unsupported" wall. [ingested 2026-06-10]
- [EMC status can be stale](emc_status_stale_use_output.md) — get_emc_job_status may say "running" forever after a finished build; poll get_emc_job_output for ground truth. Data file is emc_build.data, not cell.data. [ingested 2026-06-10]
