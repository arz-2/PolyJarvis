#!/bin/bash
export CUDA_VISIBLE_DEVICES=2
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_6ab56c73
cd /home/alexzhao/PolyJarvis/data/PVC4/lammps/thermal/tg_sweep_r25
env CUDA_VISIBLE_DEVICES=2 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PVC4/lammps/thermal/tg_sweep_r25/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PVC4/lammps/thermal/tg_sweep_r25/6ab56c73_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"6ab56c73","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PVC4/lammps/thermal/tg_sweep_r25"}' > /tmp/polyjarvis/sentinels/done_6ab56c73.json
else
  echo '{"run_id":"6ab56c73","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_6ab56c73.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_6ab56c73

