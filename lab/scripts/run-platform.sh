#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
if [[ -z "${LAB_WINDOWS_PASSWORD:-}" && -f .lab/windows-password ]]; then
  LAB_WINDOWS_PASSWORD=$(<.lab/windows-password)
  export LAB_WINDOWS_PASSWORD
fi
[[ -n "${LAB_WINDOWS_PASSWORD:-}" ]] || { echo "Missing lab Windows secret; run windows:prepare." >&2; exit 1; }
if [[ -f .lab/ca.pem ]]; then export REQUESTS_CA_BUNDLE="$PWD/.lab/ca.pem"; fi
export PLATFORM_INVENTORY="$PWD/environments/lab/inventory.yml"
exec ./scripts/deploy.sh "$@"
