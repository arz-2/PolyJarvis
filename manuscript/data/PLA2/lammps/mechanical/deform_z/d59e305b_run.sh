#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_d59e305b
cd /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/deform_z
env CUDA_VISIBLE_DEVICES=1 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/deform_z/05_deform.in >> /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/deform_z/d59e305b_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"d59e305b","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/deform_z"}' > /tmp/polyjarvis/sentinels/done_d59e305b.json
else
  echo '{"run_id":"d59e305b","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_d59e305b.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_d59e305b

