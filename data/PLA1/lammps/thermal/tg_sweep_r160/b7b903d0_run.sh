#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
cd /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r160
mpirun -np 4 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r160/tg_sweep_r160.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r160/b7b903d0_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"b7b903d0","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA1/lammps/thermal/tg_sweep_r160"}' > /tmp/polyjarvis/sentinels/done_b7b903d0.json
else
  echo '{"run_id":"b7b903d0","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_b7b903d0.json
fi

