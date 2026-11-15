#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
tofu -chdir=lab/tofu/environments/lab init -input=false
