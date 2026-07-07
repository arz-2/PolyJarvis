#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_3f619e8f
cd /home/arz2/PolyJarvis/data/PE3/lammps/thermal/tg_sweep_r25
mpirun -np 8 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/PE3/lammps/thermal/tg_sweep_r25/tg_sweep.in >> /home/arz2/PolyJarvis/data/PE3/lammps/thermal/tg_sweep_r25/3f619e8f_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"3f619e8f","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PE3/lammps/thermal/tg_sweep_r25"}' > /tmp/polyjarvis/sentinels/done_3f619e8f.json
else
  echo '{"run_id":"3f619e8f","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_3f619e8f.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_3f619e8f

