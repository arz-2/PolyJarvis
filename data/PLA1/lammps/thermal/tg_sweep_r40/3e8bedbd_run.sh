#!/bin/bash
export CUDA_VISIBLE_DEVICES=2
cd /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40
mpirun -np 4 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40/tg_sweep_r40.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40/3e8bedbd_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"3e8bedbd","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r40"}' > /tmp/polyjarvis/sentinels/done_3e8bedbd.json
else
  echo '{"run_id":"3e8bedbd","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_3e8bedbd.json
fi

