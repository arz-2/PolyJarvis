#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
cd /home/arz2/PolyJarvis/data/PE1/lammps/thermal/tg_sweep
mpirun -np 1 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/PE1/lammps/thermal/tg_sweep/tg_sweep.in >> /home/arz2/PolyJarvis/data/PE1/lammps/thermal/tg_sweep/b6c18b47_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"b6c18b47","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PE1/lammps/thermal/tg_sweep"}' > /tmp/polyjarvis/sentinels/done_b6c18b47.json
else
  echo '{"run_id":"b6c18b47","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_b6c18b47.json
fi

