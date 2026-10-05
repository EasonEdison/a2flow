package dev.a2flow.management.a2ui.preview;

import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.google.protobuf.ByteString;

import dev.a2flow.management.a2ui.runtime.proto.A2uiExecutionGrpc;
import dev.a2flow.management.a2ui.runtime.proto.ActRequest;
import dev.a2flow.management.a2ui.runtime.proto.ActivateRequest;
import dev.a2flow.management.a2ui.runtime.proto.RuntimeResponse;
import dev.a2flow.management.a2ui.runtime.proto.TrustedCard;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.capabilityrpc.GrpcTargetRegistry;
import dev.a2flow.management.capabilityrpc.proto.Environment;
import dev.a2flow.management.capabilityrpc.proto.ExecutionContext;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository;
import dev.a2flow.management.support.JsonSupport;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

/** ADMIN-only, process-local PRT Application integration sessions backed by the Python executor. */
@Service
public final class A2uiPrtPreviewService {
    static final String TARGET_KEY = "a2ui-execution";
    static final Duration SESSION_TTL = Duration.ofMinutes(15);
    static final int MAX_GLOBAL_SESSIONS = 100;
    static final int MAX_OWNER_SESSIONS = 10;
    private static final int MAX_RECEIPTS = 64;
    private static final int MAX_START_RECEIPTS = 200;
    private static final long RPC_TIMEOUT_SECONDS = 15;
    private static final String ASSET_TYPE = "A2UI_APPLICATION";
    private static final Pattern POSITIVE_INT64 = Pattern.compile("[1-9][0-9]{0,18}");
    private static final Pattern REQUEST_ID = Pattern.compile("[A-Za-z0-9._:-]{1,120}");
    private static final Pattern IDENTIFIER = Pattern.compile("[A-Za-z0-9._:-]{1,160}");
    private static final TypeReference<Map<String, Object>> OBJECT = new TypeReference<>() { };
    private static final TypeReference<List<Map<String, Object>>> MESSAGE_LIST = new TypeReference<>() { };

    private final AssetAuthorizationService authorization;
    private final SkillFactoryComponentAssetRepository applications;
    private final GrpcTargetRegistry targets;
    private final ConcurrentHashMap<String, PreviewSession> sessions = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, StartReceipt> starts = new ConcurrentHashMap<>();
    private final Object capacityLock = new Object();

    public A2uiPrtPreviewService(AssetAuthorizationService authorization,
            SkillFactoryComponentAssetRepository applications, GrpcTargetRegistry targets) {
        this.authorization = authorization;
        this.applications = applications;
        this.targets = targets;
    }

    public Map<String, Object> start(String operator, Map<String, String> params) {
        requireAdmin(operator);
        rejectRuntimeAuthority(params);
        long targetUserId = positiveUserId(required(params, "targetUserId"));
        String requestId = requestId(required(params, "requestId"));
        String paramsJson = canonicalObject(required(params, "paramsJson"), "A2UI_PRT_PREVIEW_PARAMS_INVALID");
        ComponentAsset application = applications.get(positiveId(required(params, "id")));
        if (application == null || !ASSET_TYPE.equals(application.getAssetType())
                || StringUtils.isBlank(application.getComponentName())) {
            throw failure("A2UI_PRT_PREVIEW_APPLICATION_NOT_FOUND");
        }
        String fingerprint = dev.a2flow.management.release.ReleaseDigestUtils.sha256(
                JsonSupport.toJSON(List.of(application.getId(), application.getComponentName(),
                        targetUserId, paramsJson)));
        String key = operator + "\u0000" + requestId;
        PreviewSession session;
        synchronized (capacityLock) {
            cleanup();
            StartReceipt prior = starts.get(key);
            if (prior != null) {
                return prior.resultOrThrow(fingerprint);
            }
            if (starts.size() >= MAX_START_RECEIPTS) {
                throw failure("A2UI_PRT_PREVIEW_REQUEST_LIMIT_REACHED");
            }
            enforceCapacity(operator);
            starts.put(key, StartReceipt.running(Instant.now(), fingerprint));
            session = PreviewSession.reserve(operator, targetUserId,
                    application.getComponentName(), Instant.now());
            sessions.put(session.sessionId, session);
        }
        try {
            RuntimeResponse runtime = stub().activate(ActivateRequest.newBuilder()
                    .setContext(context(targetUserId, requestId))
                    .setAppCode(application.getComponentName())
                    .setParamsJson(ByteString.copyFromUtf8(paramsJson)).build());
            ValidatedRuntime validated = validateRuntime(session, runtime);
            Instant expiresAt = Instant.now().plus(SESSION_TTL);
            Map<String, Object> result = response(session, runtime, validated, requestId, expiresAt);
            session.update(validated, expiresAt);
            starts.put(key, StartReceipt.succeeded(Instant.now(), fingerprint, result));
            return deepCopy(result);
        } catch (RuntimeException exception) {
            A2uiPrtPreviewException projected = projectRpcFailure(exception);
            sessions.remove(session.sessionId, session);
            starts.put(key, StartReceipt.failed(Instant.now(), fingerprint, projected.getErrorCode()));
            throw projected;
        }
    }

