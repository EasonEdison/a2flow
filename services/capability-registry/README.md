# Capability Registry domain slice

This directory contains the first bounded Capability Registry source slice
released by `SW-P1-SUBSET-01`. It validates authored Ability definitions and
produces immutable publication metadata. It is a Python 3.11 standard-library
module, not a deployable service.

## Import

Until root packaging metadata is coordinated by the main task, import the
module through the Contracts and Capability source roots:

```bash
PYTHONPATH=packages/contracts/src:services/capability-registry/src /bin/python3.11 -c \
  'from capability_registry import AbilityDefinitionValidator'
```

`AbilityDefinitionValidator` depends on two explicit ports:

- `AdapterOperationCatalogPort` supplies trusted operation input paths and
  opaque credential-slot identifiers without invoking an operation.
- `ResultPolicySetValidatorPort` validates the shared named policy-set shape.
  `SharedResultPolicySetValidator` is the thin adapter to the shared Contracts
  package when both source roots are on `PYTHONPATH`.

Successful validation returns immutable `AbilityPublicationMetadata`. Invalid
definitions return stable `ValidationIssue` values and no publication
metadata.

## Management feature

`capability_registry.management.create_ability_feature(reader, drafts,
namespace, validator)` adapts this validator to the shared
`ManagementService`. The Host injects an
environment-bound published Ability reader and shared `DraftRepository`;
there is no implicit persistence fallback. Ordinary users can browse
published Abilities, while the shared service restricts draft operations and
publication preparation to trusted administrators.

Draft saves accept ordinary contract errors so an administrator can iterate,
but reject unknown operation references, credential material, and extra fields
that could smuggle executable code or URLs. Publication preparation validates
one immutable draft snapshot and returns a `PublicationPlan`; it does not write
a published version, execute an operation, resolve credentials, or proxy HTTP.

## Test

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=packages/contracts/src:services/capability-registry/src \
/bin/python3.11 -m unittest discover \
  -s services/capability-registry/tests -v
```

Add `services/management-api/src` to `PYTHONPATH` for the management tests.

## Boundary

This slice validates:

- the authored Ability field boundary;
- model-owned versus server-owned input separation;
- RFC 6901 source and target binding metadata;
- adapter-operation input paths and credential-slot compatibility;
- shared named success-policy publication metadata.

Required-source coverage is limited to the supported closed, top-level object
profile. This slice does not validate arbitrary JSON Schema composition such as
`allOf` or `$ref`, and it does not establish complete validation for nested
source paths. Those gates require a separate implementation release.

It does not evaluate result policies, execute an adapter or business API,
resolve credentials, retry or deduplicate business calls, persist to a
database, resolve an effective release, make authorization decisions, or run
as a resident service. Runtime remains the sole result-policy evaluator.

Passing these unit tests is source-level evidence only. It does not establish
PostgreSQL integration, multi-instance safety, deployment, Runtime integration,
E2E behavior or product readiness.
