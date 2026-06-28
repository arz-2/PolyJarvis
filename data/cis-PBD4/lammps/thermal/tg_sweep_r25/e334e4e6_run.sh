#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_e334e4e6
cd /home/arz2/PolyJarvis/data/cis-PBD4/lammps/thermal/tg_sweep_r25
env CUDA_VISIBLE_DEVICES=1 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/cis-PBD4/lammps/thermal/tg_sweep_r25/tg_sweep.in >> /home/arz2/PolyJarvis/data/cis-PBD4/lammps/thermal/tg_sweep_r25/e334e4e6_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"e334e4e6","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/cis-PBD4/lammps/thermal/tg_sweep_r25"}' > /tmp/polyjarvis/sentinels/done_e334e4e6.json
else
  echo '{"run_id":"e334e4e6","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_e334e4e6.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_e334e4e6

