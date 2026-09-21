"""Ability management adapter for the shared A2Flow management service."""

import hashlib

from a2flow_management import (
    ManagedDraft,
    ManagementError,
    ManagementFeature,
    PublicationPlan,
    ValidationReport,
    parse_draft_structure,
)
from a2flow_management.contracts import canonical
from skillweave_contracts import TrustedContext, parse_identifier

_UNTRUSTED_ISSUE_CODES = {
    "ABILITY_FIELD_UNSUPPORTED",
    "ADAPTER_OPERATION_REF_INVALID",
    "ADAPTER_OPERATION_NOT_FOUND",
    "CREDENTIAL_REQUIREMENT_FIELD_UNSUPPORTED",
    "CREDENTIAL_REQUIREMENT_INVALID",
}


def _digest(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


class AbilityManagementFeature(ManagementFeature):
    """Browse and author Ability definitions without executing operations."""

    kind = "ABILITY"

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
                raise ManagementError("ABILITY_NOT_FOUND", 404) from None
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
            "resolution": {
                "selection": published["selection"],
                "contentDigest": published["contentDigest"],
            },
        }

    def get_draft(self, context, key):
        parse_identifier(key)
        self._draft_context(context)
        draft = self.drafts.get(self.namespace, self.kind, key)
        if draft is not None:
            return draft
        published = self._published(context, key)
        return ManagedDraft.create(self.kind, key, 0, published["definition"], context.user_id)

    def create_draft(self, context, key):
        parse_identifier(key)
        self._draft_context(context)
        if self.drafts.get(self.namespace, self.kind, key) is not None:
            raise ManagementError("DRAFT_ALREADY_EXISTS", 409)
        if self.reader.asset_exists(self.kind, key, self._runtime_context(context)):
            raise ManagementError("ASSET_ALREADY_EXISTS", 409)
        document = {
            "abilityKey": key,
            "adapterOperationRef": "",
            "credentialRequirements": [],
            "defaultSuccessPolicyRef": "",
            "inputBindings": [],
            "modelArgumentSchema": {},
            "outputSchema": {},
            "resolvedInputSchema": {},
            "resultInterpretationPolicies": [],
        }
        candidate = ManagedDraft.create(self.kind, key, 1, document, context.user_id)
        return self.drafts.create(self.namespace, candidate)

    def _validate_snapshot(self, draft):
        result = self.validator.validate(draft.document)
        if not result.is_valid:
            return ValidationReport(
                False,
                tuple(
                    {
                        "code": issue.code,
                        "path": issue.path,
                        "message": issue.message,
                    }
                    for issue in result.issues
                ),
            )
        return ValidationReport.success(draft.document)

    def _admit_draft(self, key, document):
        parse_draft_structure("ABILITY", key, document)
        result = self.validator.validate(document)
        if any(issue.code in _UNTRUSTED_ISSUE_CODES for issue in result.issues):
            raise ManagementError("UNTRUSTED_ABILITY_REFERENCE")

    def save_draft(self, context, key, expected_revision, document):
        parse_identifier(key)
        self._draft_context(context)
        self._admit_draft(key, document)
        candidate = ManagedDraft.create(self.kind, key, 1, document, context.user_id)
        return self.drafts.save(self.namespace, candidate, expected_revision)

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
        if type(document) is not dict or type(document.get("definition")) is not dict:
            raise ManagementError("RETAINED_VERSION_NOT_COMPARABLE", 409)
        return document["definition"]

    def _asset_id(self, context, key):
        try:
            return self._published(context, key)["assetId"]
        except ManagementError as error:
            if error.code != "ABILITY_NOT_FOUND":
                raise
        return "ability-" + hashlib.sha256(key.encode()).hexdigest()[:24]

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
            "definition": report.normalized,
            "dependencies": [],
        }
        candidate = {**value, "contentDigest": _digest(value)}
        return PublicationPlan.create(self.kind, key, draft.revision, target, candidate)


def create_ability_feature(reader, drafts, namespace, validator):
    """Construct an Ability feature from explicit Host-owned dependencies."""

    return AbilityManagementFeature(reader, drafts, namespace, validator)
