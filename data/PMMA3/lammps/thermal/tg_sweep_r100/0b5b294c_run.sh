#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_0b5b294c
cd /home/arz2/PolyJarvis/data/PMMA3/lammps/thermal/tg_sweep_r100
env CUDA_VISIBLE_DEVICES=3 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PMMA3/lammps/thermal/tg_sweep_r100/tg_sweep.in >> /home/arz2/PolyJarvis/data/PMMA3/lammps/thermal/tg_sweep_r100/0b5b294c_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"0b5b294c","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PMMA3/lammps/thermal/tg_sweep_r100"}' > /tmp/polyjarvis/sentinels/done_0b5b294c.json
else
  echo '{"run_id":"0b5b294c","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_0b5b294c.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_0b5b294c

