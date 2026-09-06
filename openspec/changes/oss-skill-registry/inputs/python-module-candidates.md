# Python Module and Dependency Candidates

> Date: 2026-09-07
> Status: ENG-01 read / reviewed-input planning only
> Runtime/service readiness: NO READY
> Constraint: no dependency install, root manifest change, shared schema implementation or archive algorithm in this batch.

## Current Direction

main-brain selected Python for Skill Registry and Runtime in [ENG-01](../../skillweave-phase1/engineering-decisions.md) to avoid a second service language. The registry remains an independently importable package under `services/skill-registry/`; it is not a new long-running process and business registry logic does not move into Runtime.

The current repository has no root `pyproject.toml` or lock file. main-brain owns those files and will pin the approved Python/dependency set. This task only proposes package-local paths and dependency candidates.

## Agent Skills Format Validation

### Candidate: `skills-ref` as a conformance oracle, not a production runtime dependency

- The [Agent Skills specification](https://agentskills.io/specification) points clients to `skills-ref validate`.
- The [official skills-ref README](https://github.com/agentskills/agentskills/blob/main/skills-ref/README.md) exposes Python `validate` / `read_properties`, but explicitly says the library is for demonstration and not production.
- [PyPI 0.1.1](https://pypi.org/project/skills-ref/) is Alpha, Apache-2.0 and requires Python 3.11+.
- The official source manifest depends on `strictyaml>=1.7.3`, while published [CLI naming](https://github.com/agentskills/agentskills/issues/355) and [UTF-8 behavior](https://github.com/agentskills/agentskills/issues/536) have had reported mismatches. Pinning a release without a local conformance corpus is unsafe.

Decision: use a main-brain-pinned `skills-ref` build only in tests as the upstream format oracle. Do not make publication/runtime availability depend directly on its CLI or treat it as the domain policy engine. Production adoption requires source/version/hash review and our 14-case corpus plus non-ASCII fixtures.

## Safe YAML Candidates

### Preferred candidate for evaluation: `ruamel.yaml` safe pure loader

- The [safe pure loader](https://yaml.dev/doc/ruamel.yaml/basicuse/) avoids unknown-tag object construction and uses YAML 1.2 behavior.
- The [new API](https://yaml.dev/doc/ruamel.yaml/api/) rejects duplicate mapping keys by default; the current line also offers a maximum-depth control.
- [PyPI](https://pypi.org/project/ruamel.yaml/) reports current releases require Python 3.9+ and use the MIT license.

Risk: the project warns about API/packaging transitions and has one maintainer. If selected, main-brain must pin an exact version/hash and the package must wrap only the minimal load API.

### Operational fallback: `PyYAML` `safe_load`

- [PyYAML 6.0.3](https://pypi.org/project/PyYAML/) is classified Production/Stable, MIT licensed and supports Python 3.8+.
- Its [official documentation](https://pyyaml.org/wiki/PyYAMLDocumentation) states `safe_load` only recognizes standard tags and cannot construct arbitrary Python objects.
- It does not by itself give the strict duplicate-key/depth/profile behavior required here.

Decision gate: prefer one production YAML library, not two. Evaluate `ruamel.yaml` safe/pure first for duplicate-key and depth controls; use PyYAML only if a small, tested strict-loader wrapper covers duplicate keys, alias/depth limits and string-to-string metadata. `yaml.load`, unsafe/custom object constructors and implicit permission fields are forbidden.

`StrictYAML` remains an indirect `skills-ref` implementation detail. It rejects duplicate keys, tags and anchors, but its last PyPI release is old and its restricted syntax may reject otherwise portable input; do not couple the production domain model to it without corpus results.

## Resource Package Reading

Phase 1 should avoid generic archive extraction. The preferred contract shape is a bounded package source that yields immutable entries:

- normalized `logicalPath`;
- declared `mediaType`, `digest` and `size`;
- a read-only byte stream;
- no caller-controlled filesystem locator or credential.

The package reader must inspect first and materialize never by default:

1. require one root `SKILL.md`;
2. reject absolute paths, `..`, empty/control-character segments, duplicate/case-colliding paths, links and non-regular filesystem entries;
3. enforce entry count, per-entry bytes, total uncompressed bytes, path depth and wall-clock limits before reading;
4. stream SHA-256 while enforcing the declared size, then compare digest;
5. decode only `SKILL.md` and declared text references as strict UTF-8;
6. retain assets as opaque bytes with their descriptor;
7. never execute Markdown, scripts or `allowed-tools`.

Directory-backed test input can use Python `pathlib`/`os` with `lstat`/no-follow checks. The [pathlib documentation](https://docs.python.org/3.12/library/pathlib.html) shows lexical checks and filesystem symlink resolution differ, so `Path.resolve()` alone is not the whole security boundary.

If a future shared contract requires TAR, Python 3.12+ `tarfile.extractall(filter="data")` is the minimum baseline, but the [Python tarfile documentation](https://docs.python.org/3.12/library/tarfile.html) still requires prior inspection, temporary isolation, link/device rejection and resource limits. [ZIP has similar warnings](https://docs.python.org/3.12/library/zipfile.html), and `zipfile.Path` does not sanitize names. Archive support therefore needs a separately reviewed adapter and adversarial tests; it is not part of the first module slice.

## Candidate Module Paths

```text
services/skill-registry/
├── README.md
├── src/
│   └── skill_registry/
│       ├── __init__.py
│       ├── validation/
│       │   ├── agent_skills.py
│       │   └── frontmatter.py
│       ├── resources/
│       │   └── package_reader.py
│       ├── application/
│       │   ├── catalog_port.py
│       │   └── material_port.py
│       └── adapters/
│           └── postgres/
└── tests/
    ├── unit/
    ├── contract/
    └── fixtures/
```

Boundary notes:

- `validation/` owns deterministic package/profile checks, not Tool authorization.
- `resources/package_reader.py` consumes the contracts-owned package/resource descriptor; it does not define a second shared schema.
- `catalog_port.py` and `material_port.py` accept trusted backend context after the named contract revision. Model-visible inputs never contain `userId` or `environment`.
- PostgreSQL adapters arrive only with the contracts-owned environment/publication/version model. No SQLite/MySQL or in-memory production fallback.
- Tests reuse the reviewed neutral Skill and 14-case corpus. Actual validator results remain pending until implementation.

## Proposed Dependency Decision Sequence

1. contracts publishes the named logicalPath/resource descriptor and trusted-context revision;
2. main-brain publishes the root Python version and lock ownership;
3. run a throwaway, non-committed compatibility spike against exact `skills-ref`, `ruamel.yaml` and PyYAML candidates;
4. choose one production YAML parser and keep `skills-ref` test-only if its corpus result is acceptable;
5. implement the directory/entry reader first; keep TAR/ZIP out until separately approved;
6. record exact pinned versions, licenses, hashes and negative-test evidence before source delivery.

No candidate above is approved or installed by this document.
