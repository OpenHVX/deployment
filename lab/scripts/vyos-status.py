#!/usr/bin/env python3
"""Show current Hyper-V identities and state of the declared VyOS instances."""
import argparse
import json
from vyos_lifecycle import add_host_argument, status

parser = argparse.ArgumentParser(description=__doc__)
add_host_argument(parser)
args = parser.parse_args()
print(json.dumps(status(args.host), indent=2))
