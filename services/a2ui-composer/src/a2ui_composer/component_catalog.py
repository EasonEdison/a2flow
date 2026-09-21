"""Management of declarative A2UI component catalogs.

Catalogs register a subset of renderer implementations. They never upload or
execute JavaScript; the renderer-owned manifest below remains authoritative.
"""

import hashlib

from a2flow_asset_store.records import canonical as asset_canonical
from a2flow_asset_store.records import digest
from a2flow_management import (
    ManagedDraft,
    ManagementError,
    ManagementFeature,
    PublicationPlan,
    ValidationReport,
    parse_draft_structure,
)
from skillweave_contracts import TrustedContext, parse_identifier

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
    """Return detached renderer contracts for the M-side catalog editor."""
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
        raise ManagementError("INVALID_COMPONENT_CATALOG")
    if definition["catalogKey"] != key:
        raise ManagementError("COMPONENT_CATALOG_KEY_MISMATCH")
    parse_identifier(definition["catalogKey"])
    parse_identifier(definition["protocolProfileRef"])
    if definition["protocolProfileRef"] != _IMPLEMENTED_PROTOCOL:
        raise ManagementError("UNSUPPORTED_COMPONENT_PROTOCOL")
    components = definition["components"]
    if (
        type(components) is not list
        or not components
        or len(components) > len(_IMPLEMENTED_COMPONENTS)
        or any(type(name) is not str for name in components)
    ):
        raise ManagementError("INVALID_COMPONENT_DECLARATIONS")
    if len(components) != len(set(components)):
        raise ManagementError("INVALID_COMPONENT_DECLARATIONS")
    if any(name not in _IMPLEMENTED_COMPONENTS for name in components):
        raise ManagementError("COMPONENT_NOT_IMPLEMENTED")
    return {
        "catalogKey": definition["catalogKey"],
        "protocolProfileRef": definition["protocolProfileRef"],
        "components": list(components),
    }


def validate_catalog_compatibility(application, catalog, component_names=None):
    if type(application) is not dict or type(catalog) is not dict:
        raise ManagementError("APPLICATION_COMPONENT_CATALOG_INVALID")
    asset = application.get("asset")
    if type(asset) is not dict:
        raise ManagementError("APPLICATION_COMPONENT_CATALOG_INVALID")
    catalog_key = asset.get("componentCatalogRef")
    normalized = validate_component_definition(catalog_key, catalog)
    if normalized["protocolProfileRef"] != asset.get("protocolProfileRef"):
        raise ManagementError("APPLICATION_COMPONENT_PROTOCOL_MISMATCH")
    if component_names is None:
        template = application.get("surfaceTemplate")
        components = template.get("components") if type(template) is dict else None
        if type(components) is not list:
            raise ManagementError("APPLICATION_COMPONENT_CATALOG_INVALID")
        component_names = {item.get("component") for item in components if type(item) is dict}
    if not set(component_names) <= set(normalized["components"]):
        raise ManagementError("APPLICATION_COMPONENT_NOT_REGISTERED")
    return True


def _component_document(key, document):
    if (
        type(document) is not dict
        or set(document) != {"definition", "dependencies"}
        or document.get("dependencies") != []
    ):
        raise ManagementError("INVALID_COMPONENT_DRAFT_FIELDS")
    return {
        "definition": validate_component_definition(key, document.get("definition")),
        "dependencies": [],
    }


