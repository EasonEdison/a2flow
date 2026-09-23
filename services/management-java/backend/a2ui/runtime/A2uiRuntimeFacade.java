package dev.a2flow.management.a2ui.runtime;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.stereotype.Service;
import dev.a2flow.management.a2ui.runtime.A2uiRuntimeContracts.*;
import dev.a2flow.management.a2ui.runtime.action.A2uiCapabilityOutcomeEvaluator;
import dev.a2flow.management.a2ui.runtime.adapter.A2uiResultAdapterEngine;
import dev.a2flow.management.a2ui.runtime.capability.CapabilityExecutionResult;
import dev.a2flow.management.a2ui.runtime.ledger.A2uiMessageSnapshotReducer;
import dev.a2flow.management.a2ui.runtime.ledger.A2uiRuntimeSurfaceLedger;
import dev.a2flow.management.a2ui.runtime.mapping.A2uiCapabilityRequestMapper;
import dev.a2flow.management.a2ui.runtime.mapping.A2uiCapabilityRequestMapper.MappingInputs;
import dev.a2flow.management.a2ui.runtime.show.A2uiApplicationShowRenderer;
import dev.a2flow.management.a2ui.runtime.show.A2uiApplicationShowRenderer.TrustedShowContext;
import dev.a2flow.management.a2ui.gateway.A2uiActionBindingResolver;
import dev.a2flow.management.capabilityrpc.CapabilityExecutionPort;
import dev.a2flow.management.capabilityrpc.CapabilityRpcContext;
import dev.a2flow.management.support.JsonSupport;

/**
 * 确定性计算 facade：发布读取 -> Show -> 顺序 Load，或已保存卡片 -> Action -> 结果适配。
 * 不保存消息、不启动 Agent、不推进 Workflow；Python 必须先持有请求去重/消息租约，成功后 CAS 提交。
 * Show/映射/分支/适配算法复用迁移实现；仅移除原 Gateway 中的 Cookie、公司存储与传输职责。
 */
@Service
public final class A2uiRuntimeFacade {
    private final PublishedApplicationProvider publications;
    private final CapabilityExecutionPort capabilities;
    private final A2uiApplicationShowRenderer show = new A2uiApplicationShowRenderer();
    private final A2uiCapabilityRequestMapper mapper = new A2uiCapabilityRequestMapper();
    private final A2uiResultAdapterEngine adapters = new A2uiResultAdapterEngine();
    private final A2uiMessageSnapshotReducer reducer = new A2uiMessageSnapshotReducer();
    private final A2uiCapabilityOutcomeEvaluator outcomes = new A2uiCapabilityOutcomeEvaluator();
    private final A2uiActionBindingResolver bindings = new A2uiActionBindingResolver();
    private final A2uiTrustedRuntimeContextProvider clock = new A2uiTrustedRuntimeContextProvider();

    public A2uiRuntimeFacade(PublishedApplicationProvider publications, CapabilityExecutionPort capabilities) {
        this.publications = publications;
        this.capabilities = capabilities;
    }

    /** 只读发布选择，绝不执行 Show、Load 或业务能力。 */
    public Description describe(CapabilityRpcContext context, String appCode) {
        validateContext(context);
        var published = publications.current(appCode, context.environment(), context.userId());
        return new Description(published.identity(), published.build().getParamsSchema(),
                published.build().getInteractionMode().name(), actionDescriptors(published), catalog(published));
    }

