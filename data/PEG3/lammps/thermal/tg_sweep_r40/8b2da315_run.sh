#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_8b2da315
cd /home/alexzhao/PolyJarvis/data/PEG3/lammps/thermal/tg_sweep_r40
env CUDA_VISIBLE_DEVICES=0 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PEG3/lammps/thermal/tg_sweep_r40/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PEG3/lammps/thermal/tg_sweep_r40/8b2da315_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"8b2da315","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PEG3/lammps/thermal/tg_sweep_r40"}' > /tmp/polyjarvis/sentinels/done_8b2da315.json
else
  echo '{"run_id":"8b2da315","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_8b2da315.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_8b2da315

