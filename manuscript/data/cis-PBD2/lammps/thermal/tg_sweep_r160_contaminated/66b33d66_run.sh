#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_66b33d66
cd /home/arz2/PolyJarvis/data/cis-PBD2/lammps/thermal/tg_sweep_r160
env CUDA_VISIBLE_DEVICES=0 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/cis-PBD2/lammps/thermal/tg_sweep_r160/tg_sweep.in >> /home/arz2/PolyJarvis/data/cis-PBD2/lammps/thermal/tg_sweep_r160/66b33d66_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"66b33d66","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/cis-PBD2/lammps/thermal/tg_sweep_r160"}' > /tmp/polyjarvis/sentinels/done_66b33d66.json
else
  echo '{"run_id":"66b33d66","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_66b33d66.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_66b33d66

