"""Authorized management facade for publication history and configuration selection."""

from collections.abc import Callable
from typing import Protocol, TypeVar

from a2flow_asset_store.records import AssetError
from skillweave_contracts import AssetKind, Environment, JsonObject

from .contracts import (
    ManagementError,
    PublicationTarget,
    PublicationTargetMapping,
    TrustedManagementContext,
    require_admin,
    require_reader,
)

_CONFLICTS = {
    "ASSET_CONFLICT",
    "STALE_SERVING_SELECTION",
    "SERVING_DEPENDENCY_MISMATCH",
}
_NOT_FOUND = {"ASSET_NOT_FOUND", "VERSION_NOT_FOUND"}
Result = TypeVar("Result")


class PublicationRepository(Protocol):
    environment: Environment

    def publication_history(self, namespace: str, kind: AssetKind, key: str) -> JsonObject: ...

    def retained_version(
        self, namespace: str, kind: AssetKind, key: str, version_id: str
    ) -> JsonObject: ...

    def publish_candidate(
        self,
        namespace: str,
        kind: AssetKind,
        key: str,
        candidate: JsonObject,
        target: PublicationTargetMapping,
        expected_serving_digest: str,
    ) -> JsonObject: ...

    def rollback_configuration(
        self,
        namespace: str,
        kind: AssetKind,
        key: str,
        version_id: str,
        target: PublicationTargetMapping,
        expected_serving_digest: str,
    ) -> JsonObject: ...


class PublicationService:
    def __init__(self, repository: PublicationRepository, namespace: str) -> None:
        for name in (
            "publication_history",
            "retained_version",
            "publish_candidate",
            "rollback_configuration",
        ):
            if not callable(getattr(repository, name, None)):
                raise ManagementError("PUBLICATION_REPOSITORY_REQUIRED")
        self.repository = repository
        self.namespace = namespace

    @staticmethod
    def _translate(operation: Callable[[], Result]) -> Result:
        try:
            return operation()
        except AssetError as error:
            if error.code in _CONFLICTS:
                raise ManagementError(error.code, 409) from None
            if error.code in _NOT_FOUND:
                raise ManagementError(error.code, 404) from None
            raise ManagementError(error.code, 400) from None

    def _environment(self, context: TrustedManagementContext) -> None:
        if context.environment != self.repository.environment:
            raise ManagementError("TRUSTED_ENVIRONMENT_MISMATCH", 403)

    def history(self, context: TrustedManagementContext, kind: AssetKind, key: str) -> JsonObject:
        require_reader(context)
        self._environment(context)
        return self._translate(
            lambda: self.repository.publication_history(self.namespace, kind, key)
        )

    def version(
        self,
        context: TrustedManagementContext,
        kind: AssetKind,
        key: str,
        version_id: str,
    ) -> JsonObject:
        require_reader(context)
        self._environment(context)
        return self._translate(
            lambda: self.repository.retained_version(self.namespace, kind, key, version_id)
        )

    def publish(
        self,
        context: TrustedManagementContext,
        kind: AssetKind,
        key: str,
        candidate: JsonObject,
        target: PublicationTarget,
        expected_serving_digest: str,
    ) -> JsonObject:
        require_admin(context)
        self._environment(context)
        if target.environment != context.environment:
            raise ManagementError("TARGET_ENVIRONMENT_MISMATCH")
        return self._translate(
            lambda: self.repository.publish_candidate(
                self.namespace, kind, key, candidate, target.to_mapping(), expected_serving_digest
            )
        )

    def rollback(
        self,
        context: TrustedManagementContext,
        kind: AssetKind,
        key: str,
        target: PublicationTarget,
        expected_serving_digest: str,
    ) -> JsonObject:
        require_admin(context)
        self._environment(context)
        if target.environment != context.environment:
            raise ManagementError("TARGET_ENVIRONMENT_MISMATCH")
        return self._translate(
            lambda: self.repository.rollback_configuration(
                self.namespace,
                kind,
                key,
                target.version_id,
                target.to_mapping(),
                expected_serving_digest,
            )
        )
