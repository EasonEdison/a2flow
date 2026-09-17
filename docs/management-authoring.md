# Management creation, references, and comparison

The management UI supports ADMIN-only draft creation for SKILL, ABILITY, APPLICATION, and WORKFLOW. Select a kind and choose `新建`; the immutable key is validated by the backend. Creation writes revision 1 only. It does not retain a release or change serving state. ADMIN listings include unpublished drafts with `draftOnly: true` and `draftRevision`; USER listings remain published-only.

Draft-only assets obtain their empty history and CAS token from `GET /management/assets/{kind}/{key}/versions`. Clients must use the returned `servingDigest`; they must not synthesize an empty digest. A first ONLINE publication must target STABLE. Duplicate keys conflict even when the current user would not resolve an existing gray-routed publication, and the draft repository remains the atomic final guard for concurrent creation.

Reference controls use authorized published lists. Logical references store keys. Application ability release references store `key@versionId` from exact retained history. Loading, empty, unavailable, malformed, and history-error states are distinct. Malformed values are preserved and disabled until explicitly repaired in full JSON. History errors offer retry, and catalogs refresh after publication.

Version comparison is read-only. `GET /management/assets/{kind}/{key}/versions/{versionId}` returns an exact retained version with `document` mapped to the same authored representation accepted by `POST /management/assets/{kind}/{key}/comparison-documents`. Generated asset envelope fields are excluded; authored fields and unknown draft fields remain visible. Invalid but structurally valid draft objects can be compared, while malformed full JSON is reported locally. Draft comparison runs only on explicit request, and pending field buffers are visibly excluded.

Structured differences distinguish missing values, null, types, ordered arrays, reorder operations, and escaped JSON Pointer paths. Nested values are recursively summarized with depth, entry-count, and size bounds. Truncation always produces a visible `truncated` entry or marker.

## Compatible endpoints

- `GET /management/assets/{kind}`: published assets for USER; published plus draft-only summaries for ADMIN.
- `POST /management/assets/{kind}/{key:path}/draft`: create an ADMIN-only revision-1 draft with no request body.
- `GET /management/assets/{kind}/{key:path}/versions`: exact retained history and authoritative serving CAS, including the absent-history CAS for an existing ADMIN draft.
- `GET /management/assets/{kind}/{key:path}/versions/{versionId}`: exact retained version; no latest fallback; `document` is the authored comparison representation.
- `POST /management/assets/{kind}/{key:path}/comparison-documents`: map one ADMIN-supplied draft object to the authored comparison representation without publication-validity gating.

Existing draft save, validate, prepare, explicit publish, and rollback contracts are unchanged. Identity, roles, namespace, environment, and gray routing remain server-owned.
