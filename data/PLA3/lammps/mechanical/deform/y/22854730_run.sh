#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_22854730
cd /home/arz2/PolyJarvis/data/PLA3/lammps/mechanical/deform/y
env CUDA_VISIBLE_DEVICES=1 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PLA3/lammps/mechanical/deform/y/05_deform_y.in >> /home/arz2/PolyJarvis/data/PLA3/lammps/mechanical/deform/y/22854730_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"22854730","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA3/lammps/mechanical/deform/y"}' > /tmp/polyjarvis/sentinels/done_22854730.json
else
  echo '{"run_id":"22854730","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_22854730.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_22854730

