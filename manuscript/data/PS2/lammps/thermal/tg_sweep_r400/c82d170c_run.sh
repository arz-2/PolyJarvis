#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_c82d170c
cd /home/alexzhao/PolyJarvis/data/PS2/lammps/thermal/tg_sweep_r400
env CUDA_VISIBLE_DEVICES=1 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PS2/lammps/thermal/tg_sweep_r400/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PS2/lammps/thermal/tg_sweep_r400/c82d170c_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"c82d170c","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PS2/lammps/thermal/tg_sweep_r400"}' > /tmp/polyjarvis/sentinels/done_c82d170c.json
else
  echo '{"run_id":"c82d170c","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_c82d170c.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_c82d170c

