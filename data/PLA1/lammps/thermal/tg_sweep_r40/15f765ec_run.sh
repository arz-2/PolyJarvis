#!/bin/bash
export CUDA_VISIBLE_DEVICES=2
cd /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40
mpirun -np 1 /home/arz2/lammps-install/bin/lmp -k on g 1 -sf kk -pk kokkos newton on neigh half -in /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40/tg_sweep_r40.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40/15f765ec_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"15f765ec","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40"}' > /tmp/polyjarvis/sentinels/done_15f765ec.json
else
  echo '{"run_id":"15f765ec","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_15f765ec.json
fi

