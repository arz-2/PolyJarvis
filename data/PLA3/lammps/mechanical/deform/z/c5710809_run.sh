#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_c5710809
cd /home/arz2/PolyJarvis/data/PLA3/lammps/mechanical/deform/z
env CUDA_VISIBLE_DEVICES=1 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PLA3/lammps/mechanical/deform/z/05_deform_z.in >> /home/arz2/PolyJarvis/data/PLA3/lammps/mechanical/deform/z/c5710809_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"c5710809","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA3/lammps/mechanical/deform/z"}' > /tmp/polyjarvis/sentinels/done_c5710809.json
else
  echo '{"run_id":"c5710809","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_c5710809.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_c5710809

