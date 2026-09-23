package dev.a2flow.management.a2ui.gateway;

import static dev.a2flow.management.a2ui.gateway.A2uiActionGatewayErrorCode.ACTION_INVALID;
import static dev.a2flow.management.a2ui.gateway.A2uiActionGatewayErrorCode.ACTION_NOT_BOUND;
import static dev.a2flow.management.a2ui.gateway.A2uiActionGatewayErrorCode.ACTION_SOURCE_INVALID;
import static dev.a2flow.management.a2ui.gateway.A2uiActionGatewayErrorCode.BUILD_ACTION_CLOSURE_INVALID;
import static dev.a2flow.management.a2ui.gateway.A2uiActionGatewayErrorCode.RUNTIME_SESSION_MISMATCH;

import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiActionDeclaration;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationBuild;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledActionBinding;
import dev.a2flow.management.a2ui.gateway.A2uiActionGatewayModels.A2uiActionInvocation;
import dev.a2flow.management.a2ui.gateway.A2uiActionGatewayModels.A2uiResolvedAction;
import dev.a2flow.management.a2ui.gateway.A2uiActionGatewayModels.A2uiRuntimeSession;

/**
 * v0.9.1 Action 到不可变 Build ActionBinding 的唯一解析器。
 *
 * <p>上游传入 transport-neutral invocation、服务端 session 快照和已发布 Build；下游 mapper 只接收
 * closure 已验证的 binding/context。本类不查询 latest/draft，不执行 Capability，不选择物理 transport，
 * 也不把非法 A2UI Action 送入 Adviser/CARD fallback。
 */
public class A2uiActionBindingResolver {

    private static final String PROTOCOL_VERSION = "v0.9.1";
    private static final String MESSAGE_VERSION_KEY = "version";
    private static final String MESSAGE_ACTION_KEY = "action";
    private static final String ACTION_NAME_KEY = "name";
    private static final String ACTION_SURFACE_ID_KEY = "surfaceId";
    private static final String ACTION_SOURCE_COMPONENT_ID_KEY = "sourceComponentId";
    private static final String ACTION_TIMESTAMP_KEY = "timestamp";
    private static final String ACTION_CONTEXT_KEY = "context";
    private static final Set<String> MESSAGE_KEYS = Set.of(MESSAGE_VERSION_KEY, MESSAGE_ACTION_KEY);
    private static final Set<String> ACTION_KEYS = Set.of(
            ACTION_NAME_KEY, ACTION_SURFACE_ID_KEY, ACTION_SOURCE_COMPONENT_ID_KEY,
            ACTION_TIMESTAMP_KEY, ACTION_CONTEXT_KEY);

    private final A2uiActionContextValidator contextValidator = new A2uiActionContextValidator();

    /** 解析并验证一个完整 Action；失败时不会返回 binding 或部分 context。 */
    public A2uiResolvedAction resolve(A2uiActionInvocation invocation,
            A2uiRuntimeSession session, A2uiApplicationBuild build) {
        validateSession(invocation, session, build);
        Map<String, Object> action = parseAction(invocation.getMessage());
        String name = stringValue(action.get(ACTION_NAME_KEY));
        String surfaceId = stringValue(action.get(ACTION_SURFACE_ID_KEY));
        String sourceComponentId = stringValue(action.get(ACTION_SOURCE_COMPONENT_ID_KEY));
        String timestamp = stringValue(action.get(ACTION_TIMESTAMP_KEY));
        Map<String, Object> context = mapValue(action.get(ACTION_CONTEXT_KEY));
        if (isBlank(name) || isBlank(surfaceId) || isBlank(sourceComponentId)
                || isBlank(timestamp) || context == null || !validTimestamp(timestamp)) {
            throw new A2uiActionGatewayException(ACTION_INVALID);
        }
        A2uiCompiledActionBinding binding = resolveBinding(build, surfaceId, name);
        if (!Objects.equals(sourceComponentId, binding.getSourceComponentId())
                || binding.getAllowedSourceComponentIds() == null
                || !binding.getAllowedSourceComponentIds().contains(sourceComponentId)) {
            throw new A2uiActionGatewayException(ACTION_SOURCE_INVALID);
        }
        validateDeclarationClosure(build, binding);
        contextValidator.validate(context, binding.getContextSchema());
        return new A2uiResolvedAction(
                invocation,
                name,
                surfaceId,
                sourceComponentId,
                timestamp,
                A2uiGatewayJsonSupport.immutableMap(context),
                binding);
    }

