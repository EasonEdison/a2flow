# Capability Registry Subset 01 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first importable Capability Registry Python domain slice for authored Ability validation, adapter-operation binding validation and immutable publication metadata.

**Architecture:** Keep the domain module independent of Runtime and transport. `AbilityDefinitionValidator` consumes an `AdapterOperationCatalogPort` plus a `ResultPolicySetValidatorPort`; `SharedResultPolicySetValidator` adapts the public `skillweave_contracts.ResultInterpretationPolicySet.from_mapping`, while this domain owns Ability fields, model/server input separation and adapter metadata compatibility.

**Tech Stack:** Python 3.11 standard library, immutable dataclasses, `typing.Protocol`, `unittest`.

**Spec:** `openspec/changes/skillweave-phase1/implementation-release-01.md` (`SW-P1-SUBSET-01`) and `openspec/changes/oss-capability-registry/specs/capability-registry/spec.md`.

## Global Constraints

- Source is limited to `services/capability-registry/` and this change directory; root manifests remain main-brain-owned.
- The wire contract remains `SW-CONTRACTS-P1-CANDIDATE.1`; only the subset named by `SW-P1-SUBSET-01` is implementation-approved.
- The module must not evaluate result policies, invoke business APIs, retry business calls, provide idempotency, access PostgreSQL or resolve credentials.
- Model arguments must not expose `userId`, environment, authorization, credentials or release/version selection.
- Credential metadata contains only opaque slot identifiers; no credential value or backend locator enters the authored Ability.
- Tests use Python 3.11 with no dependency install and must demonstrate RED before production code.

---

### Task 1: Immutable domain result and validation ports

**Files:**
- Create: `services/capability-registry/src/capability_registry/__init__.py`
- Create: `services/capability-registry/src/capability_registry/models.py`
- Create: `services/capability-registry/src/capability_registry/ports.py`
- Create: `services/capability-registry/src/capability_registry/validation.py`
- Test: `services/capability-registry/tests/test_validation.py`

**Interfaces:**
- Produces: `ValidationIssue(code, path, message)`, `AdapterOperationDescriptor`, `AbilityPublicationMetadata`, `AbilityDefinitionValidation`.
- Produces: `AdapterOperationCatalogPort.lookup(operation_ref)` and `ResultPolicySetValidatorPort.validate(policy_set)`.
- Produces: `AbilityDefinitionValidator.validate(payload)`; successful validation has immutable metadata and no issues.

- [x] **Step 1: Write the happy-path test**

Create a complete literal Ability payload using model `/query`, trusted `/userId`, one `demoRead` credential slot and the approved policy set. Inject recording port fakes and assert exact immutable publication metadata plus the exact policy-set mapping passed to the contract port.

- [x] **Step 2: Run the test and verify RED**

Run:

```bash
PYTHONPATH=services/capability-registry/src /bin/python3.11 -m unittest services/capability-registry/tests/test_validation.py -v
```

Expected: import failure because `capability_registry` does not exist.

- [x] **Step 3: Implement the minimum public types and happy path**

Use frozen, slotted dataclasses. The validator must assemble this exact policy-set projection before calling the shared port:

```python
policy_set = {
    "resultInterpretationPolicies": payload["resultInterpretationPolicies"],
    "defaultSuccessPolicyRef": payload["defaultSuccessPolicyRef"],
}
```

It may produce metadata only when both ports and all domain checks return no issues.

- [x] **Step 4: Run the test and verify GREEN**

Run the same command and require zero failures.

### Task 2: Model/server boundary and authored payload failures

**Files:**
- Modify: `services/capability-registry/src/capability_registry/validation.py`
- Modify: `services/capability-registry/tests/test_validation.py`

**Interfaces:**
- Consumes: `AbilityDefinitionValidator.validate(payload)`.
- Produces stable issues with JSON-style paths; invalid results have `metadata is None`.

- [x] **Step 1: Add failing table-driven tests**

Use independent literal mutations and assert these behaviors:

- a model schema property named `userId`, `environment`, `credentialRef` or `releaseVersion` yields `MODEL_ARGUMENT_RESERVED_FIELD`;
- unknown top-level fields or credential requirement fields such as `referenceId`, `value`, `secret` or `token` are rejected;
- only `MODEL_ARGUMENT` and `TRUSTED_CONTEXT` authored bindings are accepted in this slice;
- model source paths must reference declared model properties;
- trusted source paths are limited to `/userId` and `/environment`;
- binding target paths must be valid, unique and non-overlapping.

