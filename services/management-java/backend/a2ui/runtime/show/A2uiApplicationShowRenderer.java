package dev.a2flow.management.a2ui.runtime.show;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.a2ui.runtime.ledger.A2uiMessageSnapshotReducer;
import dev.a2flow.management.a2ui.runtime.ledger.A2uiRuntimeSurfaceLedger;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationBuild;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledShowInputBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowInputSource;
import dev.a2flow.management.a2ui.runtime.show.A2uiJsonPointerValueMapper.LookupValue;
import dev.a2flow.management.skillfactory.a2ui.A2uiOfficialComponentSchemaValidator;
import dev.a2flow.management.skillfactory.a2ui.A2uiOfficialComponentSchemaValidator.ValidationException;

/**
 * A2Flow A2UI Application 首屏 ShowTemplate 渲染器。
 *
 * <p>上游 Artifact Reader 提供不可变 Build，Toolkit handler 提供已校验 params 与 typed trusted context；
 * 本类先校验 params schema，再按发布顺序把 APP_PARAMS/TRUSTED_CONTEXT/CONSTANT 写入 initial messages，
 * 最后用与历史快照相同的 reducer 对完整消息批次做原子协议校验。下游只能拿到可直接放入
 * {@code event:a2ui.data.value} 的消息数组。本类不执行 Load/Action、不访问 业务数据源、不发送 SSE，
 * 也不会把 cookie、credential、trace 或 transport authority 放入可配置上下文。</p>
 */
@Component
public class A2uiApplicationShowRenderer {

    private static final String ROOT_PATH = "/";
    private static final String FIELD_USER_ID = "userId";
    private static final String FIELD_CLIENT = "client";
    private static final String FIELD_OPERATOR = "operator";
    private static final String FIELD_ENVIRONMENT = "environment";
    private static final String FIELD_CONSTANT_VALUE = "value";
    private static final String CONSTANT_VALUE_PATH = "/value";
    private static final String ERROR_REQUEST_INVALID = "A2UI Show render request is invalid";
    private static final String ERROR_PARAMS_INVALID = "A2UI Show params do not match published schema";
    private static final String ERROR_BINDING_INVALID = "A2UI Show input binding is invalid";
    private static final String ERROR_SOURCE_MISSING = "A2UI Show required input is missing";
    private static final String ERROR_MESSAGE_INVALID = "A2UI Show rendered messages are invalid";

    private final A2uiJsonSchemaSubsetValidator schemaValidator;
    private final A2uiJsonPointerValueMapper valueMapper;
    private final A2uiMessageSnapshotReducer messageReducer;
    private final A2uiOfficialComponentSchemaValidator officialComponentValidator;

    public A2uiApplicationShowRenderer() {
        this.schemaValidator = new A2uiJsonSchemaSubsetValidator();
        this.valueMapper = new A2uiJsonPointerValueMapper();
        this.messageReducer = new A2uiMessageSnapshotReducer();
        this.officialComponentValidator = new A2uiOfficialComponentSchemaValidator();
    }

    /**
     * 生成并原子校验首次展示消息；任何参数、绑定或协议错误都在 Load/Capability 发生前失败关闭。
     */
    public List<Map<String, Object>> render(A2uiApplicationBuild artifact,
            Map<String, Object> params, TrustedShowContext trustedContext) {
        // 结构性请求校验先于schema和任何消息处理，非法Artifact直接失败关闭。
        validateRequest(artifact, params, trustedContext);
        try {
            // paramsSchema描述的都是调用者必须在首屏前提供的参数，不包含Load生成字段。
            schemaValidator.validate(artifact.getParamsSchema(), params);
        } catch (A2uiJsonSchemaSubsetValidator.ValidationException exception) {
            throw new RenderException(Code.PARAMS_INVALID, ERROR_PARAMS_INVALID, exception);
        }

        // 不直接修改发布Artifact中的模板；每次激活都从一份深拷贝开始。
        List<Map<String, Object>> messages = copyMessages(artifact.getInitialMessages());
        Map<String, Object> trustedValues = trustedContext.toBindingMap();

        // 严格按发布顺序把APP_PARAMS、TRUSTED_CONTEXT或CONSTANT写到指定消息JSON Pointer。
        for (A2uiCompiledShowInputBinding binding : artifact.getInputBindings()) {
            applyBinding(messages, params, trustedValues, binding);
        }
        try {
            officialComponentValidator.validateMessages(
                    messages, artifact.getCatalog().getComponentOrigins());
        } catch (ValidationException exception) {
            throw new RenderException(Code.MESSAGE_INVALID, ERROR_MESSAGE_INVALID, exception);
        }
        try {
            // 在空Ledger上整批回放，确保createSurface、组件树和data model能够自包含恢复。
            messageReducer.reduce(A2uiRuntimeSurfaceLedger.empty(), messages);
        } catch (RuntimeException exception) {
            throw new RenderException(Code.MESSAGE_INVALID, ERROR_MESSAGE_INVALID, exception);
        }
        return messages;
    }

