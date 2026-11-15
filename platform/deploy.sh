#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${PLATFORM_INVENTORY:?Set PLATFORM_INVENTORY to an existing host inventory}"
[[ -f "$PLATFORM_INVENTORY" ]] || { echo "Inventory not found: $PLATFORM_INVENTORY" >&2; exit 1; }
export ANSIBLE_CONFIG="$PWD/platform/ansible/ansible.cfg"
export ANSIBLE_COLLECTIONS_PATH="$PWD/.ansible/collections"
ansible-playbook -i "$PLATFORM_INVENTORY" "${PLATFORM_PLAYBOOK:-platform/ansible/playbooks/configure.yml}" "$@"
