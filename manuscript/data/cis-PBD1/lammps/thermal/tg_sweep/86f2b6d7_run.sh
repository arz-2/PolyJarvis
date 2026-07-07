#!/bin/bash
export CUDA_VISIBLE_DEVICES=
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_86f2b6d7
cd /home/arz2/PolyJarvis/data/cis-PBD1/lammps/thermal/tg_sweep
mpirun -np 8 /home/arz2/lammps-install/bin/lmp -in /home/arz2/PolyJarvis/data/cis-PBD1/lammps/thermal/tg_sweep/tg_sweep.in >> /home/arz2/PolyJarvis/data/cis-PBD1/lammps/thermal/tg_sweep/86f2b6d7_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"86f2b6d7","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/cis-PBD1/lammps/thermal/tg_sweep"}' > /tmp/polyjarvis/sentinels/done_86f2b6d7.json
else
  echo '{"run_id":"86f2b6d7","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_86f2b6d7.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_86f2b6d7

