package dev.a2flow.management.a2ui.runtime.ledger;

import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * A2Flow B 端单条消息的 A2UI Surface 当前态账本。
 *
 * <p>账本按 Surface 保存 createSurface 元数据、按 component id 索引的组件当前态和 data model 当前态。
 * 上游 reducer 每批先复制账本再应用完整消息，成功后才把新账本交给持久化层；本类不访问数据库、
 * 不发送 SSE，也不执行 CapabilityAction。旧 CARD_CONTAINER/BUSINESS_DSL 不进入该账本。</p>
 */
public final class A2uiRuntimeSurfaceLedger {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final TypeReference<LinkedHashMap<String, Object>> MAP_TYPE =
            new TypeReference<LinkedHashMap<String, Object>>() { };

    private final LinkedHashMap<String, SurfaceState> surfaces;

    private A2uiRuntimeSurfaceLedger(LinkedHashMap<String, SurfaceState> surfaces) {
        this.surfaces = surfaces;
    }

    /** 创建不包含任何 Surface 的新账本。 */
    public static A2uiRuntimeSurfaceLedger empty() {
        return new A2uiRuntimeSurfaceLedger(new LinkedHashMap<>());
    }

    /** 仅暴露Surface存在性，避免Action Gateway读取或修改账本内部可变状态。 */
    public boolean hasSurface(String surfaceId) {
        return surfaceId != null && surfaces.containsKey(surfaceId);
    }

    /**
     * 创建完全隔离的 staging 副本，确保后续某条消息失败时不会污染已提交账本。
     */
    A2uiRuntimeSurfaceLedger copy() {
        LinkedHashMap<String, SurfaceState> copied = new LinkedHashMap<>();
        surfaces.forEach((surfaceId, surface) -> copied.put(surfaceId, surface.copy()));
        return new A2uiRuntimeSurfaceLedger(copied);
    }

    LinkedHashMap<String, SurfaceState> surfaces() {
        return surfaces;
    }

    static Map<String, Object> copyMap(Map<String, Object> source) {
        return OBJECT_MAPPER.convertValue(source, MAP_TYPE);
    }

    /** 单个 Surface 的协议当前态，仅允许同 package 的 reducer 修改。 */
    static final class SurfaceState {
        private final String protocolVersion;
        private final Map<String, Object> createSurface;
        private final LinkedHashMap<String, Map<String, Object>> components;
        private JsonNode dataModel;
        private boolean dataModelDefined;

        SurfaceState(String protocolVersion, Map<String, Object> createSurface) {
            this(protocolVersion, copyMap(createSurface), new LinkedHashMap<>(), null, false);
        }

        private SurfaceState(String protocolVersion, Map<String, Object> createSurface,
                LinkedHashMap<String, Map<String, Object>> components,
                JsonNode dataModel, boolean dataModelDefined) {
            this.protocolVersion = protocolVersion;
            this.createSurface = createSurface;
            this.components = components;
            this.dataModel = dataModel;
            this.dataModelDefined = dataModelDefined;
        }

        SurfaceState copy() {
            LinkedHashMap<String, Map<String, Object>> copiedComponents = new LinkedHashMap<>();
            components.forEach((componentId, component) ->
                    copiedComponents.put(componentId, copyMap(component)));
            JsonNode copiedDataModel = dataModel == null ? null : dataModel.deepCopy();
            return new SurfaceState(protocolVersion, copyMap(createSurface), copiedComponents,
                    copiedDataModel, dataModelDefined);
        }

        String getProtocolVersion() {
            return protocolVersion;
        }

        Map<String, Object> getCreateSurface() {
            return createSurface;
        }

        LinkedHashMap<String, Map<String, Object>> getComponents() {
            return components;
        }

        JsonNode getDataModel() {
            return dataModel;
        }

        void setDataModel(JsonNode dataModel) {
            this.dataModel = dataModel;
            this.dataModelDefined = true;
        }

        boolean isDataModelDefined() {
            return dataModelDefined;
        }
    }
}
