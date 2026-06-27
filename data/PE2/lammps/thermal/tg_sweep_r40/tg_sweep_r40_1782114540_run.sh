#!/bin/bash
export CUDA_VISIBLE_DEVICES=1
export PATH=/home/arz2/openmpi/bin:/usr/bin:$PATH
export LD_LIBRARY_PATH=/home/arz2/openmpi/lib:/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
mkdir -p /tmp/polyjarvis-run-sentinels
echo $$ > /tmp/polyjarvis-run-sentinels/TG_PID.tmp
cd /home/arz2/PolyJarvis/data/PE2/lammps/thermal/tg_sweep_r40
/home/arz2/lammps-install/bin/lmp -in /home/arz2/PolyJarvis/data/PE2/lammps/thermal/tg_sweep_r40/tg_sweep.in >> /home/arz2/PolyJarvis/data/PE2/lammps/thermal/tg_sweep_r40/tg_sweep_run.log 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo '{"run_id":"tg_sweep_r40_thermal","status":"completed","work_dir":"/home/arz2/PolyJarvis/data/PE2/lammps/thermal/tg_sweep_r40"}' > /tmp/polyjarvis-run-sentinels/done_tg_sweep_r40_thermal.json
else
  echo '{"run_id":"tg_sweep_r40_thermal","status":"failed","exit_code":"'$RC'"}' > /tmp/polyjarvis-run-sentinels/done_tg_sweep_r40_thermal.json
fi
rm -f /tmp/polyjarvis-run-sentinels/TG_PID.tmp