    public RuntimeResult activate(CapabilityRpcContext context, ActivateRequest request) {
        validateContext(context);
        if (request == null || request.params() == null) { throw new RuntimeFailure("A2UI_REQUEST_INVALID"); }
        var published = publications.current(request.appCode(), context.environment(), context.userId());
        if (!Objects.equals(published.identity().sourceId(), request.expectedSourceId())
                || !Objects.equals(published.identity().digest(), request.expectedDigest())) {
            throw new RuntimeFailure("RESET_REQUIRED");
        }
        var build = published.build();
        var supplemental = clock.capture();
        var trusted = trusted(context, supplemental);
        var messages = new ArrayList<>(show.render(build, request.params(), new TrustedShowContext(
                context.userId(), context.client(), Long.toString(context.userId()), context.environment().name())));
        var ledger = reducer.reduce(A2uiRuntimeSurfaceLedger.empty(), messages);
        CapabilityExecutionResult previous = null;
        var executions = new ArrayList<ExecutionSummary>();
        // 保留原 Activation 顺序语义：后一个 Load 可读前一个完整结果；业务失败渲染后停止后续 Load。
        for (var binding : build.getLoadBindings()) {
            var args = mapper.map(binding.getRequestMappings(), inputs(context, Map.of(), request.params(),
                    previous, supplemental));
            var result = execute(binding.getCapability().getActionCode(), args, context, binding.getBindingId());
            var batch = adapters.adapt(ledger,
                    result.isSuccess() ? binding.getSuccessOutcome() : binding.getFailureOutcome(),
                    result.isSuccess() ? binding.getResultAdapters() : binding.getFailureResultAdapters(),
                    result, trusted, Map.of());
            messages.addAll(batch.toWireMessages());
            ledger = batch.getNextLedger();
            executions.add(summary(binding.getBindingId(), result, result.isSuccess()));
            previous = result;
            if (!result.isSuccess()) { break; }
        }
        reducer.reduce(A2uiRuntimeSurfaceLedger.empty(), messages);
        var catalog = build.getCatalog();
        var session = new dev.a2flow.management.a2ui.gateway.A2uiActionGatewayModels.A2uiRuntimeSession(
                java.util.UUID.randomUUID().toString(), build.getAppBuildId(), build.getProtocolVersion(),
                catalog.getCatalogId(), catalog.getRevision(), catalog.getDigest());
        return response(published, request.params(), messages, ledger, executions, false, null, session);
    }

    public RuntimeResult act(CapabilityRpcContext context, ActionRequest request) {
        validateContext(context);
        if (request == null || request.card() == null || request.invocation() == null) {
            throw new RuntimeFailure("A2UI_REQUEST_INVALID");
        }
        var card = request.card();
        if (card.release() == null || card.userId() != context.userId()
                || card.release().environment() != context.environment() || card.params() == null
                || card.snapshot() == null || card.revision() != request.invocation().getExpectedSurfaceRevision()
                || !Objects.equals(context.requestId(), request.invocation().getIdempotencyKey())) {
            throw new RuntimeFailure("A2UI_CARD_CONTEXT_MISMATCH");
        }
        var published = publications.current(card.release().appCode(), context.environment(), context.userId());
        if (!published.identity().equals(card.release())) { throw new RuntimeFailure("RESET_REQUIRED"); }
        var resolved = bindings.resolve(request.invocation(), card.session(), published.build());
        var ledger = reducer.reduce(A2uiRuntimeSurfaceLedger.empty(), card.snapshot());
        if (!ledger.hasSurface(resolved.getSurfaceId())) { throw new RuntimeFailure("A2UI_SURFACE_NOT_FOUND"); }
        var binding = resolved.getBinding();
        var supplemental = clock.capture();
        var args = mapper.map(binding.getRequestMappings(), inputs(context, resolved.getActionContext(),
                card.params(), null, supplemental));
        var result = execute(binding.getCapability().getActionCode(), args, context, binding.getBindingId());
        var selected = outcomes.select(binding, result);
        var batch = adapters.adapt(ledger, selected.getOutcome(), selected.getAdapters(), result,
                trusted(context, supplemental), resolved.getActionContext());
        return response(published, card.params(), batch.toWireMessages(), batch.getNextLedger(),
                List.of(summary(binding.getBindingId(), result, selected.isSucceeded())),
                selected.isCompletesWorkflowInteraction(), selected.getBranchId(), card.session());
    }

