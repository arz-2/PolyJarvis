#!/bin/bash
export CUDA_VISIBLE_DEVICES=
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_1100182f
cd /home/alexzhao/PolyJarvis/data/PS1/lammps/mechanical/born
mpirun -np 4 /home/alexzhao/lammps-install/bin/lmp -in /home/alexzhao/PolyJarvis/data/PS1/lammps/mechanical/born/08_nvt_born.in >> /home/alexzhao/PolyJarvis/data/PS1/lammps/mechanical/born/1100182f_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"1100182f","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PS1/lammps/mechanical/born"}' > /tmp/polyjarvis/sentinels/done_1100182f.json
else
  echo '{"run_id":"1100182f","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_1100182f.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_1100182f

