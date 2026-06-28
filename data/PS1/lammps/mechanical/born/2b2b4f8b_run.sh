#!/bin/bash
export CUDA_VISIBLE_DEVICES=
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_2b2b4f8b
cd /home/alexzhao/PolyJarvis/data/PS1/lammps/mechanical/born
mpirun -np 4 /home/alexzhao/lammps-install/bin/lmp -in /home/alexzhao/PolyJarvis/data/PS1/lammps/mechanical/born/08_nvt_born.in >> /home/alexzhao/PolyJarvis/data/PS1/lammps/mechanical/born/2b2b4f8b_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"2b2b4f8b","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PS1/lammps/mechanical/born"}' > /tmp/polyjarvis/sentinels/done_2b2b4f8b.json
else
  echo '{"run_id":"2b2b4f8b","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_2b2b4f8b.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_2b2b4f8b

