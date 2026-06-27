#!/bin/bash
export CUDA_VISIBLE_DEVICES=
cd /home/arz2/PolyJarvis/data/PVC1/lammps/mechanical/born
mpirun -np 4 /home/arz2/lammps-install/bin/lmp -in /home/arz2/PolyJarvis/data/PVC1/lammps/mechanical/born/nvt_born.in >> /home/arz2/PolyJarvis/data/PVC1/lammps/mechanical/born/10c265bb_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"10c265bb","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PVC1/lammps/mechanical/born"}' > /tmp/polyjarvis/sentinels/done_10c265bb.json
else
  echo '{"run_id":"10c265bb","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_10c265bb.json
fi

