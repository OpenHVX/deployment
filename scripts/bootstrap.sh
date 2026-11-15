#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements.txt
export ANSIBLE_CONFIG="$PWD/platform/ansible/ansible.cfg"
export ANSIBLE_COLLECTIONS_PATH="$PWD/.ansible/collections"
.venv/bin/ansible-galaxy collection install -p "$PWD/.ansible/collections" -r platform/ansible/requirements.yml