    private CapabilityExecutionResult execute(String actionCode, Map<String, Object> arguments,
            CapabilityRpcContext context, String bindingId) {
        // 子请求稳定绑定 binding，重放不能把不同 Load 当成同一业务请求；不自动重试。
        var child = new CapabilityRpcContext(context.userId(), context.environment(),
                "a2ui:" + dev.a2flow.management.release.ReleaseDigestUtils.sha256(
                        JsonSupport.toJSON(List.of(context.requestId(), bindingId))), context.client());
        var result = capabilities.executeActionCode(actionCode, JsonSupport.toJSON(arguments), child);
        if (result == null) { throw new RuntimeFailure("A2UI_CAPABILITY_RESULT_INVALID"); }
        return CapabilityExecutionResult.builder().actionCode(result.getActionCode())
                .capabilityVersion(result.getCapabilityVersion()).clientType(result.getClientType())
                .requestedEnvironment(context.environment().name())
                .resolvedEnvironment(result.getResolvedEnvironment() == null ? null : result.getResolvedEnvironment().name())
                .success(result.isSuccess()).httpStatus(result.getHttpStatus() > 0 ? result.getHttpStatus() : null)
                .contentType(result.getContentType()).traceId(result.getTraceId()).data(result.getData())
                .errorCode(result.getErrorCode() == null ? null : result.getErrorCode().name())
                .message(result.getMessage()).build();
    }

    private MappingInputs inputs(CapabilityRpcContext context, Map<String, Object> action,
            Map<String, Object> params, CapabilityExecutionResult previous, Map<String, Object> supplemental) {
        return new MappingInputs(action, params, previous == null ? null : previous.toMap(),
                context.userId(), context.client(), Long.toString(context.userId()),
                context.environment().name(), supplemental);
    }

    private Map<String, Object> trusted(CapabilityRpcContext context, Map<String, Object> supplemental) {
        var result = new LinkedHashMap<String, Object>(supplemental);
        result.put("userId", context.userId());
        result.put("client", context.client());
        result.put("operator", Long.toString(context.userId()));
        result.put("environment", context.environment().name());
        return result;
    }

    private ExecutionSummary summary(String bindingId, CapabilityExecutionResult result, boolean success) {
        return new ExecutionSummary(bindingId, result.getActionCode(), success,
                result.getCapabilityVersion(), result.getErrorCode());
    }

    private RuntimeResult response(PublishedApplication published, Map<String, Object> params,
            List<Map<String, Object>> messages, A2uiRuntimeSurfaceLedger ledger,
            List<ExecutionSummary> executions, boolean complete, String branch,
            dev.a2flow.management.a2ui.gateway.A2uiActionGatewayModels.A2uiRuntimeSession session) {
        return new RuntimeResult(published.identity(), params, List.copyOf(messages),
                reducer.toSnapshotMessages(ledger), List.copyOf(executions), actionDescriptors(published),
                complete, branch, catalog(published), session, published.build().getInteractionMode().name(),
                executions.stream().allMatch(ExecutionSummary::success));
    }

    private List<ActionDescriptor> actionDescriptors(PublishedApplication published) {
        return published.build().getActionBindings().stream().map(binding -> new ActionDescriptor(
                binding.getSurfaceId(), binding.getSourceComponentId(), binding.getActionCode(),
                binding.getContextSchema())).toList();
    }

    private CatalogDescriptor catalog(PublishedApplication published) {
        var build = published.build();
        return new CatalogDescriptor(build.getProtocolVersion(), build.getCatalog().getCatalogId(),
                build.getCatalog().getRevision(), build.getCatalog().getDigest());
    }

    private void validateContext(CapabilityRpcContext context) {
        if (context == null || context.environment() == null || context.requestId() == null
                || context.requestId().isBlank() || context.client() == null || context.client().isBlank()) {
            throw new RuntimeFailure("A2UI_TRUSTED_CONTEXT_REQUIRED");
        }
    }
}
