#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_375232d1
cd /home/alexzhao/PolyJarvis/data/PEEK_2/attempts/thermal/attempt-0001/work/tg_sweep_r100
env CUDA_VISIBLE_DEVICES=0 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PEEK_2/attempts/thermal/attempt-0001/work/tg_sweep_r100/tg_step_T590_e0.in >> /home/alexzhao/PolyJarvis/data/PEEK_2/attempts/thermal/attempt-0001/work/tg_sweep_r100/375232d1_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"375232d1","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PEEK_2/attempts/thermal/attempt-0001/work/tg_sweep_r100"}' > /tmp/polyjarvis/sentinels/done_375232d1.json
else
  echo '{"run_id":"375232d1","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_375232d1.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_375232d1

