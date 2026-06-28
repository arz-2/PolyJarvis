#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_93a661cd
cd /home/arz2/PolyJarvis/data/PSU2/lammps/thermal/tg_sweep_rec1_r400
env CUDA_VISIBLE_DEVICES=3 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PSU2/lammps/thermal/tg_sweep_rec1_r400/tg_sweep.in >> /home/arz2/PolyJarvis/data/PSU2/lammps/thermal/tg_sweep_rec1_r400/93a661cd_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"93a661cd","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PSU2/lammps/thermal/tg_sweep_rec1_r400"}' > /tmp/polyjarvis/sentinels/done_93a661cd.json
else
  echo '{"run_id":"93a661cd","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_93a661cd.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_93a661cd

