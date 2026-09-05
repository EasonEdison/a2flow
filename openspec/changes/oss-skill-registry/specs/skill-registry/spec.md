# Skill Registry Capability Specification

> Status: **PROPOSED**
> Runtime readiness: **NO READY**

## ADDED Requirements

### Requirement: Register a unique Skill catalog entry

The system MUST create a stable Skill identity for a valid `namespace + slug`, MUST enforce uniqueness across all application instances through PostgreSQL, and MUST return the same result for the same scoped idempotency key. Namespace, slug and identity become immutable after creation.

#### Scenario: Register a new Skill

- **GIVEN** an authorized author and no existing `demo/research-assistant` entry
- **WHEN** the author submits namespace `demo`, slug `research-assistant`, required display metadata and an idempotency key
- **THEN** the system returns one `skillId`, `metadataRevision = 1`, and `lifecycleState = ACTIVE`
- **AND** repeating the same request with the same idempotency key returns the same identity rather than creating a duplicate

### Requirement: Edit metadata without lost updates

The system MUST update editable catalog metadata only when `expectedMetadataRevision` matches the current value. It MUST NOT mutate immutable identity fields or silently overwrite a concurrent change.

#### Scenario: Reject a stale metadata update

- **GIVEN** a Skill whose current `metadataRevision` is 4
- **WHEN** one author successfully updates with expected revision 4 and another request still submits expected revision 4
- **THEN** the first update returns `metadataRevision = 5`
- **AND** the stale request returns a conflict containing current revision 5 and does not overwrite the stored metadata

### Requirement: Freeze an immutable Skill revision

The system MUST freeze a version draft atomically against its expected generation. A frozen `SkillRevisionRef`, revision envelope and `revisionDigest` MUST be immutable and independently addressable before final publication.

#### Scenario: Freeze a current draft generation

- **GIVEN** version draft generation 3 with a valid SemVer, package descriptor and declared capability requirements
- **WHEN** the author freezes it with `expectedGeneration = 3`
- **THEN** the system returns one stable `skillRevisionRef` and `revisionDigest`
- **AND** later draft edits or retries cannot modify the frozen revision
- **AND** a freeze request using an older generation is rejected as a conflict

### Requirement: Validate a Skill package without executing it

The system MUST verify descriptor size and digest, enforce bounded safe inspection, and validate the Agent Skills `SKILL.md` structure. It MUST NOT execute scripts, Markdown instructions or declared tools during registration.

#### Scenario: Validate a conforming package

- **GIVEN** a content-addressed artifact within configured limits whose root contains `SKILL.md` with valid `name` and `description`, and whose directory name matches `name`
- **WHEN** validation inspects the frozen Skill revision
- **THEN** structural and integrity checks are marked passed
- **AND** presence of `scripts/` does not cause any script to run
- **AND** an experimental `allowed-tools` field is recorded only as compatibility metadata, never as authorization

### Requirement: Fail closed on malformed or unsafe package structure

The system MUST produce stable, field/path-scoped validation errors for missing required metadata, name mismatch, path traversal, absolute paths, device files, escaping symlinks or configured resource-limit violations. Deterministic invalid input MUST NOT be retried automatically.

#### Scenario: Reject an unsafe package

- **GIVEN** a package containing a path traversal entry or escaping symlink, or lacking a valid root `SKILL.md`
- **WHEN** validation inspects the artifact
- **THEN** the report status is `FAILED` with a stable error code and safe path context
- **AND** no package content is executed or written outside the inspection boundary
- **AND** publication remains blocked

### Requirement: Fail closed on content-integrity mismatch

The system MUST recompute the artifact digest and observed size. It MUST NOT accept locator contents that differ from the registered descriptor, even if retrying the locator later would return another payload.

#### Scenario: Detect a mutable locator or corrupted artifact

- **GIVEN** a revision declaring digest D and size S
- **WHEN** the artifact provider returns bytes whose digest or size differs from D/S
- **THEN** validation reports an integrity failure
- **AND** the system does not substitute the returned digest, does not downgrade to a warning, and does not publish

### Requirement: Resolve and lock dependencies before publication

The system MUST resolve each required Capability SemVer range to an exact published `CapabilityReleaseRef` and digest during validation. Final publication MUST also require one exact `WorkflowReleaseRef` bound to the current `SkillRevisionRef`. Runtime MUST NOT resolve ranges dynamically.

#### Scenario: Block missing, stale or mismatched dependencies

- **GIVEN** a Skill revision whose required Capability range has no eligible release, whose previously locked release is revoked, or whose Workflow release points to another Skill revision
- **WHEN** validation or the final publish gate runs
- **THEN** publication is rejected with a dependency-specific error
- **AND** a previously passed report that is expired, policy-stale or dependency-stale cannot be reused
- **AND** the author must revalidate after dependencies become valid

### Requirement: Publish exactly one immutable release

The system MUST use the shared publication contract and a scoped idempotency key so concurrent or retried publish requests produce at most one release for a Skill SemVer. Only a successfully published release may appear in the public directory.

#### Scenario: Recover an ambiguous concurrent publication

- **GIVEN** a passed, current validation report, an exact matching Workflow release, an unused Skill SemVer and two application instances processing the same publish idempotency key
- **WHEN** the shared PublicationPort accepts the request but one caller loses the response
- **THEN** retries/query-by-key converge on the same `PublishedSkillRef`
- **AND** PostgreSQL contains one publication for the Skill SemVer
- **AND** directory lookup returns the immutable package descriptor, dependency lock and Workflow release only after public state is PUBLISHED
- **AND** no caller treats timeout alone as proof of failure or creates a second release
