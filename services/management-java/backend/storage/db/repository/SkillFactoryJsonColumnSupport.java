package dev.a2flow.management.storage.db.repository;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.support.JsonSupport;

/**
 * SkillFactory JSON 文本列写入校验工具。
 *
 * <p>领域对象和 DO 使用 String 承载 JSON 文本；PostgreSQL 新实例使用 TEXT 保持现有类型映射。
 * 所有 Repository 在写入前通过本类阻断空字符串和非法 JSON，避免问题延迟到 JDBC 执行阶段。
 */
final class SkillFactoryJsonColumnSupport {

    private static final String ERROR_JSON_REQUIRED_SUFFIX = " must not be blank";
    private static final String ERROR_JSON_INVALID_SUFFIX = " is invalid JSON";

    private SkillFactoryJsonColumnSupport() {
    }

    /**
     * 校验必填 JSON 列并返回原始 JSON 文本。
     */
    static String required(String json, String fieldName) {
        String normalized = nullable(json, fieldName);
        if (normalized == null) {
            throw new IllegalArgumentException(fieldName + ERROR_JSON_REQUIRED_SUFFIX);
        }
        return normalized;
    }

    /**
     * 校验可空 JSON 列；空字符串归一化为 SQL NULL。
     */
    static String nullable(String json, String fieldName) {
        String normalized = StringUtils.trimToNull(json);
        if (normalized == null) {
            return null;
        }
        try {
            JsonSupport.fromJSON(normalized, Object.class);
            return normalized;
        } catch (Exception exception) {
            throw new IllegalArgumentException(fieldName + ERROR_JSON_INVALID_SUFFIX, exception);
        }
    }
}
