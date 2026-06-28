#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_e116c47f
cd /home/arz2/PolyJarvis/data/PLA3/lammps/mechanical/deform/x
env CUDA_VISIBLE_DEVICES=1 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PLA3/lammps/mechanical/deform/x/05_deform_x.in >> /home/arz2/PolyJarvis/data/PLA3/lammps/mechanical/deform/x/e116c47f_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"e116c47f","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA3/lammps/mechanical/deform/x"}' > /tmp/polyjarvis/sentinels/done_e116c47f.json
else
  echo '{"run_id":"e116c47f","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_e116c47f.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_e116c47f

