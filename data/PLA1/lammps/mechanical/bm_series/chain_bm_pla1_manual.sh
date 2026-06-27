#!/bin/bash
# PLA1 Murnaghan BM series — bm_pla1_manual
SENTINEL_DIR=/tmp/polyjarvis/sentinels

echo '[bm_P-1000] starting'
cd /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P-1000
env CUDA_VISIBLE_DEVICES=0 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos comm host -in /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P-1000/bm_P-1000.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P-1000/bm_P-1000_stdout.log 2>&1 || { echo '[bm_P-1000] FAILED'; echo '{"run_id":"bm_pla1_manual","status":"failed","failed_at":"bm_P-1000"}' > $SENTINEL_DIR/done_bm_pla1_manual.json; exit 1; }
echo '[bm_P-1000] done'

echo '[bm_P-500] starting'
cd /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P-500
env CUDA_VISIBLE_DEVICES=0 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos comm host -in /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P-500/bm_P-500.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P-500/bm_P-500_stdout.log 2>&1 || { echo '[bm_P-500] FAILED'; echo '{"run_id":"bm_pla1_manual","status":"failed","failed_at":"bm_P-500"}' > $SENTINEL_DIR/done_bm_pla1_manual.json; exit 1; }
echo '[bm_P-500] done'

echo '[bm_P0] starting'
cd /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P0
env CUDA_VISIBLE_DEVICES=0 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos comm host -in /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P0/bm_P0.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P0/bm_P0_stdout.log 2>&1 || { echo '[bm_P0] FAILED'; echo '{"run_id":"bm_pla1_manual","status":"failed","failed_at":"bm_P0"}' > $SENTINEL_DIR/done_bm_pla1_manual.json; exit 1; }
echo '[bm_P0] done'

echo '[bm_P500] starting'
cd /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P500
env CUDA_VISIBLE_DEVICES=0 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos comm host -in /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P500/bm_P500.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P500/bm_P500_stdout.log 2>&1 || { echo '[bm_P500] FAILED'; echo '{"run_id":"bm_pla1_manual","status":"failed","failed_at":"bm_P500"}' > $SENTINEL_DIR/done_bm_pla1_manual.json; exit 1; }
echo '[bm_P500] done'

echo '[bm_P1000] starting'
cd /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P1000
env CUDA_VISIBLE_DEVICES=0 /home/arz2/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk -pk kokkos comm host -in /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P1000/bm_P1000.in >> /home/arz2/PolyJarvis/data/PLA1/lammps/mechanical/bm_series/bm_P1000/bm_P1000_stdout.log 2>&1 || { echo '[bm_P1000] FAILED'; echo '{"run_id":"bm_pla1_manual","status":"failed","failed_at":"bm_P1000"}' > $SENTINEL_DIR/done_bm_pla1_manual.json; exit 1; }
echo '[bm_P1000] done'

echo '{"run_id":"bm_pla1_manual","status":"completed","pressures":[-1000, -500, 0, 500, 1000]}' > $SENTINEL_DIR/done_bm_pla1_manual.json
