#!/bin/bash
export CUDA_VISIBLE_DEVICES=2
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_3399c42d
cd /home/arz2/PolyJarvis/data/cis-PBD3/lammps/thermal/tg_sweep_r50
env CUDA_VISIBLE_DEVICES=2 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/cis-PBD3/lammps/thermal/tg_sweep_r50/tg_sweep.in >> /home/arz2/PolyJarvis/data/cis-PBD3/lammps/thermal/tg_sweep_r50/3399c42d_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"3399c42d","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/cis-PBD3/lammps/thermal/tg_sweep_r50"}' > /tmp/polyjarvis/sentinels/done_3399c42d.json
else
  echo '{"run_id":"3399c42d","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_3399c42d.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_3399c42d

