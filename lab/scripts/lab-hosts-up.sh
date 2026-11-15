#!/usr/bin/env bash
set -euo pipefail

if ! command -v mise >/dev/null 2>&1; then
  echo "mise est requis. Installez mise puis relancez." >&2
  exit 1
fi

cd "$(dirname "$0")/../.."
# Reconfiguring simulated hosts can interrupt their nested platform. When Linux
# management already exists, use the same admission/drain procedure before any
# host changes. A failed probe stops here; it is not permission to bypass it.
if [[ -f .lab/infra/linux.yml ]]; then
  mise run lab:maintenance:enter
fi
mise run bootstrap
mise run check:host
mise run tofu:init
mise run windows:prepare
mise run tofu:plan
mise run tofu:apply
mise run ansible:bootstrap
echo "Lab Windows hosts are ready. Platform configuration is a separate step."
if [[ -f .lab/infra/linux.yml ]]; then
  echo "Existing platform admission remains in maintenance; continue platform deployment or inspect and run lab:maintenance:resume."
fi
