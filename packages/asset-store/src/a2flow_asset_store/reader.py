"""Single-snapshot environment-local resolution. Never invokes model or Tools."""
from skill_registry import (
    CatalogPort, MaterialPort, SkillMaterial, TrustedResolutionEvidence,
)
from skillweave_contracts import TrustedContext, TrustedInvocationContext
from skill_registry import TrustedContext as RegistryContext

from .records import AssetError, ResolvedAbility, ResolvedWorkflow, canonical
from .validation import entries, namespace


def owner_context(value):
    if isinstance(value, TrustedInvocationContext):
        value = value.trusted_context
    if isinstance(value, RegistryContext):
        value = TrustedContext(user_id=value.user_id, environment=value.environment)
    if type(value) is not TrustedContext:
        raise AssetError("TRUSTED_CONTEXT_REQUIRED")
    return value


class AssetReader(CatalogPort, MaterialPort):
    """Namespace and physical environment are injected by the trusted host."""
    def __init__(self, repository, namespace):
        self.repository = repository
        self.namespace = globals()["namespace"](namespace)

    def _snapshot(self, context):
        owner = owner_context(context)
        if owner.environment != self.repository.environment:
            raise AssetError("ENVIRONMENT_MISMATCH")
        bundle = self.repository.read(self.namespace)
        if bundle.environment != owner.environment or bundle.namespace != self.namespace:
            raise AssetError("DESTINATION_MISMATCH")
        return owner, bundle

    def _resolve(self, bundle, owner, kind, key):
        states = [s for s in bundle.serving if (s["kind"], s["key"]) == (kind, key)]
        if len(states) != 1:
            raise AssetError("ASSET_NOT_FOUND")
        state = states[0]
        if owner.environment == "PRT":
            version, selection = state["current"], "PRT_CURRENT"
        elif state["gray"] is not None and owner.user_id in state["grayUserIds"]:
            version, selection = state["gray"], "ONLINE_GRAY"
        else:
            version, selection = state["stable"], "ONLINE_STABLE"
        matches = [a for a in bundle.assets if a.identity == (kind, key, version)]
        if len(matches) != 1:
            raise AssetError("SELECTED_VERSION_MISSING")
        return matches[0], selection

    def _closure(self, bundle, owner, asset):
        found = {}
        def visit(current):
            key = current.kind + ":" + current.asset_id
            if key in found:
                if found[key] != current.version_id:
                    raise AssetError("VERSION_CONFLICT")
                return
            found[key] = current.version_id
            for dep in current.document["dependencies"]:
                child, _ = self._resolve(bundle, owner, dep["kind"], dep["key"])
                visit(child)
        visit(asset)
        return tuple(sorted(found.items()))

    def _read(self, kind, key, context):
        owner, bundle = self._snapshot(context)
        asset, selection = self._resolve(bundle, owner, kind, key)
        return owner, bundle, asset, selection, self._closure(bundle, owner, asset)

    def list_skills(self, trusted_context):
        owner, bundle = self._snapshot(trusted_context)
        result = []
        for state in bundle.serving:
            if state["kind"] == "SKILL":
                asset, _ = self._resolve(bundle, owner, "SKILL", state["key"])
                result.append({"skillKey": asset.key, "assetId": asset.asset_id,
                               "versionId": asset.version_id})
        return tuple(result)

    def load_skill(self, skill_key, trusted_context):
        owner, _, asset, selection, _ = self._read("SKILL", skill_key, trusted_context)
        material = entries(asset.definition)
        return SkillMaterial(material[0], material[1:],
            tuple(asset.definition["requiredToolNames"]), TrustedResolutionEvidence(
                skill_key, asset.asset_id, asset.version_id, asset.content_digest,
                owner.environment, selection, "asset:" + asset.content_digest[7:]))

    def resolve_workflow(self, definition_key, owner):
        _, _, asset, _, versions = self._read("WORKFLOW", definition_key, owner)
        return ResolvedWorkflow(canonical(asset.definition), versions)

    def list_workflows(self, owner):
        owner, bundle = self._snapshot(owner)
        result = []
        for state in bundle.serving:
            if state["kind"] == "WORKFLOW":
                asset, _ = self._resolve(bundle, owner, "WORKFLOW", state["key"])
                result.append({"definitionKey": asset.key, "inputSchema": {
                    "type": "object", "additionalProperties": False,
                    "required": ["requirement"], "properties": {"requirement": {
                        "type": "string", "minLength": 1, "maxLength": 2000}}}})
        return tuple(result)

    def versions(self, owner, definition_key):
        return self.resolve_workflow(definition_key, owner).effective_versions

    def resolve_ability(self, ability_key, invocation_context):
        _, _, asset, _, versions = self._read("ABILITY", ability_key, invocation_context)
        metadata = self.repository.validator.ability.validate(asset.definition).metadata
        if metadata is None:
            raise AssetError("INVALID_ABILITY")
        return ResolvedAbility(canonical(asset.definition), metadata, versions,
                               asset.asset_id, asset.version_id, asset.content_digest)

    def resolve_application(self, application_key, invocation_context):
        owner, bundle, asset, _, versions = self._read("APPLICATION", application_key, invocation_context)
        for action in asset.definition["actionPolicies"]:
            ability_key, expected_version = action["abilityReleaseRef"].split("@")
            resolved, _ = self._resolve(bundle, owner,
                                        "ABILITY", ability_key)
            if resolved.version_id != expected_version:
                raise AssetError("APPLICATION_BINDING_VERSION_MISMATCH")
        return {
            "application": asset.definition,
            "resolvedVersion": {"asset": {"assetType": "APPLICATION", "assetId": asset.asset_id},
                                "versionId": asset.version_id},
            "contentDigest": asset.content_digest, "recordedVersions": versions,
        }
