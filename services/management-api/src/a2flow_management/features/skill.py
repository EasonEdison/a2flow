"""Skill management: browse, edit bounded drafts, validate and prepare release."""
import base64
import hashlib
import re

from a2flow_asset_store.records import canonical as asset_canonical, digest
from a2flow_asset_store.validation import entries as validate_entries
from skillweave_contracts import TrustedContext, parse_identifier, parse_skill_key
from skill_registry import validate_package_entries

from ..contracts import (
    ManagedDraft, ManagementError, PublicationPlan, ValidationReport,
)
from ..service import ManagementFeature
from .skill_workspace import SkillWorkspaceMixin

_FRONTMATTER = re.compile(r"\A---\n(?P<header>.*?)\n---\n", re.DOTALL)
_DRAFT_KEYS = {
    "metadata", "skillMd", "requiredToolNames", "abilityBindings",
    "applicationBindings", "resources",
}


def _closed(value, keys, code="INVALID_DRAFT_FIELDS"):
    if type(value) is not dict or set(value) != set(keys):
        raise ManagementError(code)


def _metadata(skill_md):
    match = _FRONTMATTER.match(skill_md)
    if match is None:
        raise ManagementError("SKILL_FRONTMATTER_REQUIRED")
    values = {}
    for line in match.group("header").splitlines():
        if ":" not in line:
            raise ManagementError("INVALID_SKILL_FRONTMATTER")
        key, value = line.split(":", 1)
        if key in values or key not in {"name", "description"} or not value.strip():
            raise ManagementError("INVALID_SKILL_FRONTMATTER")
        values[key] = value.strip()
    if set(values) != {"name", "description"}:
        raise ManagementError("INVALID_SKILL_FRONTMATTER")
    return values


def _verified(material):
    return validate_package_entries(
        (material.instruction_entry, *material.resource_entries))


def _required_tools(document):
    """Host tool requirements are platform-derived, never author-managed grants."""
    return [tool for field, tool in (
        ("abilityBindings", "execute_ability"),
        ("applicationBindings", "render_application"),
    ) if document.get(field)]


def _entry(handle, path, media_type, raw):
    return {
        "handleId": handle, "logicalPath": path, "mediaType": media_type,
        "byteSize": len(raw), "contentDigest": digest(raw),
        "base64": base64.b64encode(raw).decode("ascii"),
    }


