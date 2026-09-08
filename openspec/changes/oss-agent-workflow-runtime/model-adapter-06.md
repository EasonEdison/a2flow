# AF-MODEL-06-D3: DeepSeek SDK-backed native model

Status: SOURCE REVIEW; offline evidence only, Runtime NO READY.
Authority: main-brain ADR-0003 and release D3 at server main a42d23a.
DeepSeek only. No other provider, Agent loop, protocol framework or new dependency.

## Construction and execution

model_config.py validates one chat-completions route, official endpoint spellings,
explicit deepseek-v4-pro / deepseek-v4-flash IDs, credential reference, timeout and
closed thinking/reasoning_effort/max_tokens options. Unsupported options reject.
model_factory.py resolves trusted host config/SecretStr and constructs DeepSeekChat
with OpenAI/AsyncOpenAI clients, timeout and max_retries=0. Host-injected clients are
supported for tests/lifetime management; no environment routing or fallback.

deepseek_model.py implements documented BaseChatModel custom interfaces:
_generate/_agenerate and _stream/_astream, _llm_type/_identifying_params and public
bind_tools. It never subclasses/overrides private ChatDeepSeek serializers.
The installed OpenAI SDK owns HTTP, typed response parsing and native SSE.

Standard outbound conversion uses public convert_to_openai_messages per native
message, validates role/shape alignment, and adds only DeepSeek reasoning_content.
No blind zip, pass-through unknown input blocks or opaque extension replay.
Native AIMessage/AIMessageChunk is the sole authoritative history; model_content.py
produces a detached view, not another execution/history schema or AF05 HTTP output.

## Supported / unsupported matrix

| Boundary | Supported and evidenced | Explicitly unsupported / not claimed |
| --- | --- | --- |
| API/config | DeepSeek chat completions, closed pro/flash configuration | Other providers/routes/models, speculative options |
| Input/history | System/human/assistant/tool, text/string or closed text blocks, normalized Tool calls | Images/audio/files, arbitrary blocks, legacy function/audio/tool fields, partial chunks as history |
| Reasoning replay | Every retained assistant reasoning string, including no-tool turns; full and stream native round trip | Tools-enabled thinking history missing reasoning; unreturned hidden reasoning |
| Output | Text/reasoning/function calls/usage/finish/refusal; typed payload retains all response/choice/message extensions | Arbitrary future continuation semantics or automatic opaque-field forwarding |
| Streaming | Native SDK SSE, interleaved Tool fragments, usage-only tail, repeated identical Tool IDs/names | Multiple choices/usage/finish markers, changing identity, post-finish content |
| Tool completion | Strict full JSON object, duplicate keys/nonfinite/truncated/scalar arguments rejected before dispatch | Partial-parser repair, malformed/missing finish accepted as success |
| Finish/error | stop or tool_calls consistent with result; refusal preserved; SDK error propagates, retries0 | length/content_filter/unknown or missing finish treated as completed |
| Async | Native SDK async invoke/stream; close/early-close/cancellation evidence | Live-network latency/cancellation guarantees |
| Harness | Actual deepseek:deepseek-v4-pro wire Tools limited to injected lookup; admission, Finalizer, stop retained | Live pro/flash behavior or broad production availability |

Both model IDs are configured by host; actual controlled harness fixture uses pro.
No claim that synthetic data is captured provider output or live model capability.

## Raw records, IDs, size and retention

Each typed model_dump is wrapped as one ordered deepseek_payloads record under
native additional_kwargs. The outer record has no index, so native list merging
does not merge matching provider indexes, concatenate signed identifiers or add
opaque numbers. Raw root/choice/message/delta fields remain unchanged in their
respective typed records; SDK-added defaults mean this is not raw byte capture.

Provider response IDs stay in metadata/raw records. Native message IDs are generated
by core, preventing repeated provider IDs from replacing earlier LangGraph history.
The adapter retains only native Tool fragments separately for strict end-of-stream
validation, not a duplicate raw-response/history accumulator.

No silent truncation/eviction or independent durable store is added. Storage is
proportional to retained typed payload records; native merge/view copies add memory
overhead. The trusted host must budget retention/request size before live deployment.
No universal payload-size guarantee or bounded live-memory proof is made here.
Host-supplied clients remain host-managed; every SDK response stream is closed in
sync/async context managers, including exceptions and cancellation.

## Evidence and delivery boundary

regression-06.md records28 focused tests:12 config/core,5 upstream characterization
and11 positive project-adapter gates. Upstream known-gap tests remain separately
named; they do not count as compatibility. AF05 safe HTTP, Tool admission, Finalizer
and assembly source remain unchanged. No raw response is exposed by HTTP.

No live provider/credentials, PG, listener or deployment. Worker-only source review;
main/GitHub integration requires exact coordinator release.

Sources: [BaseChatModel custom-model interface](https://reference.langchain.com/python/langchain-core/language_models/chat_models/BaseChatModel),
[OpenAI SDK v3.8.0](https://github.com/openai/openai-python/tree/v3.8.0),
[DeepSeek thinking contract](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/).
