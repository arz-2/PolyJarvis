#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_446fce1c
cd /home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r40
mpirun -np 4 /home/alexzhao/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r40/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r40/446fce1c_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"446fce1c","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r40"}' > /tmp/polyjarvis/sentinels/done_446fce1c.json
else
  echo '{"run_id":"446fce1c","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_446fce1c.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_446fce1c

