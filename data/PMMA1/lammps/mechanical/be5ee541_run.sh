#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
cd /home/arz2/PolyJarvis/data/PMMA1/lammps/mechanical
mpirun -np 4 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/PMMA1/lammps/mechanical/05_deform_fast.in >> /home/arz2/PolyJarvis/data/PMMA1/lammps/mechanical/be5ee541_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"be5ee541","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PMMA1/lammps/mechanical"}' > /tmp/polyjarvis/sentinels/done_be5ee541.json
else
  echo '{"run_id":"be5ee541","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_be5ee541.json
fi

