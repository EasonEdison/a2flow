package dev.a2flow.management.a2ui.application;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiActionBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiActionDeclaration;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationDraft;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiLoadBinding;
import dev.a2flow.management.a2ui.catalog.A2uiKuaishouCatalogImporter;
import dev.a2flow.management.a2ui.registry.A2uiRegistryValidationException;

/**
 * 将受控 Application blueprint 转换为普通 canonical authoring draft。
 *
 * <p>上游是 M 端 blueprint 导入动作，下游仍是通用 Application Registry/compiler/release 链路。
 * 本服务只读取随代码发布的静态 JSON 并执行协议边界校验，不创建 Registry/Release 数据，不解析
 * 当前 Capability，不按 appCode 修改 compiler，也不为 Workflow 保留码生成 M 端 Binding。
 */
@Service
public class A2uiApplicationBlueprintService {

    private static final String RESOURCE_ROOT = "skillfactory/a2ui/v0_9_1/blueprints/";
    private static final String BASIC_BLUEPRINT_CODE = "a2ui_kuaishou_basic_smoke";
    private static final String HITL_BLUEPRINT_CODE = "a2ui_kuaishou_hitl_smoke";
    private static final String ERROR_BLUEPRINT_NOT_FOUND = "A2UI_APPLICATION_BLUEPRINT_NOT_FOUND";
    private static final String ERROR_BLUEPRINT_INVALID = "A2UI_APPLICATION_BLUEPRINT_INVALID";
    private static final Map<String, String> BLUEPRINT_RESOURCES = blueprintResources();
    private static final List<Map<String, Object>> BLUEPRINTS = List.of(
            blueprint(BASIC_BLUEPRINT_CODE, "快手基础示例",
                    "包含基础展示与标准 Action Binding 的快手 Application 示例"),
            blueprint(HITL_BLUEPRINT_CODE, "快手人工确认示例",
                    "包含 action.context path binding 的快手 HITL Application 示例"));

    private final A2uiShowTemplateAnalyzer showTemplateAnalyzer = new A2uiShowTemplateAnalyzer();

    /**
     * 返回服务端受控的可导入 Blueprint 列表；不暴露 Workflow Runtime 模板。
     */
    public List<Map<String, Object>> listBlueprints() {
        return BLUEPRINTS;
    }

    /**
     * 导入一份新的普通 draft；每次调用都返回深拷贝，调用方可继续编辑后再走 create/update。
     */
    public Map<String, Object> importDraft(String blueprintCode) {
        String resource = BLUEPRINT_RESOURCES.get(blueprintCode);
        if (resource == null) {
            throw new A2uiRegistryValidationException(ERROR_BLUEPRINT_NOT_FOUND);
        }
        Map<String, Object> source = jsonObject(readResource(resource));
        validateBlueprint(blueprintCode, source);
        return jsonObject(JsonSupport.toJSON(A2uiImmutableJsonSupport.canonicalize(source)));
    }

    private void validateBlueprint(String blueprintCode, Map<String, Object> source) {
        A2uiApplicationDraft draft = JsonSupport.fromJSON(
                JsonSupport.toJSON(source), A2uiApplicationDraft.class);
        if (draft == null
                || !blueprintCode.equals(draft.getAppCode())
                || !A2uiKuaishouCatalogImporter.CATALOG_ID.equals(draft.getCatalogId())
                || source.containsKey("clientDataModel")) {
            throw new A2uiRegistryValidationException(ERROR_BLUEPRINT_INVALID);
        }
        List<A2uiActionDeclaration> declarations = showTemplateAnalyzer.analyze(
                draft.getShowTemplate(), draft.getCatalogId()).getActionDeclarations();
        showTemplateAnalyzer.validateInputBindings(draft.getShowTemplate());
        for (A2uiActionDeclaration declaration : declarations) {
            rejectReserved(declaration == null ? null : declaration.getActionCode());
        }
        for (A2uiLoadBinding binding : safe(draft.getLoadBindings())) {
            rejectReserved(binding == null || binding.getCapability() == null
                    ? null : binding.getCapability().getActionCode());
        }
        for (A2uiActionBinding binding : safe(draft.getActionBindings())) {
            rejectReserved(binding == null ? null : binding.getActionCode());
            rejectReserved(binding == null || binding.getCapability() == null
                    ? null : binding.getCapability().getActionCode());
        }
    }

    private void rejectReserved(String actionCode) {
        if (A2uiReservedActionCode.isReserved(actionCode)) {
            throw new A2uiRegistryValidationException(ERROR_BLUEPRINT_INVALID);
        }
    }

    private String readResource(String resource) {
        ClassLoader loader = A2uiApplicationBlueprintService.class.getClassLoader();
        try (InputStream input = loader.getResourceAsStream(resource)) {
            if (input == null) {
                throw new A2uiRegistryValidationException(ERROR_BLUEPRINT_INVALID);
            }
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException exception) {
            throw new A2uiRegistryValidationException(ERROR_BLUEPRINT_INVALID);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> jsonObject(String json) {
        Object value = JsonSupport.fromJSON(json, Object.class);
        if (!(value instanceof Map)) {
            throw new A2uiRegistryValidationException(ERROR_BLUEPRINT_INVALID);
        }
        return (Map<String, Object>) value;
    }

    private <T> List<T> safe(List<T> values) {
        return values == null ? Collections.emptyList() : values;
    }

    private static Map<String, String> blueprintResources() {
        Map<String, String> resources = new LinkedHashMap<>();
        resources.put(BASIC_BLUEPRINT_CODE, RESOURCE_ROOT + "a2ui_kuaishou_basic_smoke.json");
        resources.put(HITL_BLUEPRINT_CODE, RESOURCE_ROOT + "a2ui_kuaishou_hitl_smoke.json");
        return Collections.unmodifiableMap(resources);
    }

    private static Map<String, Object> blueprint(String blueprintCode, String name,
            String description) {
        Map<String, Object> blueprint = new LinkedHashMap<>();
        blueprint.put("blueprintCode", blueprintCode);
        blueprint.put("name", name);
        blueprint.put("description", description);
        blueprint.put("catalogId", A2uiKuaishouCatalogImporter.CATALOG_ID);
        return Collections.unmodifiableMap(blueprint);
    }
}
