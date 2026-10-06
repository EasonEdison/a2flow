"""Reusable bounded A2UI validators for asset-store and Runtime wiring."""

from .errors import ValidationError

from .component_catalog import validate_component_definition
from .validation import _definition_profile
from .schema import validate_json_data


def application_validator(value):
    try:
        if type(value) is not dict:
            return False
        asset = value.get("asset")
        if type(asset) is not dict or type(asset.get("applicationKey")) is not str:
            return False
        _definition_profile(asset["applicationKey"], value)
        return True
    except (ValidationError, ValueError, TypeError):
        return False


def component_validator(value):
    try:
        if type(value) is not dict or type(value.get("catalogKey")) is not str:
            return False
        validate_component_definition(value["catalogKey"], value)
        return True
    except (ValidationError, ValueError, TypeError):
        return False


def application_data_validator(application, value):
    """Validate the actual authored input schema, never fixed demo keys."""
    if application_validator(application) is not True:
        return False
    schema = application["surfaceTemplate"]["inputSchema"]
    try:
        return validate_json_data(schema, value)
    except ValidationError:
        return False
