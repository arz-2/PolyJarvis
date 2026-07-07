#!/bin/bash
export CUDA_VISIBLE_DEVICES=2
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_2ec568ec
cd /home/alexzhao/PolyJarvis/data/PVC2/lammps/thermal/tg_sweep_r160
env CUDA_VISIBLE_DEVICES=2 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PVC2/lammps/thermal/tg_sweep_r160/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PVC2/lammps/thermal/tg_sweep_r160/2ec568ec_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"2ec568ec","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PVC2/lammps/thermal/tg_sweep_r160"}' > /tmp/polyjarvis/sentinels/done_2ec568ec.json
else
  echo '{"run_id":"2ec568ec","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_2ec568ec.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_2ec568ec

