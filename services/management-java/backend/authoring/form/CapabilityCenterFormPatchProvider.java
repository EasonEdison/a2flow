package dev.a2flow.management.authoring.form;

import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

/**
 * 业务能力中心表单修改提案的字段与身份规则。
 *
 * <p>上游是通用 {@code propose_form_patch} 服务，下游是业务能力创建/编辑页。本类只允许模型
 * 修改公共业务字段和 PC/APP/COMMON 独立技术契约，系统推导的技术输出 Schema 和观测类型始终由平台维护。
 */
@Component
public class CapabilityCenterFormPatchProvider implements AuthoringFormPatchProvider {

    public static final String FORM_CAPABILITY_ACTION = "capability-center.action.v1";

    private static final String DOMAIN_CAPABILITY_CENTER = "CAPABILITY_CENTER";
    private static final String ENTITY_DRAFT_PREFIX = "capability-draft:";
    private static final String OPERATION_REMOVE = "remove";
    private static final List<String> EDITABLE_ROOT_PATHS = List.of(
            "/basicInfo", "/supportedClients", "/clientVariants", "/governance");
    private static final Set<String> SUPPORTED_CLIENTS = Set.of("PC", "APP", "COMMON");
    private static final Set<String> FORBIDDEN_PATH_SEGMENTS = Set.of(
            "technicalOutputSchema", "observedType");

    @Override
    public boolean supports(String formKey) {
        return FORM_CAPABILITY_ACTION.equals(formKey);
    }

    @Override
    public void validateContext(String authoringDomain, String formKey, String entityId,
            Map<String, Object> currentDraft) {
        if (!DOMAIN_CAPABILITY_CENTER.equals(StringUtils.upperCase(authoringDomain, Locale.ROOT))) {
            throw new IllegalArgumentException("业务能力 formKey 只能用于 CAPABILITY_CENTER Authoring");
        }
        if (!supports(formKey)) {
            throw new IllegalArgumentException("未注册的业务能力 formKey: " + formKey);
        }
        if (!StringUtils.startsWith(entityId, ENTITY_DRAFT_PREFIX)
                || StringUtils.isBlank(StringUtils.removeStart(entityId, ENTITY_DRAFT_PREFIX))) {
            throw new IllegalArgumentException("业务能力 entityId 必须使用 capability-draft 身份");
        }
        if (currentDraft == null || currentDraft.isEmpty()) {
            throw new IllegalArgumentException("currentDraft 必须是非空 JSON 对象");
        }
    }

    @Override
    public Object validateAndSanitizeValue(String formKey, String entityId, String operation,
            String path, Object value) {
        if (!isEditablePath(path)) {
            throw new IllegalArgumentException("form patch path 不在当前业务能力表单允许范围内: " + path);
        }
        return OPERATION_REMOVE.equals(operation) ? null : value;
    }

    private boolean isEditablePath(String path) {
        boolean editableRoot = EDITABLE_ROOT_PATHS.stream()
                .anyMatch(root -> root.equals(path) || StringUtils.startsWith(path, root + "/"));
        if (!editableRoot) {
            return false;
        }
        String[] segments = StringUtils.split(path, '/');
        if (StringUtils.startsWith(path, "/clientVariants/")
                && (segments.length < 2 || !SUPPORTED_CLIENTS.contains(segments[1]))) {
            return false;
        }
        for (String segment : segments) {
            if (FORBIDDEN_PATH_SEGMENTS.contains(segment)) {
                return false;
            }
        }
        return true;
    }
}
