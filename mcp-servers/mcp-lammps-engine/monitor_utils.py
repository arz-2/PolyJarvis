"""Pure-logic helpers for run-completion monitoring.

Kept stdlib-only and free of the fastmcp server so the command-building logic
that the Monitor tool depends on can be unit-tested without importing server.py
(which pulls in fastmcp and the live RunManager). server.py imports these.
"""


def pidfile_path(run_id: str, sentinel_dir) -> str:
    """Path of the pidfile for a run. Single source of truth: the wrapper/chain
    writes its own ``$$`` here and build_watch_command reads it back, so the two
    sides cannot drift apart."""
    return f"{sentinel_dir}/pid_{run_id}"


def build_watch_command(
    sentinel_path: str,
    pidfile: str = "",
    progress_file: str = "",
    n_stages: int = 0,
) -> str:
    """Return the shell command passed to the Monitor tool to wait for a run.

    The command checks the completion sentinel FIRST on every iteration, then
    falls back to a process-liveness check by reading the pidfile written by the
    long-lived wrapper/chain (its own ``$$``). ``$!`` cannot be used: under
    ``setsid nohup bash … &`` it captures the short-lived setsid launcher, which
    exits within ~1 s — checking it would false-fail every healthy run.

    If the pidfile is missing or empty (the brief window before the wrapper
    writes it, or runs that never wrote one) the liveness branch is skipped and
    the command degrades to a pure sentinel-wait — never a false PROCESS_DEAD.
    When the PID is gone and no sentinel was written (wrapper OOM-killed, box
    rebooted), it emits ``PROCESS_DEAD_NO_SENTINEL`` and exits non-zero instead
    of hanging silently until the Monitor timeout. The 2 s recheck closes the
    race where the wrapper writes the sentinel and exits between iterations.

    When ``progress_file`` is given (chains), the command emits one ``PROGRESS``
    line per newly-completed stage — a discrete terminal notification with a
    small ASCII bar. Monitor is line-based, so this is per-stage, not an animated
    bar; one event per stage keeps it well under the too-many-events limit.

    Persistence: this command already loops to completion (``while [ ! -f
    "$SENTINEL" ]``) and the per-stage ``SEEN`` counter is persisted to
    ``$SENTINEL.seen`` so it survives re-arms without replaying already-seen
    stages. A multi-hour chain therefore needs no special "persistent monitor" —
    the ONLY reason the orchestrator re-arms (~hourly) is the Monitor *tool's*
    fixed ``timeout_ms`` cap (3.6e6 ms = 1 h), a harness limit, not a property of
    this command. Re-arming by calling ``watch_run`` again on a bare timeout is
    expected, cheap, and lossless — treat it as routine, not a sign of failure.
    """
    pidfile = pidfile or ""
    progress_file = progress_file or ""
    # emit_progress prints a PROGRESS line for each stage completed since last seen.
    # SEEN is persisted to a checkpoint file so re-arms don't replay already-seen lines.
    emit = (
        # Load SEEN from checkpoint (survives re-arms); default 0 on first arm.
        'SEEN_FILE="${SENTINEL}.seen"\n'
        'SEEN=$(cat "$SEEN_FILE" 2>/dev/null || echo 0)\n'
        'emit_progress() {\n'
        '  [ -n "$PROGRESS" ] && [ -f "$PROGRESS" ] || return 0\n'
        '  local total name bar i\n'
        # grep -c already prints 0 (and exits 1) on zero matches, so use || true,
        # not || echo 0, which would make total="0\\n0" and break the arithmetic.
        # The quote-optional pattern matches both progress writers: the chain writer emits
        # quoted JSON, but the Tg-sweep deck's `shell echo` goes through LAMMPS's input
        # parser, which strips the inner double quotes ({stage:T,status:done}).
        '  total=$(grep -cE \'"?status"?:"?done"?\' "$PROGRESS" 2>/dev/null || true)\n'
        '  [ -z "$total" ] && total=0\n'
        '  while [ "$SEEN" -lt "$total" ]; do\n'
        '    SEEN=$((SEEN+1))\n'
        '    echo "$SEEN" > "$SEEN_FILE"\n'
        '    name=$(grep -E \'"?status"?:"?done"?\' "$PROGRESS" | sed -n "${SEEN}p"'
        ' | sed -E \'s/.*"?stage"?:"?([^",}]+)"?.*/\\1/\')\n'
        '    bar=""; i=0; while [ "$i" -lt "$NSTAGES" ]; do'
        ' if [ "$i" -lt "$SEEN" ]; then bar="$bar#"; else bar="$bar-"; fi; i=$((i+1)); done\n'
        '    echo "PROGRESS [$bar] $SEEN/$NSTAGES done: $name"\n'
        '  done\n'
        '}\n'
    )
    return (
        f'SENTINEL="{sentinel_path}"; PIDFILE="{pidfile}"\n'
        f'PROGRESS="{progress_file}"; NSTAGES={int(n_stages)}\n'
        f'{emit}'
        f'while [ ! -f "$SENTINEL" ]; do\n'
        f'  emit_progress\n'
        f'  PID=$(cat "$PIDFILE" 2>/dev/null || true)\n'
        f'  if [ -n "$PID" ] && ! kill -0 "$PID" 2>/dev/null; then\n'
        f'    sleep 2; [ -f "$SENTINEL" ] && break\n'
        f"    echo 'PROCESS_DEAD_NO_SENTINEL'; exit 3\n"
        f'  fi\n'
        f'  sleep 30\n'
        f'done\n'
        f'emit_progress\n'
        f"echo 'RUN_COMPLETE'; cat \"$SENTINEL\"\n"
        f'rm -f "$SEEN_FILE"'
    )
