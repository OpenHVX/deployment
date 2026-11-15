#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export PLATFORM_PLAYBOOK=platform/ansible/playbooks/bootstrap.yml
exec ./lab/scripts/run-platform.sh "$@"
