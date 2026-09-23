package dev.a2flow.management.lifecycle;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Pattern;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.support.TraceIds;
import dev.a2flow.management.access.AssetAction;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.agentcore.runtime.engine.model.BaseAgentContext;
import dev.a2flow.management.agentcore.runtime.tool.CapabilityActionToolProvider;
import dev.a2flow.management.agentcore.runtime.tool.TrustedToolContext;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.model.CapabilityActionExecutionPreview;
import dev.a2flow.management.release.AssetReleaseApplicationService;
import dev.a2flow.management.release.ReleaseAssetAdapter;
import dev.a2flow.management.release.ReleaseAssetAdapterRegistry;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.ReleaseValidationEvidence;

import lombok.extern.slf4j.Slf4j;

/**
 * 能力中心校验页的直接 dry-run 服务。
 *
 * <p>上游是统一 SkillFactory M 端 handler 的 {@code CAPABILITY_DRY_RUN} method，下游复用已发布运行链路
 * 的 Provider、Executor 和 Protobuf gRPC Transport。编辑权限校验后，只执行精确 revision 的已保存草稿。
 * 环境只允许显式选择 PRT/ONLINE，支持端只允许显式选择 PC/APP/COMMON，模型入参只读取该
 * revision 对应端的 canonical 入参 Demo。
 * userId 来自可信宿主；Cookie/curl 输入明确拒绝，不进入执行上下文。
 */
@Service
@Slf4j
public class CapabilityActionDryRunService {
    @Resource
    private dev.a2flow.management.access.ManagementIdentityProvider managementIdentityProvider;

    private static final String PARAM_DRAFT_ID = "draftId";
    private static final String PARAM_REVISION = "revision";
    private static final String PARAM_ENVIRONMENT = "environment";
    private static final String PARAM_CLIENT_TYPE = "clientType";
    private static final String PARAM_CREDENTIAL_INPUT = "credentialInput";
    private static final String FIELD_AGENT_CONTEXT = "agentContext";
    private static final String FIELD_BASIC_INFO = "basicInfo";
    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_CLIENT_VARIANTS = "clientVariants";
    private static final String FIELD_MODEL_CONTRACT = "modelContract";
    private static final String FIELD_INPUT_EXAMPLE_JSON = "inputExampleJson";
    private static final String FIELD_SUCCESS = "success";
    private static final String FIELD_HTTP_STATUS = "httpStatus";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final String FIELD_ENVIRONMENT = "environment";
    private static final String FIELD_CLIENT_TYPE = "clientType";
    private static final String FIELD_EFFECTIVE_ARGUMENTS = "effectiveArguments";
    private static final String FIELD_EFFECTIVE_REQUEST_BODY = "effectiveRequestBody";
    private static final String FIELD_TOOL_RESULT = "toolResult";
    private static final String CHECK_CAPABILITY_DRY_RUN_PC = "CAPABILITY_DRY_RUN_PC";
    private static final String CHECK_CAPABILITY_DRY_RUN_APP = "CAPABILITY_DRY_RUN_APP";
    private static final String CHECK_CAPABILITY_DRY_RUN_COMMON = "CAPABILITY_DRY_RUN_COMMON";
    private static final String CHECK_CAPABILITY_DRY_RUN_ONLINE_PC = "CAPABILITY_DRY_RUN_ONLINE_PC";
    private static final String CHECK_CAPABILITY_DRY_RUN_ONLINE_APP = "CAPABILITY_DRY_RUN_ONLINE_APP";
    private static final String CHECK_CAPABILITY_DRY_RUN_ONLINE_COMMON =
            "CAPABILITY_DRY_RUN_ONLINE_COMMON";
    private static final String RULE_CAPABILITY_DRY_RUN = "capability-dry-run-client-v1";
    private static final String RULE_CAPABILITY_DRY_RUN_ONLINE = "capability-dry-run-online-client-v1";
    private static final String CLIENT_PC = "PC";
    private static final String CLIENT_APP = "APP";
    private static final String CLIENT_COMMON = "COMMON";
    private static final String ERROR_SAVED_CLIENT_NOT_SUPPORTED =
            "saved capability draft does not support client ";
    private static final String ERROR_CLIENT_TYPE_INVALID =
            "clientType only supports PC, APP or COMMON";
    private static final String VALIDATION_PASSED = "PASSED";
    private static final String VALIDATION_FAILED = "FAILED";
    private static final String SUMMARY_DRY_RUN_PASSED = "PRT API 验证通过";
    private static final String SUMMARY_DRY_RUN_FAILED = "PRT API 验证失败";
    private static final String SUMMARY_DRY_RUN_ONLINE_PASSED = "ONLINE API 验证通过";
    private static final String SUMMARY_DRY_RUN_ONLINE_FAILED = "ONLINE API 验证失败";

