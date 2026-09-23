package dev.a2flow.management.lifecycle.domain;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import dev.a2flow.management.support.JsonSupport;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 组件 Registry 领域对象。
 *
 * <p>该对象表达组件当前可编辑内容和运行态身份，不携带 MyBatis 注解，也不保存发布版本或环境
 * 生效状态。不可变发布快照由共享发布领域按组件资产 ID 关联维护。
 */
@Data
@Accessors(chain = true)
public class ComponentAsset {

    private Long id;
    private String assetType;
    private String componentName;
    private String componentNameCn;
    /** A2UI 原子组件类型；仅 A2UI_ATOM 使用，旧 CARD_COMPONENT / BUSINESS_DSL 不读取。 */
    private String a2uiComponentType;
    /** A2UI 原子组件规范的 canonical JSON；不承载 Catalog 发布权威或 renderer 证据。 */
    private String a2uiContractJson;
    private String dslType;
    private String agentUiDsl;
    private Integer protocolVersion;
    private String interactionMode;
    private String bundleUrl;
    private String appBundleUrl;
    private String owner;
    private String scene;
    private String paramsSchemaJson;
    private String renderTemplateJson;
    private String officialDemoJson;
    private String messageDemoJson;
    private String allowedActionsJson;
    private String runtimeConfigJson;
    private String integrationPrompt;
    private List<String> supportClients = new ArrayList<>();
    private Boolean enabled;
    private String attribute;
    private String operator;
    private Long createTime;
    private Long updateTime;

    /**
     * 读取 A2UI 原子组件的结构化 contract；解析失败直接抛错，不向旧 DSL 形态降级。
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getA2uiContract() {
        if (a2uiContractJson == null || a2uiContractJson.trim().isEmpty()) {
            return null;
        }
        return JsonSupport.fromJSON(a2uiContractJson, Map.class);
    }

    /**
     * 设置 A2UI 原子组件的结构化 contract，并由 Registry 统一保存 JSON 列。
     */
    public ComponentAsset setA2uiContract(Map<String, Object> contract) {
        this.a2uiContractJson = contract == null ? null : JsonSupport.toJSON(contract);
        return this;
    }
}