    private void validateRequest(A2uiApplicationBuild artifact,
            Map<String, Object> params, TrustedShowContext trustedContext) {
        if (artifact == null || StringUtils.isAnyBlank(artifact.getAppCode(), artifact.getAppBuildId())
                || artifact.getParamsSchema() == null || artifact.getInitialMessages() == null
                || artifact.getInitialMessages().isEmpty() || artifact.getInputBindings() == null
                || params == null || trustedContext == null || !trustedContext.isValid()) {
            throw new RenderException(Code.REQUEST_INVALID, ERROR_REQUEST_INVALID);
        }
    }

    private List<Map<String, Object>> copyMessages(List<Map<String, Object>> source) {
        List<Map<String, Object>> copied = new ArrayList<>(source.size());
        for (Map<String, Object> message : source) {
            Object value = valueMapper.write(new LinkedHashMap<>(), ROOT_PATH, message);
            if (!(value instanceof Map)) {
                throw new RenderException(Code.MESSAGE_INVALID, ERROR_MESSAGE_INVALID);
            }
            copied.add(castMap(value));
        }
        return copied;
    }

    private void applyBinding(List<Map<String, Object>> messages,
            Map<String, Object> params, Map<String, Object> trustedValues,
            A2uiCompiledShowInputBinding binding) {
        if (binding == null || binding.getSource() == null
                || StringUtils.isBlank(binding.getTargetPath())
                || binding.getTargetMessageIndex() < 0
                || binding.getTargetMessageIndex() >= messages.size()) {
            throw new RenderException(Code.BINDING_INVALID, ERROR_BINDING_INVALID);
        }
        LookupValue sourceValue = resolveSource(params, trustedValues, binding);
        if (!sourceValue.isFound() || sourceValue.getValue() == null) {
            // 非必填绑定缺值时保留模板原值；必填缺值则禁止产生不完整首屏。
            if (binding.isRequired()) {
                throw new RenderException(Code.SOURCE_MISSING, ERROR_SOURCE_MISSING);
            }
            return;
        }
        try {
            // 单个Binding只替换目标Pointer，其他组件和data model内容保持不变。
            Object rendered = valueMapper.write(
                    messages.get(binding.getTargetMessageIndex()),
                    binding.getTargetPath(), sourceValue.getValue());
            if (!(rendered instanceof Map)) {
                throw new RenderException(Code.BINDING_INVALID, ERROR_BINDING_INVALID);
            }
            messages.set(binding.getTargetMessageIndex(), castMap(rendered));
        } catch (A2uiJsonPointerValueMapper.MappingException exception) {
            throw new RenderException(Code.BINDING_INVALID, ERROR_BINDING_INVALID, exception);
        }
    }

    private LookupValue resolveSource(Map<String, Object> params,
            Map<String, Object> trustedValues, A2uiCompiledShowInputBinding binding) {
        if (A2uiShowInputSource.CONSTANT == binding.getSource()) {
            Map<String, Object> constantSource = new LinkedHashMap<>();
            constantSource.put(FIELD_CONSTANT_VALUE, binding.getConstantValue());
            return valueMapper.read(constantSource, CONSTANT_VALUE_PATH);
        }
        if (StringUtils.isBlank(binding.getSourcePath())) {
            throw new RenderException(Code.BINDING_INVALID, ERROR_BINDING_INVALID);
        }
        try {
            if (A2uiShowInputSource.APP_PARAMS == binding.getSource()) {
                return valueMapper.read(params, binding.getSourcePath());
            }
            if (A2uiShowInputSource.TRUSTED_CONTEXT == binding.getSource()) {
                return valueMapper.read(trustedValues, binding.getSourcePath());
            }
        } catch (A2uiJsonPointerValueMapper.MappingException exception) {
            throw new RenderException(Code.BINDING_INVALID, ERROR_BINDING_INVALID, exception);
        }
        throw new RenderException(Code.BINDING_INVALID, ERROR_BINDING_INVALID);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> castMap(Object value) {
        return (Map<String, Object>) value;
    }

    public enum Code {
        REQUEST_INVALID,
        PARAMS_INVALID,
        BINDING_INVALID,
        SOURCE_MISSING,
        MESSAGE_INVALID
    }

    /** Show 首屏渲染失败；异常不携带 params、可信上下文或消息正文。 */
    public static class RenderException extends RuntimeException {
        private final Code code;

        RenderException(Code code, String message) {
            super(message);
            this.code = code;
        }

        RenderException(Code code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        public Code getCode() {
            return code;
        }
    }

    /**
     * 允许进入发布态 ShowBinding 的可信字段白名单；构造时即排除 trace、cookie 和 transport authority。
     */
    public static final class TrustedShowContext {
        private final Long userId;
        private final String client;
        private final String operator;
        private final String environment;

        public TrustedShowContext(Long userId, String client,
                String operator, String environment) {
            this.userId = userId;
            this.client = client;
            this.operator = operator;
            this.environment = environment;
        }

        private boolean isValid() {
            return userId != null
                    && StringUtils.isNoneBlank(client, environment);
        }

        private Map<String, Object> toBindingMap() {
            Map<String, Object> values = new LinkedHashMap<>();
            values.put(FIELD_USER_ID, userId);
            values.put(FIELD_CLIENT, client);
            if (StringUtils.isNotBlank(operator)) {
                values.put(FIELD_OPERATOR, operator);
            }
            values.put(FIELD_ENVIRONMENT, environment);
            return values;
        }
    }
}
