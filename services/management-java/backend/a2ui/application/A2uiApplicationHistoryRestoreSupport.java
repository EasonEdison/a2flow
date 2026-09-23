package dev.a2flow.management.a2ui.application;

import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.HISTORY_SNAPSHOT_INVALID;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.PROTOCOL_UNSUPPORTED;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.support.JsonSupport;

/**
 * 将历史发布 manifest 映射为可编辑的 Application 编排。
 *
 * <p>上游发布适配器负责快照完整性与资产身份校验，下游 Registry 负责作者态校验及落库。
 * 消息、绑定和交互配置全部来自冻结产物；名称、描述未进入旧 manifest，由调用方保留当前基础信息。
 * 本类不执行能力、不查询最新编排或依赖，不把发布权限字段复制回作者态。
 */
public final class A2uiApplicationHistoryRestoreSupport {

    private static final String PROTOCOL_VERSION = "v0.9.1";
    private static final String FIELD_PROTOCOL_VERSION = "protocolVersion";
    private static final String FIELD_APP_CODE = "appCode";
    private static final String FIELD_NAME_CN = "nameCn";
    private static final String FIELD_DESCRIPTION = "description";
    private static final String FIELD_CATALOG = "catalog";
    private static final String FIELD_CATALOG_ID = "catalogId";
    private static final String FIELD_SHOW_TEMPLATE = "showTemplate";
    private static final String FIELD_TEMPLATE_CODE = "templateCode";
    private static final String FIELD_SHOW_TEMPLATE_CODE = "showTemplateCode";
    private static final String FIELD_PARAMS_SCHEMA = "paramsSchema";
    private static final String FIELD_SURFACE_DECLARATIONS = "surfaceDeclarations";
    private static final String FIELD_MESSAGE_TEMPLATES = "messageTemplates";
    private static final String FIELD_INITIAL_MESSAGES = "initialMessages";
    private static final String FIELD_INPUT_BINDINGS = "inputBindings";
    private static final String FIELD_LOAD_BINDINGS = "loadBindings";
    private static final String FIELD_ACTION_BINDINGS = "actionBindings";
    private static final String FIELD_INTERACTION_MODE = "interactionMode";

    private A2uiApplicationHistoryRestoreSupport() {
    }

    /** 重组冻结字段并深拷贝，避免编辑新变更时污染历史快照的嵌套对象。 */
    @SuppressWarnings("unchecked")
    public static Map<String, Object> restore(String manifestJson,
            String appCode, String nameCn, Object description) {
        Map<String, Object> manifest = parseManifest(manifestJson);
        if (manifest == null || !StringUtils.equals(appCode, text(manifest, FIELD_APP_CODE))) {
            throw invalidSnapshot();
        }
        if (!PROTOCOL_VERSION.equals(text(manifest, FIELD_PROTOCOL_VERSION))) {
            throw new A2uiApplicationValidationException(PROTOCOL_UNSUPPORTED);
        }
        Map<String, Object> show = new LinkedHashMap<>();
        show.put(FIELD_TEMPLATE_CODE, text(manifest, FIELD_SHOW_TEMPLATE_CODE));
        show.put(FIELD_PARAMS_SCHEMA, object(manifest, FIELD_PARAMS_SCHEMA));
        show.put(FIELD_SURFACE_DECLARATIONS, objects(manifest, FIELD_SURFACE_DECLARATIONS, true));
        show.put(FIELD_MESSAGE_TEMPLATES, objects(manifest, FIELD_INITIAL_MESSAGES, true));
        show.put(FIELD_INPUT_BINDINGS, objects(manifest, FIELD_INPUT_BINDINGS, false));

        Map<String, Object> source = new LinkedHashMap<>();
        source.put(FIELD_APP_CODE, appCode);
        source.put(FIELD_NAME_CN, nameCn);
        source.put(FIELD_DESCRIPTION, description);
        source.put(FIELD_CATALOG_ID, text(object(manifest, FIELD_CATALOG), FIELD_CATALOG_ID));
        source.put(FIELD_SHOW_TEMPLATE, show);
        source.put(FIELD_LOAD_BINDINGS, objects(manifest, FIELD_LOAD_BINDINGS, false));
        source.put(FIELD_ACTION_BINDINGS, objects(manifest, FIELD_ACTION_BINDINGS, false));
        source.put(FIELD_INTERACTION_MODE, text(manifest, FIELD_INTERACTION_MODE));
        Map<String, Object> restored = JsonSupport.fromJSON(JsonSupport.toJSON(source), Map.class);
        A2uiApplicationActionScanService actionScanService = new A2uiApplicationActionScanService();
        actionScanService.requireReleaseClosure(actionScanService.scan(restored));
        return restored;
    }

    /** 非 JSON 或顶层类型损坏属于历史快照错误，不对用户暴露解析器堆栈。 */
    @SuppressWarnings("unchecked")
    private static Map<String, Object> parseManifest(String manifestJson) {
        try {
            return JsonSupport.fromJSON(manifestJson, Map.class);
        } catch (RuntimeException exception) {
            throw invalidSnapshot();
        }
    }

    /** 缺失字段和错误类型必须拒绝，不能用空结构替代历史业务编排。 */
    private static List<?> objects(Map<String, Object> source, String field, boolean nonEmpty) {
        Object value = source.get(field);
        if (!(value instanceof List<?> values) || (nonEmpty && values.isEmpty())) {
            throw invalidSnapshot();
        }
        for (Object element : values) {
            if (!(element instanceof Map<?, ?>)) {
                throw invalidSnapshot();
            }
        }
        return values;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Map<String, Object> source, String field) {
        Object value = source.get(field);
        if (!(value instanceof Map<?, ?>)) {
            throw invalidSnapshot();
        }
        return (Map<String, Object>) value;
    }

    private static String text(Map<String, Object> source, String field) {
        Object value = source.get(field);
        if (!(value instanceof String text) || StringUtils.isBlank(text)) {
            throw invalidSnapshot();
        }
        return text;
    }

    private static A2uiApplicationValidationException invalidSnapshot() {
        return new A2uiApplicationValidationException(HISTORY_SNAPSHOT_INVALID);
    }
}
