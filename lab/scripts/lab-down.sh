#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../tofu/environments/lab"
umask 077
tofu plan -destroy -input=false -out=destroy.tfplan
trap 'rm -f destroy.tfplan' EXIT
tofu show -no-color destroy.tfplan
read -r -p "Appliquer la destruction de tous les hôtes du lab affichés ? Saisir lab-hv01 : " answer
[[ "$answer" == "lab-hv01" ]] || { echo "Annulation."; exit 0; }
tofu apply -input=false destroy.tfplan
