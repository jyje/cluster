import importlib.util
import unittest
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "scripts/check_argocd_chart_upgrade.py"
SPEC = importlib.util.spec_from_file_location("argocd_chart_upgrade", PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class SchemaComparisonTests(unittest.TestCase):
    def setUp(self):
        self.old = {"type": "object", "properties": {"spec": {
            "type": "object", "properties": {"enabled": {"type": "boolean"}}
        }}}

    def test_added_optional_field_is_allowed(self):
        new = {"type": "object", "properties": {"spec": {
            "type": "object", "properties": {"enabled": {"type": "boolean"},
                                               "added": {"type": "string"}}
        }}}
        self.assertEqual(module.compare_schemas(self.old, new), ([], []))

    def test_removed_field_is_rejected(self):
        new = {"type": "object", "properties": {"spec": {"type": "object"}}}
        self.assertIn("/spec/enabled", module.compare_schemas(self.old, new)[0])

    def test_tightened_required_is_rejected(self):
        new = {"type": "object", "properties": {"spec": {
            "type": "object", "required": ["enabled"],
            "properties": {"enabled": {"type": "boolean"}}
        }}}
        self.assertIn("/spec", module.compare_schemas(self.old, new)[1])

    def test_description_changes_are_ignored(self):
        new = {"type": "object", "properties": {"spec": {
            "type": "object", "description": "updated",
            "properties": {"enabled": {"type": "boolean", "description": "updated"}}
        }}}
        self.assertEqual(module.compare_schemas(self.old, new), ([], []))


if __name__ == "__main__":
    unittest.main()
