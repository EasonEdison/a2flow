package dev.a2flow.management.model;

import java.util.ArrayList;
import java.util.List;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 组件中心返回给统一 RPC 的组件资产 DTO。
 *
 * <p>该对象是页面和 Skill 创建侧消费的稳定 API 形态，字段命名保持驼峰并对齐紧凑 Registry。
 * 它不承载 DB 注解，也不代表 Skill 草稿内的绑定关系或发布状态表结构。
 */
@Data
@Accessors(chain = true)
public class SkillFactoryComponentAsset {

    private Long id;
    private String assetType;
    private String componentName;
    private String componentNameCn;
    private String a2uiComponentType;
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
    private String integrationPrompt;
    private String allowedActionsJson;
    private String runtimeConfigJson;
    private List<String> supportClients = new ArrayList<>();
    private Boolean enabled;
    private String attribute;
    private Boolean published;
    private Integer publishedVersion;
    private AssetReleaseEnvironmentFacts releaseEnvironmentFacts;
    private String operator;
    private Long createTime;
    private Long updateTime;
}
