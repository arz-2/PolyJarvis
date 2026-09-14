#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_c06e846f
cd /home/alexzhao/PolyJarvis/data/PE_2/attempts/thermal/attempt-0001/work/tg_sweep_r40
env CUDA_VISIBLE_DEVICES=3 /home/alexzhao/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/alexzhao/PolyJarvis/data/PE_2/attempts/thermal/attempt-0001/work/tg_sweep_r40/tg_step_T100_e0.in >> /home/alexzhao/PolyJarvis/data/PE_2/attempts/thermal/attempt-0001/work/tg_sweep_r40/c06e846f_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"c06e846f","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PE_2/attempts/thermal/attempt-0001/work/tg_sweep_r40"}' > /tmp/polyjarvis/sentinels/done_c06e846f.json
else
  echo '{"run_id":"c06e846f","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_c06e846f.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_c06e846f

