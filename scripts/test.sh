#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for script in scripts/*.sh lab/scripts/*.sh; do bash -n "$script"; done
python -m unittest discover -s tests -v
tofu fmt -check -recursive tofu
tofu -chdir=tofu/environments/lab init -backend=false -input=false -lockfile=readonly
tofu -chdir=tofu/environments/lab validate
export ANSIBLE_CONFIG="$PWD/ansible/ansible.cfg"
for playbook in ansible/playbooks/*.yml; do
  ansible-playbook --syntax-check -i tests/fixtures/inventory.yml "$playbook"
done
printf 'Validation statique réussie. Les tests Windows/Hyper-V/OpenHVX nécessitent le lab.\n'
