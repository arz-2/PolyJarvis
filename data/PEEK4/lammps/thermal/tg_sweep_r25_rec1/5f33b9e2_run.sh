#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_5f33b9e2
cd /home/alexzhao/PolyJarvis/data/PEEK4/lammps/thermal/tg_sweep_r25
env CUDA_VISIBLE_DEVICES=0 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PEEK4/lammps/thermal/tg_sweep_r25/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PEEK4/lammps/thermal/tg_sweep_r25/5f33b9e2_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"5f33b9e2","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PEEK4/lammps/thermal/tg_sweep_r25"}' > /tmp/polyjarvis/sentinels/done_5f33b9e2.json
else
  echo '{"run_id":"5f33b9e2","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_5f33b9e2.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_5f33b9e2

