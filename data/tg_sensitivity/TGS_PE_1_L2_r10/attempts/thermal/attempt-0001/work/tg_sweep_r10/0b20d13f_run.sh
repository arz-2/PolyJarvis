#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_0b20d13f
cd /home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L2_r10/attempts/thermal/attempt-0001/work/tg_sweep_r10
env CUDA_VISIBLE_DEVICES=0 /home/alexzhao/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L2_r10/attempts/thermal/attempt-0001/work/tg_sweep_r10/tg_step_T350_e0.in >> /home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L2_r10/attempts/thermal/attempt-0001/work/tg_sweep_r10/0b20d13f_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"0b20d13f","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/tg_sensitivity/TGS_PE_1_L2_r10/attempts/thermal/attempt-0001/work/tg_sweep_r10"}' > /tmp/polyjarvis/sentinels/done_0b20d13f.json
else
  echo '{"run_id":"0b20d13f","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_0b20d13f.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_0b20d13f

