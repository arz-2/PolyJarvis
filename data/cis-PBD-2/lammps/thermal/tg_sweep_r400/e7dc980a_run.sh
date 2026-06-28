#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_e7dc980a
cd /home/arz2/PolyJarvis/data/cis-PBD-2/lammps/thermal/tg_sweep_r400
env CUDA_VISIBLE_DEVICES=0 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/cis-PBD-2/lammps/thermal/tg_sweep_r400/tg_sweep.in >> /home/arz2/PolyJarvis/data/cis-PBD-2/lammps/thermal/tg_sweep_r400/e7dc980a_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"e7dc980a","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/cis-PBD-2/lammps/thermal/tg_sweep_r400"}' > /tmp/polyjarvis/sentinels/done_e7dc980a.json
else
  echo '{"run_id":"e7dc980a","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_e7dc980a.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_e7dc980a

