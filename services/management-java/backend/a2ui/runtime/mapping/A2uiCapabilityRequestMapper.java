package dev.a2flow.management.a2ui.runtime.mapping;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiMappingSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledRequestMapping;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledRequestTransform;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiRequestTransformType;
import dev.a2flow.management.a2ui.runtime.show
        .A2uiJsonPointerValueMapper;
import dev.a2flow.management.a2ui.runtime.show
        .A2uiJsonPointerValueMapper.LookupValue;

import lombok.extern.slf4j.Slf4j;

/**
 * A2UI Load/Action Binding 到 CapabilityAction 参数的确定性映射器。
 *
 * <p>上游只传入 Build 冻结的 A2uiCompiledRequestMapping、已校验 Action context、typed trusted context 和可选
 * Application调用参数、前序 CompositeAction 结果；本类按发布顺序从五种封闭 source读取结构化值
 * 并写入新的参数对象。业务字符串和同根业务数组可按 Build 冻结的封闭转换处理，
 * 不推断业务语义。
 * 重叠 target、缺失 source、非法 JSON Pointer 或脚本式配置均失败关闭。下游 CapabilityExecutor 仍
 * 负责按当前生效 Capability schema 重验参数并通过 RPC 传递可信 userId；本类不执行能力、
 * 不保存凭证、不读取 Cookie，也不允许客户端 context 覆盖 trusted map。</p>
 */
@Component
@Slf4j
public class A2uiCapabilityRequestMapper {

    private static final String ROOT_PATH = "/";
    private static final String FIELD_USER_ID = "userId";
    private static final String FIELD_CLIENT = "client";
    private static final String FIELD_OPERATOR = "operator";
    private static final String FIELD_ENVIRONMENT = "environment";
    private static final String FIELD_WORKFLOW_RUN_ID = "workflowRunId";
    private static final String FIELD_NODE_RUN_ID = "nodeRunId";
    private static final String FIELD_PRESENTATION_ID = "presentationId";
    private static final int MAX_MAPPINGS = 256;
    private static final String ERROR_REQUEST_INVALID = "A2UI Capability mapping request is invalid";
    private static final String ERROR_MAPPING_INVALID = "A2UI Capability mapping is invalid";
    private static final String ERROR_SOURCE_MISSING = "A2UI Capability mapping source is missing";
    private static final String ERROR_TARGET_CONFLICT = "A2UI Capability mapping target conflicts";
    private static final String ERROR_TRANSFORM_INVALID = "A2UI Capability mapping transform is invalid";

    private final A2uiJsonPointerValueMapper valueMapper;

    public A2uiCapabilityRequestMapper() {
        this.valueMapper = new A2uiJsonPointerValueMapper();
    }

