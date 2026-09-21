"""Explicit cross-environment publication from the control-plane draft."""

from collections.abc import Mapping
from functools import partial
from typing import Protocol, cast

from .contracts import (
    AssetKind,
    Environment,
    JsonObject,
    JsonValue,
    ManagementError,
    PublicationPlan,
    PublicationTarget,
    PublicationTargetMapping,
    TrustedManagementContext,
    canonical,
    require_admin,
)
from .publication import PublicationRepository, PublicationService


class SourceManagementService(Protocol):
    def _feature(self, kind: AssetKind) -> object: ...

    def prepare_publication(
        self,
        context: TrustedManagementContext,
        kind: AssetKind,
        key: str,
        expected_revision: int,
        target: PublicationTarget,
    ) -> PublicationPlan: ...


class ReleaseRepository(PublicationRepository, Protocol):
    database: str

    def check_publication_ready(self, namespace: str) -> JsonObject: ...

    def check_candidate(
        self,
        namespace: str,
        kind: AssetKind,
        key: str,
        candidate: JsonObject,
        target: PublicationTargetMapping,
        expected_serving_digest: str,
    ) -> JsonObject: ...


class ReleaseService:
    def __init__(
        self,
        service: SourceManagementService,
        repositories: Mapping[Environment, ReleaseRepository],
        namespace: str,
        source_environment: Environment,
    ) -> None:
        self.service = service
        self.repositories = dict(repositories)
        self.namespace = namespace
        self.source_environment = source_environment
        for environment, repository in repositories.items():
            if repository.environment != environment:
                raise ManagementError("RELEASE_REPOSITORY_ENVIRONMENT_MISMATCH")
        if (
            "PRT" in repositories
            and "ONLINE" in repositories
            and repositories["PRT"].database == repositories["ONLINE"].database
        ):
            raise ManagementError("RELEASE_DATABASES_MUST_BE_SEPARATE")

    def _repository(self, environment: object) -> ReleaseRepository:
        if type(environment) is not str or environment not in self.repositories:
            raise ManagementError("RELEASE_TARGET_UNAVAILABLE", 409)
        return self.repositories[cast(Environment, environment)]

    def _context(
        self, context: TrustedManagementContext, environment: Environment
    ) -> TrustedManagementContext:
        require_admin(context)
        if context.environment != self.source_environment:
            raise ManagementError("TRUSTED_ENVIRONMENT_MISMATCH", 403)
        self._repository(environment)
        return TrustedManagementContext(context.user_id, environment, context.roles)

    def targets(self, context: TrustedManagementContext) -> JsonObject:
        require_admin(context)
        targets: list[JsonValue] = []
        environments: tuple[Environment, ...] = ("PRT", "ONLINE")
        for environment in environments:
            item: JsonObject = {
                "environment": environment,
                "available": False,
                "channels": ["CURRENT"] if environment == "PRT" else ["STABLE", "GRAY"],
            }
            if environment not in self.repositories:
                item["errorCode"] = "RELEASE_TARGET_NOT_CONFIGURED"
            else:
                try:
                    self._context(context, environment)
                    PublicationService._translate(
                        partial(
                            self.repositories[environment].check_publication_ready,
                            self.namespace,
                        )
                    )
                    item["available"] = True
                except ManagementError as error:
                    item["errorCode"] = error.code
            targets.append(item)
        return {"sourceEnvironment": self.source_environment, "targets": targets}

    def history(
        self,
        context: TrustedManagementContext,
        environment: Environment,
        kind: AssetKind,
        key: str,
    ) -> JsonObject:
        target_context = self._context(context, environment)
        self.service._feature(kind)
        publications = PublicationService(self._repository(environment), self.namespace)
        try:
            return publications.history(target_context, kind, key)
        except ManagementError as error:
            if error.code != "ASSET_NOT_FOUND":
                raise
            from hashlib import sha256

            return {
                "kind": kind,
                "key": key,
                "versions": [],
                "serving": None,
                "servingDigest": "sha256:" + sha256(b"null").hexdigest(),
            }

    def _plan(
        self,
        context: TrustedManagementContext,
        environment: Environment,
        kind: AssetKind,
        key: str,
        revision: int,
        target: PublicationTarget,
    ) -> PublicationPlan:
        self._context(context, environment)
        if target.environment != environment:
            raise ManagementError("TARGET_ENVIRONMENT_MISMATCH")
        # Domain preparation reads the source draft and source dependency pins.
        # The exact candidate then must independently validate in the target DB.
        source_target = PublicationTarget(
            self.source_environment,
            target.version_id,
            "CURRENT" if self.source_environment == "PRT" else "STABLE",
        )
        source_plan = self.service.prepare_publication(context, kind, key, revision, source_target)
        return PublicationPlan.create(
            kind, key, source_plan.draft_revision, target, source_plan.candidate
        )

    def check(
        self,
        context: TrustedManagementContext,
        environment: Environment,
        kind: AssetKind,
        key: str,
        revision: int,
        target: PublicationTarget,
    ) -> JsonObject:
        plan = self._plan(context, environment, kind, key, revision, target)
        history = self.history(context, environment, kind, key)
        result = cast(JsonObject, dict(plan.to_mapping()))
        serving_digest = history.get("servingDigest")
        if type(serving_digest) is not str:
            raise ManagementError("INVALID_SERVING_DIGEST", 500)
        checked = PublicationService._translate(
            lambda: self._repository(environment).check_candidate(
                self.namespace,
                kind,
                key,
                plan.candidate,
                plan.target.to_mapping(),
                serving_digest,
            )
        )
        result.update(checked)
        result["preparedRevision"] = plan.draft_revision
        result["candidateIdentity"] = {
            "kind": plan.kind,
            "key": plan.key,
            "versionId": plan.target.version_id,
            "contentDigest": plan.content_digest,
        }
        result["validation"] = {"valid": True, "issues": []}
        return result

    def publish(
        self,
        context: TrustedManagementContext,
        environment: Environment,
        kind: AssetKind,
        key: str,
        revision: int,
        target: PublicationTarget,
        candidate: JsonObject,
        expected_serving_digest: str,
    ) -> JsonObject:
        plan = self._plan(context, environment, kind, key, revision, target)
        if canonical(plan.candidate) != canonical(candidate):
            raise ManagementError("PREPARED_CANDIDATE_MISMATCH", 409)
        target_context = self._context(context, environment)
        return PublicationService(self._repository(environment), self.namespace).publish(
            target_context, kind, key, plan.candidate, target, expected_serving_digest
        )
