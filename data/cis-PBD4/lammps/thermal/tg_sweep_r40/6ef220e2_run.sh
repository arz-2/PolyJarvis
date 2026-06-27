#!/bin/bash
export CUDA_VISIBLE_DEVICES=
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_6ef220e2
cd /home/arz2/PolyJarvis/data/cis-PBD4/lammps/thermal/tg_sweep_r40
mpirun -np 8 /home/arz2/lammps-install/bin/lmp -in /home/arz2/PolyJarvis/data/cis-PBD4/lammps/thermal/tg_sweep_r40/tg_sweep.in >> /home/arz2/PolyJarvis/data/cis-PBD4/lammps/thermal/tg_sweep_r40/6ef220e2_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"6ef220e2","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/cis-PBD4/lammps/thermal/tg_sweep_r40"}' > /tmp/polyjarvis/sentinels/done_6ef220e2.json
else
  echo '{"run_id":"6ef220e2","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_6ef220e2.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_6ef220e2

