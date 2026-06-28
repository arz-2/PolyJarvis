#!/bin/bash
export CUDA_VISIBLE_DEVICES=2
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_97f81b0d
cd /home/alexzhao/PolyJarvis/data/PVC3/lammps/thermal/tg_sweep_r50
env CUDA_VISIBLE_DEVICES=2 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PVC3/lammps/thermal/tg_sweep_r50/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PVC3/lammps/thermal/tg_sweep_r50/97f81b0d_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"97f81b0d","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PVC3/lammps/thermal/tg_sweep_r50"}' > /tmp/polyjarvis/sentinels/done_97f81b0d.json
else
  echo '{"run_id":"97f81b0d","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_97f81b0d.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_97f81b0d

