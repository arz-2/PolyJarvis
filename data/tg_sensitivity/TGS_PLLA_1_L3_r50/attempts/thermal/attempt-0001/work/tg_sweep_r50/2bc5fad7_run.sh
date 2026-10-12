#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_2bc5fad7
cd /home/arz2/PolyJarvis_v2/data/tg_sensitivity/TGS_PLLA_1_L3_r50/attempts/thermal/attempt-0001/work/tg_sweep_r50
env CUDA_VISIBLE_DEVICES=1 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis_v2/data/tg_sensitivity/TGS_PLLA_1_L3_r50/attempts/thermal/attempt-0001/work/tg_sweep_r50/tg_step_T320_e0.in >> /home/arz2/PolyJarvis_v2/data/tg_sensitivity/TGS_PLLA_1_L3_r50/attempts/thermal/attempt-0001/work/tg_sweep_r50/2bc5fad7_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"2bc5fad7","status":"completed","work_dir":"/home/arz2/PolyJarvis_v2/data/tg_sensitivity/TGS_PLLA_1_L3_r50/attempts/thermal/attempt-0001/work/tg_sweep_r50"}' > /tmp/polyjarvis/sentinels/done_2bc5fad7.json
else
  echo '{"run_id":"2bc5fad7","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_2bc5fad7.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_2bc5fad7