    /** 按发布顺序生成一个全新的 Capability 参数对象；不修改任何 source。 */
    public Map<String, Object> map(List<A2uiCompiledRequestMapping> mappings, MappingInputs inputs) {
        if (mappings == null || mappings.size() > MAX_MAPPINGS
                || inputs == null || !inputs.isValid()) {
            throw new MappingException(Code.REQUEST_INVALID, ERROR_REQUEST_INVALID);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        Set<String> writtenTargets = new HashSet<>();
        for (A2uiCompiledRequestMapping mapping : mappings) {
            validateMapping(mapping, writtenTargets);
            SourceValue sourceValue = resolveSource(mapping, inputs);
            if (!sourceValue.found) {
                throw new MappingException(Code.SOURCE_MISSING, ERROR_SOURCE_MISSING);
            }
            try {
                Object mapped = valueMapper.write(result,
                        mapping.getTargetPath(), transformValue(mapping, sourceValue.value, inputs));
                if (!(mapped instanceof Map)) {
                    throw new MappingException(Code.MAPPING_INVALID, ERROR_MAPPING_INVALID);
                }
                result = castMap(mapped);
            } catch (A2uiJsonPointerValueMapper.MappingException exception) {
                throw new MappingException(Code.MAPPING_INVALID, ERROR_MAPPING_INVALID, exception);
            }
        }
        return result;
    }

    private void validateMapping(A2uiCompiledRequestMapping mapping, Set<String> writtenTargets) {
        if (mapping == null || mapping.getSource() == null
                || StringUtils.isBlank(mapping.getTargetPath())
                || ROOT_PATH.equals(mapping.getTargetPath())) {
            throw new MappingException(Code.MAPPING_INVALID, ERROR_MAPPING_INVALID);
        }
        for (String writtenTarget : writtenTargets) {
            if (pathsConflict(writtenTarget, mapping.getTargetPath())) {
                throw new MappingException(Code.TARGET_CONFLICT, ERROR_TARGET_CONFLICT);
            }
        }
        writtenTargets.add(mapping.getTargetPath());
        if (A2uiMappingSource.CONSTANT != mapping.getSource()
                && StringUtils.isBlank(mapping.getSourcePath())) {
            throw new MappingException(Code.MAPPING_INVALID, ERROR_MAPPING_INVALID);
        }
        A2uiCompiledRequestTransform transform = mapping.getTransform();
        if (transform != null) {
            boolean allowedSource = mapping.getSource() == A2uiMappingSource.ACTION_CONTEXT
                    || mapping.getSource() == A2uiMappingSource.APP_PARAMS;
            boolean validStringPrefix = transform.getType() == A2uiRequestTransformType.STRING_PREFIX
                    && StringUtils.isNotEmpty(transform.getPrefix())
                    && transform.getMaskSourcePath() == null;
            boolean validBooleanMask = transform.getType()
                    == A2uiRequestTransformType.ARRAY_FILTER_BY_BOOLEAN_MASK
                    && transform.getPrefix() == null
                    && StringUtils.isNotBlank(transform.getMaskSourcePath());
            if (!allowedSource || !validStringPrefix && !validBooleanMask) {
                throw new MappingException(Code.MAPPING_INVALID, ERROR_TRANSFORM_INVALID);
            }
        }
    }

    /** 仅执行已冻结的封闭转换；禁止类型强转、默认值、跨来源取值或原值回退。 */
    private Object transformValue(A2uiCompiledRequestMapping mapping, Object sourceValue, MappingInputs inputs) {
        A2uiCompiledRequestTransform transform = mapping.getTransform();
        if (transform == null) {
            return sourceValue;
        }
        if (transform.getType() == A2uiRequestTransformType.STRING_PREFIX) {
            if (!(sourceValue instanceof String)) {
                log.warn("A2UI请求参数前缀转换拒绝非字符串, source:{}, targetPath:{}",
                        mapping.getSource(), mapping.getTargetPath());
                throw new MappingException(Code.MAPPING_INVALID, ERROR_TRANSFORM_INVALID);
            }
            log.debug("A2UI请求参数前缀转换完成, source:{}, targetPath:{}",
                    mapping.getSource(), mapping.getTargetPath());
            return transform.getPrefix() + sourceValue;
        }
        SourceValue maskValue = resolveSource(mapping.getSource(),
                transform.getMaskSourcePath(), inputs);
        if (!maskValue.found || !(sourceValue instanceof List)
                || !(maskValue.value instanceof List)) {
            log.warn("A2UI请求数组过滤拒绝非法来源, source:{}, targetPath:{}",
                    mapping.getSource(), mapping.getTargetPath());
            throw new MappingException(Code.MAPPING_INVALID, ERROR_TRANSFORM_INVALID);
        }
        return filterByBooleanMask(mapping, (List<?>) sourceValue, (List<?>) maskValue.value);
    }

    /**
     * 生成保持源顺序的新数组，只处理两数组重叠前缀。
     * 任一非布尔值在 Capability 前失败。
     */
    private List<Object> filterByBooleanMask(A2uiCompiledRequestMapping mapping, List<?> source,
            List<?> mask) {
        if (mask.stream().anyMatch(value -> !(value instanceof Boolean))) {
            log.warn("A2UI请求数组过滤拒绝非法布尔mask, source:{}, targetPath:{}, "
                            + "sourceSize:{}, maskSize:{}",
                    mapping.getSource(), mapping.getTargetPath(), source.size(), mask.size());
            throw new MappingException(Code.MAPPING_INVALID, ERROR_TRANSFORM_INVALID);
        }
        List<Object> selected = new ArrayList<>();
        int overlapSize = Math.min(source.size(), mask.size());
        for (int index = 0; index < overlapSize; index++) {
            if (Boolean.TRUE.equals(mask.get(index))) {
                selected.add(source.get(index));
            }
        }
        log.debug("A2UI请求数组过滤完成, source:{}, targetPath:{}, sourceSize:{}, "
                        + "selectedSize:{}",
                mapping.getSource(), mapping.getTargetPath(), source.size(), selected.size());
        return selected;
    }

    private SourceValue resolveSource(A2uiCompiledRequestMapping mapping, MappingInputs inputs) {
        if (A2uiMappingSource.CONSTANT == mapping.getSource()) {
            return SourceValue.found(mapping.getConstantValue());
        }
        return resolveSource(mapping.getSource(), mapping.getSourcePath(), inputs);
    }

    private SourceValue resolveSource(A2uiMappingSource mappingSource, String sourcePath,
            MappingInputs inputs) {
        Map<String, Object> source;
        if (A2uiMappingSource.ACTION_CONTEXT == mappingSource) {
            source = inputs.actionContext;
        } else if (A2uiMappingSource.APP_PARAMS == mappingSource) {
            source = inputs.applicationParams;
        } else if (A2uiMappingSource.TRUSTED_CONTEXT == mappingSource) {
            source = inputs.trustedValues();
        } else if (A2uiMappingSource.CAPABILITY_PREVIOUS_RESULT == mappingSource) {
            source = inputs.previousCapabilityResult;
        } else {
            throw new MappingException(Code.MAPPING_INVALID, ERROR_MAPPING_INVALID);
        }
        if (source == null) {
            return SourceValue.missing();
        }
        try {
            LookupValue value = valueMapper.read(source, sourcePath);
            return value.isFound() ? SourceValue.found(value.getValue()) : SourceValue.missing();
        } catch (A2uiJsonPointerValueMapper.MappingException exception) {
            throw new MappingException(Code.MAPPING_INVALID, ERROR_MAPPING_INVALID, exception);
        }
    }

    private boolean pathsConflict(String left, String right) {
        return left.equals(right) || left.startsWith(right + ROOT_PATH)
                || right.startsWith(left + ROOT_PATH);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> castMap(Object value) {
        return (Map<String, Object>) value;
    }

    public enum Code {
        REQUEST_INVALID,
        MAPPING_INVALID,
        SOURCE_MISSING,
        TARGET_CONFLICT
    }

    /** 映射失败只携带稳定分类，不携带 Action context、能力结果或可信字段值。 */
    public static class MappingException extends RuntimeException {
        private final Code code;

        MappingException(Code code, String message) {
            super(message);
            this.code = code;
        }

        MappingException(Code code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        public Code getCode() {
            return code;
        }
    }

    /**
     * 映射输入按信任级别分槽；trusted map 只导出业务身份枚举，不含 Cookie/Authorization/trace。
     */
    public static final class MappingInputs {
        private final Map<String, Object> actionContext;
        private final Map<String, Object> applicationParams;
        private final Map<String, Object> previousCapabilityResult;
        private final Long userId;
        private final String client;
        private final String operator;
        private final String environment;
        private final String workflowRunId;
        private final String nodeRunId;
        private final String presentationId;
        private final Map<String, Object> supplementalTrustedValues;

        public MappingInputs(Map<String, Object> actionContext,
                Map<String, Object> previousCapabilityResult,
                Long userId, String client, String operator, String environment) {
            this(actionContext, Collections.emptyMap(), previousCapabilityResult,
                    userId, client, operator, environment, null, null, null,
                    Collections.emptyMap());
        }

        @SuppressWarnings("checkstyle:ParameterNumber")
        public MappingInputs(Map<String, Object> actionContext,
                Map<String, Object> applicationParams,
                Map<String, Object> previousCapabilityResult,
                Long userId, String client, String operator, String environment) {
            this(actionContext, applicationParams, previousCapabilityResult,
                    userId, client, operator, environment, null, null, null,
                    Collections.emptyMap());
        }

        @SuppressWarnings("checkstyle:ParameterNumber")
        public MappingInputs(Map<String, Object> actionContext,
                Map<String, Object> applicationParams,
                Map<String, Object> previousCapabilityResult,
                Long userId, String client, String operator, String environment,
                Map<String, Object> supplementalTrustedValues) {
            this(actionContext, applicationParams, previousCapabilityResult,
                    userId, client, operator, environment, null, null, null,
                    supplementalTrustedValues);
        }

        @SuppressWarnings("checkstyle:ParameterNumber")
        public MappingInputs(Map<String, Object> actionContext,
                Map<String, Object> previousCapabilityResult,
                Long userId, String client, String operator, String environment,
                String workflowRunId, String nodeRunId, String presentationId) {
            this(actionContext, Collections.emptyMap(), previousCapabilityResult,
                    userId, client, operator, environment,
                    workflowRunId, nodeRunId, presentationId, Collections.emptyMap());
        }

        @SuppressWarnings("checkstyle:ParameterNumber")
        public MappingInputs(Map<String, Object> actionContext,
                Map<String, Object> applicationParams,
                Map<String, Object> previousCapabilityResult,
                Long userId, String client, String operator, String environment,
                String workflowRunId, String nodeRunId, String presentationId) {
            this(actionContext, applicationParams, previousCapabilityResult,
                    userId, client, operator, environment,
                    workflowRunId, nodeRunId, presentationId, Collections.emptyMap());
        }

        @SuppressWarnings("checkstyle:ParameterNumber")
        private MappingInputs(Map<String, Object> actionContext,
                Map<String, Object> applicationParams,
                Map<String, Object> previousCapabilityResult,
                Long userId, String client, String operator, String environment,
                String workflowRunId, String nodeRunId, String presentationId,
                Map<String, Object> supplementalTrustedValues) {
            this.actionContext = actionContext == null
                    ? Collections.emptyMap() : new LinkedHashMap<>(actionContext);
            this.applicationParams = applicationParams == null
                    ? Collections.emptyMap() : new LinkedHashMap<>(applicationParams);
            this.previousCapabilityResult = previousCapabilityResult == null
                    ? null : new LinkedHashMap<>(previousCapabilityResult);
            this.userId = userId;
            this.client = client;
            this.operator = operator;
            this.environment = environment;
            this.workflowRunId = workflowRunId;
            this.nodeRunId = nodeRunId;
            this.presentationId = presentationId;
            this.supplementalTrustedValues = supplementalTrustedValues == null
                    ? Collections.emptyMap() : new LinkedHashMap<>(supplementalTrustedValues);
        }

        private boolean isValid() {
            return userId != null
                    && StringUtils.isNoneBlank(client, environment)
                    && !containsReservedTrustedField(supplementalTrustedValues);
        }

        private boolean containsReservedTrustedField(Map<String, Object> values) {
            return values.containsKey(FIELD_USER_ID)
                    || values.containsKey(FIELD_CLIENT)
                    || values.containsKey(FIELD_OPERATOR)
                    || values.containsKey(FIELD_ENVIRONMENT)
                    || values.containsKey(FIELD_WORKFLOW_RUN_ID)
                    || values.containsKey(FIELD_NODE_RUN_ID)
                    || values.containsKey(FIELD_PRESENTATION_ID);
        }

        private Map<String, Object> trustedValues() {
            Map<String, Object> values = new LinkedHashMap<>();
            values.put(FIELD_USER_ID, userId);
            values.put(FIELD_CLIENT, client);
            if (StringUtils.isNotBlank(operator)) {
                values.put(FIELD_OPERATOR, operator);
            }
            values.put(FIELD_ENVIRONMENT, environment);
            if (StringUtils.isNotBlank(workflowRunId)) {
                values.put(FIELD_WORKFLOW_RUN_ID, workflowRunId);
            }
            if (StringUtils.isNotBlank(nodeRunId)) {
                values.put(FIELD_NODE_RUN_ID, nodeRunId);
            }
            if (StringUtils.isNotBlank(presentationId)) {
                values.put(FIELD_PRESENTATION_ID, presentationId);
            }
            values.putAll(supplementalTrustedValues);
            return values;
        }
    }

    private static final class SourceValue {
        private final boolean found;
        private final Object value;

        private SourceValue(boolean found, Object value) {
            this.found = found;
            this.value = value;
        }

        private static SourceValue found(Object value) {
            return new SourceValue(true, value);
        }

        private static SourceValue missing() {
            return new SourceValue(false, null);
        }
    }
}