class ComponentCatalogManagementFeature(ManagementFeature):
    kind = "COMPONENT"

    def __init__(self, reader, drafts, namespace):
        self.reader, self.drafts, self.namespace = reader, drafts, namespace

    @staticmethod
    def _runtime_context(context):
        return TrustedContext(context.user_id, context.environment)

    def _draft_context(self, context):
        if context.environment != self.drafts.environment:
            raise ManagementError("DRAFT_ENVIRONMENT_MISMATCH", 403)

    def _published(self, context, key):
        parse_identifier(key)
        try:
            return self.reader.resolve_asset(self.kind, key, self._runtime_context(context))
        except Exception as error:
            if getattr(error, "code", None) == "ASSET_NOT_FOUND":
                raise ManagementError("COMPONENT_CATALOG_NOT_FOUND", 404) from None
            raise

    def list_published(self, context):
        return self.reader.list_assets(self.kind, self._runtime_context(context))

    def get_published(self, context, key):
        published = self._published(context, key)
        return {
            "kind": self.kind,
            "key": key,
            "assetId": published["assetId"],
            "versionId": published["versionId"],
            "definition": published["definition"],
            "componentDeclarations": list(implemented_component_declarations()),
            "resolution": {
                "selection": published["selection"],
                "contentDigest": published["contentDigest"],
                "recordedVersions": published["recordedVersions"],
            },
        }

    def get_draft(self, context, key):
        parse_identifier(key)
        self._draft_context(context)
        draft = self.drafts.get(self.namespace, self.kind, key)
        if draft is not None:
            return draft
        return ManagedDraft.create(
            self.kind,
            key,
            0,
            {
                "definition": self._published(context, key)["definition"],
                "dependencies": [],
            },
            context.user_id,
        )

    def create_draft(self, context, key):
        parse_identifier(key)
        self._draft_context(context)
        if self.drafts.get(self.namespace, self.kind, key) is not None:
            raise ManagementError("DRAFT_ALREADY_EXISTS", 409)
        if self.reader.asset_exists(self.kind, key, self._runtime_context(context)):
            raise ManagementError("ASSET_ALREADY_EXISTS", 409)
        draft = ManagedDraft.create(
            self.kind,
            key,
            1,
            {
                "definition": {
                    "catalogKey": key,
                    "protocolProfileRef": "",
                    "components": [],
                },
                "dependencies": [],
            },
            context.user_id,
        )
        return self.drafts.create(self.namespace, draft)

    def save_draft(self, context, key, expected_revision, document):
        parse_identifier(key)
        self._draft_context(context)
        parse_draft_structure("COMPONENT", key, document)
        draft = ManagedDraft.create(self.kind, key, 0, document, context.user_id)
        return self.drafts.save(self.namespace, draft, expected_revision)

    def _validate_snapshot(self, draft):
        try:
            document = _component_document(draft.key, draft.document)
            definition = document["definition"]
            self.reader.repository.validator.validate_definition(self.kind, draft.key, definition)
        except ManagementError as error:
            return ValidationReport.failure(error.code)
        except Exception as error:
            return ValidationReport.failure(getattr(error, "code", "INVALID_COMPONENT_CATALOG"))
        return ValidationReport.success(document)

    def validate_draft(self, context, key):
        return self._validate_snapshot(self.get_draft(context, key))

    def comparison_document(self, context, key, document):
        parse_identifier(key)
        self._draft_context(context)
        if type(document) is not dict:
            raise ManagementError("DRAFT_NOT_COMPARABLE", 409)
        return document

    def retained_comparison_document(self, context, key, document):
        parse_identifier(key)
        if (
            type(document) is not dict
            or type(document.get("definition")) is not dict
            or document.get("dependencies") != []
        ):
            raise ManagementError("RETAINED_VERSION_NOT_COMPARABLE", 409)
        return {
            "definition": document["definition"],
            "dependencies": [],
        }

    def _asset_id(self, context, key):
        try:
            return self._published(context, key)["assetId"]
        except ManagementError as error:
            if error.code != "COMPONENT_CATALOG_NOT_FOUND":
                raise
        return "component-" + hashlib.sha256(key.encode()).hexdigest()[:24]

    def prepare_publication(self, context, key, expected_revision, target):
        draft = self.get_draft(context, key)
        if draft.revision != expected_revision:
            raise ManagementError("DRAFT_REVISION_CONFLICT", 409)
        report = self._validate_snapshot(draft)
        if not report.valid:
            raise ManagementError("DRAFT_NOT_PUBLISHABLE", 409)
        value = {
            "kind": self.kind,
            "key": key,
            "assetId": self._asset_id(context, key),
            "versionId": target.version_id,
            "definition": report.normalized["definition"],
            "dependencies": report.normalized["dependencies"],
        }
        candidate = {**value, "contentDigest": digest(asset_canonical(value))}
        return PublicationPlan.create(self.kind, key, draft.revision, target, candidate)


def create_component_feature(reader, drafts, namespace):
    return ComponentCatalogManagementFeature(reader, drafts, namespace)
