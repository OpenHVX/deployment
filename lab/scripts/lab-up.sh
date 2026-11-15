#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
mise run lab:hosts:up
./lab/scripts/run-platform.sh
mise run test:lab
mise run lab:platform:up
echo "Hyper-V hosts, infrastructure VMs, Ceph and OpenHVX on K3s deployed."
