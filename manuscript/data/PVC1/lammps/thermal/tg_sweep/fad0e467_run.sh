#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
cd /home/arz2/PolyJarvis/data/PVC1/lammps/thermal/tg_sweep
mpirun -np 4 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/PVC1/lammps/thermal/tg_sweep/tg_sweep.in >> /home/arz2/PolyJarvis/data/PVC1/lammps/thermal/tg_sweep/fad0e467_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"fad0e467","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PVC1/lammps/thermal/tg_sweep"}' > /tmp/polyjarvis/sentinels/done_fad0e467.json
else
  echo '{"run_id":"fad0e467","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_fad0e467.json
fi

