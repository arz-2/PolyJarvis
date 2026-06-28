#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_e4aa7555
cd /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/deform_y
env CUDA_VISIBLE_DEVICES=1 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/deform_y/05_deform.in >> /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/deform_y/e4aa7555_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"e4aa7555","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/deform_y"}' > /tmp/polyjarvis/sentinels/done_e4aa7555.json
else
  echo '{"run_id":"e4aa7555","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_e4aa7555.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_e4aa7555

