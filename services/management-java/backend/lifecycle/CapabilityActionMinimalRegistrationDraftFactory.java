package dev.a2flow.management.lifecycle;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;

/**
 * 业务能力首次中文名注册的最小草稿工厂。
 *
 * <p>上游 {@link CapabilityActionDraftService} 已完成 JSON 结构解析和敏感字段清理，本类只接受
 * 协议字段与 `basicInfo.nameCn`，生成可持久化的最小 canonical Map。它不补 actionCode、端契约、
 * API 来源、治理策略或分类关系；这些信息只能在进入编辑页后由完整保存链路提交。
 */
final class CapabilityActionMinimalRegistrationDraftFactory {

    private static final String FIELD_PAYLOAD_TYPE = "payloadType";
    private static final String FIELD_MODE = "mode";
    private static final String FIELD_BASIC_INFO = "basicInfo";
    private static final String FIELD_NAME_CN = "nameCn";
    private static final String PAYLOAD_TYPE_SNAPSHOT = "CAPABILITY_DRAFT_SNAPSHOT";
    private static final String MODE_CREATE = "CREATE";
    private static final String ERROR_NAME_REQUIRED = "中文名称不能为空";
    private static final String ERROR_FIELDS_INVALID = "最小注册只允许填写中文名称";
    private static final Set<String> ALLOWED_ROOT_FIELDS =
            Set.of(FIELD_PAYLOAD_TYPE, FIELD_MODE, FIELD_BASIC_INFO);

    private CapabilityActionMinimalRegistrationDraftFactory() {
    }

    /** 校验最小注册字段并返回不含任何占位业务/技术事实的新 Map。 */
    static Map<String, Object> canonicalize(Map<String, Object> proposedDraft) {
        Map<String, Object> source = proposedDraft == null ? Map.of() : proposedDraft;
        if (!ALLOWED_ROOT_FIELDS.containsAll(source.keySet())) {
            throw new IllegalArgumentException(ERROR_FIELDS_INVALID);
        }
        Object basicInfoValue = source.get(FIELD_BASIC_INFO);
        if (!(basicInfoValue instanceof Map)) {
            throw new IllegalArgumentException(ERROR_NAME_REQUIRED);
        }
        Map<?, ?> proposedBasicInfo = (Map<?, ?>) basicInfoValue;
        if (!Set.of(FIELD_NAME_CN).containsAll(proposedBasicInfo.keySet())) {
            throw new IllegalArgumentException(ERROR_FIELDS_INVALID);
        }
        Object nameValue = proposedBasicInfo.get(FIELD_NAME_CN);
        String nameCn = nameValue instanceof String ? StringUtils.trim((String) nameValue) : null;
        if (StringUtils.isBlank(nameCn)) {
            throw new IllegalArgumentException(ERROR_NAME_REQUIRED);
        }
        Map<String, Object> canonical = new LinkedHashMap<>();
        canonical.put(FIELD_PAYLOAD_TYPE, PAYLOAD_TYPE_SNAPSHOT);
        canonical.put(FIELD_MODE, MODE_CREATE);
        canonical.put(FIELD_BASIC_INFO, new LinkedHashMap<>(Map.of(FIELD_NAME_CN, nameCn)));
        return canonical;
    }
}
