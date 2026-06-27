#!/bin/bash
export CUDA_VISIBLE_DEVICES=
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_0b5a1c8c
cd /home/arz2/PolyJarvis/data/PEEK1/lammps/mechanical/08_nvt_born/
mpirun -np 1 /home/arz2/lammps-install/bin/lmp -in /home/arz2/PolyJarvis/data/PEEK1/lammps/mechanical/08_nvt_born/08_nvt_born.in >> /home/arz2/PolyJarvis/data/PEEK1/lammps/mechanical/08_nvt_born//0b5a1c8c_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"0b5a1c8c","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PEEK1/lammps/mechanical/08_nvt_born/"}' > /tmp/polyjarvis/sentinels/done_0b5a1c8c.json
else
  echo '{"run_id":"0b5a1c8c","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_0b5a1c8c.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_0b5a1c8c

