"""Bounded bundle validation and existing domain validators, no execution."""
import base64
import binascii
import re

from skill_registry import PackageEntry, PackageEntryDescriptor, validate_package_entries
from skillweave_contracts import parse_identifier, parse_skill_key
from capability_registry import AbilityDefinitionValidator, SharedResultPolicySetValidator

from .records import (
    Asset, AssetError, Bundle, KINDS, MAX_ASSETS, canonical, closed, digest,
)

_NAMESPACE = re.compile(r"[a-z][a-z0-9-]{0,63}")


def namespace(value):
    if type(value) is not str or not _NAMESPACE.fullmatch(value):
        raise AssetError("EXACT_NAMESPACE_REQUIRED")
    return value


def environment(value):
    if value not in ("PRT", "ONLINE"):
        raise AssetError("INVALID_ENVIRONMENT")
    return value


def entries(definition):
    closed(definition, {"entries", "requiredToolNames"})
    if type(definition["entries"]) is not list or not 1 <= len(definition["entries"]) <= 128:
        raise AssetError("INVALID_ENTRIES")
    result = []
    for entry in definition["entries"]:
        closed(entry, {"handleId", "logicalPath", "mediaType", "byteSize",
                       "contentDigest", "base64"})
        if type(entry["base64"]) is not str or len(entry["base64"]) > 6 * 1024 * 1024:
            raise AssetError("INVALID_ENTRY_BYTES")
        try:
            raw = base64.b64decode(entry["base64"], validate=True)
        except (ValueError, binascii.Error):
            raise AssetError("INVALID_ENTRY_BYTES") from None
        result.append(PackageEntry(PackageEntryDescriptor(
            entry["handleId"], entry["logicalPath"], entry["mediaType"],
            entry["byteSize"], entry["contentDigest"]), raw))
    verified = validate_package_entries(result)
    if verified[0].logical_path != "SKILL.md" or not verified[0].text:
        raise AssetError("INVALID_INSTRUCTIONS")
    names = definition["requiredToolNames"]
    if type(names) is not list or len(names) > 32:
        raise AssetError("INVALID_TOOL_HINTS")
    for name in names:
        parse_identifier(name)
    if len(set(names)) != len(names):
        raise AssetError("INVALID_TOOL_HINTS")
    return tuple(result)


