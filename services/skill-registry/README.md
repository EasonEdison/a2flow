# Skill Registry domain slice

Status: source-only implementation approved by SW-P1-SUBSET-01. Runtime readiness
remains **NO READY**.

## Included

- Immutable package entry/resource descriptors.
- Finite entry-count, per-entry byte, total-byte, logical-path length and path-depth
  limits.
- Exact logical-path uniqueness and safe relative-path validation.
- Declared size/digest verification against actual bytes.
- Strict UTF-8 decoding for `text/*` material and opaque retention of binary
  material.
- Abstract catalog/material ports with model input separated from server-supplied
  trusted context.
- Mapping of verified material and trusted resolution evidence into the approved
  `useSkillResult` shape.

Resource handles always use `READ_ONLY`. `requiredToolNames` is compatibility
metadata only; this package has no Tool or script executor and grants no
permissions.

## Trust boundary

The material adapter supplies descriptors, bytes/streams and resolution evidence.
This module recomputes each resource size and SHA-256 digest from actual bytes.
The artifact-level digest has no synthetic default and is copied only from the
required trusted resolution evidence input because canonical package digest
construction is not part of this release.

Constructing a `TrustedContext` or `TrustedResolutionEvidence` value does not
prove provenance. The future server adapter/admission layer must establish that
trust before calling this module.

## Excluded

This slice does not parse YAML/frontmatter, extract archives, execute shell or
scripts, accept model-provided filesystem locators, implement PRT/ONLINE
resolution, connect to a database, start a process, deploy a service, or provide a
production fallback. Root packaging and lock files remain externally owned.

## Verification

Python 3.11 is the release target. The source is standard-library-only; the
contract-compatibility test reuses the repository's existing `jsonschema` test
dependency.

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=services/skill-registry/src \
python3 -m unittest discover -s services/skill-registry/tests -v
```

Passing unit/schema checks prove bounded source behavior and wire shape only.
They do not prove trusted provenance, persistence, multi-instance behavior,
Runtime integration, deployment or product availability.
