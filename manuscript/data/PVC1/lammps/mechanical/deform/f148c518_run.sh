#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
cd /home/arz2/PolyJarvis/data/PVC1/lammps/mechanical/deform
mpirun -np 4 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/PVC1/lammps/mechanical/deform/deform.in >> /home/arz2/PolyJarvis/data/PVC1/lammps/mechanical/deform/f148c518_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"f148c518","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PVC1/lammps/mechanical/deform"}' > /tmp/polyjarvis/sentinels/done_f148c518.json
else
  echo '{"run_id":"f148c518","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_f148c518.json
fi