class SkillManagementFeature(SkillWorkspaceMixin, ManagementFeature):
    kind = "SKILL"

    def __init__(self, reader, drafts, namespace):
        self.reader, self.drafts, self.namespace = reader, drafts, namespace

    def _runtime_context(self, context):
        return TrustedContext(context.user_id, context.environment)

    def _draft_context(self, context):
        if context.environment != self.drafts.environment:
            raise ManagementError("DRAFT_ENVIRONMENT_MISMATCH", 403)

    def list_published(self, context):
        runtime = self._runtime_context(context)
        result = []
        for descriptor in self.reader.list_skills(runtime):
            material = self.reader.load_skill(descriptor["skillKey"], runtime)
            meta = _metadata(_verified(material)[0].text)
            result.append({**descriptor, "name": meta["name"],
                           "description": meta["description"]})
        return tuple(result)

    def get_published(self, context, key):
        parse_skill_key(key)
        runtime = self._runtime_context(context)
        material = self.reader.load_skill(key, runtime)
        verified = _verified(material)
        meta = _metadata(verified[0].text)
        return {
            "kind": self.kind, "key": key, "metadata": meta,
            "skillMd": verified[0].text,
            "requiredToolNames": list(material.required_tool_names),
            "resources": [{
                "handleId": item.handle_id, "logicalPath": item.logical_path,
                "mediaType": item.media_type, "byteSize": item.byte_size,
                "contentDigest": item.content_digest,
            } for item in verified[1:]],
            "resolution": {
                "assetId": material.resolution_evidence.asset_id,
                "versionId": material.resolution_evidence.version_id,
                "contentDigest": material.resolution_evidence.content_digest,
                "selection": material.resolution_evidence.selection,
            },
        }

    def get_draft(self, context, key):
        parse_skill_key(key)
        self._draft_context(context)
        draft = self.drafts.get(self.namespace, self.kind, key)
        if draft is not None:
            return draft
        published = self.reader.resolve_asset(
            self.kind, key, self._runtime_context(context))
        definition = published["definition"]
        instruction, *resources = definition["entries"]
        skill_md = base64.b64decode(
            instruction["base64"], validate=True).decode("utf-8")
        document = {
            "metadata": _metadata(skill_md), "skillMd": skill_md,
            "requiredToolNames": list(definition["requiredToolNames"]),
            "abilityBindings": [item["key"] for item in published["dependencies"]
                                if item["kind"] == "ABILITY"],
            "applicationBindings": [item["key"] for item in published["dependencies"]
                                    if item["kind"] == "APPLICATION"],
            "resources": resources,
        }
        return ManagedDraft.create(
            self.kind, key, 0, document, context.user_id)

    def create_draft(self, context, key):
        parse_skill_key(key)
        self._draft_context(context)
        if self.drafts.get(self.namespace, self.kind, key) is not None:
            raise ManagementError("DRAFT_ALREADY_EXISTS", 409)
        if self.reader.asset_exists(self.kind, key, self._runtime_context(context)):
            raise ManagementError("ASSET_ALREADY_EXISTS", 409)
        name = key.rsplit("/", 1)[-1]
        document = {
            "metadata": {"name": name, "description": "待配置"},
            "skillMd": f"---\nname: {name}\ndescription: 待配置\n---\n\n",
            "requiredToolNames": [], "abilityBindings": [],
            "applicationBindings": [], "resources": [],
        }
        candidate = ManagedDraft.create(
            self.kind, key, 1, document, context.user_id)
        return self.drafts.create(self.namespace, candidate)

    def save_draft(self, context, key, expected_revision, document):
        parse_skill_key(key)
        self._draft_context(context)
        # Accept legacy clients/drafts but discard their authored tool selection.
        if type(document) is dict:
            document = {**document, "requiredToolNames": _required_tools(document)}
        candidate = ManagedDraft.create(
            self.kind, key, 1, document, context.user_id)
        return self.drafts.save(self.namespace, candidate, expected_revision)

    def _validate_document(self, document, context):
        if type(document) is dict:
            document = {**document, "requiredToolNames": _required_tools(document)}
        _closed(document, _DRAFT_KEYS)
        _closed(document["metadata"], {"name", "description"}, "INVALID_METADATA")
        for value in document["metadata"].values():
            if type(value) is not str or not 1 <= len(value) <= 2000:
                raise ManagementError("INVALID_METADATA")
        skill_md = document["skillMd"]
        if type(skill_md) is not str or not skill_md.strip():
            raise ManagementError("INVALID_SKILL_MD")
        if _metadata(skill_md) != document["metadata"]:
            raise ManagementError("SKILL_METADATA_MISMATCH")
        for field in ("requiredToolNames", "abilityBindings", "applicationBindings"):
            values = document[field]
            if type(values) is not list or len(values) > 64:
                raise ManagementError("INVALID_BINDINGS")
            for value in values:
                parse_identifier(value)
            if len(set(values)) != len(values):
                raise ManagementError("INVALID_BINDINGS")
        resources = document["resources"]
        if type(resources) is not list or len(resources) > 127:
            raise ManagementError("INVALID_RESOURCES")
        definition = {
            "entries": [_entry("skill-instructions", "SKILL.md", "text/markdown",
                               skill_md.encode("utf-8"))] + resources,
            "requiredToolNames": document["requiredToolNames"],
        }
        try:
            validate_entries(definition)
            for kind, field in (("ABILITY", "abilityBindings"),
                                ("APPLICATION", "applicationBindings")):
                for key in document[field]:
                    self.reader.resolve_asset(kind, key, self._runtime_context(context))
        except Exception as error:
            code = getattr(error, "code", "INVALID_SKILL_DRAFT")
            raise ManagementError(code) from None
        return definition

    def _validate_snapshot(self, draft, context):
        try:
            definition = self._validate_document(draft.document, context)
        except ManagementError as error:
            return ValidationReport.failure(error.code)
        return ValidationReport.success({
            "definition": definition,
            "dependencies": [
                *[{"kind": "ABILITY", "key": value}
                  for value in draft.document["abilityBindings"]],
                *[{"kind": "APPLICATION", "key": value}
                  for value in draft.document["applicationBindings"]],
            ],
        })

    def validate_draft(self, context, key):
        return self._validate_snapshot(self.get_draft(context, key), context)

    def comparison_document(self, context, key, document):
        parse_skill_key(key)
        self._draft_context(context)
        if type(document) is not dict:
            raise ManagementError("DRAFT_NOT_COMPARABLE", 409)
        return document

    def retained_comparison_document(self, context, key, document):
        parse_skill_key(key)
        if type(document) is not dict or type(document.get("definition")) is not dict:
            raise ManagementError("RETAINED_VERSION_NOT_COMPARABLE", 409)
        definition = document["definition"]
        instruction, *resources = definition.get("entries", ())
        if type(instruction) is not dict or type(instruction.get("base64")) is not str:
            raise ManagementError("RETAINED_VERSION_NOT_COMPARABLE", 409)
        try:
            skill_md = base64.b64decode(
                instruction["base64"], validate=True).decode("utf-8")
            metadata = _metadata(skill_md)
        except (ValueError, UnicodeDecodeError, ManagementError):
            raise ManagementError("RETAINED_VERSION_NOT_COMPARABLE", 409) from None
        dependencies = document.get("dependencies", [])
        return {
            "metadata": metadata,
            "skillMd": skill_md,
            "requiredToolNames": definition.get("requiredToolNames", []),
            "abilityBindings": [item.get("key") for item in dependencies
                                if type(item) is dict and item.get("kind") == "ABILITY"],
            "applicationBindings": [item.get("key") for item in dependencies
                                    if type(item) is dict and item.get("kind") == "APPLICATION"],
            "resources": resources,
        }

    def prepare_publication(self, context, key, expected_revision, target):
        self.require_clean_workspace(context, key)
        draft = self.get_draft(context, key)
        if draft.revision != expected_revision:
            raise ManagementError("DRAFT_REVISION_CONFLICT", 409)
        report = self._validate_snapshot(draft, context)
        if not report.valid:
            raise ManagementError("DRAFT_NOT_PUBLISHABLE", 409)
        normalized = report.normalized
        asset_id = "skill-" + hashlib.sha256(key.encode()).hexdigest()[:24]
        try:
            published = self.reader.resolve_asset(
                self.kind, key, self._runtime_context(context))
            asset_id = published["assetId"]
        except Exception as error:
            if getattr(error, "code", None) not in {"ASSET_NOT_FOUND"}:
                raise
        value = {
            "kind": self.kind, "key": key, "assetId": asset_id,
            "versionId": target.version_id,
            "definition": normalized["definition"],
            "dependencies": normalized["dependencies"],
        }
        candidate = {**value, "contentDigest": digest(asset_canonical(value))}
        return PublicationPlan.create(
            self.kind, key, draft.revision, target, candidate)


def create_skill_feature(reader, drafts, namespace):
    return SkillManagementFeature(reader, drafts, namespace)
