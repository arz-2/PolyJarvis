#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_c026ee25
cd /home/arz2/PolyJarvis/data/PSU2/lammps/thermal/tg_sweep_r160
env CUDA_VISIBLE_DEVICES=3 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PSU2/lammps/thermal/tg_sweep_r160/tg_sweep.in >> /home/arz2/PolyJarvis/data/PSU2/lammps/thermal/tg_sweep_r160/c026ee25_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"c026ee25","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PSU2/lammps/thermal/tg_sweep_r160"}' > /tmp/polyjarvis/sentinels/done_c026ee25.json
else
  echo '{"run_id":"c026ee25","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_c026ee25.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_c026ee25

