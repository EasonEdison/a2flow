"""Authorized management facade for publication history and configuration selection."""
from a2flow_asset_store.records import AssetError
from skillweave_contracts.user_id import user_id_to_wire

from .contracts import ManagementError, require_admin, require_reader


_CONFLICTS = {
    "ASSET_CONFLICT", "STALE_SERVING_SELECTION",
    "SERVING_DEPENDENCY_MISMATCH",
}
_NOT_FOUND = {"ASSET_NOT_FOUND", "VERSION_NOT_FOUND"}


class PublicationService:
    def __init__(self, repository, namespace):
        for name in (
                "publication_history", "retained_version", "publish_candidate",
                "rollback_configuration"):
            if not callable(getattr(repository, name, None)):
                raise ManagementError("PUBLICATION_REPOSITORY_REQUIRED")
        self.repository = repository
        self.namespace = namespace

    @staticmethod
    def _translate(operation):
        try:
            return operation()
        except AssetError as error:
            if error.code in _CONFLICTS:
                raise ManagementError(error.code, 409) from None
            if error.code in _NOT_FOUND:
                raise ManagementError(error.code, 404) from None
            raise ManagementError(error.code, 400) from None

    def _environment(self, context):
        if context.environment != self.repository.environment:
            raise ManagementError("TRUSTED_ENVIRONMENT_MISMATCH", 403)

    def history(self, context, kind, key):
        require_reader(context)
        self._environment(context)
        return self._translate(lambda: self.repository.publication_history(
            self.namespace, kind, key))

    def version(self, context, kind, key, version_id):
        require_reader(context)
        self._environment(context)
        return self._translate(lambda: self.repository.retained_version(
            self.namespace, kind, key, version_id))

    def publish(self, context, kind, key, candidate, target,
                expected_serving_digest):
        require_admin(context)
        self._environment(context)
        if target.environment != context.environment:
            raise ManagementError("TARGET_ENVIRONMENT_MISMATCH")
        value = {
            "environment": target.environment,
            "versionId": target.version_id,
            "channel": target.channel,
            "grayUserIds": [user_id_to_wire(user) for user in target.gray_user_ids],
        }
        return self._translate(lambda: self.repository.publish_candidate(
            self.namespace, kind, key, candidate, value,
            expected_serving_digest))

    def rollback(self, context, kind, key, target,
                 expected_serving_digest):
        require_admin(context)
        self._environment(context)
        if target.environment != context.environment:
            raise ManagementError("TARGET_ENVIRONMENT_MISMATCH")
        value = {
            "environment": target.environment,
            "versionId": target.version_id,
            "channel": target.channel,
            "grayUserIds": [user_id_to_wire(user) for user in target.gray_user_ids],
        }
        return self._translate(lambda: self.repository.rollback_configuration(
            self.namespace, kind, key, target.version_id, value,
            expected_serving_digest))
