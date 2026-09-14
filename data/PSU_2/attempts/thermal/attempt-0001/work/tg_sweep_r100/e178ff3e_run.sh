#!/bin/bash
export CUDA_VISIBLE_DEVICES=2
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_e178ff3e
cd /home/alexzhao/PolyJarvis/data/PSU_2/attempts/thermal/attempt-0001/work/tg_sweep_r100
env CUDA_VISIBLE_DEVICES=2 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PSU_2/attempts/thermal/attempt-0001/work/tg_sweep_r100/tg_step_T660_e0.in >> /home/alexzhao/PolyJarvis/data/PSU_2/attempts/thermal/attempt-0001/work/tg_sweep_r100/e178ff3e_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"e178ff3e","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PSU_2/attempts/thermal/attempt-0001/work/tg_sweep_r100"}' > /tmp/polyjarvis/sentinels/done_e178ff3e.json
else
  echo '{"run_id":"e178ff3e","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_e178ff3e.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_e178ff3e

