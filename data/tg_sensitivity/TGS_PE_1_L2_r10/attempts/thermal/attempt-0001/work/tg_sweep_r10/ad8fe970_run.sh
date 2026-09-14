#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_ad8fe970
cd /home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L2_r10/attempts/thermal/attempt-0001/work/tg_sweep_r10
env CUDA_VISIBLE_DEVICES=0 /home/alexzhao/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L2_r10/attempts/thermal/attempt-0001/work/tg_sweep_r10/tg_step_T210_e0.in >> /home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L2_r10/attempts/thermal/attempt-0001/work/tg_sweep_r10/ad8fe970_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"ad8fe970","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L2_r10/attempts/thermal/attempt-0001/work/tg_sweep_r10"}' > /tmp/polyjarvis/sentinels/done_ad8fe970.json
else
  echo '{"run_id":"ad8fe970","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_ad8fe970.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_ad8fe970