class BundleValidator:
    """Application/component validators are required explicit host-owned bindings."""
    def __init__(self, operation_catalog, *, application_validator, component_validator):
        if not callable(application_validator) or not callable(component_validator):
            raise AssetError("VALIDATOR_REQUIRED")
        self.ability = AbilityDefinitionValidator(
            operation_catalog, SharedResultPolicySetValidator())
        self.application_validator = application_validator
        self.component_validator = component_validator

    def validate_definition(self, kind, key, definition):
        if kind == "SKILL":
            entries(definition)
        elif kind == "ABILITY":
            result = self.ability.validate(definition)
            if not result.is_valid or result.metadata.ability_key != key:
                raise AssetError("INVALID_ABILITY")
        elif kind == "WORKFLOW":
            if (set(definition) - {"definitionKey", "displayName",
                                   "entryNodeId", "nodes"}
                    or not {"definitionKey", "entryNodeId", "nodes"}
                    <= set(definition)):
                raise AssetError("UNSUPPORTED_WORKFLOW")
            nodes = definition["nodes"]
            if (definition["definitionKey"] != key or type(nodes) is not list
                    or not 2 <= len(nodes) <= 8):
                raise AssetError("UNSUPPORTED_WORKFLOW")
            if definition.get("displayName") is not None and (
                not isinstance(definition["displayName"], str)
                or not 1 <= len(definition["displayName"]) <= 200):
                raise AssetError("INVALID_WORKFLOW_DISPLAY_NAME")
            for node in nodes:
                if (set(node) - {"nodeId", "skillKey", "displayName"}
                        or not {"nodeId", "skillKey"} <= set(node)):
                    raise AssetError("UNSUPPORTED_WORKFLOW")
                parse_identifier(node["nodeId"])
                parse_skill_key(node["skillKey"])
                if node.get("displayName") is not None and (
                    not isinstance(node["displayName"], str)
                    or not 1 <= len(node["displayName"]) <= 200):
                    raise AssetError("INVALID_WORKFLOW_DISPLAY_NAME")
            if (len({node["nodeId"] for node in nodes}) != len(nodes)
                    or definition["entryNodeId"] != nodes[0]["nodeId"]):
                raise AssetError("INVALID_WORKFLOW_ENTRY")
        elif kind == "APPLICATION":
            if self.application_validator(definition) is not True:
                raise AssetError("INVALID_APPLICATION")
        elif kind == "COMPONENT":
            if self.component_validator(definition) is not True:
                raise AssetError("INVALID_COMPONENT")

    def validate(self, document, *, expected_namespace, expected_environment):
        namespace(expected_namespace)
        environment(expected_environment)
        canonical(document)
        closed(document, {"format", "namespace", "environment", "assets", "serving"})
        if document["format"] != "AF-MVP-08-ASSETS-1":
            raise AssetError("UNSUPPORTED_BUNDLE")
        if document["namespace"] != expected_namespace or document["environment"] != expected_environment:
            raise AssetError("DESTINATION_MISMATCH")
        source = document["assets"]
        if type(source) is not list or not 1 <= len(source) <= MAX_ASSETS:
            raise AssetError("ASSET_LIMIT")
        result, identities, ids = [], set(), {}
        for item in source:
            closed(item, {"kind", "key", "assetId", "versionId", "definition",
                          "dependencies", "contentDigest"})
            kind = item["kind"]
            if type(kind) is not str or kind not in KINDS:
                raise AssetError("UNKNOWN_ASSET_KIND")
            key = item["key"]
            (parse_skill_key if kind == "SKILL" else parse_identifier)(key)
            parse_identifier(item["assetId"])
            parse_identifier(item["versionId"])
            identity = kind, key, item["versionId"]
            if identity in identities:
                raise AssetError("DUPLICATE_ASSET")
            identities.add(identity)
            id_key = kind, item["assetId"]
            if id_key in ids and ids[id_key] != key:
                raise AssetError("ASSET_ID_ALIAS")
            ids[id_key] = key
            for previous in result:
                if (previous.kind, previous.key) == (kind, key) and previous.asset_id != item["assetId"]:
                    raise AssetError("ASSET_ID_CHANGED")
            deps = item["dependencies"]
            if type(deps) is not list or len(deps) > MAX_ASSETS:
                raise AssetError("INVALID_DEPENDENCIES")
            dep_keys = set()
            for dep in deps:
                closed(dep, {"kind", "key"})
                if type(dep["kind"]) is not str or dep["kind"] not in KINDS:
                    raise AssetError("INVALID_DEPENDENCIES")
                (parse_skill_key if dep["kind"] == "SKILL" else parse_identifier)(dep["key"])
                dk = dep["kind"], dep["key"]
                if dk in dep_keys:
                    raise AssetError("DUPLICATE_DEPENDENCY")
                dep_keys.add(dk)
            self.validate_definition(kind, key, item["definition"])
            if kind == "WORKFLOW":
                required = {("SKILL", n["skillKey"]) for n in item["definition"]["nodes"]}
                if not required <= dep_keys:
                    raise AssetError("MISSING_SKILL_BINDING")
            data = canonical({k: v for k, v in item.items() if k != "contentDigest"})
            if digest(data) != item["contentDigest"]:
                raise AssetError("DIGEST_MISMATCH")
            result.append(Asset(kind, key, item["assetId"], item["versionId"], data, digest(data)))
        serving = document["serving"]
        if type(serving) is not list or len(serving) > MAX_ASSETS:
            raise AssetError("INVALID_SERVING")
        seen = set()
        for state in serving:
            closed(state, {"kind", "key", "current", "stable", "gray", "grayUserIds"})
            sk = state["kind"], state["key"]
            if sk in seen:
                raise AssetError("DUPLICATE_SERVING")
            seen.add(sk)
            users = state["grayUserIds"]
            if type(users) is not list or len(users) > 1024:
                raise AssetError("INVALID_GRAY_USERS")
            for user in users:
                parse_identifier(user)
            if len(users) != len(set(users)):
                raise AssetError("INVALID_GRAY_USERS")
            if expected_environment == "PRT":
                if not state["current"] or state["stable"] is not None or state["gray"] is not None or users:
                    raise AssetError("INVALID_PRT_SERVING")
            elif state["current"] is not None or not state["stable"]:
                raise AssetError("INVALID_ONLINE_SERVING")
            if state["gray"] is None and users:
                raise AssetError("GRAY_VERSION_REQUIRED")
            if state["gray"] is not None and state["gray"] == state["stable"]:
                raise AssetError("DUPLICATE_SERVING_VERSION")
            for slot in ("current", "stable", "gray"):
                version = state[slot]
                if version is not None:
                    parse_identifier(version)
                    if (*sk, version) not in identities:
                        raise AssetError("MISSING_SERVING_VERSION")
        if seen != {(a.kind, a.key) for a in result}:
            raise AssetError("MISSING_SERVING_STATE")
        for asset in result:
            if asset.kind != "APPLICATION":
                continue
            document = asset.document
            declared = {(d["kind"], d["key"]) for d in document["dependencies"]}
            application = asset.definition
            component = application["asset"]["componentCatalogRef"]
            if ("COMPONENT", component) not in declared:
                raise AssetError("MISSING_COMPONENT_BINDING")
            for action in application["actionPolicies"]:
                reference = action["abilityReleaseRef"]
                if type(reference) is not str or reference.count("@") != 1:
                    raise AssetError("INVALID_ABILITY_RELEASE_REF")
                ability_key, version_id = reference.split("@")
                if ("ABILITY", ability_key) not in declared:
                    raise AssetError("MISSING_ABILITY_BINDING")
                if not any(a.kind == "ABILITY" and a.key == ability_key and a.version_id == version_id for a in result):
                    raise AssetError("MISSING_ABILITY_RELEASE")
        for asset in result:
            for dep in asset.document["dependencies"]:
                if (dep["kind"], dep["key"]) not in seen:
                    raise AssetError("MISSING_DEPENDENCY")
        # Check every authored version, not only today's selected versions.
        graph = {}
        for asset in result:
            graph.setdefault((asset.kind, asset.key), set()).update(
                (d["kind"], d["key"]) for d in asset.document["dependencies"])
        visited = set()
        def visit(key, stack):
            if key in stack:
                raise AssetError("CYCLIC_DEPENDENCY")
            if key in visited:
                return
            for child in graph[key]:
                visit(child, stack | {key})
            visited.add(key)
        for key in graph:
            visit(key, set())
        return Bundle(expected_namespace, expected_environment, tuple(result), canonical(serving))
