#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
cd /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40
mpirun -np 1 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40/tg_sweep_r40.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40/d6435a8d_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"d6435a8d","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40"}' > /tmp/polyjarvis/sentinels/done_d6435a8d.json
else
  echo '{"run_id":"d6435a8d","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_d6435a8d.json
fi

