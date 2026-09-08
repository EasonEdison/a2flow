# AF06-D1 regression evidence

Date: 2026-09-08. Owner evidence, not main-brain acceptance.
Python 3.11.13; existing langchain-core 1.6.2, Pydantic 2.13.5.
All fixtures are hand-authored synthetic data, not captured provider responses.

## Executed

Command from assigned worker:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=packages/contracts/src:services/agent-workflow-runtime/src:services/agent-workflow-runtime/tests \
/home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python \
-m unittest test_model_config test_model_content -v
```

12 PASS / 0.003s. Configuration 5; native content/view 7.
git diff --check PASS at this source state.

| Coverage | Evidence | Boundary |
| --- | --- | --- |
| Closed config/model/options and sanitization | 5 config tests | No installed provider constructor exercised |
| SDK block order/signature/opaque data | Native v1 blocks fixture | Not original transport order |
| Reasoning/tool/usage/finish/unknown metadata | Detached native view fixture | No recovery of adapter-dropped fields |
| Prior tool and no-tool assistant serialization | Public message_to_dict/messages_from_dict | No outgoing request evidence |
| Two fragmented calls, native chunk addition, usage-only tail | Core AIMessageChunk + conversion | Not actual provider stream |
| Refusal/unknown finish and partial marker | Opaque metadata, partial=true | No invented success/Tool execution |
| Mutation isolation, redacted repr, role check | View changes leave message unchanged | Not a public HTTP schema |

No unrelated AF05 suite/experiments repeated. No PG, listeners, real credentials,
provider calls or deployment performed. AF05 prior acceptance remains historical.

## Dependency diagnosis and one approved mirror attempt

- Earlier quiet constrained attempts timed out (90s original superseded scope;
  180s DeepSeek-only). No complete resolver delta or installation.
- Short official-index attempt: --timeout 10 --retries 0, pypi.org/simple;
  reached Collecting langchain-deepseek1.1.0 then files.pythonhosted.org wheel
  ReadTimeoutError. Not evidence of a resolver conflict.
- main-brain approved one temporary TUNA index attempt: no global settings,
  no extra-index, binary-only, existing 64 exact pins, 180s/30MiB ceiling.
- Index: https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
- Command: venv python -m pip install --dry-run --report <owned-temp>/report.json
  --index-url <above> --only-binary=:all: --disable-pip-version-check --no-cache-dir
  --progress-bar off --timeout 10 --retries 0 langchain-deepseek==1.1.0
  langchain-openai==1.6.0 plus all name==version values in af06-installed-before.json.
- Dry-run 7.48s; pip download --no-deps of exact five resolved candidates finished
  at 13.10s; official hash/size/license checks completed at total21.79s.
- Wheel sum3883001 bytes; conservatively observed temporary writes7067436 bytes.
  Every final filename, SHA256 and size matched official PyPI version metadata.
- Existing64 normalized distributions unchanged before/after. Not128 distinct
  packages: lib64 alias points to same dist-info paths.
- Download-only wheelhouse: /home/admin/OpenSource/.tmp/af06-deepseek-wheels-EqxBQ8tA.
  No installation approved or performed at this source review point.
- Full artifact details: dependency-review-06.md.

## Execution corrections

An incorrectly called patch helper created75 root files named0..74, each one newline,
all absent from pre-action status. Their exact content and ownership were checked;
a deletion patch removed only those task-generated files and correctly added the two
intended files. Final status contains only owned source/docs. The transient failed
test import was before those intended files existed; the successful12-test run is
after correction. No user data or existing tracked files were removed.

Next: fixed worker source review and dependency approval; then actual fixed SDK
mock-HTTP four-stage fixtures and harness gate, not a second broad core test run.

## AF06-D2 fixed installed SDK characterization

Installation gate accepted by main-brain. langchain-deepseek1.1.0,
langchain-openai1.6.0, openai3.8.0, regex2026.9.3, tiktoken0.14.0 installed from approved
hash-verified wheels only; old64 unchanged;69 unique; pip check/import PASS.
Earlier 'not installed' text describes the previous review point only.

Same test command with -m unittest test_deepseek_sdk_contract -v:
5 characterization tests PASS / 1.034s. Two tests named known_gap intentionally assert
observed loss; their PASS means the blocker reproduced, NOT compatibility acceptance.

- Public ChatDeepSeek http_client/http_async_client accept httpx2 Client/AsyncClient
  with MockTransport under fixed openai3.8.0. No private SDK methods overridden.
- langsmith.tracing_context(enabled=False) scopes synthetic invocations to avoid
  external tracing; no global environment settings changed.
- Actual mocked HTTP request/response through SDK: text, returned reasoning_content,
  parsed Tool calls/IDs, usage, finish/refusal and native serialization PASS.
- Actual SDK SSE parser: interleaved2 Tool argument fragments, reasoning/text deltas
  and final usage-only chunk retained by native AIMessageChunk addition.
- HTTP400 propagates SDK BadRequestError, no automatic retry/fallback.

### Exact blocking fixtures

1. test_known_gap_unknown_wire_fields_are_lost_before_native_view:
   actual HTTP fixture has opaque_message/opaque_choice/opaque_response sentinel
   fields. None is retained in native message_to_dict output. Actual SDK SSE fixture
   opaque_delta similarly disappears. Derived content_blocks cannot recover them.
2. test_known_gap_next_sdk_request_drops_reasoning_from_all_assistant_turns:
   tools bound on all3 SDK calls. First response assistant has no Tool call but
   reasoning_content=no-tool-reasoning. Second has a Tool call and tool-reasoning.
   Native messages_from_dict(message_to_dict(...)) retains both. Third SDK request,
   after ToolMessage, has2 assistant messages and both omit reasoning_content.
   This violates current selected DeepSeek tools-enabled history contract.

No fix/public seam has been released yet. Do not override adapter private methods,
reparse all SSE, duplicate the Agent loop or expose raw payload through AF05 HTTP.
Actual harness-specific verification is next and can be a separate small commit;
existing assembly is unchanged in this fixed gap-evidence source slice.

## D3 latest positive gate (supersedes earlier project-adapter blockers)

Date2026-09-08 10:26 UTC. Main-brain approved D3 custom model and servermaina42d23a
was fetched/merged before implementation. No new dependencies since accepted D2.

Final command from assigned worker:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=packages/contracts/src:services/agent-workflow-runtime/src:services/agent-workflow-runtime/tests \
/home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python \
-m unittest test_model_config test_model_content test_deepseek_sdk_contract test_deepseek_model -v
```

