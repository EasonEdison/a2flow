"""Published asset validation shared by management and runtime hosts.

The operation registry is deliberately bounded to installed business adapters;
Application definitions are validated structurally, not against demo literals.
"""

from a2flow_asset_store import BundleValidator
from a2ui_composer import (
    application_validator, application_data_validator, component_validator,
)
from activity_planning_demo import OperationCatalog


def bundle_validator():
    return BundleValidator(
        OperationCatalog(), application_validator=application_validator,
        component_validator=component_validator,
    )
