# AF-MODEL-06: Configurable providers and non-destructive content blocks

Date: 2026-09-08. Coordinator: main-brain. Owner: oss-agent-workflow-runtime.
Base: accepted AF05 source 6cadc6076f72f11137b5fb96bfeebdb7137afdcb.
Status: user-authorized continuation; bounded source/fixture implementation released, not live-provider or deployment acceptance.

## Outcome

Provide a thin host-configured model entry for Deep Agents, initially targeting DeepSeek and Alibaba Bailian. Reuse provider SDK integrations and LangChain standard content blocks while retaining provider-specific reasoning, tool calls, metadata and required history fields. Read docs/adr/0003-model-adapters-and-content-blocks.md before implementation.

## Scope and exclusive ownership

- Runtime owns services/agent-workflow-runtime/ model configuration/factory/projection modules, focused synthetic tests and its own openspec/changes/oss-agent-workflow-runtime/ model06 design/regression/readiness records. Necessary assembly changes are in scope. No other task's checkpoint may be read.
- Main-brain owns this release and ADR, their repository copies and root/shared packaging files. Other six domains stay paused. No digital-employee UI/SSE, model registry CRUD, auth-gateway implementation, full graph compiler or additional providers.
- Before work, verify worker path/branch/status/worktree ownership, fetch and merge origin/main; preserve unrelated changes. Return baseline adoption, conflicts and a concrete provider/API/package/field-coverage plan.
- Existing-dependency configuration/factory abstractions and offline tests may proceed immediately. New provider dependencies require an exact constrained dry-run/version/hash/license/change report to main-brain before installation; no upgrades to the existing SDK or global pip settings. Do not ask the user to coordinate ordinary engineering details.

## Required implementation boundaries

1. Explicit trusted provider/protocol/model profile selection and injected secret resolver; no model-name-only guessing, client-selected arbitrary endpoints/classes or embedded credentials. Unsupported routes/options fail rather than silently drop fields/options or fall back.
2. Reuse BaseChatModel/native AIMessage and AIMessageChunk plus content_blocks. Preserve execution messages separately from standard projections. Do not change AF05 safe HTTP output to expose raw provider messages.
3. Standard types handle text/reasoning/tool calls; SDK-native extensions/metadata retain otherwise unmapped fields, including signed/opaque data, usage and finish reasons. Demonstrate actual ingress retention rather than assuming content_blocks can recover fields already discarded by an adapter.
4. Support stream assembly and outbound history serialization through mature public SDK mechanisms. No hand-written universal JSON parser, framework fork, new Agent loop, provider fallback or silent option modification.
5. Target both provider paths but report unsupported routes honestly. Keep runtime host injection compatible; do not require deployment keys or a specific live model just to run synthetic tests.
6. Verify actual model/profile matching in the Deep Agents harness. Provider configuration must not re-enable implicit filesystem/execute/subagent Tools or bypass use_skill/tool admission/Finalizer/stop boundaries.

## Focused acceptance

- Logical model configuration switches adapter without changes to a Skill or business code; invalid provider/protocol/options rejected before request execution, no secrets in representations/errors.
- Synthetic provider-format fixtures exercise text plus reasoning, simultaneous reasoning/tool calls, multiple fragmented tool calls, final usage-only chunks, finish/refusal/error behavior and unknown extension fields. Do not label self-authored fixtures as captured real responses.
- Compare full and streamed message semantics; perform serialization round trip and inspect the next SDK-generated request after ToolMessage. Preserve required reasoning/signature fields, not only the display projection. Include prior no-tool assistant turns in a tools-enabled DeepSeek history according to the selected version's contract.
- Unsupported/unknown fields have a visible coverage outcome, not silent loss or blind forwarding across providers. Document size/retention constraints; no silent truncation of protocol-required data.
- Exercise controlled Deep Agents assembly with the selected model identity and injected synthetic transport; ensure permitted tools only, completed arguments before execution, current-run facts/interaction guards intact.
- Report changed source, exact versions, fixture coverage and remaining provider/PG/UI gaps. Full test-suite repetition is unnecessary for unchanged unrelated paths.

## Execution and delivery gates

No real model calls, credential lookup/installation, paid traffic, live listener, PostgreSQL window, Docker/Nginx/security change or deployment is released by this slice. Source development and constrained dependency research are in scope. Offline compatibility is not live provider proof.

Return a fixed worker commit and concise evidence to main-brain for review. Do not integrate unreviewed source into main or push GitHub; after review main-brain releases exact integration through the owner's exclusive integration worktree. Coordinate pending progress directly with main-brain, never through the user.