    private void validateSession(A2uiActionInvocation invocation,
            A2uiRuntimeSession session, A2uiApplicationBuild build) {
        if (invocation == null || session == null || build == null
                || isBlank(invocation.getCorrelationId())
                || isBlank(invocation.getRuntimeSessionToken())
                || isBlank(invocation.getAppBuildId())
                || isBlank(invocation.getIdempotencyKey())
                || invocation.getExpectedSurfaceRevision() < 0
                || !Objects.equals(invocation.getRuntimeSessionToken(), session.getRuntimeSessionToken())
                || !Objects.equals(invocation.getAppBuildId(), session.getAppBuildId())
                || !Objects.equals(build.getAppBuildId(), session.getAppBuildId())
                || !Objects.equals(PROTOCOL_VERSION, session.getProtocolVersion())
                || !Objects.equals(build.getProtocolVersion(), session.getProtocolVersion())
                || build.getCatalog() == null
                || !Objects.equals(build.getCatalog().getCatalogId(), session.getCatalogId())
                || !Objects.equals(build.getCatalog().getRevision(), session.getCatalogRevision())
                || !Objects.equals(build.getCatalog().getDigest(), session.getCatalogDigest())) {
            throw new A2uiActionGatewayException(RUNTIME_SESSION_MISMATCH);
        }
    }

    private Map<String, Object> parseAction(Map<String, Object> message) {
        if (message == null || !MESSAGE_KEYS.equals(message.keySet())
                || !Objects.equals(PROTOCOL_VERSION, message.get(MESSAGE_VERSION_KEY))) {
            throw new A2uiActionGatewayException(ACTION_INVALID);
        }
        Map<String, Object> action = mapValue(message.get(MESSAGE_ACTION_KEY));
        if (action == null || !ACTION_KEYS.equals(action.keySet())) {
            throw new A2uiActionGatewayException(ACTION_INVALID);
        }
        return action;
    }

    private A2uiCompiledActionBinding resolveBinding(A2uiApplicationBuild build,
            String surfaceId, String actionName) {
        if (build.getActionBindings() == null) {
            throw new A2uiActionGatewayException(BUILD_ACTION_CLOSURE_INVALID);
        }
        List<A2uiCompiledActionBinding> bindings = build.getActionBindings().stream()
                .filter(Objects::nonNull)
                .filter(value -> Objects.equals(surfaceId, value.getSurfaceId())
                        && Objects.equals(actionName, value.getActionCode()))
                .collect(Collectors.toList());
        if (bindings.isEmpty()) {
            throw new A2uiActionGatewayException(ACTION_NOT_BOUND);
        }
        if (bindings.size() != 1) {
            throw new A2uiActionGatewayException(BUILD_ACTION_CLOSURE_INVALID);
        }
        return bindings.get(0);
    }

    private void validateDeclarationClosure(A2uiApplicationBuild build,
            A2uiCompiledActionBinding binding) {
        if (build.getActionDeclarations() == null || isBlank(binding.getDeclarationDigest())) {
            throw new A2uiActionGatewayException(BUILD_ACTION_CLOSURE_INVALID);
        }
        List<A2uiActionDeclaration> declarations = build.getActionDeclarations().stream()
                .filter(Objects::nonNull)
                .filter(value -> Objects.equals(binding.getSurfaceId(), value.getSurfaceId())
                        && Objects.equals(binding.getActionCode(), value.getActionCode()))
                .collect(Collectors.toList());
        if (declarations.size() != 1) {
            throw new A2uiActionGatewayException(BUILD_ACTION_CLOSURE_INVALID);
        }
        A2uiActionDeclaration declaration = declarations.get(0);
        if (!Objects.equals(binding.getSourceComponentId(), declaration.getSourceComponentId())
                || !Objects.equals(binding.getDeclarationDigest(),
                        declaration.getContextTemplateDigest())) {
            throw new A2uiActionGatewayException(BUILD_ACTION_CLOSURE_INVALID);
        }
    }

    private boolean validTimestamp(String timestamp) {
        try {
            Instant.parse(timestamp);
            return true;
        } catch (DateTimeParseException e) {
            return false;
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : null;
    }

    private String stringValue(Object value) {
        return value instanceof String ? (String) value : null;
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}
