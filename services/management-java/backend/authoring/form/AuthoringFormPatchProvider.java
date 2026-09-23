package dev.a2flow.management.authoring.form;

import java.util.Map;

/**
 * SkillFactory 表单修改提案的领域规则提供者。
 *
 * <p>上游是通用 {@code propose_form_patch} 服务，下游是具体 Authoring 页面。实现类只声明
 * formKey、编辑目标身份和字段白名单，不执行表单保存、数据库写入、workspace 修改或发布动作。
 */
public interface AuthoringFormPatchProvider {

    /**
     * 判断当前提供者是否负责指定表单。
     */
    boolean supports(String formKey);

    /**
     * 校验可信 ToolContext 中的领域、编辑目标和当前表单快照。
     */
    void validateContext(String authoringDomain, String formKey, String entityId,
            Map<String, Object> currentDraft);

    /**
     * 校验并清洗单条 RFC 6902 子集操作的 value；remove 操作的 value 为 null。
     */
    Object validateAndSanitizeValue(String formKey, String entityId, String operation,
            String path, Object value);
}
