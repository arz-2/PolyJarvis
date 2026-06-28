#!/bin/bash
set -uo pipefail
RID=8e525d98r
LMP=/home/arz2/lammps-install/bin/lmp
DIR=/home/arz2/PolyJarvis/data/PMMA1/lammps/thermal/tg_sweep
SENTDIR=/tmp/polyjarvis/sentinels
mkdir -p "$SENTDIR"
echo $$ > "$SENTDIR/pid_$RID"
export CUDA_VISIBLE_DEVICES=1
export OMP_NUM_THREADS=1
cd "$DIR"
mpirun -np 4 $LMP -sf gpu -pk gpu 1 -in "$DIR/tg_sweep.in" >> "$DIR/${RID}_wrapper.stdout" 2>&1
RC=$?
if [ $RC -eq 0 ]; then
  echo "{\"run_id\":\"$RID\",\"status\":\"completed\",\"work_dir\":\"$DIR\",\"ts\":\"$(date -Iseconds)\"}" > "$SENTDIR/done_$RID.json"
else
  echo "{\"run_id\":\"$RID\",\"status\":\"failed\",\"exit_code\":\"$RC\",\"ts\":\"$(date -Iseconds)\"}" > "$SENTDIR/done_$RID.json"
fi
rm -f "$SENTDIR/pid_$RID"
