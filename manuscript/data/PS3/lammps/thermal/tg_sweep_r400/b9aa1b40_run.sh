#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_b9aa1b40
cd /home/alexzhao/PolyJarvis/data/PS3/lammps/thermal/tg_sweep_r400
env CUDA_VISIBLE_DEVICES=3 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PS3/lammps/thermal/tg_sweep_r400/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PS3/lammps/thermal/tg_sweep_r400/b9aa1b40_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"b9aa1b40","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PS3/lammps/thermal/tg_sweep_r400"}' > /tmp/polyjarvis/sentinels/done_b9aa1b40.json
else
  echo '{"run_id":"b9aa1b40","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_b9aa1b40.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_b9aa1b40

