#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_5bfba056
cd /home/arz2/PolyJarvis/data/cis-PBD-2/lammps/thermal/tg_sweep_r40
env CUDA_VISIBLE_DEVICES=0 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/cis-PBD-2/lammps/thermal/tg_sweep_r40/tg_sweep.in >> /home/arz2/PolyJarvis/data/cis-PBD-2/lammps/thermal/tg_sweep_r40/5bfba056_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"5bfba056","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/cis-PBD-2/lammps/thermal/tg_sweep_r40"}' > /tmp/polyjarvis/sentinels/done_5bfba056.json
else
  echo '{"run_id":"5bfba056","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_5bfba056.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_5bfba056