    public Map<String, Object> action(String operator, Map<String, String> params) {
        requireAdmin(operator);
        rejectRuntimeAuthority(params);
        if (!"true".equals(params.get("confirmed"))) {
            throw failure("A2UI_PRT_PREVIEW_CONFIRMATION_REQUIRED");
        }
        PreviewSession session = ownedSession(operator, required(params, "sessionId"));
        String requestId = requestId(required(params, "requestId"));
        String actionName = identifier(required(params, "actionName"));
        String surfaceId = identifier(required(params, "surfaceId"));
        String sourceComponentId = identifier(required(params, "sourceComponentId"));
        Map<String, Object> context = object(required(params, "contextJson"),
                "A2UI_PRT_PREVIEW_ACTION_CONTEXT_INVALID");
        String digest = dev.a2flow.management.release.ReleaseDigestUtils.sha256(JsonSupport.toJSON(
                List.of(actionName, surfaceId, sourceComponentId, context)));
        synchronized (session) {
            session.requireActive(Instant.now());
            ActionReceipt prior = session.receipts.get(requestId);
            if (prior != null) {
                return prior.resultOrThrow(digest);
            }
            if (session.receipts.size() >= MAX_RECEIPTS) {
                throw failure("A2UI_PRT_PREVIEW_REQUEST_LIMIT_REACHED");
            }
            session.receipts.put(requestId, ActionReceipt.running(digest));
            Map<String, Object> action = new LinkedHashMap<>();
            action.put("name", actionName);
            action.put("surfaceId", surfaceId);
            action.put("sourceComponentId", sourceComponentId);
            action.put("timestamp", OffsetDateTime.now(ZoneOffset.UTC).toString());
            action.put("context", context);
            String actionJson = JsonSupport.toJSON(Map.of(
                    "version", session.protocolVersion,
                    "action", action));
            try {
                RuntimeResponse runtime = stub().act(ActRequest.newBuilder()
                        .setContext(context(session.targetUserId, requestId))
                        .setCard(TrustedCard.newBuilder().setUserId(session.targetUserId)
                                .setAppCode(session.appCode)
                                .setParamsJson(ByteString.copyFromUtf8(session.paramsJson))
                                .setSnapshotJson(ByteString.copyFromUtf8(session.snapshotJson)))
                        .setCorrelationId(session.previewCardId)
                        .setIdempotencyKey(requestId)
                        .setActionMessageJson(ByteString.copyFromUtf8(actionJson)).build());
                ValidatedRuntime validated = validateRuntime(session, runtime);
                Instant expiresAt = Instant.now().plus(SESSION_TTL);
                Map<String, Object> result = response(session, runtime, validated, requestId, expiresAt);
                session.update(validated, expiresAt);
                session.receipts.put(requestId, ActionReceipt.succeeded(digest, result));
                return deepCopy(result);
            } catch (RuntimeException exception) {
                A2uiPrtPreviewException projected = projectRpcFailure(exception);
                session.receipts.put(requestId, ActionReceipt.failed(digest, projected.getErrorCode()));
                throw projected;
            }
        }
    }

    public Map<String, Object> close(String operator, Map<String, String> params) {
        requireAdmin(operator);
        rejectRuntimeAuthority(params);
        PreviewSession session = ownedSession(operator, required(params, "sessionId"));
        synchronized (session) {
            session.closed = true;
            sessions.remove(session.sessionId, session);
        }
        return Map.of("sessionId", session.sessionId, "closed", true);
    }

    private A2uiExecutionGrpc.A2uiExecutionBlockingStub stub() {
        return A2uiExecutionGrpc.newBlockingStub(targets.channel(TARGET_KEY, ReleaseEnvironment.PRT))
                .withDeadlineAfter(RPC_TIMEOUT_SECONDS, TimeUnit.SECONDS);
    }

