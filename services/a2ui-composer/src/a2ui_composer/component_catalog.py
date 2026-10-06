"""Renderer-owned component declarations and published catalog validation."""

from skillweave_contracts import parse_identifier
from .errors import ValidationError

_IMPLEMENTED_COMPONENTS = {
    "Button": {
        "fields": ["id", "component", "label", "action"],
        "purpose": "emit a declared action event",
    },
    "ChoicePicker": {
        "fields": ["id", "component", "options", "value", "variant"],
        "purpose": "select one value from bound options",
    },
    "Column": {
        "fields": ["id", "component", "children"],
        "purpose": "lay out declared child components",
    },
    "Text": {
        "fields": ["id", "component", "text"],
        "purpose": "render bound text",
    },
}
_IMPLEMENTED_PROTOCOL = "a2flow.mvp08.v1"


def implemented_component_declarations():
    """Return detached renderer contracts for catalog validation."""
    return tuple(
        {
            "name": name,
            "fields": list(contract["fields"]),
            "purpose": contract["purpose"],
        }
        for name, contract in sorted(_IMPLEMENTED_COMPONENTS.items())
    )


def validate_component_definition(key, definition):
    if type(definition) is not dict or set(definition) != {
        "catalogKey",
        "protocolProfileRef",
        "components",
    }:
        raise ValidationError("INVALID_COMPONENT_CATALOG")
    if definition["catalogKey"] != key:
        raise ValidationError("COMPONENT_CATALOG_KEY_MISMATCH")
    parse_identifier(definition["catalogKey"])
    parse_identifier(definition["protocolProfileRef"])
    if definition["protocolProfileRef"] != _IMPLEMENTED_PROTOCOL:
        raise ValidationError("UNSUPPORTED_COMPONENT_PROTOCOL")
    components = definition["components"]
    if (
        type(components) is not list
        or not components
        or len(components) > len(_IMPLEMENTED_COMPONENTS)
        or any(type(name) is not str for name in components)
    ):
        raise ValidationError("INVALID_COMPONENT_DECLARATIONS")
    if len(components) != len(set(components)):
        raise ValidationError("INVALID_COMPONENT_DECLARATIONS")
    if any(name not in _IMPLEMENTED_COMPONENTS for name in components):
        raise ValidationError("COMPONENT_NOT_IMPLEMENTED")
    return {
        "catalogKey": definition["catalogKey"],
        "protocolProfileRef": definition["protocolProfileRef"],
        "components": list(components),
    }


def validate_catalog_compatibility(application, catalog, component_names=None):
    if type(application) is not dict or type(catalog) is not dict:
        raise ValidationError("APPLICATION_COMPONENT_CATALOG_INVALID")
    asset = application.get("asset")
    if type(asset) is not dict:
        raise ValidationError("APPLICATION_COMPONENT_CATALOG_INVALID")
    catalog_key = asset.get("componentCatalogRef")
    normalized = validate_component_definition(catalog_key, catalog)
    if normalized["protocolProfileRef"] != asset.get("protocolProfileRef"):
        raise ValidationError("APPLICATION_COMPONENT_PROTOCOL_MISMATCH")
    if component_names is None:
        template = application.get("surfaceTemplate")
        components = template.get("components") if type(template) is dict else None
        if type(components) is not list:
            raise ValidationError("APPLICATION_COMPONENT_CATALOG_INVALID")
        component_names = {item.get("component") for item in components if type(item) is dict}
    if not set(component_names) <= set(normalized["components"]):
        raise ValidationError("APPLICATION_COMPONENT_NOT_REGISTERED")
    return True
