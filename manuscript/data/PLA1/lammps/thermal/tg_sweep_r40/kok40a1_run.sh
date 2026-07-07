#!/bin/bash
# Manual KOKKOS launch for PLA1 Tg rate-40 (orchestrator-built; engine workers mis-selected the binary).
# Single-rank KOKKOS: NO mpirun (mpirun doesn't forward CUDA_VISIBLE_DEVICES → mis-pins to GPU0).
# See memory feedback_kokkos_gpu_pinning + reference_kokkos_binary.
cd /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40
env CUDA_VISIBLE_DEVICES=0 /home/arz2/lammps-install-kokkos/bin/lmp \
    -k on g 1 -sf kk -pk kokkos comm host \
    -in /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40/tg_sweep_r40.in \
    >> /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40/kok40a1_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"kok40a1","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40"}' > /tmp/polyjarvis/sentinels/done_kok40a1.json
else
  echo '{"run_id":"kok40a1","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_kok40a1.json
fi
