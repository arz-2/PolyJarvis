#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
cd /home/arz2/PolyJarvis/data/PMMA1/lammps/mechanical/05_deform_slow
mpirun -np 4 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/arz2/PolyJarvis/data/PMMA1/lammps/mechanical/05_deform_slow/05_deform_slow.in >> /home/arz2/PolyJarvis/data/PMMA1/lammps/mechanical/05_deform_slow/811d6fd2_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"811d6fd2","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PMMA1/lammps/mechanical/05_deform_slow"}' > /tmp/polyjarvis/sentinels/done_811d6fd2.json
else
  echo '{"run_id":"811d6fd2","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_811d6fd2.json
fi