    @Resource
    private CapabilityActionDraftService capabilityActionDraftService;

    @Resource
    private CapabilityActionToolProvider capabilityActionToolProvider;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    @Resource
    private ReleaseAssetAdapterRegistry releaseAssetAdapterRegistry;

    @Resource
    private AssetReleaseApplicationService assetReleaseApplicationService;

    /**
     * 使用已保存草稿和可信宿主身份执行指定环境验证，返回瞬时请求预览和完整 ToolResult。
     */
    public Map<String, Object> execute(String operator, Map<String, String> params) {
        String draftId = required(params, PARAM_DRAFT_ID);
        int revision = positiveInteger(required(params, PARAM_REVISION), PARAM_REVISION);
        ReleaseEnvironment environment = parseEnvironment(required(params, PARAM_ENVIRONMENT));
        String clientType = parseClientType(required(params, PARAM_CLIENT_TYPE));
        if (StringUtils.isNotBlank(value(params, PARAM_CREDENTIAL_INPUT))) {
            throw new IllegalArgumentException("Cookie/curl credentials are forbidden for capability RPC");
        }
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.CAPABILITY_ACTION, draftId, AssetAction.EDIT);
        CapabilityActionDraft draft = capabilityActionDraftService.detail(draftId);
        if (!Objects.equals(draft.getRevision(), revision)) {
            throw new IllegalArgumentException("capability draft revision changed; save and retry dry-run");
        }
        Map<String, Object> sampleArguments = parseSampleArguments(draft, clientType);
        ReleaseAssetAdapter releaseAdapter = releaseAssetAdapterRegistry.get(ReleaseAssetType.CAPABILITY_ACTION);
        AssetSnapshot releaseSnapshot = releaseAdapter.currentSnapshot(draftId, Map.of());

        BaseAgentContext agentContext = new BaseAgentContext();
        agentContext.setUserId(managementIdentityProvider.userId());
        agentContext.setClient(clientType);
        agentContext.setEnv(StringUtils.lowerCase(environment.name(), Locale.ROOT));
        String traceId = TraceIds.currentOrCreate();
        Map<String, Object> trustedContext = new LinkedHashMap<>();
        trustedContext.put(FIELD_AGENT_CONTEXT, agentContext);
        trustedContext.put(TrustedToolContext.TRACE_ID, traceId);
        trustedContext.put(TrustedToolContext.REVIEWED_DEMO_APPROVED,
                environment == ReleaseEnvironment.PRT
                        && assetAuthorizationService.isAdmin(operator));
        ToolContext toolContext = new ToolContext(trustedContext);

