# MetalLB configuration

The address pools of this cluster are defined outside this repository, in the
environment's private configuration, because the addresses are LAN addresses.
Only the pool names are referenced here, for example `web-private` in
`clusters/r4spi/apps/higress.yaml`.

The node address pool that used to be defined here was removed together with
ingress-nginx. It held the addresses of the nodes themselves, so a LoadBalancer
Service that landed in it would answer ARP for an address a node already owns,
which broke the cluster once. Every pool must hold an address that no node owns.
