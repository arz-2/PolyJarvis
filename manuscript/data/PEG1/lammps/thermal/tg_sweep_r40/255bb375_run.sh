#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_255bb375
cd /home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r40
mpirun -np 4 /home/alexzhao/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r40/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r40/255bb375_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"255bb375","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r40"}' > /tmp/polyjarvis/sentinels/done_255bb375.json
else
  echo '{"run_id":"255bb375","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_255bb375.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_255bb375

