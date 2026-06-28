#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_d36ee3f2
cd /home/alexzhao/PolyJarvis/data/PEG2/lammps/thermal/tg_sweep_r400
env CUDA_VISIBLE_DEVICES=3 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PEG2/lammps/thermal/tg_sweep_r400/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PEG2/lammps/thermal/tg_sweep_r400/d36ee3f2_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"d36ee3f2","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PEG2/lammps/thermal/tg_sweep_r400"}' > /tmp/polyjarvis/sentinels/done_d36ee3f2.json
else
  echo '{"run_id":"d36ee3f2","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_d36ee3f2.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_d36ee3f2

