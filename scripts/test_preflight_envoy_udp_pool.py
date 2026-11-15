import ipaddress as ip
import unittest

from preflight_envoy_udp_pool import (
    LABEL, LEGACY_CONTROLLER, NAMESPACE, POOL, POOL_KEYS, PreflightError, check_gateway, preflight,
)


class PoolTest(unittest.TestCase):
    def setUp(self):
        # Synthetic fixture, not a live deployment address.
        self.address = "172.31.254.200"
        self.pool = {
            "metadata": {"name": POOL},
            "spec": {
                "autoAssign": False,
                "addresses": [self.address + "/32"],
                "serviceAllocation": {
                    "namespaces": [NAMESPACE],
                    "serviceSelectors": [{"matchLabels": {LABEL: "factorio"}}],
                },
            },
        }
        self.advertisements = [{"spec": {"ipAddressPools": [POOL]}}]

    def check(self, **overrides):
        args = {
            "pools": [self.pool], "advertisements": self.advertisements,
            "nodes": [], "services": [], "networks": [], "api_addresses": set(),
        }
        return preflight(**(args | overrides))

    def test_valid_pool(self):
        self.assertEqual(self.check(), ip.ip_address(self.address))

    def test_missing_pool(self):
        with self.assertRaisesRegex(PreflightError, "not been provisioned"):
            self.check(pools=[])

    def test_unsafe_pool_defaults(self):
        self.pool["spec"]["autoAssign"] = True
        with self.assertRaisesRegex(PreflightError, "disable auto-assignment"):
            self.check()

    def test_wrong_namespace(self):
        self.pool["spec"]["serviceAllocation"]["namespaces"].append("other")
        with self.assertRaisesRegex(PreflightError, "only the labeled game Service"):
            self.check()

    def test_selectorless_pool_requires_the_verified_legacy_version(self):
        del self.pool["spec"]["serviceAllocation"]
        with self.assertRaisesRegex(PreflightError, "verified legacy"):
            self.check()
        self.check(controller_image=LEGACY_CONTROLLER)

    def test_other_service_cannot_request_the_legacy_pool(self):
        with self.assertRaisesRegex(PreflightError, "explicitly requests"):
            self.check(services=[{"metadata": {"annotations": {POOL_KEYS[1]: POOL}}, "spec": {}}])
        with self.assertRaisesRegex(PreflightError, "already requested"):
            self.check(services=[{
                "metadata": {"annotations": {"metallb.universe.tf/loadBalancerIPs": self.address}},
                "spec": {},
            }])

    def test_overlapping_shared_range(self):
        shared = {"metadata": {"name": "shared"}, "spec": {"addresses": ["172.31.254.199-172.31.254.201"]}}
        with self.assertRaisesRegex(PreflightError, "overlaps another MetalLB pool"):
            self.check(pools=[self.pool, shared])

    def test_missing_advertisement(self):
        with self.assertRaisesRegex(PreflightError, "No L2Advertisement"):
            self.check(advertisements=[])

    def test_api_or_node_address(self):
        with self.assertRaisesRegex(PreflightError, "API endpoint"):
            self.check(api_addresses={ip.ip_address(self.address)})
        with self.assertRaisesRegex(PreflightError, "Kubernetes node"):
            self.check(nodes=[{"status": {"addresses": [{"type": "InternalIP", "address": self.address}]}}])

    def test_service_request(self):
        service = {"metadata": {"annotations": {"metallb.io/loadBalancerIPs": self.address}}, "spec": {}}
        with self.assertRaisesRegex(PreflightError, "already requested or in use"):
            self.check(services=[service])

    def test_cluster_network(self):
        with self.assertRaisesRegex(PreflightError, "Pod or Service network"):
            self.check(networks=["172.31.254.0/24"])

    def test_live_game_allocation(self):
        service = {
            "metadata": {
                "namespace": NAMESPACE,
                "labels": {
                    LABEL: "factorio",
                    "gateway.envoyproxy.io/owning-gateway-name": "factorio",
                    "gateway.envoyproxy.io/owning-gateway-namespace": NAMESPACE,
                },
                "annotations": {key: POOL for key in POOL_KEYS},
            },
            "spec": {"type": "LoadBalancer"},
            "status": {"loadBalancer": {"ingress": [{"ip": self.address}]}},
        }
        candidate = self.check(services=[service])
        check_gateway([service], {"status": {"addresses": [{"type": "IPAddress", "value": self.address}]}}, candidate)
        with self.assertRaisesRegex(PreflightError, "Gateway does not advertise"):
            check_gateway([service], {}, candidate)
        service["metadata"]["annotations"].clear()
        with self.assertRaisesRegex(PreflightError, "does not have exactly"):
            check_gateway([service], {}, candidate)


if __name__ == "__main__":
    unittest.main()
