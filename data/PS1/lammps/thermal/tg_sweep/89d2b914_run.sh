#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_89d2b914
cd /home/alexzhao/PolyJarvis/data/PS1/lammps/thermal/tg_sweep
mpirun -np 4 /home/alexzhao/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/alexzhao/PolyJarvis/data/PS1/lammps/thermal/tg_sweep/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PS1/lammps/thermal/tg_sweep/89d2b914_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"89d2b914","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PS1/lammps/thermal/tg_sweep"}' > /tmp/polyjarvis/sentinels/done_89d2b914.json
else
  echo '{"run_id":"89d2b914","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_89d2b914.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_89d2b914

