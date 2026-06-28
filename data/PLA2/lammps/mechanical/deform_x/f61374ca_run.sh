#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_f61374ca
cd /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/deform_x
env CUDA_VISIBLE_DEVICES=1 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/deform_x/05_deform.in >> /home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/deform_x/f61374ca_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"f61374ca","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA2/lammps/mechanical/deform_x"}' > /tmp/polyjarvis/sentinels/done_f61374ca.json
else
  echo '{"run_id":"f61374ca","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_f61374ca.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_f61374ca

