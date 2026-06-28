#!/bin/bash
export CUDA_VISIBLE_DEVICES=
cd /home/arz2/PolyJarvis/data/PMMA1/lammps/mechanical/08_nvt_born/
mpirun -np 4 /home/arz2/lammps-install/bin/lmp -in /home/arz2/PolyJarvis/data/PMMA1/lammps/mechanical/08_nvt_born/08_nvt_born.in >> /home/arz2/PolyJarvis/data/PMMA1/lammps/mechanical/08_nvt_born//bb096bff_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"bb096bff","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PMMA1/lammps/mechanical/08_nvt_born/"}' > /tmp/polyjarvis/sentinels/done_bb096bff.json
else
  echo '{"run_id":"bb096bff","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_bb096bff.json
fi

