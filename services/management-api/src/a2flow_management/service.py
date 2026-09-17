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
    def create_draft(self, context, key): ...
    def list_drafts(self, context):
        listing = getattr(self.drafts, "list", None)
        if not callable(listing):
            return ()
        return tuple({"kind": self.kind, "key": draft.key, "draftOnly": True,
                      "draftRevision": draft.revision}
                     for draft in listing(self.namespace, self.kind))

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
        published = tuple(self._feature(kind).list_published(context))
        if "ADMIN" not in context.roles:
            return published
        feature = self._feature(kind)
        drafts = getattr(feature, "list_drafts", lambda ignored: ())(context)
        known = {
            item.get("key", item.get("skillKey")) for item in published
        }
        return published + tuple(item for item in drafts if item["key"] not in known)

    def get_published(self, context, kind, key):
        require_reader(context)
        return self._feature(kind).get_published(context, key)

    def get_draft(self, context, kind, key):
        require_admin(context)
        return self._feature(kind).get_draft(context, key)

    def create_draft(self, context, kind, key):
        require_admin(context)
        return self._feature(kind).create_draft(context, key)

    def save_draft(self, context, kind, key, expected_revision, document):
        require_admin(context)
        return self._feature(kind).save_draft(context, key, expected_revision, document)

    def validate_draft(self, context, kind, key):
        require_admin(context)
        return self._feature(kind).validate_draft(context, key)

    def comparison_document(self, context, kind, key, document):
        require_admin(context)
        feature = self._feature(kind)
        comparison = getattr(feature, "comparison_document", None)
        if not callable(comparison):
            raise ManagementError("COMPARISON_NOT_SUPPORTED", 404)
        return comparison(context, key, document)

    def retained_comparison_document(self, context, kind, key, document):
        require_reader(context)
        feature = self._feature(kind)
        comparison = getattr(feature, "retained_comparison_document", None)
        if not callable(comparison):
            raise ManagementError("COMPARISON_NOT_SUPPORTED", 404)
        return comparison(context, key, document)

    def prepare_publication(self, context, kind, key, expected_revision, target):
        require_admin(context)
        if target.environment != context.environment:
            raise ManagementError("TARGET_ENVIRONMENT_MISMATCH")
        return self._feature(kind).prepare_publication(
            context, key, expected_revision, target)
