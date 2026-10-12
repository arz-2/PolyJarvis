#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_0d636457
cd /home/arz2/PolyJarvis_v2/data/PTFE_AI/attempts/thermal/attempt-0001/work/tg_sweep_r100
env CUDA_VISIBLE_DEVICES=0 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis_v2/data/PTFE_AI/attempts/thermal/attempt-0001/work/tg_sweep_r100/tg_step_T540_e1.in >> /home/arz2/PolyJarvis_v2/data/PTFE_AI/attempts/thermal/attempt-0001/work/tg_sweep_r100/0d636457_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"0d636457","status":"completed","work_dir":"/home/arz2/PolyJarvis_v2/data/PTFE_AI/attempts/thermal/attempt-0001/work/tg_sweep_r100"}' > /tmp/polyjarvis/sentinels/done_0d636457.json
else
  echo '{"run_id":"0d636457","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_0d636457.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_0d636457

