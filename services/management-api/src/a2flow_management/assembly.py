"""Thin composition root for the four released management features."""
from dataclasses import dataclass

from a2flow_asset_store.validation import namespace as validate_namespace
from a2ui_composer.component_catalog import create_component_feature
from a2ui_composer.management import create_application_feature
from a2flow_workflow_composer.management import create_workflow_feature
from capability_registry.management import create_ability_feature

from .contracts import ManagementError, TrustedManagementContext
from .dependencies import DependencyService
from .features.skill import create_skill_feature
from .http import create_app
from .publication import PublicationService
from .releases import ReleaseService
from .service import ManagementService


@dataclass(frozen=True)
class ManagementAssembly:
    service: ManagementService
    publications: PublicationService
    app: object


def create_management_app(*, reader, drafts, namespace, identity_resolver,
                          release_repositories=None):
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
        create_component_feature(reader, drafts, expected_namespace),
        create_workflow_feature(
            reader, drafts, expected_namespace, validator),
    )
    service = ManagementService(features)
    publications = PublicationService(repository, expected_namespace)
    dependencies = DependencyService(repository, drafts, expected_namespace)
    repositories = dict(release_repositories or {})
    repositories[reader_environment] = repository
    releases = ReleaseService(
        service, repositories, expected_namespace, reader_environment)

    def environment_identity(scope):
        identity = identity_resolver(scope)
        if (type(identity) is TrustedManagementContext
                and identity.environment != reader_environment):
            raise ManagementError("TRUSTED_ENVIRONMENT_MISMATCH", 403)
        return identity

    return ManagementAssembly(
        service, publications,
        create_app(service, identity_resolver=environment_identity,
                   publications=publications, dependencies=dependencies,
                   releases=releases))
