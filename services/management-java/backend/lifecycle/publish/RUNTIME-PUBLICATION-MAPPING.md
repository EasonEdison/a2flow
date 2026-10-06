# Java PostgreSQL publication

`JdbcRuntimeSkillPublicationAdapter` and `RuntimeAssetPublisher` persist SKILL,
ABILITY and APPLICATION material directly through `RuntimePublicationStore`.
The management publication process requires no Python interpreter, HTTP bridge,
bridge token or subprocess. The Python Runtime remains the consumer.

## Configuration

Each of PRT and ONLINE requires `A2FLOW_PUBLICATION_<ENV>_JDBC_URL`, `USER`,
`PASSWORD`, `DATABASE`, `NAMESPACE`. URLs must use PostgreSQL JDBC. Database names
must differ. Every transaction checks `current_database()` and the existing
`a2flow_asset_environment` marker; there is no alternate-environment fallback.
Credentials belong in the deployment secret environment, never source.

An operator provisions the asset-store schema and publication receipt migration
before use. The runtime does not initialize or alter schema.

## Persistence compatibility

The existing bytea tables and `AF-MVP-08-ASSETS-1` document contract are unchanged.
Canonical documents exclude `contentDigest`; their SHA-256 is stored separately.
JSON uses UTF-8, Unicode code-point key sorting, no whitespace, finite Python-style
floating point rendering and duplicate-key rejection. Exact compiler `payloadJson`
bytes are retained inside the Java runtime profile envelope.

Skill versions hash `[sourceId,sourceDigest,packageDigest]`; Java asset versions
hash `[sourceId,sourceDigest]`, both prefixed `java-`. Existing asset IDs survive
new versions. Request fingerprints and runtime receipt IDs retain the former
bridge algorithms, allowing retries to read prior receipt rows.

Archive validation checks roots, entries, traversal, duplicates, symlinks,
encryption, UTF-8 text and expansion limits. Skill dependencies come only from
the frozen snapshot; unsupported legacy component bindings fail explicitly.
Ability/Application validation preserves the Java compiler's complete envelope
and checks identity, payload digest, compiled catalog and declared capabilities.

Under the namespace advisory lock, the store validates retained hashes/identities,
dependency existence/cycles, serving references, all existing routing cohorts and
legacy Application ability/catalog pins. Legacy Ability/Component documents are
retained as already imported immutable material; this publisher does not accept
new legacy definitions or replace their original domain compilers.

One transaction retains the immutable candidate, changes serving with byte-level
CAS, verifies readback and inserts the receipt. Collision, missing dependencies,
stale CAS or readback failure rolls back. Matching receipt retries check retained
bytes and return the original receipt without changing serving. SQL/commit errors
report an uncertain outcome; callers retry only with the same request identity.

Publication selects PRT CURRENT or ONLINE STABLE; existing Java release governance
continues owning gray admission. This migration does not add gray Skill publishing.
Runtime resolves current assets per trusted environment/user and requires no card
RESET after publication.

## Verification

`PublicationMaterialTest` checks canonical JSON, archive rejection and envelopes.
`PublicationJdbcAdapterTest` targets explicitly configured isolated PostgreSQL
databases and checks receipts, collision, stale CAS, failed-write rollback,
Ability/Application materials and environment separation.
`publication_reader_parity.py` reads those rows through the real Python asset
repository/reader and compares deterministic random numeric/Unicode fixtures to
Python canonical JSON. This is test tooling only, not a management dependency.

Source/build verification does not imply deployment or browser acceptance.
