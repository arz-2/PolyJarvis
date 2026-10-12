#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_318c0367
cd /home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L1_r20/attempts/thermal/attempt-0001/work/tg_sweep_r20
env CUDA_VISIBLE_DEVICES=1 /home/alexzhao/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L1_r20/attempts/thermal/attempt-0001/work/tg_sweep_r20/tg_step_T450_e0.in >> /home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L1_r20/attempts/thermal/attempt-0001/work/tg_sweep_r20/318c0367_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"318c0367","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L1_r20/attempts/thermal/attempt-0001/work/tg_sweep_r20"}' > /tmp/polyjarvis/sentinels/done_318c0367.json
else
  echo '{"run_id":"318c0367","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_318c0367.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_318c0367

