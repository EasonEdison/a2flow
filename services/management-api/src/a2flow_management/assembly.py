"""Thin composition root for the four released management features."""
from dataclasses import dataclass

from a2flow_asset_store.validation import namespace as validate_namespace
from a2ui_composer.management import create_application_feature
from a2flow_workflow_composer.management import create_workflow_feature
from capability_registry.management import create_ability_feature

from .contracts import ManagementError, TrustedManagementContext
from .features.skill import create_skill_feature
from .http import create_app
from .service import ManagementService


@dataclass(frozen=True)
class ManagementAssembly:
    service: ManagementService
    app: object


def create_management_app(*, reader, drafts, namespace, identity_resolver):
    """Compose one service/app; performs no I/O and starts no listener."""
    expected_namespace = validate_namespace(namespace)
    if getattr(reader, "namespace", None) != expected_namespace:
        raise ManagementError("READER_NAMESPACE_MISMATCH")
    repository = getattr(reader, "repository", None)
    reader_environment = getattr(repository, "environment", None)
    draft_environment = getattr(drafts, "environment", None)
    if reader_environment not in {"PRT", "ONLINE"}:
        raise ManagementError("READER_ENVIRONMENT_REQUIRED")
    if draft_environment != reader_environment:
        raise ManagementError("DRAFT_ENVIRONMENT_MISMATCH")
    validator = getattr(repository, "validator", None)
    ability_validator = getattr(validator, "ability", None)
    if validator is None or ability_validator is None:
        raise ManagementError("ASSET_VALIDATOR_REQUIRED")
    features = (
        create_skill_feature(reader, drafts, expected_namespace),
        create_ability_feature(
            reader, drafts, expected_namespace, ability_validator),
        create_application_feature(reader, drafts, expected_namespace),
        create_workflow_feature(
            reader, drafts, expected_namespace, validator),
    )
    service = ManagementService(features)

    def environment_identity(scope):
        identity = identity_resolver(scope)
        if (type(identity) is TrustedManagementContext
                and identity.environment != reader_environment):
            raise ManagementError("TRUSTED_ENVIRONMENT_MISMATCH", 403)
        return identity

    return ManagementAssembly(
        service, create_app(service, identity_resolver=environment_identity))
