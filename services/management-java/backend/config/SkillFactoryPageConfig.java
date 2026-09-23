package dev.a2flow.management.config;

import java.util.List;
import java.util.Map;

import lombok.Data;

/**
 * SkillFactory M端页面配置。
 *
 * <p>该模型承接 `skillFactoryPageConfig` KConf 中单个业务配置项，由 SkillFactory 自己的
 * KConf 读取器解析成强类型对象。
 * 它只描述页面展示所需的专员、快捷提示、参考组件/DSL资产、作者工作台入口 Agent 和跳转链接，不承接运行态
 * userId、鉴权、AI Coding engine 或组件中心资产注册逻辑。
 */
@Data
public class SkillFactoryPageConfig {

    private String agentId;
    private String ownerId;
    private String scopeType;
    private String capabilityProductionHost;
    private String capabilityPreReleaseHost;
    private List<Map<String, Object>> specialists;
    private List<Map<String, Object>> businessDomains;
    private List<Map<String, Object>> capabilityDomains;
    private List<Map<String, Object>> quickPrompts;
    private List<Map<String, Object>> referenceComponents;
    private List<Map<String, Object>> referenceRenderAssets;
    private Map<String, Object> links;
}