28 PASS / 1.594s.12 config/core +5 old SDK characterization +11 project-adapter
positive gates. The2 known_gap tests still describe upstream behavior, not the new
factory. test_deepseek_sdk_contract now explicitly constructs upstream ChatDeepSeek;
test_deepseek_model constructs the project DeepSeekChat through trusted factory.

New positive test_deepseek_model evidence:

- Actual SDK mock HTTP retains reasoning, text, parsed calls, usage and unknown root/
  choice/message fields inside ordered typed payload records.
- Native serialization after both no-tool and Tool assistant responses retains
  reasoning; next actual tools-enabled SDK request includes both reasoning strings.
  Raw markers/deepseek_payloads never leak into outbound requests.
- Actual SDK SSE retains interleaved2 tool calls, repeated identical IDs/names,
  reasoning/text, usage-only tail and each original raw typed record. Native merged
  raw IDs/numbers/signature fields are not concatenated/added/corrupted.
- Stream -> native complete message -> serialization -> next actual Tool-result
  request preserves reasoning and both call IDs, without replaying raw payloads.
- Core callbacks invoked once per emitted chunk; adapter never invokes token
  callbacks itself. SDK sync and native async normal/early close verified.
- Async task cancellation while blocked in SSE and sync ReadError close response
  resources. Truncated args, length and missing finish reject rather than succeed.
- Strict full Tool JSON rejects truncated objects, duplicate keys, NaN/infinite
  numeric results and non-object roots.
- Actual graph.stream(messages/updates) cannot dispatch partial Tool arguments or
  a stream missing valid termination; no synthetic executor call occurs.
- Actual Deep Agents model identity/harness key limits outgoing tools to lookup;
  lifecycle-bound successful Tool fact/Finalizer retained. Extra args cause no
  executor call and Finalizer rejects. STOPPED prevents SDK invocation.
- Unsupported input blocks/missing reasoning/options and deliberately misaligned
  public conversion reject before transport. Model representations exclude clients
  and synthetic secret. SDK clients both max_retries0; HTTP400 no fallback.

D3 fixture correction: directly assigning repeated provider response IDs as native
message IDs initially caused reducer replacement and absent Finalizer facts.
Production adapter now lets core allocate native IDs; original provider IDs remain
in metadata/raw records. The successful harness test includes repeated provider IDs.
Earlier old-SDK fixture replacement omitted explicit base_url, causing mock path
assertions (no network); explicit original endpoint restored before final28PASS.

No AF05/PG/experiments broad rerun. Source unchanged after the final28PASS except
evidence docs. No private SDK override, global settings, extra packages or live calls.
