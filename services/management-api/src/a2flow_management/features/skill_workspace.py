"""Database-backed file workspace, isolated from saved drafts and runtime assets."""
import base64
import hashlib

from a2flow_asset_store.validation import entries as validate_entries
from skillweave_contracts import parse_skill_key

from ..contracts import ManagedDraft, ManagementError, canonical


def _response_size(value):
    # Match the HTTP output bound before writes: never persist an unreadable tree
    # or commit successfully and then report an output-size failure to the editor.
    if len(canonical(value)) > 2 * 1024 * 1024:
        raise ManagementError("OUTPUT_TOO_LARGE", 413)


def workspace_namespace(namespace):
    # Reserved, bounded identity in the existing draft store, never an asset namespace.
    return "skill-workspace:" + hashlib.sha256(namespace.encode()).hexdigest()


class SkillWorkspaceMixin:
    def _workspace_row(self, key):
        return self.drafts.get(workspace_namespace(self.namespace), self.kind, key)

    def _document_entries(self, document):
        from .skill import _entry
        return [_entry("skill-instructions", "SKILL.md", "text/markdown",
                       document["skillMd"].encode("utf-8")), *document["resources"]]

    def get_workspace(self, context, key):
        parse_skill_key(key)
        self._draft_context(context)
        draft = self.get_draft(context, key)
        row = self._workspace_row(key)
        if row is not None and row.document["dirty"]:
            document = row.document
        else:
            document = {"baseDraftRevision": draft.revision,
                        "entries": self._document_entries(draft.document), "dirty": False}
        return {**document, "workspaceRevision": row.revision if row else 0}

    def _checked_workspace(self, context, key, expected_revision):
        if type(expected_revision) is not int or expected_revision < 0:
            raise ManagementError("INVALID_EXPECTED_REVISION")
        value = self.get_workspace(context, key)
        if value["workspaceRevision"] != expected_revision:
            raise ManagementError("WORKSPACE_REVISION_CONFLICT", 409)
        return value

    def _save_workspace(self, context, key, value, entries):
        # Validate package safety/limits/encoding, but allow unfinished SKILL.md prose.
        try:
            validate_entries({"entries": entries, "requiredToolNames": []})
        except Exception as error:
            raise ManagementError(getattr(error, "code", "INVALID_WORKSPACE_FILES")) from None
        document = {"baseDraftRevision": value["baseDraftRevision"],
                    "entries": entries, "dirty": True}
        _response_size({**document, "workspaceRevision": value["workspaceRevision"] + 1})
        candidate = ManagedDraft.create(self.kind, key, 1, document, context.user_id)
        try:
            saved = self.drafts.save(workspace_namespace(self.namespace), candidate,
                                     value["workspaceRevision"])
        except ManagementError as error:
            if error.code == "DRAFT_REVISION_CONFLICT":
                raise ManagementError("WORKSPACE_REVISION_CONFLICT", 409) from None
            raise
        return {**saved.document, "workspaceRevision": saved.revision}

    def save_workspace_file(self, context, key, expected_revision, path, media_type, encoded):
        from .skill import _entry
        value = self._checked_workspace(context, key, expected_revision)
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            raise ManagementError("INVALID_FILE_BASE64") from None
        if path == "SKILL.md" and media_type != "text/markdown":
            raise ManagementError("INVALID_INSTRUCTION_MEDIA_TYPE")
        entries = value["entries"]
        previous = next((entry for entry in entries if entry["logicalPath"] == path), None)
        handle = previous["handleId"] if previous else "file-" + hashlib.sha256(path.encode()).hexdigest()[:24]
        replacement = _entry(handle, path, media_type, raw)
        if previous is None:
            entries.append(replacement)
        else:
            entries = [replacement if entry["logicalPath"] == path else entry for entry in entries]
        return self._save_workspace(context, key, value, entries)

    def delete_workspace_file(self, context, key, expected_revision, path):
        value = self._checked_workspace(context, key, expected_revision)
        if path == "SKILL.md":
            raise ManagementError("INSTRUCTION_FILE_REQUIRED")
        entries = [entry for entry in value["entries"] if entry["logicalPath"] != path]
        if len(entries) == len(value["entries"]):
            raise ManagementError("WORKSPACE_FILE_NOT_FOUND", 404)
        return self._save_workspace(context, key, value, entries)

    def commit_workspace(self, context, key, expected_revision, expected_draft_revision):
        from .skill import _metadata
        value = self._checked_workspace(context, key, expected_revision)
        draft = self.get_draft(context, key)
        if (draft.revision != expected_draft_revision
                or value["baseDraftRevision"] != expected_draft_revision):
            raise ManagementError("WORKSPACE_BASE_DRAFT_CONFLICT", 409)
        if not value["dirty"]:
            return {"workspace": value, "draft": draft.to_mapping()}
        instruction, *resources = value["entries"]
        skill_md = base64.b64decode(instruction["base64"], validate=True).decode("utf-8")
        document = {**draft.document, "skillMd": skill_md,
                    "metadata": _metadata(skill_md), "resources": resources}
        candidate = ManagedDraft.create(self.kind, key, draft.revision + 1, document, context.user_id)
        cleaned = ManagedDraft.create(self.kind, key, 1, {
            "baseDraftRevision": draft.revision + 1,
            "entries": value["entries"], "dirty": False,
        }, context.user_id)
        _response_size({"workspace": {**cleaned.document, "workspaceRevision": expected_revision + 1},
                        "draft": candidate.to_mapping()})
        saved, workspace = self.drafts.commit_workspace(
            self.namespace, candidate, expected_draft_revision,
            workspace_namespace(self.namespace), cleaned, expected_revision)
        return {"workspace": {**workspace.document, "workspaceRevision": workspace.revision},
                "draft": saved.to_mapping()}

    def require_clean_workspace(self, context, key):
        parse_skill_key(key)
        self._draft_context(context)
        row = self._workspace_row(key)
        if row is not None and row.document["dirty"]:
            raise ManagementError("WORKSPACE_NOT_COMMITTED", 409)