    private ExecutionContext context(long targetUserId, String requestId) {
        return ExecutionContext.newBuilder().setUserId(targetUserId).setEnvironment(Environment.PRT)
                .setRequestId(requestId).setClient("PC").build();
    }

    private Map<String, Object> response(PreviewSession session, RuntimeResponse runtime,
            ValidatedRuntime validated, String requestId, Instant expiresAt) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("sessionId", session.sessionId);
        result.put("previewCardId", session.previewCardId);
        result.put("targetUserId", Long.toString(session.targetUserId));
        result.put("environment", "PRT");
        result.put("client", "PC");
        result.put("appCode", session.appCode);
        result.put("requestId", requestId);
        result.put("expiresAt", expiresAt.toString());
        result.put("release", Map.of(
                "appCode", runtime.getRelease().getAppCode(),
                "sourceId", runtime.getRelease().getSourceId(),
                "digest", runtime.getRelease().getDigest(),
                "appBuildId", runtime.getRelease().getAppBuildId(),
                "environment", runtime.getRelease().getEnvironment().name()));
        result.put("catalog", Map.of(
                "protocolVersion", runtime.getCatalog().getProtocolVersion(),
                "catalogId", runtime.getCatalog().getCatalogId(),
                "catalogRevision", runtime.getCatalog().getCatalogRevision(),
                "catalogDigest", runtime.getCatalog().getCatalogDigest()));
        result.put("messages", validated.snapshot);
        result.put("actions", runtime.getActionsList().stream().map(value -> Map.of(
                "name", value.getActionName(),
                "surfaceId", value.getSurfaceId(),
                "sourceComponentId", value.getComponentId())).toList());
        result.put("executions", runtime.getExecutionsList().stream().map(value -> Map.of(
                "bindingId", value.getBindingId(), "actionCode", value.getActionCode(),
                "success", value.getSuccess(), "capabilityVersion", value.getCapabilityVersion(),
                "errorCode", value.getErrorCode())).toList());
        List<Map<String, Object>> effects = new ArrayList<>();
        runtime.getComposerDraftEffectsList().forEach(value -> effects.add(Map.of(
                "type", value.getType(), "mode", value.getMode(),
                "requestId", value.getRequestId(), "text", value.getText())));
        result.put("composerDraftEffects", effects);
        result.put("businessSuccess", runtime.getBusinessSuccess());
        result.put("completeInteraction", runtime.getCompleteInteraction());
        result.put("selectedBranchId", runtime.getSelectedBranchId());
        return deepCopy(result);
    }

    private ValidatedRuntime validateRuntime(PreviewSession session, RuntimeResponse runtime) {
        if (StringUtils.isNotBlank(runtime.getErrorCode())
                || !session.appCode.equals(runtime.getRelease().getAppCode())
                || runtime.getRelease().getEnvironment() != Environment.PRT
                || StringUtils.isAnyBlank(runtime.getRelease().getSourceId(),
                        runtime.getRelease().getDigest(), runtime.getRelease().getAppBuildId(),
                        runtime.getCatalog().getProtocolVersion())) {
            throw failure(StringUtils.isNotBlank(runtime.getErrorCode())
                    ? runtime.getErrorCode() : "A2UI_PRT_PREVIEW_RELEASE_MISMATCH");
        }
        String paramsJson = canonicalObject(runtime.getParamsJson().toStringUtf8(),
                "A2UI_PRT_PREVIEW_RUNTIME_RESPONSE_INVALID");
        List<Map<String, Object>> snapshot = read(runtime.getSnapshotJson(), MESSAGE_LIST,
                "A2UI_PRT_PREVIEW_RUNTIME_RESPONSE_INVALID");
        return new ValidatedRuntime(paramsJson, runtime.getSnapshotJson().toStringUtf8(),
                runtime.getCatalog().getProtocolVersion(), snapshot);
    }

    private void requireAdmin(String operator) {
        if (!authorization.isAdmin(operator)) {
            throw failure("A2UI_PRT_PREVIEW_ADMIN_REQUIRED");
        }
    }

    private void rejectRuntimeAuthority(Map<String, String> params) {
        if (params != null && (params.containsKey("environment") || params.containsKey("client")
                || params.containsKey("appCode") || params.containsKey("snapshotJson")
                || params.containsKey("trustedCard") || params.containsKey("runtimeSessionToken"))) {
            throw failure("A2UI_PRT_PREVIEW_AUTHORITY_INPUT_FORBIDDEN");
        }
    }

    private PreviewSession ownedSession(String operator, String sessionId) {
        if (!isUuid(sessionId)) {
            throw failure("A2UI_PRT_PREVIEW_SESSION_INVALID");
        }
        PreviewSession session = sessions.get(sessionId);
        if (session == null || !session.operator.equals(operator)) {
            throw failure("A2UI_PRT_PREVIEW_SESSION_NOT_FOUND");
        }
        return session;
    }

    private void cleanup() {
        Instant now = Instant.now();
        sessions.entrySet().removeIf(entry -> entry.getValue().expired(now));
        starts.entrySet().removeIf(entry -> entry.getValue().expired(now));
    }

    private void enforceCapacity(String operator) {
        if (sessions.size() >= MAX_GLOBAL_SESSIONS
                || sessions.values().stream().filter(value -> value.operator.equals(operator)).count()
                        >= MAX_OWNER_SESSIONS) {
            throw failure("A2UI_PRT_PREVIEW_SESSION_LIMIT_REACHED");
        }
    }

    private A2uiPrtPreviewException projectRpcFailure(RuntimeException exception) {
        if (exception instanceof A2uiPrtPreviewException preview) {
            return preview;
        }
        if (exception instanceof StatusRuntimeException rpc) {
            Status.Code code = rpc.getStatus().getCode();
            String description = rpc.getStatus().getDescription();
            if (code == Status.Code.DEADLINE_EXCEEDED || code == Status.Code.UNAVAILABLE
                    || code == Status.Code.UNKNOWN || code == Status.Code.INTERNAL) {
                return failure("A2UI_PRT_PREVIEW_OUTCOME_UNKNOWN");
            }
            if (description != null && description.matches("[A-Z0-9_]{1,120}")) {
                return failure(description);
            }
            return failure("A2UI_PRT_PREVIEW_EXECUTION_FAILED");
        }
        return failure("A2UI_PRT_PREVIEW_EXECUTION_FAILED");
    }

    private long positiveId(String value) {
        return positiveLong(value, "A2UI_PRT_PREVIEW_APPLICATION_ID_INVALID");
    }

    private long positiveUserId(String value) {
        return positiveLong(value, "A2UI_PRT_PREVIEW_TARGET_USER_ID_INVALID");
    }

    private long positiveLong(String value, String code) {
        if (!POSITIVE_INT64.matcher(value).matches()) {
            throw failure(code);
        }
        try {
            long parsed = Long.parseLong(value);
            if (parsed <= 0) {
                throw failure(code);
            }
            return parsed;
        } catch (NumberFormatException exception) {
            throw failure(code);
        }
    }

    private String requestId(String value) {
        if (!REQUEST_ID.matcher(value).matches()) {
            throw failure("A2UI_PRT_PREVIEW_REQUEST_ID_INVALID");
        }
        return value;
    }

    private String identifier(String value) {
        if (!IDENTIFIER.matcher(value).matches()) {
            throw failure("A2UI_PRT_PREVIEW_ACTION_INVALID");
        }
        return value;
    }

    private String canonicalObject(String value, String code) {
        return JsonSupport.toJSON(object(value, code));
    }

    private Map<String, Object> object(String value, String code) {
        try {
            Map<String, Object> result = JsonSupport.mapper().readValue(value, OBJECT);
            if (result == null) {
                throw failure(code);
            }
            return result;
        } catch (A2uiPrtPreviewException exception) {
            throw exception;
        } catch (Exception exception) {
            throw failure(code);
        }
    }

    private <T> T read(ByteString value, TypeReference<T> type, String code) {
        try {
            T result = JsonSupport.mapper().readValue(value.toByteArray(), type);
            if (result == null) {
                throw failure(code);
            }
            return result;
        } catch (A2uiPrtPreviewException exception) {
            throw exception;
        } catch (Exception exception) {
            throw failure(code);
        }
    }

    private Map<String, Object> deepCopy(Map<String, Object> value) {
        return copy(value);
    }

    private static Map<String, Object> copy(Map<String, Object> value) {
        try {
            return JsonSupport.mapper().readValue(JsonSupport.toJSON(value), OBJECT);
        } catch (Exception exception) {
            throw new A2uiPrtPreviewException("A2UI_PRT_PREVIEW_RUNTIME_RESPONSE_INVALID");
        }
    }

    private String required(Map<String, String> params, String field) {
        String value = params == null ? null : params.get(field);
        if (StringUtils.isBlank(value)) {
            throw failure("A2UI_PRT_PREVIEW_" + field.replaceAll("([a-z])([A-Z])", "$1_$2")
                    .toUpperCase() + "_REQUIRED");
        }
        return value;
    }

    private boolean isUuid(String value) {
        try {
            return UUID.fromString(value).toString().equals(value);
        } catch (RuntimeException exception) {
            return false;
        }
    }

    private A2uiPrtPreviewException failure(String code) {
        return new A2uiPrtPreviewException(code);
    }

    private static final class PreviewSession {
        private final String sessionId = UUID.randomUUID().toString();
        private final String previewCardId = UUID.randomUUID().toString();
        private final String operator;
        private final long targetUserId;
        private final String appCode;
        private String paramsJson;
        private String snapshotJson;
        private String protocolVersion;
        private volatile Instant expiresAt;
        private boolean closed;
        private final LinkedHashMap<String, ActionReceipt> receipts = new LinkedHashMap<>();

        private PreviewSession(String operator, long targetUserId, String appCode) {
            this.operator = operator;
            this.targetUserId = targetUserId;
            this.appCode = appCode;
        }

        static PreviewSession reserve(String operator, long targetUserId, String appCode,
                Instant now) {
            PreviewSession value = new PreviewSession(operator, targetUserId, appCode);
            value.expiresAt = now.plus(SESSION_TTL);
            return value;
        }

        void update(ValidatedRuntime response, Instant expiresAt) {
            paramsJson = response.paramsJson;
            snapshotJson = response.snapshotJson;
            protocolVersion = response.protocolVersion;
            this.expiresAt = expiresAt;
        }

        synchronized boolean expired(Instant now) {
            return closed || !expiresAt.isAfter(now);
        }

        void requireActive(Instant now) {
            if (closed || !expiresAt.isAfter(now)) {
                throw new A2uiPrtPreviewException("A2UI_PRT_PREVIEW_SESSION_EXPIRED");
            }
        }
    }

    private record ValidatedRuntime(String paramsJson, String snapshotJson, String protocolVersion,
            List<Map<String, Object>> snapshot) { }

    private record StartReceipt(Instant createdAt, String fingerprint, String state, Map<String, Object> result,
            String errorCode) {
        static StartReceipt running(Instant now, String fingerprint) {
            return new StartReceipt(now, fingerprint, "RUNNING", null, null);
        }
        static StartReceipt succeeded(Instant now, String fingerprint, Map<String, Object> result) {
            return new StartReceipt(now, fingerprint, "SUCCEEDED", result, null);
        }
        static StartReceipt failed(Instant now, String fingerprint, String errorCode) {
            return new StartReceipt(now, fingerprint, "FAILED", null, errorCode);
        }
        boolean expired(Instant now) { return !createdAt.plus(SESSION_TTL).isAfter(now); }
        Map<String, Object> resultOrThrow(String requestedFingerprint) {
            if (!fingerprint.equals(requestedFingerprint)) {
                throw new A2uiPrtPreviewException("A2UI_PRT_PREVIEW_REQUEST_ID_REUSE_MISMATCH");
            }
            if ("SUCCEEDED".equals(state)) {
                return copy(result);
            }
            if ("RUNNING".equals(state)) {
                throw new A2uiPrtPreviewException("A2UI_PRT_PREVIEW_REQUEST_IN_PROGRESS");
            }
            throw new A2uiPrtPreviewException(errorCode);
        }
    }

    private record ActionReceipt(String digest, String state, Map<String, Object> result,
            String errorCode) {
        static ActionReceipt running(String digest) {
            return new ActionReceipt(digest, "RUNNING", null, null);
        }
        static ActionReceipt succeeded(String digest, Map<String, Object> result) {
            return new ActionReceipt(digest, "SUCCEEDED", result, null);
        }
        static ActionReceipt failed(String digest, String errorCode) {
            return new ActionReceipt(digest, "FAILED", null, errorCode);
        }
        Map<String, Object> resultOrThrow(String requestedDigest) {
            if (!digest.equals(requestedDigest)) {
                throw new A2uiPrtPreviewException("A2UI_PRT_PREVIEW_REQUEST_ID_REUSE_MISMATCH");
            }
            if ("SUCCEEDED".equals(state)) {
                return copy(result);
            }
            if ("RUNNING".equals(state)) {
                throw new A2uiPrtPreviewException("A2UI_PRT_PREVIEW_REQUEST_IN_PROGRESS");
            }
            throw new A2uiPrtPreviewException(errorCode);
        }
    }
}
