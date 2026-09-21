"""Explicit cross-environment publication from the control-plane draft."""
from .contracts import (
    ManagementError, PublicationPlan, PublicationTarget, TrustedManagementContext,
    canonical, require_admin,
)
from .publication import PublicationService


class ReleaseService:
    def __init__(self, service, repositories, namespace, source_environment):
        self.service = service
        self.repositories = repositories
        self.namespace = namespace
        self.source_environment = source_environment
        for environment, repository in repositories.items():
            if repository.environment != environment:
                raise ManagementError("RELEASE_REPOSITORY_ENVIRONMENT_MISMATCH")
        if ("PRT" in repositories and "ONLINE" in repositories
                and repositories["PRT"].database == repositories["ONLINE"].database):
            raise ManagementError("RELEASE_DATABASES_MUST_BE_SEPARATE")

    def _context(self, context, environment):
        require_admin(context)
        if context.environment != self.source_environment:
            raise ManagementError("TRUSTED_ENVIRONMENT_MISMATCH", 403)
        if environment not in self.repositories:
            raise ManagementError("RELEASE_TARGET_UNAVAILABLE", 409)
        return TrustedManagementContext(context.user_id, environment, context.roles)

    def targets(self, context):
        require_admin(context)
        targets = []
        for environment in ("PRT", "ONLINE"):
            item = {"environment": environment, "available": False,
                    "channels": ["CURRENT"] if environment == "PRT" else ["STABLE", "GRAY"]}
            if environment not in self.repositories:
                item["errorCode"] = "RELEASE_TARGET_NOT_CONFIGURED"
            else:
                try:
                    self._context(context, environment)
                    PublicationService._translate(
                        lambda: self.repositories[environment].read(self.namespace))
                    item["available"] = True
                except ManagementError as error:
                    item["errorCode"] = error.code
            targets.append(item)
        return {"sourceEnvironment": self.source_environment, "targets": targets}

    def history(self, context, environment, kind, key):
        target_context = self._context(context, environment)
        self.service._feature(kind)
        publications = PublicationService(self.repositories[environment], self.namespace)
        try:
            return publications.history(target_context, kind, key)
        except ManagementError as error:
            if error.code != "ASSET_NOT_FOUND":
                raise
            from hashlib import sha256
            return {"kind": kind, "key": key, "versions": [], "serving": None,
                    "servingDigest": "sha256:" + sha256(b"null").hexdigest()}

    def _plan(self, context, environment, kind, key, revision, target):
        self._context(context, environment)
        if target.environment != environment:
            raise ManagementError("TARGET_ENVIRONMENT_MISMATCH")
        # Domain preparation reads the source draft and source dependency pins.
        # The exact candidate then must independently validate in the target DB.
        source_target = PublicationTarget(
            self.source_environment, target.version_id,
            "CURRENT" if self.source_environment == "PRT" else "STABLE")
        source_plan = self.service.prepare_publication(
            context, kind, key, revision, source_target)
        return PublicationPlan.create(kind, key, source_plan.draft_revision,
                                      target, source_plan.candidate)

    def check(self, context, environment, kind, key, revision, target):
        plan = self._plan(context, environment, kind, key, revision, target)
        history = self.history(context, environment, kind, key)
        result = plan.to_mapping()
        checked = PublicationService._translate(
            lambda: self.repositories[environment].check_candidate(
                self.namespace, kind, key, plan.candidate, result["target"],
                history["servingDigest"]))
        result.update(checked)
        result["preparedRevision"] = plan.draft_revision
        result["validation"] = {"valid": True, "issues": []}
        return result

    def publish(self, context, environment, kind, key, revision, target,
                candidate, expected_serving_digest):
        plan = self._plan(context, environment, kind, key, revision, target)
        if canonical(plan.candidate) != canonical(candidate):
            raise ManagementError("PREPARED_CANDIDATE_MISMATCH", 409)
        target_context = self._context(context, environment)
        return PublicationService(self.repositories[environment], self.namespace).publish(
            target_context, kind, key, plan.candidate, target, expected_serving_digest)
