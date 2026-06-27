#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export PATH=/home/alexzhao/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/home/alexzhao/openmpi/lib:${LD_LIBRARY_PATH:-}
export OPAL_PREFIX=/home/alexzhao/openmpi
mkdir -p /tmp/polyjarvis/sentinels
echo $$ > /tmp/polyjarvis/sentinels/pid_1d134bae
cd /home/alexzhao/PolyJarvis/data/PE4/lammps/thermal/tg_sweep_r10
env CUDA_VISIBLE_DEVICES=0 /home/alexzhao/lammps-install/bin/lmp -sf gpu -pk gpu 1 -in /home/alexzhao/PolyJarvis/data/PE4/lammps/thermal/tg_sweep_r10/tg_sweep.in >> /home/alexzhao/PolyJarvis/data/PE4/lammps/thermal/tg_sweep_r10/1d134bae_wrapper.stdout 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"1d134bae","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PE4/lammps/thermal/tg_sweep_r10"}' > /tmp/polyjarvis/sentinels/done_1d134bae.json
else
  echo '{"run_id":"1d134bae","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis/sentinels/done_1d134bae.json
fi
rm -f /tmp/polyjarvis/sentinels/pid_1d134bae

