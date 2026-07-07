#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_37f88f7c
cd /home/arz2/PolyJarvis/data/cis-PBD4/lammps/thermal/tg_sweep_r10
env CUDA_VISIBLE_DEVICES=1 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/cis-PBD4/lammps/thermal/tg_sweep_r10/tg_sweep.in >> /home/arz2/PolyJarvis/data/cis-PBD4/lammps/thermal/tg_sweep_r10/37f88f7c_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"37f88f7c","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/cis-PBD4/lammps/thermal/tg_sweep_r10"}' > /tmp/polyjarvis/sentinels/done_37f88f7c.json
else
  echo '{"run_id":"37f88f7c","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_37f88f7c.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_37f88f7c

