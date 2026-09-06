# Skill Registry Capability Specification

> Baseline: SW-P1-20260907.2
> Status: **PROPOSED**
> Runtime readiness: **NO READY**

## ADDED Requirements

### Requirement: Separate discovery from authorized material loading

The system MUST expose descriptive Skill catalog metadata separately from instructions and resources. Browsing permission MUST NOT imply authorization to load a Skill body, resource bytes, package locator or credential.

#### Scenario: Ordinary user browses catalog metadata

- **GIVEN** an ordinary authenticated user can browse M-side assets
- **WHEN** the user lists available Skills
- **THEN** the response contains only authorized discovery fields such as skillKey, name, description, tags and availability
- **AND** it does not contain instructions, resource bytes, private locator, credential or administrator metadata

### Requirement: Restrict authoring to administrators

The system MUST allow administrators to create, edit, validate and publish Skill assets in the current M environment. It MUST deny the same operations to ordinary users even though they can browse and use authorized Skills.

#### Scenario: Ordinary user attempts to publish

- **GIVEN** an ordinary user with catalog browse and B-side Skill-use permission
- **WHEN** the user calls a create, edit, package-upload or publish operation
- **THEN** the operation is denied with the shared authorization error
- **AND** no draft, package reference or publication record is created

### Requirement: Use environment-local resolution

The system MUST resolve every Skill inside the trusted current environment. PRT MUST read only PRT current. ONLINE MUST read only ONLINE stable or one ONLINE gray version selected by trusted userId, never PRT, and MUST serve no third version.

#### Scenario: ONLINE caller cannot fall back to PRT

- **GIVEN** a Skill exists in PRT but has no eligible ONLINE release
- **WHEN** an ONLINE use_skill request is resolved
- **THEN** resolution returns Skill not found/unavailable for ONLINE
- **AND** it does not query or return the PRT release

#### Scenario: ONLINE gray uses trusted userId

- **GIVEN** ONLINE stable and ONLINE gray releases exist
- **WHEN** trusted backend context identifies a userId in the gray cohort
- **THEN** the resolver returns the ONLINE gray release and its version evidence
- **AND** a model-supplied userId, environment or gray target is rejected or ignored as untrusted input

### Requirement: Route all Skill usage through use_skill

The system MUST require Runtime to load published Skill instructions/resources through the authorized `use_skill` Tool. Native SDK directory activation, raw package locator access or direct registry body reads MUST NOT be alternate first-version entry paths.

#### Scenario: Deny native-directory bypass

- **GIVEN** a published Skill is visible in discovery metadata
- **WHEN** a caller attempts to activate it through a native SDK skills directory or a raw locator without use_skill authorization
- **THEN** material loading is denied
- **AND** no instructions or resources are projected into the agent context

### Requirement: Keep Skill reusable across conversation and Workflow

The system MUST publish instructions/resources independently from Workflow graphs. The same immutable Skill release MUST be consumable through use_skill in conversation and in any authorized Workflow node without package rewriting, mode flags, routing fields or Workflow-specific output adaptation.

#### Scenario: Reuse one package unchanged

- **GIVEN** the `evidence-first-brief` package has one skillKey, version and digest
- **WHEN** conversation execution and a Workflow Skill node each call use_skill with that skillKey
- **THEN** both resolve the same effective release for the same trusted environment/user context
- **AND** both receive byte-identical instructions/resources
- **AND** neither requires route, nextNode, workflowId or mode-specific output fields

### Requirement: Validate Agent Skills package structure without executing it

The system MUST validate a package against the approved Agent Skills-compatible profile, including required `SKILL.md`, complete name/description/compatibility constraints, name/directory match, digest/size and safe paths. `SKILL.md` and text references MUST be UTF-8. Binary assets MUST be handled as opaque media-typed bytes rather than rejected for not being UTF-8. Validation MUST NOT execute Markdown, scripts or tools.

#### Scenario: Accept the independent instruction sample

- **GIVEN** `examples/evidence-first-brief/` contains valid `SKILL.md` and a referenced read-only output guide
- **WHEN** the candidate validator inspects it
- **THEN** required metadata, name/directory match and reference existence pass
- **AND** the package has no Workflow-specific routing contract

#### Scenario: Reject unsafe or malformed packages

- **GIVEN** a package is missing SKILL.md, has an invalid name, name/directory mismatch, path traversal, absolute path, device file, escaping symlink or digest mismatch
- **WHEN** validation runs
- **THEN** validation fails closed with a stable candidate error code
- **AND** no content is executed and publication remains blocked

### Requirement: Separate deterministic package validation from execution authorization

The system MUST NOT infer execution permission or publication failure by scanning natural-language instructions. The presence of scripts, an experimental allowed-tools field, or ordinary instructions mentioning an authorized Tool MUST NOT itself grant permission or make an otherwise valid package fail. Phase 1 MAY preserve script bytes as non-executable resources. A structured request for an unsupported executable profile MUST be rejected explicitly and separately.

#### Scenario: Instruction mentions an authorized Tool

- **GIVEN** a structurally valid Skill body says to use execute_ability when the host authorizes it and may include allowed-tools metadata
- **WHEN** package validation runs
- **THEN** deterministic format/path/digest validation can pass
- **AND** no Tool permission is granted
- **AND** the validator does not reject the package merely because those words or metadata exist

#### Scenario: Revision requests an unsupported executable profile

- **GIVEN** a structured authoring/revision field explicitly requests a script-executable profile that Phase 1 does not support
- **WHEN** validation or use_skill admission runs
- **THEN** it returns the approved unsupported-execution-profile error
- **AND** no script runs
- **AND** ordinary instruction text is not used to infer this profile

### Requirement: Publish Skill independently from Workflow

The system MUST publish a Skill release without a WorkflowReleaseRef, graph binding or route/result adapter. Workflow definitions MAY reference a published Skill, but Skill publication MUST NOT depend on any Workflow.

#### Scenario: Publish a standalone Skill

- **GIVEN** an administrator has a valid Skill revision and approved shared publication inputs
- **WHEN** the administrator publishes the revision
- **THEN** one immutable Skill release is created by the shared publication contract
- **AND** the release contains no Workflow binding or routing fields
- **AND** multiple conversations and Workflows can reference it

### Requirement: Return version evidence for admission checks

A successful material load MUST include effective Skill release/version and configuration evidence needed by Runtime to compare execution/continue ingress with current configuration. The registry MUST NOT instruct Runtime to continue silently on a stale version.

#### Scenario: Effective version changes before continue

- **GIVEN** a waiting run recorded Skill version evidence V1
- **WHEN** the current trusted environment resolves V2 before continue
- **THEN** the material/resolver contract exposes the mismatch
- **AND** Runtime can block new work and prompt explicit Workflow reset
- **AND** the registry does not serve V1 as a frozen continuation fallback
