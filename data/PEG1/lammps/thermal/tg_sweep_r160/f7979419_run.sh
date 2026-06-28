#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_f7979419
cd /home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r160
mpirun -np 4 /home/alexzhao/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r160/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r160/f7979419_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"f7979419","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r160"}' > /tmp/polyjarvis/sentinels/done_f7979419.json
else
  echo '{"run_id":"f7979419","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_f7979419.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_f7979419

