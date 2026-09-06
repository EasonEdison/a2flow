# Capability Registry domain slice

This directory contains the first bounded Capability Registry source slice
released by `SW-P1-SUBSET-01`. It validates authored Ability definitions and
produces immutable publication metadata. It is a Python 3.11 standard-library
module, not a deployable service.

## Import

Until root packaging metadata is coordinated by the main task, import the
module through its source root:

```bash
PYTHONPATH=services/capability-registry/src /bin/python3.11 -c \
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

## Test

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=packages/contracts/src:services/capability-registry/src \
/bin/python3.11 -m unittest discover \
  -s services/capability-registry/tests -v
```

## Boundary

This slice validates:

- the authored Ability field boundary;
- model-owned versus server-owned input separation;
- RFC 6901 source and target binding metadata;
- adapter-operation input paths and credential-slot compatibility;
- shared named success-policy publication metadata.

It does not evaluate result policies, execute an adapter or business API,
resolve credentials, retry or deduplicate business calls, persist to a
database, resolve an effective release, make authorization decisions, or run
as a resident service. Runtime remains the sole result-policy evaluator.

Passing these unit tests is source-level evidence only. It does not establish
PostgreSQL integration, multi-instance safety, deployment, Runtime integration,
E2E behavior or product readiness.
