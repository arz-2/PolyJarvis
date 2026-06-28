#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_a8ea3a0c
cd /home/alexzhao/PolyJarvis/data/PEG2/lammps/equil/npt_production_ext
env CUDA_VISIBLE_DEVICES=0 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PEG2/lammps/equil/npt_production_ext/npt_ext.in >> /home/alexzhao/PolyJarvis/data/PEG2/lammps/equil/npt_production_ext/a8ea3a0c_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"a8ea3a0c","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PEG2/lammps/equil/npt_production_ext"}' > /tmp/polyjarvis/sentinels/done_a8ea3a0c.json
else
  echo '{"run_id":"a8ea3a0c","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_a8ea3a0c.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_a8ea3a0c

