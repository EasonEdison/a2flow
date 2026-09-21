"""Workflow management for the sequential runtime-supported graph subset."""

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
from skillweave_contracts import TrustedContext, parse_identifier, parse_skill_key


class WorkflowManagementFeature(ManagementFeature):
    """Browse Workflow assets and prepare, but never execute, publication plans."""

    kind = "WORKFLOW"

    def __init__(self, reader, drafts, namespace, validator):
        self.reader = reader
        self.drafts = drafts
        self.namespace = namespace
        self.validator = validator

    def _runtime_context(self, context):
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
                raise ManagementError("WORKFLOW_NOT_FOUND", 404) from None
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
            "dependencies": published["dependencies"],
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
        published = self._published(context, key)
        definition = published["definition"]
        document = {
            "definitionKey": definition["definitionKey"],
            "topology": "SEQUENTIAL",
            "nodes": definition["nodes"],
        }
        return ManagedDraft.create(self.kind, key, 0, document, context.user_id)

    def create_draft(self, context, key):
        parse_identifier(key)
        self._draft_context(context)
        if self.drafts.get(self.namespace, self.kind, key) is not None:
            raise ManagementError("DRAFT_ALREADY_EXISTS", 409)
        if self.reader.asset_exists(self.kind, key, self._runtime_context(context)):
            raise ManagementError("ASSET_ALREADY_EXISTS", 409)
        candidate = ManagedDraft.create(
            self.kind,
            key,
            1,
            {"definitionKey": key, "topology": "SEQUENTIAL", "nodes": []},
            context.user_id,
        )
        return self.drafts.create(self.namespace, candidate)

    def _admit_draft(self, key, document):
        parsed = parse_draft_structure("WORKFLOW", key, document)
        for node in parsed.nodes:
            parse_identifier(node.nodeId)
            parse_skill_key(node.skillKey)

    def save_draft(self, context, key, expected_revision, document):
        parse_identifier(key)
        self._draft_context(context)
        self._admit_draft(key, document)
        candidate = ManagedDraft.create(self.kind, key, 1, document, context.user_id)
        return self.drafts.save(self.namespace, candidate, expected_revision)

    def _validate_snapshot(self, draft, context):
        document = draft.document
        try:
            self._admit_draft(draft.key, document)
        except ManagementError as error:
            return ValidationReport.failure(error.code)
        if document["topology"] != "SEQUENTIAL":
            return ValidationReport.failure("UNSUPPORTED_WORKFLOW_TOPOLOGY", "/topology")
        nodes = document["nodes"]
        definition = {
            "definitionKey": draft.key,
            "entryNodeId": nodes[0]["nodeId"] if nodes else None,
            "nodes": nodes,
        }
        try:
            self.validator.validate_definition(self.kind, draft.key, definition)
            seen = set()
            dependencies = []
            for node in nodes:
                skill_key = node["skillKey"]
                self.reader.resolve_asset("SKILL", skill_key, self._runtime_context(context))
                if skill_key not in seen:
                    seen.add(skill_key)
                    dependencies.append({"kind": "SKILL", "key": skill_key})
        except Exception as error:
            return ValidationReport.failure(getattr(error, "code", "INVALID_WORKFLOW_DRAFT"))
        return ValidationReport.success(
            {
                "definition": definition,
                "dependencies": dependencies,
            }
        )

    def validate_draft(self, context, key):
        return self._validate_snapshot(self.get_draft(context, key), context)

    def comparison_document(self, context, key, document):
        parse_identifier(key)
        self._draft_context(context)
        if type(document) is not dict:
            raise ManagementError("DRAFT_NOT_COMPARABLE", 409)
        return document

    def retained_comparison_document(self, context, key, document):
        parse_identifier(key)
        if type(document) is not dict or type(document.get("definition")) is not dict:
            raise ManagementError("RETAINED_VERSION_NOT_COMPARABLE", 409)
        definition = document["definition"]
        nodes = definition.get("nodes")
        if type(nodes) is not list:
            raise ManagementError("RETAINED_VERSION_NOT_COMPARABLE", 409)
        return {
            "definitionKey": definition.get("definitionKey", key),
            "topology": "SEQUENTIAL",
            "nodes": nodes,
        }

    def _asset_id(self, context, key):
        try:
            return self._published(context, key)["assetId"]
        except ManagementError as error:
            if error.code != "WORKFLOW_NOT_FOUND":
                raise
        return "workflow-" + hashlib.sha256(key.encode()).hexdigest()[:24]

    def prepare_publication(self, context, key, expected_revision, target):
        draft = self.get_draft(context, key)
        if draft.revision != expected_revision:
            raise ManagementError("DRAFT_REVISION_CONFLICT", 409)
        report = self._validate_snapshot(draft, context)
        if not report.valid:
            raise ManagementError("DRAFT_NOT_PUBLISHABLE", 409)
        normalized = report.normalized
        value = {
            "kind": self.kind,
            "key": key,
            "assetId": self._asset_id(context, key),
            "versionId": target.version_id,
            "definition": normalized["definition"],
            "dependencies": normalized["dependencies"],
        }
        candidate = {**value, "contentDigest": digest(asset_canonical(value))}
        return PublicationPlan.create(self.kind, key, draft.revision, target, candidate)


def create_workflow_feature(reader, drafts, namespace, validator):
    """Construct a Workflow feature from explicit Host-owned dependencies."""

    return WorkflowManagementFeature(reader, drafts, namespace, validator)
