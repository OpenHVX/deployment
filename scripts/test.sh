#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for script in scripts/*.sh lab/scripts/*.sh platform/*.sh; do bash -n "$script"; done
python -m unittest discover -s lab/tests -v
tofu fmt -check -recursive lab/tofu
tofu -chdir=lab/tofu/environments/lab init -backend=false -input=false -lockfile=readonly
tofu -chdir=lab/tofu/environments/lab validate
export ANSIBLE_CONFIG="$PWD/platform/ansible/ansible.cfg"
for playbook in platform/ansible/playbooks/*.yml; do
  ansible-playbook --syntax-check -i 'lab-hv01,' "$playbook"
done
printf 'Validation statique réussie. Les tests Windows/Hyper-V/OpenHVX nécessitent le lab.\n'
