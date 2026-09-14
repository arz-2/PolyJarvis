#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_ef54bf15
cd /home/alexzhao/PolyJarvis/data/PE_1/attempts/thermal/attempt-0003/work/tg_sweep_r40
env CUDA_VISIBLE_DEVICES=0 /home/alexzhao/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/alexzhao/PolyJarvis/data/PE_1/attempts/thermal/attempt-0003/work/tg_sweep_r40/tg_step_T330_e0.in >> /home/alexzhao/PolyJarvis/data/PE_1/attempts/thermal/attempt-0003/work/tg_sweep_r40/ef54bf15_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"ef54bf15","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PE_1/attempts/thermal/attempt-0003/work/tg_sweep_r40"}' > /tmp/polyjarvis/sentinels/done_ef54bf15.json
else
  echo '{"run_id":"ef54bf15","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_ef54bf15.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_ef54bf15

