package dev.a2flow.management.lifecycle;

import org.apache.commons.lang3.StringUtils;

import lombok.extern.slf4j.Slf4j;

/**
 * Skill 描述字段校验器。
 *
 * <p>统一承接注册和基础信息更新入口的描述长度规则：按 Unicode 字符统计，回车和换行不计入额度。
 * 本类只负责字段校验，不负责编辑权限、持久化或工作区生命周期。
 */
@Slf4j
final class SkillDescriptionValidator {

    private static final int MAX_DESCRIPTION_LENGTH = 500;
    private static final String ERROR_DESCRIPTION_TOO_LONG = "Skill 描述最多500字符（换行不计）";

    private SkillDescriptionValidator() {
    }

    /**
     * 校验 Skill 描述的非换行字符数。
     */
    static void validate(String skillCode, String description, String operator) {
        long descriptionLength = countNonNewlineCharacters(description);
        if (descriptionLength <= MAX_DESCRIPTION_LENGTH) {
            return;
        }
        log.warn("SkillFactory校验Skill描述失败，非换行字符超限, skillCode:{}, descriptionLength:{}, "
                        + "maxLength:{}, operator:{}",
                skillCode, descriptionLength, MAX_DESCRIPTION_LENGTH, operator);
        throw new IllegalArgumentException(ERROR_DESCRIPTION_TOO_LONG);
    }

    private static long countNonNewlineCharacters(String description) {
        if (StringUtils.isEmpty(description)) {
            return 0;
        }
        return description.codePoints()
                .filter(codePoint -> codePoint != '\n' && codePoint != '\r')
                .count();
    }
}
