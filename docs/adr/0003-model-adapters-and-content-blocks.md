# ADR-0003: Thin model adapters and structured content blocks

Date: 2026-09-08. Status: ACCEPTED engineering direction for AF-MODEL-06; implementation and provider verification pending.

## Requirement and decision

The user requests configuration-driven switching between DeepSeek and Alibaba Bailian, preserving provider-returned reasoning content, text, tool calls and other response fields. A thin adapter should expose typed blocks instead of distributing provider JSON parsing throughout the Runtime. This does not change Deep Agents as the Agent SDK or authorize live API calls, credential installation or deployment.

Use LangChain provider integrations and its standard content blocks as the first-choice implementation. Deep Agents continues to consume BaseChatModel and native AIMessage/AIMessageChunk objects. Our module owns trusted configuration, explicit adapter selection, capability validation and non-destructive projection; it does not reimplement the Agent loop or a universal LLM wire protocol.

Select by explicit provider + API protocol + model/profile, not model-name substring alone. The same model family can be hosted behind different protocols/providers. Unknown combinations fail explicitly, without provider fallback, speculative parameter dropping or implicit import from configuration.

## Two representations, separate purposes

1. Execution/history: retain the SDK message with provider-native content, additional fields, metadata, usage, identifiers and opaque continuation fields. Preserve the provider response payload through a reviewed public SDK hook if the selected integration otherwise loses required data. Never replace the message with only its text or standard block projection.
2. Standard view: derive typed content blocks for text, reasoning, tool calls and supported multimodal/provider tools. Preserve block order, IDs/indexes, signatures and extension data. Usage, finish reason and request/model identifiers remain envelope metadata rather than fabricated content blocks.

Unknown provider fields must not disappear silently: preserve them as provider-scoped opaque extension data through a verified path, or explicitly report the route unsupported. Merely keeping AIMessage.content is not proof of retaining the original HTTP response. Completion is bounded by an explicit field-coverage matrix for the chosen provider/protocol/SDK version, including unknown-field fixtures. Do not promise arbitrary future fields are universally supported.

Retention, model-history replay and user display are distinct policies. Preserve opaque/signed fields unchanged for compatible-provider replay; do not blindly forward arbitrary extensions to another provider, interpret encrypted reasoning as text, expose raw messages through the AF05 safe HTTP projection, or log credentials/headers/prompts. Actual provider-returned reasoning or summaries can be retained; hidden reasoning that the provider does not return cannot be recovered. Public UI behavior is unchanged by this engine slice.

## Streaming and round-trip gates

- Reuse AIMessageChunk/native stream assembly, not concatenation of all content into one string or manual accumulation of provider JSON.
- Verify reasoning deltas, text deltas, fragmented tool arguments, multiple interleaved tool calls, empty final usage chunks, termination/refusal/error states and preserved IDs/indexes.
- Do not execute incomplete tool-call argument fragments. Only admitted, complete validated tool calls reach existing Tools.
- Verify a complete response and an accumulated stream retain equivalent semantic fields where the provider contract permits comparison; byte-for-byte transport equivalence is not claimed.
- Verify serialization/deserialization and the next outgoing tool-result turn retain all provider-required reasoning/signature/continuation information. DeepSeek's current thinking-mode documentation requires reasoning_content history to be returned when tools are supplied, including prior turns without actual tool calls. Pin this rule to the chosen API/model; do not copy older R1 rules indiscriminately.
- Keep the existing controlled Tool and Finalizer boundaries. Check actual provider/model harness-profile matching so default filesystem/subagent Tools cannot become enabled by model selection.

## Configuration and ownership

Host configuration resolves a logical model reference to provider, protocol, model ID, reviewed endpoint, credential reference, timeouts and validated generation/provider options. Secrets remain in host secret resolution, never in source examples, model-controlled arguments or HTTP bodies. Shared mutable global environment settings are not a per-request routing mechanism.

No automatic switch midway through an existing execution, cross-provider history conversion or fallback is introduced. Initial provider implementations target DeepSeek and Bailian; the precise Bailian model/route and package pins are engineering validation inputs, not guessed from the console URL. Lack of credentials does not block offline fixture tests, but does block a live compatibility claim.

## Alternatives assessed

| Option | Assessment |
| --- | --- |
| LangChain provider adapters + content_blocks | Preferred: directly compatible with Deep Agents, typed text/reasoning/tool/multimodal blocks and native message/chunk history. Adapter coverage still needs verification. |
| PydanticAI ModelResponse.parts | Mature analogous Python design with TextPart, ThinkingPart, ToolCallPart and provider_details. Reference for preservation semantics; do not add a second Agent framework or duplicate message conversion without evidence the selected stack is insufficient. |
| LiteLLM | Provides reasoning_content, thinking_blocks and provider-specific data. Useful if a model gateway becomes a requirement, but an OpenAI-compatible downstream client can still discard extensions. Adds another translation layer; not first choice here. Do not enable automatic parameter removal to hide incompatibility. |
| All providers through ChatOpenAI with a different base_url | Rejected as the general preservation strategy: official documentation says nonstandard third-party response fields are not extracted/preserved. Only use a route whose exact required fields are proven. |
| Custom universal JSON parser | Rejected: duplicate protocol/chunk/history maintenance, contrary to the thin-layer goal. A narrowly scoped provider extension needs a demonstrated gap and public extension seam. |

## Evidence and re-evaluation

Read-only inspection confirms accepted server source 6cadc6076f72f11137b5fb96bfeebdb7137afdcb injects BaseChatModel through assembly.build_engine; a configurable provider factory is not present in that inspected assembly. The current source delivery is not live provider evidence.

Re-evaluate only if selected public adapters demonstrably discard necessary fields, cannot preserve stream/history semantics through public hooks, or require incompatible dependency changes. Report the exact fixture/field/path before choosing another library or writing a provider shim. Runtime reports offline contract evidence separately from real-provider and PostgreSQL evidence.

Official sources checked on 2026-09-08:

- [LangChain messages and content blocks](https://docs.langchain.com/oss/python/langchain/messages): typed standard projection, native content, metadata and chunk accumulation.
- [ChatOpenAI API scope](https://docs.langchain.com/oss/python/integrations/chat/openai): third-party reasoning extensions are not guaranteed preserved.
- [DeepSeek thinking mode](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/): reasoning and tool-history round trip.
- [PydanticAI message parts](https://pydantic.dev/docs/ai/api/pydantic-ai/messages/): typed parts and provider_details for otherwise unmapped fields/replay.
- [PydanticAI thinking](https://pydantic.dev/docs/ai/capabilities/thinking/): model/provider profiles and thinking handling.
- [LiteLLM reasoning content](https://docs.litellm.ai/docs/reasoning_content): reasoning/thinking fields and downstream-client loss risks.
