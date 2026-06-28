#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_b8f6eb08
cd /home/alexzhao/PolyJarvis/data/PS2/lammps/thermal/tg_sweep_r40
env CUDA_VISIBLE_DEVICES=1 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PS2/lammps/thermal/tg_sweep_r40/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PS2/lammps/thermal/tg_sweep_r40/b8f6eb08_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"b8f6eb08","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PS2/lammps/thermal/tg_sweep_r40"}' > /tmp/polyjarvis/sentinels/done_b8f6eb08.json
else
  echo '{"run_id":"b8f6eb08","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_b8f6eb08.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_b8f6eb08

