#!/bin/bash
# Manual KOKKOS launch for PLA1 Tg rate-640 (multirate 3/3) on GPU 3.
# Single-rank KOKKOS: NO mpirun (mpirun mis-pins to GPU0); explicit CUDA_VISIBLE_DEVICES=3.
cd /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r640
env CUDA_VISIBLE_DEVICES=3 /home/arz2/lammps-install-kokkos/bin/lmp \
    -k on g 1 -sf kk -pk kokkos comm host \
    -in /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r640/tg_sweep_r640.in \
    >> /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r640/kok640_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"kok640","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r640"}' > /tmp/polyjarvis/sentinels/done_kok640.json
else
  echo '{"run_id":"kok640","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_kok640.json
fi
