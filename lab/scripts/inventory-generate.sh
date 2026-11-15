#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
tofu -chdir=lab/tofu/environments/lab output -json | python lab/scripts/generate-inventory.py
