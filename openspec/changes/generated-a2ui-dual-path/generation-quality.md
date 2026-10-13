# Generated A2UI design quality regression

Source baseline: `b6104b2`. Scope: four representative single-call design requests and authoritative candidate admission. This is an operator acceptance runner, not a unit-test suite. It does not activate a card, invoke LoadBinding or business Actions, write assets, publish, or deploy.

## Entry point and bounded inputs

Run from the repository root in an existing Python 3.11+ environment with the project's execution and Agent Runtime dependencies available:

```sh
python -m deploy.a2ui_generation_quality.runner --help
python -m deploy.a2ui_generation_quality.runner
```

The default is a plan. It uses only the standard library, reads no files or databases, and constructs no provider client. There is no implicit live mode. The operator supplies an approved verification owner and the existing published-asset database secret file; the runner never searches chat records for an identity. It reads `A2FLOW_CAPABILITY_DSN_FILE`, `A2FLOW_CAPABILITY_DATABASE`, `A2FLOW_CAPABILITY_ENVIRONMENT`, and `A2FLOW_DEEPSEEK_KEY_FILE` as optional argument defaults. These are existing deployment settings, not new secret configuration. Explicit arguments can point at already-approved local secret files when the database is reached through an existing SSH tunnel. Do not put a DSN or provider key directly on the command line.

```sh
python -m deploy.a2ui_generation_quality.runner --read-only \
  --dsn-file /path/to/existing/published-database-secret \
  --database APPROVED_DATABASE --environment PRT --user-id APPROVED_OWNER

python -m deploy.a2ui_generation_quality.runner --live --max-calls 4 \
  --dsn-file /path/to/existing/published-database-secret \
  --database APPROVED_DATABASE --environment PRT --user-id APPROVED_OWNER \
  --provider-key-file /path/to/existing/deepseek-secret
```

Placeholders above must be resolved by the coordinator. No package installation, SSH tunnel, credential copying or environment mutation is performed by the runner. The execution container alone may lack model dependencies; the runtime container alone may lack execution packages. Use an already-prepared combined Python environment. Do not assume `deploy.realchat.launcher.configure()` points at the authoritative publication database; the runner intentionally does not call that function.

Full live execution requires explicit `--max-calls 4`. For a separately approved smaller run, repeat `--case people`, `--case reading`, `--case topic`, or `--case manuscript`, and set `--max-calls` to exactly the unique selected count. Duplicates and count mismatches are rejected. The runner performs at most one model attempt per selected case. A failed source/matrix check skips that case's live call and is reported as failure. Every new invocation is a new budget decision; there is no automatic retry, repair, alternate provider, saved candidate reuse or fallback.

The live model configuration matches the realchat host: `deepseek-v4-flash`, thinking disabled, 4096 output tokens, 30-second timeout, SDK retries disabled through the existing factory. Each request reuses `DeepAgentA2uiGenerator`, including its isolated history, empty tools and single-call guard.

## Authoritative read and validation

`A2uiRuntimeService.describe_generation_source` is the production service method backing `DescribeGenerationSource`. It reads the chosen user's published Application and Catalog via `PostgresApplicationReader`; that reader explicitly opens `REPEATABLE READ READ ONLY` transactions. The runner supplies an invoker that always rejects business calls and never invokes activation. Contract and candidate validation reuse `generation.contract` and `generation.validate_candidate`; no parallel protocol implementation or schema copy is maintained.

The Application/Catalog are rechecked after each live attempt. A concurrent publication produces `SOURCE_CHANGED_DURING_PROBE` or a clear read error, with no retry. This does not create a single snapshot transaction spanning the provider call; it detects observed changes, not an unobservable change-and-revert.

| Case | Existing Application | Requested layout | Manual quality review after a separately authorized rendered preview |
| --- | --- | --- | --- |
| people | `people-selector` | Separate explanation, selection and pagination areas using Card | Selection stays legible; pagination and fill-composer controls remain discoverable; no invented person groups or records |
| reading | `reading-point-selector` | Reading cards with claim, quote, explanation and declared additional read-only fields | Clear quote hierarchy; evidence location/model suggestion are understandable; List items do not bleed data across scopes |
| topic | `content-topic-selector` | Editable title, angle and confirmation hierarchy | Item editing and confirm target are unambiguous; each template keeps its own bindings |
| manuscript | `content-manuscript-editor` | Editor, preview, save/confirm/export areas | Long text remains usable; controls do not suggest success before user action; no clipped controls |

## Admission matrix

These probes operate only on in-memory copies of the current published source. They do not call a provider in `--read-only` mode. Positive source acceptance is a contract control, not evidence of model quality.

| Probe | Expected result |
| --- | --- |
| Published components, same anchors, approved action placements, relative List paths and input properties | Admitted by the real validator; admitted action-binding IDs equal the published set |
| New Text for a declared `readOnlyDisplayBindings` field inside its existing List lineage | Admitted; if no such field exists, explicitly `NOT_APPLICABLE` |
| Wrong message version | `A2UI_GENERATION_MESSAGE_VERSION_INVALID` |
| Model-added updateDataModel | `A2UI_GENERATION_MESSAGE_ENVELOPE_INVALID` |
| Remove server-action placements while leaving action-bearing components | `A2UI_GENERATION_ACTION_NOT_ALLOWED` |
| Text refers to an undeclared absolute path | `A2UI_GENERATION_DATA_PATH_NOT_ALLOWED` |
| Rename an engineering Text anchor while retaining its tree references | `A2UI_GENERATION_ANCHOR_MISSING` |
| Existing relative Text also referenced outside its List scope | `A2UI_GENERATION_DATA_PATH_NOT_ALLOWED`; absence of relative Text is `NOT_APPLICABLE` |
| Fresh generated candidate | Real schema/admission must pass; all published action bindings must survive; layout structure must change |

The matrix deliberately targets the four existing source layouts. An unexpected source shape reports `MATRIX_SHAPE_UNSUPPORTED`; it is not silently skipped. Admission protects envelope, Catalog types, anchors, input targets, allowed data paths, List lineage and approved actions. The runner does not expand supported components or assert that a valid layout is aesthetically successful. Structural difference is a coarse signal; rendering and human inspection remain required for layout-quality acceptance.

## Evidence and interpretation

Output is newline-delimited JSON: one safe result per case followed by aggregate counts and failure codes. No contracts, candidate JSON, user IDs, request/response bodies, secret content, private business data or exception messages are persisted. Third-party stdout/stderr and logging are suppressed during execution. The operator may retain the safe summary in a private acceptance record.

`modelCalls` is a conservative model-attempt count, incremented immediately before generator invocation; a client-construction or provider failure still consumes that attempt. It is not billing or provider completion telemetry. Expected negative rejections count as passed controls. Unexpected acceptance, unexpected rejection, setup failure or unchanged structure makes the process exit 1. Exit 0 means the selected automatic controls passed only. Every report includes `visualReview: NOT_PERFORMED`; there is no overall visual-quality or deployed-readiness claim.

Development verification for this delivery: syntax/AST, default plan, help and missing-budget CLI rejection only. The host default python3 is 3.6 and cannot parse this project; the checks were rerun successfully with the existing /usr/bin/python3.11. No database access, provider call, unit test, activation, publication or deployment was performed during implementation. Live acceptance and rendered visual evidence remain pending coordinator execution.
