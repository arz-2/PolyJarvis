#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_7f2ad6ae
cd /home/alexzhao/PolyJarvis/data/PSU_1/attempts/thermal/attempt-0001/work/tg_sweep_r100
env CUDA_VISIBLE_DEVICES=3 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PSU_1/attempts/thermal/attempt-0001/work/tg_sweep_r100/tg_step_T300_e0.in >> /home/alexzhao/PolyJarvis/data/PSU_1/attempts/thermal/attempt-0001/work/tg_sweep_r100/7f2ad6ae_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"7f2ad6ae","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PSU_1/attempts/thermal/attempt-0001/work/tg_sweep_r100"}' > /tmp/polyjarvis/sentinels/done_7f2ad6ae.json
else
  echo '{"run_id":"7f2ad6ae","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_7f2ad6ae.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_7f2ad6ae

