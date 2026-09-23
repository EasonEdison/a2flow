package dev.a2flow.management.a2ui.application;

import java.util.List;
import java.util.Map;
import java.util.Set;

import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiRequestTransformType;

/**
 * 请求转换的原始作者态形态校验器。
 *
 * <p>Registry 保存与 manifest 反序列化前共用此边界，防止 Jackson 丢弃未知字段或把标量强转成
 * 字符串。这里只校验封闭 transform 结构；来源及 schema 由 compiler 校验，不访问存储或执行转换。
 */
public final class A2uiRequestTransformValidator {

    private static final String FIELD_LOAD_BINDINGS = "loadBindings";
    private static final String FIELD_ACTION_BINDINGS = "actionBindings";
    private static final String FIELD_REQUEST_MAPPINGS = "requestMappings";
    private static final String FIELD_TRANSFORM = "transform";
    private static final String FIELD_TYPE = "type";
    private static final String FIELD_PREFIX = "prefix";
    private static final String FIELD_MASK_SOURCE_PATH = "maskSourcePath";
    private static final Set<String> STRING_PREFIX_FIELDS = Set.of(FIELD_TYPE, FIELD_PREFIX);
    private static final Set<String> BOOLEAN_MASK_FIELDS = Set.of(FIELD_TYPE, FIELD_MASK_SOURCE_PATH);

    private A2uiRequestTransformValidator() {
    }

    /** 保存和解析前校验两类 Binding；未配置转换保持 identity，非法结构直接拒绝。 */
    public static void validate(Map<String, Object> source) {
        validateBindings(source.get(FIELD_LOAD_BINDINGS));
        validateBindings(source.get(FIELD_ACTION_BINDINGS));
    }

    private static void validateBindings(Object rawBindings) {
        if (rawBindings == null) {
            return;
        }
        if (!(rawBindings instanceof List)) {
            throw invalid();
        }
        for (Object rawBinding : (List<?>) rawBindings) {
            if (!(rawBinding instanceof Map)) {
                throw invalid();
            }
            Object rawMappings = ((Map<?, ?>) rawBinding).get(FIELD_REQUEST_MAPPINGS);
            if (rawMappings == null) {
                continue;
            }
            if (!(rawMappings instanceof List)) {
                throw invalid();
            }
            for (Object rawMapping : (List<?>) rawMappings) {
                if (!(rawMapping instanceof Map)) {
                    throw invalid();
                }
                validateTransform(((Map<?, ?>) rawMapping).get(FIELD_TRANSFORM));
            }
        }
    }

    /** 按转换类型校验精确字段闭包；路径的 RFC 6901 与 schema 语义由 compiler 继续校验。 */
    private static void validateTransform(Object rawTransform) {
        if (rawTransform == null) {
            return;
        }
        if (!(rawTransform instanceof Map)) {
            throw invalid();
        }
        Map<?, ?> transform = (Map<?, ?>) rawTransform;
        Object rawType = transform.get(FIELD_TYPE);
        if (A2uiRequestTransformType.STRING_PREFIX.name().equals(rawType)) {
            Object prefix = transform.get(FIELD_PREFIX);
            if (STRING_PREFIX_FIELDS.equals(transform.keySet())
                    && prefix instanceof String && !((String) prefix).isEmpty()) {
                return;
            }
        } else if (A2uiRequestTransformType.ARRAY_FILTER_BY_BOOLEAN_MASK.name().equals(rawType)) {
            Object maskSourcePath = transform.get(FIELD_MASK_SOURCE_PATH);
            if (BOOLEAN_MASK_FIELDS.equals(transform.keySet())
                    && maskSourcePath instanceof String
                    && !((String) maskSourcePath).isEmpty()) {
                return;
            }
        }
        throw invalid();
    }

    private static A2uiApplicationValidationException invalid() {
        return new A2uiApplicationValidationException(A2uiApplicationErrorCode.DRAFT_INVALID);
    }
}
