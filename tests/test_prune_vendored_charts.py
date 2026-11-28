import importlib.util
import unittest
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "scripts/prune_vendored_charts.py"
SPEC = importlib.util.spec_from_file_location("prune_vendored_charts", PATH)
prune = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prune)


def chart(*versions):
    return {("demo", "demo"): {f"helm/demo/demo-{v}": v for v in versions}}


def names(*versions):
    return [f"helm/demo/demo-{v}" for v in versions]


def deployed(*versions):
    return {f"demo-{v}": position for position, v in enumerate(versions)}


class VersionKeyTest(unittest.TestCase):
    def test_numbers_compare_numerically(self):
        self.assertGreater(prune.version_key("1.10.0"), prune.version_key("1.9.2"))

    def test_prerelease_sorts_before_release(self):
        self.assertLess(prune.version_key("v0.2.0-alpha.2"), prune.version_key("v0.2.0"))


class DeploymentOrderTest(unittest.TestCase):
    def test_latest_added_line_wins_and_flat_paths_count(self):
        order = prune.deployment_order([
            "+    path: helm/demo-1.0.0",
            "+    path: helm/demo/demo-2.0.0",
            "-    path: helm/demo/demo-2.0.0",
            "+    path: 'helm/demo/demo-1.0.0' # rollback",
            "+    # path: helm/demo/demo-3.0.0",
        ])
        self.assertGreater(order["demo-1.0.0"], order["demo-2.0.0"])
        self.assertNotIn("demo-3.0.0", order)


class SelectRemovalsTest(unittest.TestCase):
    def test_keeps_three_latest_deployments_and_pending_versions(self):
        removals = prune.select_removals(
            chart("1.0.0", "2.0.0", "3.0.0", "4.0.0", "5.0.0", "6.0.0"),
            deployed("1.0.0", "2.0.0", "3.0.0", "4.0.0"),
            {"helm/demo/demo-4.0.0"},
            set(),
        )
        self.assertEqual(removals, names("1.0.0"))

    def test_removes_skipped_version_that_was_never_deployed(self):
        removals = prune.select_removals(
            chart("1.0.0", "2.0.0", "3.0.0"),
            deployed("1.0.0", "3.0.0"),
            {"helm/demo/demo-3.0.0"},
            set(),
        )
        self.assertEqual(removals, names("2.0.0"))

    def test_orders_by_deployment_not_by_version(self):
        removals = prune.select_removals(
            chart("1.0.0", "2.0.0", "3.0.0", "4.0.0"),
            deployed("4.0.0", "3.0.0", "2.0.0", "1.0.0"),
            {"helm/demo/demo-1.0.0"},
            set(),
        )
        # 4.0.0 is newer than the referenced rollback target, so it stays as pending.
        self.assertEqual(removals, [])

    def test_retired_chart_keeps_only_deployed_history(self):
        removals = prune.select_removals(
            chart("1.0.0", "2.0.0"), deployed("1.0.0"), set(), set()
        )
        self.assertEqual(removals, names("2.0.0"))

    def test_never_deployed_chart_is_removed_unless_cataloged(self):
        self.assertEqual(
            prune.select_removals(chart("1.0.0", "2.0.0"), {}, set(), set()),
            names("1.0.0", "2.0.0"),
        )
        self.assertEqual(
            prune.select_removals(chart("1.0.0", "2.0.0"), {}, set(), {("demo", "demo")}),
            names("1.0.0"),
        )


if __name__ == "__main__":
    unittest.main()
