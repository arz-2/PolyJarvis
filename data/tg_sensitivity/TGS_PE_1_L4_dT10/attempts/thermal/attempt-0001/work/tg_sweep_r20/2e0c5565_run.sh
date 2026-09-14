#!/bin/bash
export CUDA_VISIBLE_DEVICES=2
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_2e0c5565
cd /home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L4_dT10/attempts/thermal/attempt-0001/work/tg_sweep_r20
env CUDA_VISIBLE_DEVICES=2 /home/alexzhao/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L4_dT10/attempts/thermal/attempt-0001/work/tg_sweep_r20/tg_step_T540_e0.in >> /home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L4_dT10/attempts/thermal/attempt-0001/work/tg_sweep_r20/2e0c5565_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"2e0c5565","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L4_dT10/attempts/thermal/attempt-0001/work/tg_sweep_r20"}' > /tmp/polyjarvis/sentinels/done_2e0c5565.json
else
  echo '{"run_id":"2e0c5565","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_2e0c5565.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_2e0c5565

