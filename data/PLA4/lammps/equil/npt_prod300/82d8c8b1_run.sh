#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/usr/bin:$PATH
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
unset OPAL_PREFIX
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_82d8c8b1
cd /home/arz2/PolyJarvis/data/PLA4/lammps/equil/npt_prod300
env CUDA_VISIBLE_DEVICES=0 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/arz2/PolyJarvis/data/PLA4/lammps/equil/npt_prod300/npt_prod300_resume.in >> /home/arz2/PolyJarvis/data/PLA4/lammps/equil/npt_prod300/82d8c8b1_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"82d8c8b1","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PLA4/lammps/equil/npt_prod300"}' > /tmp/polyjarvis/sentinels/done_82d8c8b1.json
else
  echo '{"run_id":"82d8c8b1","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_82d8c8b1.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_82d8c8b1

