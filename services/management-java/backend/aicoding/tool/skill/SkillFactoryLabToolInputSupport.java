package dev.a2flow.management.aicoding.tool.skill;

import java.math.BigDecimal;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;

/**
 * Skill 运行诊断 Tool 的结构化参数解析辅助类。
 *
 * <p>上游只接收模型生成的 JSON object，本类负责字段白名单、整数精度、必填值和枚举值校验。
 * 它不读取 ToolContext、不补充当前 workspace 的 skillCode，也不承担查询、分页或重试策略。
 */
final class SkillFactoryLabToolInputSupport {

    private static final String ERROR_INPUT_INVALID = "lab runtime query tool input is invalid";
    private static final String ERROR_INPUT_OBJECT = "tool input must be a JSON object";
    private static final String ERROR_UNSUPPORTED_FIELD = "tool input contains unsupported fields";
    private static final String ERROR_REQUIRED_POSITIVE_INTEGER = "is required and must be a positive integer";
    private static final String ERROR_POSITIVE_INTEGER = "must be a positive integer";
    private static final String ERROR_STRING = "must be a string";
    private static final String ERROR_INTEGER = "must be an integer";
    private static final String ERROR_RANGE_PREFIX = "must be between 1 and ";
    private static final String ERROR_ENUM_PREFIX = "must be one of ";

    private SkillFactoryLabToolInputSupport() {
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> parseObject(String toolInput, Set<String> allowedFields) {
        if (StringUtils.isBlank(toolInput)) {
            return Collections.emptyMap();
        }
        try {
            Object parsed = JsonSupport.fromJSON(toolInput, Object.class);
            if (!(parsed instanceof Map<?, ?>)) {
                throw new IllegalArgumentException(ERROR_INPUT_OBJECT);
            }
            Map<String, Object> input = new LinkedHashMap<>((Map<String, Object>) parsed);
            if (!allowedFields.containsAll(input.keySet())) {
                throw new IllegalArgumentException(ERROR_UNSUPPORTED_FIELD);
            }
            return input;
        } catch (ToolException e) {
            throw e;
        } catch (Exception e) {
            throw new ToolException(ERROR_INPUT_INVALID, e, ToolException.ErrorCode.INVALID_PARAMS);
        }
    }

    static long requiredPositiveLong(Map<String, Object> input, String field) {
        Long value = optionalPositiveLong(input, field);
        if (value == null) {
            throw invalid(field, ERROR_REQUIRED_POSITIVE_INTEGER);
        }
        return value;
    }

    static Long optionalPositiveLong(Map<String, Object> input, String field) {
        if (!input.containsKey(field) || input.get(field) == null) {
            return null;
        }
        long value = exactLong(input.get(field), field);
        if (value <= 0) {
            throw invalid(field, ERROR_POSITIVE_INTEGER);
        }
        return value;
    }

    static int positiveInt(Map<String, Object> input, String field, int defaultValue, int maxValue) {
        if (!input.containsKey(field) || input.get(field) == null) {
            return defaultValue;
        }
        long value = exactLong(input.get(field), field);
        if (value <= 0 || value > maxValue) {
            throw invalid(field, ERROR_RANGE_PREFIX + maxValue);
        }
        return (int) value;
    }

    static String optionalString(Map<String, Object> input, String field) {
        if (!input.containsKey(field) || input.get(field) == null) {
            return null;
        }
        Object rawValue = input.get(field);
        if (!(rawValue instanceof String)) {
            throw invalid(field, ERROR_STRING);
        }
        return StringUtils.trimToNull((String) rawValue);
    }

    static String optionalEnum(Map<String, Object> input, String field, Set<String> allowedValues) {
        String value = optionalString(input, field);
        if (value == null) {
            return null;
        }
        String normalized = StringUtils.upperCase(value);
        if (!allowedValues.contains(normalized)) {
            throw invalid(field, ERROR_ENUM_PREFIX + allowedValues);
        }
        return normalized;
    }

    private static long exactLong(Object rawValue, String field) {
        try {
            return new BigDecimal(String.valueOf(rawValue)).longValueExact();
        } catch (ArithmeticException | NumberFormatException e) {
            throw new ToolException(field + " " + ERROR_INTEGER, e,
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
    }

    private static ToolException invalid(String field, String reason) {
        return new ToolException(field + " " + reason, ToolException.ErrorCode.INVALID_PARAMS);
    }
}
