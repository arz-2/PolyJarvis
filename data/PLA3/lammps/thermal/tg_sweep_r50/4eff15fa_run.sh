#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_4eff15fa
cd /home/arz2/PolyJarvis/data/PLA3/lammps/thermal/tg_sweep_r50
env CUDA_VISIBLE_DEVICES=0 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PLA3/lammps/thermal/tg_sweep_r50/tg_sweep.in >> /home/arz2/PolyJarvis/data/PLA3/lammps/thermal/tg_sweep_r50/4eff15fa_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"4eff15fa","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA3/lammps/thermal/tg_sweep_r50"}' > /tmp/polyjarvis/sentinels/done_4eff15fa.json
else
  echo '{"run_id":"4eff15fa","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_4eff15fa.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_4eff15fa

