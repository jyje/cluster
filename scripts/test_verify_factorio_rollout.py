import unittest

from verify_factorio_rollout import (
    VerificationError, check_app, check_gateway, check_restart, check_service, check_volume,
)


class RolloutTest(unittest.TestCase):
    def test_exact_sync_revision(self):
        status = {
            "operationState": {"phase": "Succeeded", "syncResult": {"revision": "expected"}},
            "sync": {"status": "Synced", "revision": "expected"},
            "health": {"status": "Healthy"},
        }
        check_app({"status": status}, "expected")
        with self.assertRaisesRegex(VerificationError, "exact requested revision"):
            check_app({"status": status}, "wrong")

    def test_only_udp_service(self):
        game_port = {"port": 34197, "targetPort": 34197, "protocol": "UDP"}
        check_service({"spec": {"type": "ClusterIP", "ports": [game_port]}})
        with self.assertRaisesRegex(VerificationError, "exactly ClusterIP"):
            check_service({"spec": {"type": "ClusterIP", "ports": [game_port, {"protocol": "TCP"}]}})

    def test_claim_requires_matching_retain_volume(self):
        claim = {
            "metadata": {"annotations": {"argocd.argoproj.io/sync-options": "Prune=false,Delete=false"}, "uid": "c"},
            "status": {"phase": "Bound"},
        }
        pv = {"spec": {"persistentVolumeReclaimPolicy": "Retain", "claimRef": {"uid": "c"}}}
        check_volume(claim, pv)
        pv["spec"]["claimRef"]["uid"] = "different"
        with self.assertRaisesRegex(VerificationError, "both protected"):
            check_volume(claim, pv)

    def test_gateway_and_route_generations(self):
        def true(kind):
            return {"type": kind, "status": "True", "observedGeneration": 2}

        gateway = {"metadata": {"generation": 2}, "status": {"conditions": [true("Programmed")]}}
        parent = {
            "controllerName": "gateway.envoyproxy.io/gatewayclass-controller",
            "parentRef": {"name": "factorio", "namespace": "envoy-gateway-system", "sectionName": "game"},
            "conditions": [true("Accepted"), true("ResolvedRefs")],
        }
        route = {"metadata": {"generation": 2}, "status": {"parents": [parent]}}
        check_gateway(gateway, route)
        route["metadata"]["generation"] += 1
        with self.assertRaisesRegex(VerificationError, "resolved references"):
            check_gateway(gateway, route)

    def test_restart_checks_pod_storage_and_save(self):
        before = {
            "revision": "commit", "pod_uid": "old", "claim_uid": "claim",
            "volume_uid": "volume", "save_hashes": ["save-1", "save-2"],
        }
        after = before | {"pod_uid": "new", "save_hashes": ["save-2", "save-3"]}
        check_restart(before, after)
        with self.assertRaisesRegex(VerificationError, "not been replaced"):
            check_restart(before, before)
        with self.assertRaisesRegex(VerificationError, "claim or volume"):
            check_restart(before, after | {"volume_uid": "another"})
        with self.assertRaisesRegex(VerificationError, "fingerprint remains"):
            check_restart(before, after | {"save_hashes": ["different"]})


if __name__ == "__main__":
    unittest.main()
