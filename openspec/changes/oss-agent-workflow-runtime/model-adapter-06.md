# AF-MODEL-06-D1: DeepSeek-only source slice

Status: PARTIAL SOURCE / REVIEW REQUEST. Runtime NO READY.
Baseline: c3c8f4697c0b3220980189ab6a409fd7fb8e807f. Date: 2026-09-08.
Authority: main-brain model-adapter-release-06.md and ADR-0003, delta D1.
Bailian and all other provider work are stopped.

## Implemented boundaries

- model_config.py: trusted closed Pydantic configuration; one DeepSeek chat-completions
  route, explicit deepseek-v4-pro / deepseek-v4-flash models, two official endpoint
  spellings, injected credential reference and bounded timeout. Thinking, reasoning
  effort and max tokens are explicit options; unknown/ignored combinations reject.
- model_factory.py: one lazy ChatDeepSeek constructor, injected host config and
  SecretStr resolution, synthetic HTTP-client injection, fixed sanitized errors,
  max_retries=0. No provider registry, fallback or environment mutation.
- model_content.py: native content_blocks plus detached copies of metadata and
  extensions. SDK message is the sole authoritative execution/history record.
  The view is derived, has no replay method, and is not an AF05 HTTP response.
- No new provider package is installed at this review point. Constructor compatibility,
  field ingress/outgoing retention and actual Deep Agents profile matching are pending.
  The factory is not wired into service/HTTP or existing assembly.

The view preserves the SDK projection order, not original wire order. Native core
serialization is used directly in fixtures; no custom serializer/parser/Agent loop.
A partial chunk remains marked partial, even if SDK best-effort parsing has produced
partial argument objects. The view cannot admit or execute tools.

## Retention and size policy

No data is truncated, reinterpreted, logged or forwarded by the view. The native
message remains under the host's retention/access policy; this slice adds no durable
store or public exposure. Extra/signed fields in existing messages are copied opaque.
Future wire fields are NOT universally supported: without verified adapter ingress,
the route's unknown-field retention outcome is UNVERIFIED / unsupported for acceptance.
No hidden provider reasoning can be recovered.

## Four-stage provider gate, still open

1. Actual fixed SDK HTTP ingress of synthetic DeepSeek-format responses, including
   reasoning, text, tool calls, refusals, finish/usage and unknown extensions.
2. Actual SDK streaming of interleaved fragmented calls and usage-only tail.
3. Native serialization/deserialization retaining all returned protocol-required data.
4. SDK-generated next request after ToolMessage, including reasoning from earlier
   assistant turns with no tool call.

Hand-constructed native fixtures prove only core/view behavior, NOT stages 1/2/4.
Static fixed-wheel inspection found ChatDeepSeek._get_request_payload delegates to
BaseChatOpenAI and rewrites list content; it does not itself add reasoning history.
This is a gap hypothesis, not runtime proof. No private method is overridden.
If the actual fixed SDK drops required fields and a reviewed public seam is unavailable,
report the minimal failing fixture to main-brain rather than building a protocol stack.

Actual harness/profile matching and controlled Tool/Finalizer/stop paths must be
verified using this model's synthetic outgoing SDK requests before acceptance.
Existing AF05 safe output and assembly are unchanged.

## Sources

- [Current DeepSeek thinking contract](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)
- [Native LangChain messages](https://docs.langchain.com/oss/python/langchain/messages)
- [DeepSeek integration](https://docs.langchain.com/oss/python/integrations/chat/deepseek)
- [DeepSeek 1.1.0 metadata](https://pypi.org/pypi/langchain-deepseek/1.1.0/json)

Current DeepSeek docs require reasoning history when tools are supplied, including
prior no-tool assistant turns. Older R1 wording on the integration overview is not
used to relax this gate.

## AF06-D2 evidence update (supersedes initial uninstalled state above)

Fixed5 dependencies are now authorized/installed and independently accepted.
Actual SDK synthetic transport verifies constructor, ingress and SSE as detailed
in regression-06.md. Two blocking losses are reproduced: unknown raw payload fields,
and all assistant reasoning_content omitted from tools-enabled outgoing history.
The request-payload gap is no longer merely a static hypothesis.

Public observations: ChatDeepSeek accepts injected http_client/http_async_client;
the current underlying OpenAI SDK uses httpx2 transports. Synthetic MockTransport
captures actual generated requests without inspecting/overriding SDK internals.
Public native serialization retains reasoning; loss is later at SDK request conversion.
Transport/context-based fix proposal is pending main-brain review. No raw HTTP/SSE
parser or alternative Agent/history framework is introduced.
