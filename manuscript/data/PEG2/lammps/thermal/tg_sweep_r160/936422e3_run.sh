#!/bin/bash
export CUDA_VISIBLE_DEVICES=3
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_936422e3
cd /home/alexzhao/PolyJarvis/data/PEG2/lammps/thermal/tg_sweep_r160
env CUDA_VISIBLE_DEVICES=3 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos -in /home/alexzhao/PolyJarvis/data/PEG2/lammps/thermal/tg_sweep_r160/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PEG2/lammps/thermal/tg_sweep_r160/936422e3_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"936422e3","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PEG2/lammps/thermal/tg_sweep_r160"}' > /tmp/polyjarvis/sentinels/done_936422e3.json
else
  echo '{"run_id":"936422e3","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_936422e3.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_936422e3

