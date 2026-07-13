#!/usr/bin/env bash
# Run one full pathway bundle with a fail-stop host-memory floor.
#
# Usage:
#   MIN_MEM_AVAILABLE_GIB=35 WATCHDOG_LOG=/path/watchdog.tsv \
#     ./analysis/run_with_memory_watchdog.sh COMMAND [ARG ...]
#
# This wrapper never promotes or verifies output. Use a fresh out-root, then run the pinned
# independent W4 verifier over every shipped byte before the bundle is admitted.
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "usage: $0 COMMAND [ARG ...]" >&2
  exit 64
fi

min_gib="${MIN_MEM_AVAILABLE_GIB:-35}"
poll_seconds="${WATCHDOG_POLL_SECONDS:-5}"
log="${WATCHDOG_LOG:-./pathway-memory-watchdog.tsv}"

if ! [[ "$min_gib" =~ ^[0-9]+$ ]] || (( min_gib < 1 )); then
  echo "MIN_MEM_AVAILABLE_GIB must be a positive integer" >&2
  exit 64
fi
if ! [[ "$poll_seconds" =~ ^[0-9]+$ ]] || (( poll_seconds < 1 )); then
  echo "WATCHDOG_POLL_SECONDS must be a positive integer" >&2
  exit 64
fi

min_kib=$((min_gib * 1024 * 1024))
mkdir -p "$(dirname "$log")"
printf 'timestamp_utc\tpid\tmem_available_kib\tmin_required_kib\n' > "$log"

# The pathway cosine is pure Python. BLAS threads add no speed and make a later fork start
# from an unnecessarily multi-threaded parent. These must be set before Python starts.
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

setsid "$@" &
pid=$!

terminate_group() {
  kill -TERM -- "-$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 1
  done
  kill -KILL -- "-$pid" 2>/dev/null || true
}
trap terminate_group INT TERM

while kill -0 "$pid" 2>/dev/null; do
  available_kib=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  printf '%s\t%s\t%s\t%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$pid" "$available_kib" "$min_kib" >> "$log"
  if (( available_kib < min_kib )); then
    echo "memory watchdog: MemAvailable ${available_kib} KiB fell below " \
         "${min_kib} KiB; terminating the unadmitted bundle" >&2
    terminate_group
    wait "$pid" 2>/dev/null || true
    exit 75
  fi
  sleep "$poll_seconds"
done

wait "$pid"
