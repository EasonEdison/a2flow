"""Generic A2UI profile checks independent from canonical demo equality."""

from copy import deepcopy
import importlib.util
import unittest

from a2flow_asset_store import BundleValidator
from a2ui_composer import (
    application_data_validator,
    application_validator,
    component_validator,
)
from activity_planning_demo import OperationCatalog, package_application_definition
from activity_planning_demo.bundle import NAMESPACE
from activity_planning_demo.package_bundle import make_package_bundle


class GenericProfileTests(unittest.TestCase):
    def test_three_node_package_bundle_passes_generic_validators(self):
        document = make_package_bundle("PRT")
        validator = BundleValidator(
            OperationCatalog(), application_validator=application_validator,
            component_validator=component_validator)
        result = validator.validate(
            document, expected_namespace=NAMESPACE,
            expected_environment="PRT")
        self.assertEqual(3, len([
            asset for asset in result.assets if asset.kind == "APPLICATION"]))

    def test_changed_label_is_not_tied_to_canonical_demo_bytes(self):
        application = package_application_definition(
            "activity-package.choose-plan")
        changed = deepcopy(application)
        changed["surfaceTemplate"]["components"][-1]["label"] = "Use this plan"
        self.assertTrue(application_validator(changed))

    @unittest.skipUnless(
        importlib.util.find_spec("jsonschema") is not None,
        "jsonschema is supplied by the deployment/test image")
    def test_data_validator_uses_actual_surface_input_schema(self):
        application = package_application_definition(
            "activity-package.display")
        valid = {
            "title": "Launch", "selectedPlan": "Plan A",
            "confirmedSchedule": "Tomorrow", "packageSummary": "Ready",
        }
        self.assertTrue(application_data_validator(application, valid))
        self.assertFalse(application_data_validator(
            application, {**valid, "unexpected": "denied"}))


if __name__ == "__main__":
    unittest.main()
