#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_81ff0bd2
cd /home/alexzhao/PolyJarvis/data/PSU_1/attempts/thermal/attempt-0001/work/tg_sweep_r100
env CUDA_VISIBLE_DEVICES=3 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PSU_1/attempts/thermal/attempt-0001/work/tg_sweep_r100/tg_step_T460_e0.in >> /home/alexzhao/PolyJarvis/data/PSU_1/attempts/thermal/attempt-0001/work/tg_sweep_r100/81ff0bd2_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"81ff0bd2","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PSU_1/attempts/thermal/attempt-0001/work/tg_sweep_r100"}' > /tmp/polyjarvis/sentinels/done_81ff0bd2.json
else
  echo '{"run_id":"81ff0bd2","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_81ff0bd2.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_81ff0bd2

