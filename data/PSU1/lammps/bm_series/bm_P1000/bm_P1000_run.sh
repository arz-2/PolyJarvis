#!/bin/bash
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_bm_P1000
source /home/arz2/miniforge3/etc/profile.d/conda.sh; conda activate mol-builder
cd /home/arz2/PolyJarvis/data/PSU1/lammps/bm_series/bm_P1000
env CUDA_VISIBLE_DEVICES=3 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PSU1/lammps/bm_series/bm_P1000/bm_P1000.in >> bm_P1000_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then echo "{\"run_id\":\"bm_P1000\",\"status\":\"completed\"}" > /tmp/polyjarvis/sentinels/done_bm_P1000.json
else echo "{\"run_id\":\"bm_P1000\",\"status\":\"failed\",\"exit_code\":\"$RC\"}" > /tmp/polyjarvis/sentinels/done_bm_P1000.json; fi
rm -f /tmp/polyjarvis/sentinels/pid_bm_P1000
