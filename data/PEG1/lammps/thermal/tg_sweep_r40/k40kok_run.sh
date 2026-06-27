#!/bin/bash
# Manual KOKKOS launch for PEG1 Tg sweep r40 (run_lammps_script lacks an engine arg).
# Full GPU offload via the KOKKOS binary: -k on g 1 -sf kk ; deck has `package kokkos gpu 1 comm no` and /kk styles.
export CUDA_VISIBLE_DEVICES=0
RUN=k40kok
SENT="/tmp/polyjarvis/sentinels/done_${RUN}.json"
PIDF="/tmp/polyjarvis/sentinels/pid_${RUN}"
mkdir -p /tmp/polyjarvis/sentinels
cd /home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r40
mpirun -np 1 /home/alexzhao/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk \
  -in tg_sweep.in >> k40kok_wrapper.stdout 2>&1 &
LMP=$!
echo "$LMP" > "$PIDF"
wait "$LMP"
RC=$?
if [ "$RC" -eq 0 ]; then
  echo '{"run_id":"k40kok","status":"completed","work_dir":"/home/alexzhao/PolyJarvis/data/PEG1/lammps/thermal/tg_sweep_r40"}' > "$SENT"
else
  echo '{"run_id":"k40kok","status":"failed","exit_code":"'"$RC"'"}' > "$SENT"
fi
rm -f "$PIDF"
