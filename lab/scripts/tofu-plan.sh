#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
./lab/scripts/check-host.sh
tofu fmt -check -recursive lab/tofu
tofu -chdir=lab/tofu/environments/lab validate
umask 077
tofu -chdir=lab/tofu/environments/lab plan -input=false -out=lab.tfplan
./lab/scripts/check-host.sh lab.tfplan
