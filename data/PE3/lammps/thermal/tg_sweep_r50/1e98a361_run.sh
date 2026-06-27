#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_1e98a361
cd /home/arz2/PolyJarvis/data/PE3/lammps/thermal/tg_sweep_r50
mpirun -np 2 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/PE3/lammps/thermal/tg_sweep_r50/tg_sweep.in >> /home/arz2/PolyJarvis/data/PE3/lammps/thermal/tg_sweep_r50/1e98a361_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"1e98a361","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PE3/lammps/thermal/tg_sweep_r50"}' > /tmp/polyjarvis/sentinels/done_1e98a361.json
else
  echo '{"run_id":"1e98a361","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_1e98a361.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_1e98a361

