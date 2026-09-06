# SkillWeave shared contracts candidate

- Revision: `SW-CONTRACTS-P1-CANDIDATE.1`
- Authority baseline: `SW-P1-20260907.2`
- Status: `PROVISIONAL`; main-brain review is required before dependent implementation.

The bounded Skill/Policy closure named by `SW-P1-SUBSET-01` is approved for source
implementation. This does not approve the rest of the candidate bundle or establish
runtime readiness.

## Contents

- `schemas/contracts-bundle.schema.json`: transport-neutral common shapes.
- `tests/fixtures/valid/` and `tests/fixtures/invalid/`: synthetic project-owned examples.
- `tests/cases.json`: expected validity for each fixture.
- `tests/validate_contracts.py`: focused no-install check using the server's existing validator.
- `src/skillweave_contracts/`: Python 3.11 strict model/serialization adapter for the
  approved Skill/Policy closure only.

## Covered boundaries

- Backend-trusted `userId` plus PRT/ONLINE context shape.
- PRT current and ONLINE stable/candidate serving states; historical versions are outside the serving-state object and are not deleted by this contract.
- Environment-local resolution with ONLINE stable/gray selections sourced only from ONLINE.
- ALLOW versus RESET_REQUIRED version guard results.
- Platform control request envelopes and scoped targets with non-empty, asset-unique recorded versions, excluding business idempotency.
- A minimal reusable `ResultInterpretationPolicy`, explicit Action success/completion fragments and distinct Run/Node/Interaction/Result event references with per-run sequence.
- A model-visible `{skillKey}` request plus server-only invocation context and `content + artifact` result with digest-bound, read-only material handles addressed by normalized package-relative `logicalPath`.

JSON Schema validates shape, not provenance or runtime behavior. The model-facing Tool schema must not expose TrustedContext fields. PostgreSQL database separation, multi-instance control dedupe, ingress ordering, A2UI success evaluation and event transactions require later integration evidence.

`ResultInterpretationPolicy` deliberately supports only `SCHEMA_VALID` and `JSON_POINTER_EQUALS`. A Capability publishes `resultInterpretationPolicies` as an array plus `defaultSuccessPolicyRef`; the focused validator enforces unique policy refs and a resolvable default. Runtime owns one pure interpreter after output-schema validation. A missing JSON Pointer path is different from a found JSON null, can never match, and must be reported as `PATH_MISSING`; string, number, boolean and null values are compared without implicit coercion. `actionSuccessPolicyBinding` keeps `successPolicyRef` separate from `completeInteractionOnSuccess`, while `actionOutcomeFacts` records output-schema validity, policy match, Action-call success and interaction completion as four independent facts.

## Focused check

~~~sh
python3 packages/contracts/tests/validate_contracts.py
~~~

The check combines Draft 4 shape validation with bounded cross-reference checks for asset-unique recorded versions, policy refs/default resolution and unique resource logical paths. The current server provides Python 3.6.8 and jsonschema 2.6.0 (Draft 4 only). Draft 4 is used solely so this bounded candidate can be checked without installing dependencies; it does not freeze the final repository dependency or protocol version.

## Python/Runtime packaging recommendation

`requiredToolNames` is descriptive compatibility metadata only and never grants Tool authorization.

ENG-01 keeps JSON Schema and examples as the cross-language source of truth while allowing a thin Python adapter. Runtime has verified Python 3.11.13 and Pydantic 2.13.5; the proposed compatibility range is Python `>=3.11,<4` and, only when typed models are added, Pydantic `>=2.13,<3`. Root lock ownership fixes exact patches.

After main-brain names an approved revision and authorizes dependency work, the minimal layout is:

~~~text
packages/contracts/
  pyproject.toml
  src/skillweave_contracts/
    __init__.py
    models.py
    schema_loader.py
    py.typed
~~~

The module-local project must not carry a second lock or modify the root manifest. It must not depend on or import Deep Agents, LangGraph, PostgreSQL drivers or Runtime adapters; Runtime's currently tested versions are compatibility evidence, not contracts dependencies. The approved first source slice intentionally adds no dependency or packaging metadata.

## Approved Python adapter

The source slice has no third-party runtime dependency and is importable by adding
`packages/contracts/src` to `PYTHONPATH`. Consumers parse decoded JSON mappings through
the exact schema definition name or the named model:

~~~python
from skillweave_contracts import ResultInterpretationPolicySet, parse_definition

request = parse_definition("useSkillRequest", {"skillKey": "demo/evidence"})
policy_set = ResultInterpretationPolicySet.from_mapping(payload)
serialized = policy_set.to_mapping()
~~~

`ContractValidationError.issues` is an immutable tuple of
`ValidationIssue(path, code, message)`. `validate_definition(name, payload)` exposes the
same bounded validation as returned issues. Inputs reject extra fields and implicit type
coercion; nested model collections are tuples and serialization returns defensive copies.
`load_approved_schema()` reads and filters the neutral schema source rather than copying
it into a second authority. Unknown or provisional definition names fail closed.

The adapter deliberately does not evaluate result policies, resolve Skills, authorize
Tools, inspect host paths, execute scripts, access databases, or prove trusted-context
provenance.

Focused Python 3.11 check:

~~~sh
PYTHONPATH=packages/contracts/src python3.11 -m unittest discover \
  -s packages/contracts/tests/python -v
~~~

## Public references

- [JSON Schema Draft 4](https://json-schema.org/draft-04/json-schema-core)
- [RFC 6901 JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901.html)
