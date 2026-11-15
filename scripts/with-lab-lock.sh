#!/usr/bin/env bash
# One workstation process owns lab mutations at a time. The parent keeps fd 9
# open while children run; nested mise tasks reuse that ownership instead of
# deadlocking. This is an operator lock, not an authorization/security boundary.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${OPENHVX_LAB_LOCK_ROOT:-}" == "$PWD" ]]; then
  exec "$@"
fi
mkdir -p .lab
exec 9>.lab/deployment.lock
flock -n 9 || { echo 'Another lab operation is running. Wait for it to finish; do not delete the lock file.' >&2; exit 1; }
export OPENHVX_LAB_LOCK_ROOT="$PWD"
# Do not exec: the shell must retain the descriptor even when Python closes
# inherited descriptors before spawning its own children.
"$@"
