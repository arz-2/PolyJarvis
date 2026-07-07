#!/bin/bash
export CUDA_VISIBLE_DEVICES=0,2,3
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_df832d7e
cd /home/arz2/PolyJarvis/data/PEEK1/lammps/mechanical/deform
mpirun -np 3 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 3 -in /home/arz2/PolyJarvis/data/PEEK1/lammps/mechanical/deform/npt_deform.in >> /home/arz2/PolyJarvis/data/PEEK1/lammps/mechanical/deform/df832d7e_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"df832d7e","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PEEK1/lammps/mechanical/deform"}' > /tmp/polyjarvis/sentinels/done_df832d7e.json
else
  echo '{"run_id":"df832d7e","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_df832d7e.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_df832d7e

