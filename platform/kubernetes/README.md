# OpenHVX on K3s

`render.py --work PRIVATE_DIRECTORY --ca CA_PEM` renders the current lab topology
from persistent private environment secrets and the source image tag. Output stays
in the private directory because it contains Kubernetes Secrets.

Resources include three-member MongoDB/RabbitMQ StatefulSets, three auth/gateway/
controller replicas, three WS brokers with stable identities and peer routing,
the Ceph connector, TLS ingress, and one Traefik instance per node.

See [the lab runbook](../../docs/lab-platform.md) for deployment, credentials,
verification, recovery, and current limits. `operations/` contains explicit operator
recovery tools; none is invoked automatically to bypass uncertain task outcomes.
