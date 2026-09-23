package dev.a2flow.management.storage.db.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 组件资产数据对象。
 *
 * <p>该 DO 严格对应紧凑 `skill_component_registry` 表，只允许在 storage Repository 内使用。
 * 上层生命周期、发布、Authoring 和 RPC 代码必须使用领域对象或 API DTO。
 */
@Data
@Accessors(chain = true)
@TableName("skill_component_registry")
public class SkillFactoryComponentAssetDO {

    /**
     * 组件资产主键。
     */
    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /**
     * 资产类型：CARD_COMPONENT / BUSINESS_DSL / A2UI_ATOM。
     */
    @TableField("asset_type")
    private String assetType;

    /**
     * 前端组件、业务 DSL 或 A2UI 原子组件的稳定标识。
     */
    @TableField("component_name")
    private String componentName;

    /**
     * 组件中文名，用于组件中心页面展示。
     */
    @TableField("component_name_cn")
    private String componentNameCn;

    /**
     * A2UI 原子组件类型；仅 A2UI_ATOM 资产写入，旧协议资产保持为空。
     */
    @TableField("a2ui_component_type")
    private String a2uiComponentType;

    /**
     * A2UI 原子组件 canonical contract JSON；不保存 Catalog 支持权威。
     */
    @TableField("a2ui_contract_json")
    private String a2uiContractJson;

    /**
     * 运行态输入协议族：CARD_CONTAINER / BUSINESS_DSL。
     */
    @TableField("dsl_type")
    private String dslType;

    /**
     * BUSINESS_DSL 运行态查找键，与协议族分开存储。
     */
    @TableField("agent_ui_dsl")
    private String agentUiDsl;

    /**
     * 运行态协议主版本。
     */
    @TableField("protocol_version")
    private Integer protocolVersion;

    /**
     * CARD_COMPONENT 展示分类：DISPLAY_ONLY / INTERACTIVE。
     */
    @TableField("interaction_mode")
    private String interactionMode;

    /**
     * PC bundle 组件地址，CARD_CONTAINER 资产必填。
     */
    @TableField("bundle_url")
    private String bundleUrl;

    /**
     * APP bundle 组件地址，CARD_CONTAINER 资产必填。
     */
    @TableField("app_bundle_url")
    private String appBundleUrl;

    /**
     * 组件负责人。
     */
    @TableField("owner")
    private String owner;

    /**
     * 适用业务场景。
     */
    @TableField("scene")
    private String scene;

    /**
     * BUSINESS_DSL 模型输出 params 的 JSON Schema。
     */
    @TableField("params_schema_json")
    private String paramsSchemaJson;

    /**
     * BUSINESS_DSL 到 A2UI 的渲染模板配置。
     */
    @TableField("render_template_json")
    private String renderTemplateJson;

    /**
     * 官方只读 demo JSON。
     */
    @TableField("official_demo_json")
    private String officialDemoJson;

    /**
     * 官方 Skill 输出的 marker 内部 JSON；业务链路使用时再补 marker。
     */
    @TableField("message_demo_json")
    private String messageDemoJson;

    /**
     * 给 Skill 创建 / AI Coding 使用的接入提示词。
     */
    @TableField("integration_prompt")
    private String integrationPrompt;

    /**
     * action / event / functionCall 白名单。
     */
    @TableField("allowed_actions_json")
    private String allowedActionsJson;

    /**
     * 类型专属运行配置。
     */
    @TableField("runtime_config_json")
    private String runtimeConfigJson;

    /**
     * 支持端原生 JSON 数组。
     */
    @TableField("support_clients")
    private String supportClients;

    /**
     * 是否可被新 Skill 引用。
     */
    @TableField("enabled")
    private Integer enabled;

    /**
     * 扩展属性 JSON，用于后续灰度字段或非核心结构化信息扩展。
     */
    @TableField("attribute")
    private String attribute;

    /**
     * 最后操作人。
     */
    @TableField("operator")
    private String operator;

    /**
     * 创建时间，毫秒时间戳。
     */
    @TableField("create_time")
    private Long createTime;

    /**
     * 更新时间，毫秒时间戳。
     */
    @TableField("update_time")
    private Long updateTime;
}
