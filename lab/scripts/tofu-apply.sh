#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
[[ -f lab/tofu/environments/lab/lab.tfplan ]] || { echo "Exécuter tofu:plan avant tofu:apply." >&2; exit 1; }
./lab/scripts/check-host.sh lab.tfplan
umask 077
tofu -chdir=lab/tofu/environments/lab apply -input=false lab.tfplan
./lab/scripts/inventory-generate.sh
