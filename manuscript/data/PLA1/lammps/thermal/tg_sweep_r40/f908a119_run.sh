#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
cd /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40
mpirun -np 1 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos comm host -in /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40/tg_sweep_r40.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40/f908a119_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"f908a119","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40"}' > /tmp/polyjarvis/sentinels/done_f908a119.json
else
  echo '{"run_id":"f908a119","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_f908a119.json
fi