- [x] **Step 2: Run the focused tests and verify RED**

Expected: each new case fails because the validator still accepts the invalid payload.

- [x] **Step 3: Implement minimum deterministic validation**

Use exact field allowlists, the approved identifier pattern and RFC 6901 syntax pattern from the contract snapshot. Do not add schema evaluation, coercion, URL fetching or a generic expression engine.

- [x] **Step 4: Run all tests and verify GREEN**

Require every table case and the original happy path to pass.

### Task 3: Adapter-operation and credential-slot compatibility

**Files:**
- Modify: `services/capability-registry/src/capability_registry/validation.py`
- Modify: `services/capability-registry/tests/test_validation.py`

**Interfaces:**
- Consumes: `AdapterOperationCatalogPort.lookup(operation_ref)`.
- Produces: `ADAPTER_OPERATION_NOT_FOUND`, `ADAPTER_INPUT_UNSUPPORTED` and `CREDENTIAL_SLOT_UNSUPPORTED` issues.

- [x] **Step 1: Add failing port-boundary tests**

Test a missing operation, an undeclared target path and an unsupported credential slot. Assert returned domain issues, not fake call counts.

- [x] **Step 2: Run tests and verify RED**

Expected: invalid cases currently return valid metadata or omit the required issue.

- [x] **Step 3: Implement minimum compatibility checks**

Lookup exactly once per validation. Compare authored target paths and credential slot identifiers to immutable sets in `AdapterOperationDescriptor`. Never request or retain a credential value.

- [x] **Step 4: Run all tests and verify GREEN**

Require zero failures and no warnings.

### Task 4: Shared Contracts policy-set adapter

**Files:**
- Create: `services/capability-registry/src/capability_registry/contract_adapter.py`
- Create: `services/capability-registry/tests/test_contract_adapter.py`

**Interfaces:**
- Consumes: `skillweave_contracts.ResultInterpretationPolicySet.from_mapping(payload)`.
- Consumes: `skillweave_contracts.ContractValidationError.issues` containing immutable `(path, code, message)` issues.
- Produces: `SharedResultPolicySetValidator.validate(policy_set)` returning Capability-domain `ValidationIssue` tuples.

- [x] **Step 1: Add failing shared-adapter tests**

Pass one valid policy set and one duplicate-ref/dangling-default set. Assert valid returns no issues and invalid preserves the shared issue paths/codes; do not test or implement policy evaluation.

- [x] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=packages/contracts/src:services/capability-registry/src /bin/python3.11 -m unittest services/capability-registry/tests/test_contract_adapter.py -v
```

Expected: import failure because `SharedResultPolicySetValidator` does not exist.

- [x] **Step 3: Implement the thin adapter**

Call `ResultInterpretationPolicySet.from_mapping` exactly once. Convert `ContractValidationError.issues` without changing code/path/message, and return an immutable tuple. Do not catch unrelated exceptions.

- [x] **Step 4: Run shared adapter and all domain tests GREEN**

Use both package `src` roots in `PYTHONPATH`; require zero failures.

### Task 5: Module documentation and delivery evidence

**Files:**
- Create: `services/capability-registry/README.md`
- Modify: `openspec/changes/oss-capability-registry/tasks.md`
- Modify: `openspec/changes/oss-capability-registry/regression.md`
- Modify: `openspec/changes/oss-capability-registry/readiness.md`
- Modify: `openspec/changes/oss-capability-registry/checkpoint-oss-capability-registry.md`

**Interfaces:**
- Documents the import command and the boundary between source evidence and Runtime readiness.

- [x] **Step 1: Run contract compatibility and module tests**

```bash
python3 packages/contracts/tests/validate_contracts.py
PYTHONPATH=services/capability-registry/src /bin/python3.11 -m unittest discover -s services/capability-registry/tests -v
```

- [x] **Step 2: Inspect imports, exact diff and clean-room boundary**

Run import smoke, `git diff --check`, owned-path scope check and sensitive-data scan. Confirm the module contains no policy evaluation, HTTP/database client, retry/idempotency implementation or credential values.

- [x] **Step 3: Update evidence without upgrading Runtime readiness**

Record exact test counts and commands. Keep shared full-bundle, PostgreSQL, Runtime and deployment gates as `NO READY`.

- [ ] **Step 4: Commit, merge latest main, reverify and integrate**

Push the worker branch, merge through the existing exclusive integration worktree and push `HEAD:main` without force.
