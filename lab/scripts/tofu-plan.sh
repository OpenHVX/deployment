#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
./lab/scripts/check-host.sh
tofu fmt -check -recursive tofu
tofu -chdir=tofu/environments/lab validate
umask 077
tofu -chdir=tofu/environments/lab plan -input=false -out=lab.tfplan
./lab/scripts/check-host.sh lab.tfplan
