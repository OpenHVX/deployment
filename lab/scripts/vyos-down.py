#!/usr/bin/env python3
"""Preview or apply destruction restricted to this deployment's VyOS VMs and disks."""
import argparse
from vyos_lifecycle import load_declaration, playbook, add_host_argument


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm', help='Exact deployment UUID shown by the preview')
    add_host_argument(parser)
    args = parser.parse_args()
    declaration = load_declaration()
    identity = declaration['vyos_deployment_id']
    if args.apply and args.confirm != identity:
        parser.error('Applying destruction requires --confirm '+identity)
    print('VyOS deployment:', identity, flush=True)
    playbook('vyos-down', args.host, {'vyos_destroy_apply': args.apply})
    print('Owned VyOS instances removed; shared image caches and infrastructure retained.' if args.apply else
          'Preview only. To apply, repeat with --apply --confirm '+identity)


if __name__ == '__main__':
    main()
