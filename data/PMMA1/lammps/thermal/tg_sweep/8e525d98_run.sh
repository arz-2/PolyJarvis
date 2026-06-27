#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
cd /home/arz2/PolyJarvis/data/PMMA1/lammps/thermal/tg_sweep
mpirun -np 4 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/PMMA1/lammps/thermal/tg_sweep/tg_sweep.in >> /home/arz2/PolyJarvis/data/PMMA1/lammps/thermal/tg_sweep/8e525d98_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"8e525d98","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PMMA1/lammps/thermal/tg_sweep"}' > /tmp/polyjarvis/sentinels/done_8e525d98.json
else
  echo '{"run_id":"8e525d98","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_8e525d98.json
fi

