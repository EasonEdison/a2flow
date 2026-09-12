"""One service composed from asset-kind management features."""
from abc import ABC, abstractmethod
from .contracts import ManagementError, require_admin, require_reader


class ManagementFeature(ABC):
    @property
    @abstractmethod
    def kind(self): ...
    @abstractmethod
    def list_published(self, context): ...
    @abstractmethod
    def get_published(self, context, key): ...
    @abstractmethod
    def get_draft(self, context, key): ...
    @abstractmethod
    def save_draft(self, context, key, expected_revision, document): ...
    @abstractmethod
    def validate_draft(self, context, key): ...
    @abstractmethod
    def prepare_publication(self, context, key, expected_revision, target): ...


class ManagementService:
    """Authorization stays centralized; modules cannot weaken it."""
    def __init__(self, features):
        self._features = {}
        for feature in features:
            if not isinstance(feature, ManagementFeature):
                raise ManagementError("INVALID_MANAGEMENT_FEATURE")
            if feature.kind in self._features:
                raise ManagementError("DUPLICATE_MANAGEMENT_FEATURE")
            self._features[feature.kind] = feature

    @property
    def kinds(self):
        return tuple(sorted(self._features))

    def _feature(self, kind):
        try:
            return self._features[kind]
        except KeyError:
            raise ManagementError("ASSET_KIND_NOT_REGISTERED", 404) from None

    def list_published(self, context, kind):
        require_reader(context)
        return self._feature(kind).list_published(context)

    def get_published(self, context, kind, key):
        require_reader(context)
        return self._feature(kind).get_published(context, key)

    def get_draft(self, context, kind, key):
        require_admin(context)
        return self._feature(kind).get_draft(context, key)

    def save_draft(self, context, kind, key, expected_revision, document):
        require_admin(context)
        return self._feature(kind).save_draft(context, key, expected_revision, document)

    def validate_draft(self, context, kind, key):
        require_admin(context)
        return self._feature(kind).validate_draft(context, key)

    def prepare_publication(self, context, kind, key, expected_revision, target):
        require_admin(context)
        if target.environment != context.environment:
            raise ManagementError("TARGET_ENVIRONMENT_MISMATCH")
        return self._feature(kind).prepare_publication(
            context, key, expected_revision, target)
