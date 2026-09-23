package dev.a2flow.management.authoring.form;

import java.util.Collection;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

/**
 * 组件中心表单修改提案的字段与身份规则。
 *
 * <p>上游是通用表单 patch 服务，下游是 CARD_COMPONENT 和 BUSINESS_DSL 创建/编辑页。
 * 本类只校验组件中心可编辑字段，不负责组件注册、更新、预览或发布，也不包含 Skill 绑定字段。
 */
@Component
public class ComponentCenterFormPatchProvider implements AuthoringFormPatchProvider {

    public static final String FORM_CARD_COMPONENT = "component-center.card-component.v1";
    public static final String FORM_BUSINESS_DSL = "component-center.business-dsl.v1";

    private static final String DOMAIN_COMPONENT_CENTER = "COMPONENT_CENTER";
    private static final String ASSET_TYPE_CARD_COMPONENT = "CARD_COMPONENT";
    private static final String ASSET_TYPE_BUSINESS_DSL = "BUSINESS_DSL";
    private static final String FIELD_ASSET_TYPE = "assetType";
    private static final String PATH_INTERACTION_MODE = "/interactionMode";
    private static final String PATH_ENABLED = "/enabled";
    private static final String INTERACTION_MODE_DISPLAY_ONLY = "DISPLAY_ONLY";
    private static final String INTERACTION_MODE_INTERACTIVE = "INTERACTIVE";
    private static final String ENTITY_DRAFT_PREFIX = "component-draft:";
    private static final String ENTITY_ASSET_PREFIX = "component-asset:";
    private static final String OPERATION_REMOVE = "remove";
    private static final Set<String> CARD_CREATE_PATHS = Set.of(
            "/componentName", "/componentNameCn", "/interactionMode", "/bundleUrl", "/appBundleUrl",
            "/owner", "/scene",
            "/messageDemoJson",
            "/officialDemoJson", "/paramsSchemaJson", "/renderTemplateJson", "/allowedActionsJson",
            "/runtimeConfigJson", "/integrationPrompt");
    private static final Set<String> CARD_EDIT_PATHS = Set.of(
            "/componentNameCn", "/interactionMode", "/bundleUrl", "/appBundleUrl", "/owner", "/scene",
            "/messageDemoJson",
            "/officialDemoJson", "/paramsSchemaJson", "/renderTemplateJson", "/allowedActionsJson",
            "/runtimeConfigJson", "/integrationPrompt");
    private static final Set<String> BUSINESS_DSL_CREATE_PATHS = Set.of(
            "/componentName", "/componentNameCn", "/agentUiDsl", "/owner", "/scene", "/paramsSchemaJson",
            "/renderTemplateJson", "/officialDemoJson", "/messageDemoJson", "/allowedActionsJson",
            "/runtimeConfigJson", "/integrationPrompt", "/enabled");
    private static final Set<String> BUSINESS_DSL_EDIT_PATHS = Set.of(
            "/componentNameCn", "/owner", "/scene", "/paramsSchemaJson", "/renderTemplateJson",
            "/officialDemoJson", "/messageDemoJson", "/allowedActionsJson", "/runtimeConfigJson",
            "/integrationPrompt", "/enabled");
    private static final List<String> EXECUTABLE_MARKERS = List.of(
            "<script", "javascript:", "eval(", "new function(", "runtime.exec(",
            "processbuilder(", "groovyshell", "groovy.shell");

    @Override
    public boolean supports(String formKey) {
        return StringUtils.equalsAny(formKey, FORM_CARD_COMPONENT, FORM_BUSINESS_DSL);
    }

    @Override
    public void validateContext(String authoringDomain, String formKey, String entityId,
            Map<String, Object> currentDraft) {
        if (!DOMAIN_COMPONENT_CENTER.equals(StringUtils.upperCase(authoringDomain, Locale.ROOT))) {
            throw new IllegalArgumentException("组件中心 formKey 只能用于 COMPONENT_CENTER Authoring");
        }
        if (!supports(formKey)) {
            throw new IllegalArgumentException("未注册的组件中心 formKey: " + formKey);
        }
        boolean createEntity = StringUtils.startsWith(entityId, ENTITY_DRAFT_PREFIX)
                && StringUtils.isNotBlank(StringUtils.removeStart(entityId, ENTITY_DRAFT_PREFIX));
        boolean editEntity = StringUtils.startsWith(entityId, ENTITY_ASSET_PREFIX)
                && StringUtils.isNumeric(StringUtils.removeStart(entityId, ENTITY_ASSET_PREFIX));
        if (!createEntity && !editEntity) {
            throw new IllegalArgumentException("组件中心 entityId 必须使用 component-draft 或 component-asset 身份");
        }
        if (currentDraft == null || currentDraft.isEmpty()) {
            throw new IllegalArgumentException("currentDraft 必须是非空 JSON 对象");
        }
        String expectedAssetType = FORM_CARD_COMPONENT.equals(formKey)
                ? ASSET_TYPE_CARD_COMPONENT : ASSET_TYPE_BUSINESS_DSL;
        if (!expectedAssetType.equals(MapUtils.getString(currentDraft, FIELD_ASSET_TYPE))) {
            throw new IllegalArgumentException("formKey 与 currentDraft.assetType 不匹配");
        }
    }

    @Override
    public Object validateAndSanitizeValue(String formKey, String entityId, String operation,
            String path, Object value) {
        if (!allowedPaths(formKey, entityId).contains(path)) {
            throw new IllegalArgumentException("form patch path 不在当前组件表单允许范围内: " + path);
        }
        if (OPERATION_REMOVE.equals(operation)) {
            return null;
        }
        if (PATH_ENABLED.equals(path) && !(value instanceof Boolean)) {
            throw new IllegalArgumentException("enabled 必须是布尔值");
        }
        if (PATH_INTERACTION_MODE.equals(path)
                && !StringUtils.equalsAny(String.valueOf(value),
                INTERACTION_MODE_DISPLAY_ONLY, INTERACTION_MODE_INTERACTIVE)) {
            throw new IllegalArgumentException("交互类型只支持纯展示或需交互");
        }
        if (!PATH_ENABLED.equals(path) && !(value instanceof String)) {
            throw new IllegalArgumentException("组件表单字段必须是字符串: " + path);
        }
        rejectExecutableContent(value);
        return value;
    }

    private Set<String> allowedPaths(String formKey, String entityId) {
        boolean editMode = StringUtils.startsWith(entityId, ENTITY_ASSET_PREFIX);
        if (FORM_CARD_COMPONENT.equals(formKey)) {
            return editMode ? CARD_EDIT_PATHS : CARD_CREATE_PATHS;
        }
        return editMode ? BUSINESS_DSL_EDIT_PATHS : BUSINESS_DSL_CREATE_PATHS;
    }

    private void rejectExecutableContent(Object value) {
        if (value instanceof Map) {
            ((Map<?, ?>) value).forEach((key, item) -> {
                rejectExecutableContent(key);
                rejectExecutableContent(item);
            });
            return;
        }
        if (value instanceof Collection) {
            ((Collection<?>) value).forEach(this::rejectExecutableContent);
            return;
        }
        if (!(value instanceof String)) {
            return;
        }
        String normalized = StringUtils.lowerCase((String) value, Locale.ROOT);
        if (EXECUTABLE_MARKERS.stream().anyMatch(normalized::contains)) {
            throw new IllegalArgumentException("组件表单不允许写入可执行代码或脚本协议");
        }
    }
}
