#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_2f83ad3a
cd /home/arz2/PolyJarvis_v2/data/PLLA_2/attempts/thermal/attempt-0001/work/tg_sweep_r100
env CUDA_VISIBLE_DEVICES=3 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis_v2/data/PLLA_2/attempts/thermal/attempt-0001/work/tg_sweep_r100/tg_step_T320_e0.in >> /home/arz2/PolyJarvis_v2/data/PLLA_2/attempts/thermal/attempt-0001/work/tg_sweep_r100/2f83ad3a_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"2f83ad3a","status":"completed","work_dir":"/home/arz2/PolyJarvis_v2/data/PLLA_2/attempts/thermal/attempt-0001/work/tg_sweep_r100"}' > /tmp/polyjarvis/sentinels/done_2f83ad3a.json
else
  echo '{"run_id":"2f83ad3a","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_2f83ad3a.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_2f83ad3a

