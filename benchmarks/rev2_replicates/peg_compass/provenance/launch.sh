#!/usr/bin/env bash
# Launch PEG_COMPASS_<i> locked runs: resume (never start), no recovery agent, advisory gates.
set -euo pipefail
cd /home/alexzhao/PolyJarvis
for RUN in "$@"; do
  case "$RUN" in PEG_COMPASS_[123]) ;; *) echo "refusing $RUN"; exit 1;; esac
  if pgrep -f "agent_api.py resume ${RUN}$" >/dev/null; then echo "$RUN already running"; continue; fi
  LOG="data/$RUN/raw/launch_$(date +%Y%m%d_%H%M%S).log"
  POLYJARVIS_GATES_ADVISORY=1 setsid nohup mcp-servers/.venv/bin/python \
    orchestration/scripts/agent_api.py resume "$RUN" > "$LOG" 2>&1 &
  WRAPPER=$!
  PID=""
  for _ in $(seq 1 20); do
    PID=$(pgrep -f "agent_api.py resume ${RUN}$" | head -1 || true)
    [ -n "$PID" ] && break
    sleep 0.5
  done
  if [ -z "$PID" ]; then echo "$RUN: no python process found (wrapper $WRAPPER); see $LOG"; exit 1; fi
  echo "$PID" > "data/$RUN/raw/launcher.pid"
  ADV=$(tr '\0' '\n' < /proc/$PID/environ | grep -c '^POLYJARVIS_GATES_ADVISORY=1$' || true)
  echo "$RUN: wrapper=$WRAPPER python_pid=$PID advisory_env=$ADV log=$LOG"
  sleep 20
done
