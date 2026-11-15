#!/usr/bin/env bash
set -euo pipefail

if ! command -v mise >/dev/null 2>&1; then
  echo "mise est requis. Installez mise puis relancez." >&2
  exit 1
fi

cd "$(dirname "$0")/../.."
mise run bootstrap
mise run check:host
mise run tofu:init
mise run windows:prepare
mise run tofu:plan
mise run tofu:apply
mise run ansible:bootstrap
echo "Lab Windows hosts are ready. Platform configuration is a separate step."