        log.info("能力中心直接dry-run开始执行, draftId:{}, revision:{}, actionCode:{}, "
                        + "clientType:{}, environment:{}, traceId:{}",
                draftId, revision, nestedActionCode(draft), clientType, environment, traceId);
        CapabilityActionExecutionPreview preview = capabilityActionToolProvider.preview(
                draft, environment, clientType, sampleArguments, toolContext);
        ToolCallback actionTool = capabilityActionToolProvider.create(draft, environment, clientType);
        String resultJson = actionTool.call(
                JsonSupport.toJSON(sampleArguments), toolContext);
        Map<String, Object> toolResult = parseResult(resultJson);
        assetReleaseApplicationService.recordValidationEvidence(
                operator, ReleaseAssetType.CAPABILITY_ACTION, draftId, releaseSnapshot.getDigest(),
                evidenceForResult(toolResult, traceId, environment, clientType));
        log.info("能力中心直接dry-run执行完成, draftId:{}, revision:{}, actionCode:{}, "
                        + "clientType:{}, environment:{}, success:{}, httpStatus:{}, traceId:{}",
                draftId, revision, nestedActionCode(draft), clientType, environment,
                MapUtils.getBoolean(toolResult, FIELD_SUCCESS),
                MapUtils.getIntValue(toolResult, FIELD_HTTP_STATUS),
                MapUtils.getString(toolResult, FIELD_TRACE_ID, traceId));
        return transientResult(environment, clientType, preview, toolResult);
    }

    /** 把真实环境调用收敛为不含响应正文和凭证的共享发布证据。 */
    ReleaseValidationEvidence evidenceForResult(Map<String, Object> result, String fallbackTraceId,
            ReleaseEnvironment environment, String clientType) {
        boolean passed = MapUtils.getBooleanValue(result, FIELD_SUCCESS);
        boolean online = environment == ReleaseEnvironment.ONLINE;
        return new ReleaseValidationEvidence()
                .setCheckCode(validationCheckCode(environment, clientType))
                .setStatus(passed ? VALIDATION_PASSED : VALIDATION_FAILED)
                .setRuleVersion(online ? RULE_CAPABILITY_DRY_RUN_ONLINE : RULE_CAPABILITY_DRY_RUN)
                .setCheckRunId(MapUtils.getString(result, FIELD_TRACE_ID, fallbackTraceId))
                .setSummary(online
                        ? passed ? clientType + " " + SUMMARY_DRY_RUN_ONLINE_PASSED
                        : clientType + " " + SUMMARY_DRY_RUN_ONLINE_FAILED
                        : passed ? clientType + " " + SUMMARY_DRY_RUN_PASSED
                        : clientType + " " + SUMMARY_DRY_RUN_FAILED);
    }

    private Map<String, Object> transientResult(ReleaseEnvironment environment, String clientType,
            CapabilityActionExecutionPreview preview, Map<String, Object> toolResult) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_ENVIRONMENT, environment.name());
        result.put(FIELD_CLIENT_TYPE, clientType);
        result.put("protocol", preview.getProtocol());
        result.put("targetKey", preview.getTargetKey());
        result.put("serviceName", preview.getServiceName());
        result.put("methodName", preview.getMethodName());
        result.put(FIELD_EFFECTIVE_ARGUMENTS, preview.getEffectiveArguments());
        result.put(FIELD_EFFECTIVE_REQUEST_BODY, preview.getEffectiveRequestBody());
        result.put(FIELD_TOOL_RESULT, toolResult);
        return result;
    }

    private Map<String, Object> parseSampleArguments(CapabilityActionDraft draft, String clientType) {
        Map<String, Object> root = draft == null ? null : draft.getDraft();
        Map<String, Object> variants = root == null
                ? Collections.emptyMap() : mapValue(root.get(FIELD_CLIENT_VARIANTS));
        Map<String, Object> variant = mapValue(variants.get(clientType));
        Object modelContractValue = variant.get(FIELD_MODEL_CONTRACT);
        if (!(modelContractValue instanceof Map)) {
            throw new IllegalArgumentException(ERROR_SAVED_CLIENT_NOT_SUPPORTED + clientType);
        }
        String sampleArgumentsJson = MapUtils.getString(
                (Map<String, Object>) modelContractValue, FIELD_INPUT_EXAMPLE_JSON);
        if (StringUtils.isBlank(sampleArgumentsJson)) {
            throw new IllegalArgumentException("saved capability inputExampleJson is required");
        }
        try {
            Object parsed = JsonSupport.fromJSON(sampleArgumentsJson, Object.class);
            if (!(parsed instanceof Map)) {
                throw new IllegalArgumentException("sampleArgumentsJson must be a JSON object");
            }
            return new LinkedHashMap<>((Map<String, Object>) parsed);
        } catch (Exception exception) {
            throw new IllegalArgumentException("sampleArgumentsJson must be a valid JSON object", exception);
        }
    }

    private ReleaseEnvironment parseEnvironment(String value) {
        String normalized = StringUtils.upperCase(StringUtils.trimToEmpty(value), Locale.ROOT);
        if (!StringUtils.equalsAny(normalized,
                ReleaseEnvironment.PRT.name(), ReleaseEnvironment.ONLINE.name())) {
            throw new IllegalArgumentException("environment only supports PRT or ONLINE");
        }
        return ReleaseEnvironment.valueOf(normalized);
    }

    private String parseClientType(String value) {
        String clientType = StringUtils.upperCase(StringUtils.trimToEmpty(value), Locale.ROOT);
        if (!StringUtils.equalsAny(clientType, CLIENT_PC, CLIENT_APP, CLIENT_COMMON)) {
            throw new IllegalArgumentException(ERROR_CLIENT_TYPE_INVALID);
        }
        return clientType;
    }

    private String validationCheckCode(ReleaseEnvironment environment, String clientType) {
        boolean online = environment == ReleaseEnvironment.ONLINE;
        String normalizedClient = parseClientType(clientType);
        boolean app = CLIENT_APP.equals(normalizedClient);
        boolean common = CLIENT_COMMON.equals(normalizedClient);
        if (online) {
            if (common) {
                return CHECK_CAPABILITY_DRY_RUN_ONLINE_COMMON;
            }
            return app ? CHECK_CAPABILITY_DRY_RUN_ONLINE_APP : CHECK_CAPABILITY_DRY_RUN_ONLINE_PC;
        }
        if (common) {
            return CHECK_CAPABILITY_DRY_RUN_COMMON;
        }
        return app ? CHECK_CAPABILITY_DRY_RUN_APP : CHECK_CAPABILITY_DRY_RUN_PC;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseResult(String resultJson) {
        try {
            Object parsed = JsonSupport.fromJSON(resultJson, Object.class);
            if (!(parsed instanceof Map)) {
                throw new IllegalArgumentException("capability dry-run result must be a JSON object");
            }
            return new LinkedHashMap<>((Map<String, Object>) parsed);
        } catch (Exception exception) {
            throw new IllegalStateException("capability dry-run result is invalid", exception);
        }
    }

    private String nestedActionCode(CapabilityActionDraft draft) {
        if (draft == null || draft.getDraft() == null
                || !(draft.getDraft().get(FIELD_BASIC_INFO) instanceof Map)) {
            return StringUtils.EMPTY;
        }
        return MapUtils.getString(
                (Map<String, Object>) draft.getDraft().get(FIELD_BASIC_INFO),
                FIELD_ACTION_CODE, StringUtils.EMPTY);
    }

    private int positiveInteger(String value, String field) {
        try {
            int parsed = Integer.parseInt(value);
            if (parsed <= 0) {
                throw new IllegalArgumentException(field + " must be positive");
            }
            return parsed;
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException(field + " must be a positive integer", exception);
        }
    }

    private String required(Map<String, String> params, String key) {
        String value = value(params, key);
        if (StringUtils.isBlank(value)) {
            throw new IllegalArgumentException(key + " is required");
        }
        return value;
    }

    private String value(Map<String, String> params, String key) {
        return params == null ? StringUtils.EMPTY : StringUtils.defaultString(params.get(key));
    }
}
