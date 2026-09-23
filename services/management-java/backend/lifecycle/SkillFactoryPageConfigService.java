package dev.a2flow.management.lifecycle;


import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.config.SkillFactoryConfigReader;
import dev.a2flow.management.config.SkillFactoryPageConfig;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 页面动态配置 Service。
 *
 * <p>该类从 sellerdata-operation-service KConf `skillFactoryPageConfig` 读取 M 端页面需要动态调整的配置，
 * 例如数字员工中文名和 digitalEmployeeId 映射、对话快捷提示、创建时参考组件和调试入口。
 * 它只负责提供页面配置，不读取运行态 userId，不做 adviser 权限校验，
 * 也不承担组件中心资产注册。
 */
@Service
@Slf4j
public class SkillFactoryPageConfigService {

    private static final String FIELD_SPECIALISTS = "specialists";
    private static final String FIELD_BUSINESS_DOMAINS = "businessDomains";
    private static final String FIELD_CAPABILITY_DOMAINS = "capabilityDomains";
    private static final String FIELD_AGENT_ID = "agentId";
    private static final String FIELD_OWNER_ID = "ownerId";
    private static final String FIELD_SCOPE_TYPE = "scopeType";
    private static final String FIELD_CAPABILITY_CLUSTERS = "capabilityClusters";
    private static final String FIELD_CAPABILITY_PRODUCTION_HOST = "capabilityProductionHost";
    private static final String FIELD_CAPABILITY_PRE_RELEASE_HOST = "capabilityPreReleaseHost";
    private static final String FIELD_BIZ_CONFIGS = "bizConfigs";
    private static final String FIELD_QUICK_PROMPTS = "quickPrompts";
    private static final String FIELD_REFERENCE_COMPONENTS = "referenceComponents";
    private static final String FIELD_REFERENCE_RENDER_ASSETS = "referenceRenderAssets";
    private static final String FIELD_LINKS = "links";
    private static final String FIELD_ID = "id";
    private static final String FIELD_NAME = "name";
    private static final String FIELD_DIGITAL_EMPLOYEE_ID = "digitalEmployeeId";
    private static final String FIELD_SPECIALIST_ID = "specialistId";
    private static final String FIELD_SPECIALIST_NAME = "specialistName";
    private static final String FIELD_ROLE_CODE = "roleCode";
    private static final String FIELD_KEY = "key";
    private static final String FIELD_VALUE = "value";
    private static final String FIELD_LABEL = "label";
    private static final String FIELD_PROMPT = "prompt";
    private static final String FIELD_CODE = "code";
    private static final String FIELD_COMPONENT_NAME = "componentName";
    private static final String FIELD_ASSET_TYPE = "assetType";
    private static final String FIELD_RENDER_PROTOCOL = "renderProtocol";
    private static final String FIELD_DSL_CODE = "dslCode";
    private static final String FIELD_LOCAL_METHOD = "localMethod";
    private static final String FIELD_SCENE = "scene";
    private static final String FIELD_OWNER = "owner";
    private static final String FIELD_LIFECYCLE_STATUS = "lifecycleStatus";
    private static final String FIELD_ENABLED = "enabled";
    private static final String FIELD_PROTOCOL_VERSION = "protocolVersion";
    private static final String FIELD_RENDERER_VERSION = "rendererVersion";
    private static final String FIELD_OFFICIAL_DEMO_JSON = "officialDemoJson";
    private static final String FIELD_INTEGRATION_PROMPT = "integrationPrompt";
    private static final String FIELD_PARAMS_SCHEMA_JSON = "paramsSchemaJson";
    private static final String FIELD_B_END_DEBUG_PAGE_URL = "bEndDebugPageUrl";
    private static final String FIELD_TRACE_PAGE_URL = "tracePageUrl";

    private static final String CONFIG_KEY_HADES_SKILL_FACTORY = "HADES_SKILL_FACTORY";
    private static final String CONFIG_KEY_HADES_COMPONENT_CENTER_AUTHORING = "HADES_COMPONENT_CENTER_AUTHORING";
    private static final String CONFIG_KEY_DEFAULT = "default";
    private static final String SCOPE_TYPE_SKILL = "SKILL";
    private static final String SCOPE_TYPE_COMPONENT = "COMPONENT";
    private static final String SKILL_CODING_AGENT_ID = "244510";
    private static final String SKILL_CODING_OWNER_ID = "system";
    private static final String SPECIALIST_LIVE_ID = "100001";
    private static final String SPECIALIST_CONTENT_ID = "100002";
    private static final String SPECIALIST_GUARANTEE_ID = "100003";
    private static final String SPECIALIST_LIVE_NAME = "直播专员";
    private static final String SPECIALIST_CONTENT_NAME = "内容专员";
    private static final String SPECIALIST_GUARANTEE_NAME = "保障专员";
    private static final String ROLE_LIVE_SPECIALIST = "live_specialist";
    private static final String ROLE_CONTENT_SPECIALIST = "content_specialist";
    private static final String ROLE_GUARANTEE_SPECIALIST = "guarantee_specialist";
    private static final String BUSINESS_DOMAIN_LIVE_VALUE = "直播经营";
    private static final String BUSINESS_DOMAIN_CONTENT_VALUE = "内容经营";
    private static final String BUSINESS_DOMAIN_GUARANTEE_VALUE = "售后保障";
    private static final String CAPABILITY_DOMAIN_PLAN_VALUE = "计划创建";
    private static final String CAPABILITY_DOMAIN_REVIEW_VALUE = "复盘诊断";
    private static final String CAPABILITY_DOMAIN_CONTENT_VALUE = "内容生成";
    private static final String CAPABILITY_DOMAIN_GUARANTEE_VALUE = "保障处理";
    private static final String QUICK_PROMPT_READINESS = "readiness";
    private static final String QUICK_PROMPT_TODO = "todo";
    private static final String QUICK_PROMPT_CARD_PROTOCOL = "card-protocol";
    private static final String COMPONENT_LIVE_PLAN_CREATE_CARD = "LivePlanCreateCard";
    private static final String COMPONENT_CHOICE_PICKER = "ChoicePicker";
    private static final String COMPONENT_MARKDOWN_CONCLUSION_CARD = "MarkdownConclusionCard";
    private static final String ASSET_TYPE_BUSINESS_DSL = "BUSINESS_DSL";
    private static final String ASSET_TYPE_CARD_CONTAINER = "CARD_CONTAINER";
    private static final String ASSET_TYPE_LOCAL_METHOD = "localMethod";
    private static final String ASSET_TYPE_A2UI_ATOM = "A2UI_ATOM";
    private static final String DSL_LIVE_STREAM_SELECTOR = "live_stream_selector";
    private static final String LOCAL_METHOD_SELECT_COMPONENT_REFS = "selectComponentRefs";
    private static final String PROTOCOL_CARD_CONTAINER = "CARD_CONTAINER";
    private static final String PROTOCOL_AGENT_UI_DSL = "agentUiDsl";
    private static final String PROTOCOL_LOCAL_METHOD = "localMethod";
    private static final String PROTOCOL_A2UI_ATOM = "A2UI_ATOM";
    private static final String PROTOCOL_A2UI = "A2UI";
    private static final String STATUS_REGISTERED = "REGISTERED";
    private static final String OWNER_SKILL_FACTORY = "skill-factory";
    private static final String SCENE_LIVE_PLAN = "直播计划";
    private static final String SCENE_LIVE_REVIEW = "直播复盘";
    private static final String SCENE_COMMON = "通用兜底";
    private static final String SCENE_SELECT_COMPONENT = "创建过程补充参考组件";
    private static final String B_END_DEBUG_PAGE_URL = "/employee/";
    private static final String TRACE_PAGE_URL = "/management/lab/observability";
    private static final String PROMPT_READINESS =
            "请基于当前 workspace 文件、参考组件、绑定验证结果和发布前检查，"
                    + "判断当前 Skill 是否达到准出标准，"
                    + "并按“已满足 / 未满足 / 风险 / 下一步动作”输出。";
    private static final String PROMPT_TODO =
            "请基于当前 Skill 草稿列出还待人工确认的信息，"
                    + "按业务逻辑、前端协议、参数来源、发布风险四类输出待定事项清单。";
    private static final String PROMPT_CARD_PROTOCOL =
            "请根据已选参考组件的接入提示，补齐当前 Skill 的输出协议样例，"
                    + "确保 componentName、data、action 字段能被前端真实渲染。";
    private static final String PROMPT_LIVE_PLAN_COMPONENT =
            "引用组件中心「直播计划创建结果卡（LivePlanCreateCard）」作为前端承接组件。"
                    + "Skill 输出 markdown 结论后追加 card-container 协议，"
                    + "componentName=LivePlanCreateCard，data 中包含 title、planTime、todoItems 和 action。";
    private static final String PROMPT_CHOICE_PICKER_COMPONENT =
            "引用 A2UI「直播复盘选择器（ChoicePicker）」作为交互组件。"
                    + "Skill 只输出 DigitalEmployeeComponentPayload，agentUiDsl=live_stream_selector，"
                    + "params 放业务参数，完整 A2UI envelope 由 adviser adapter 生成。";
    private static final String PROMPT_MARKDOWN_COMPONENT =
            "引用通用结论卡 MarkdownConclusionCard，输出面向商家的 markdown 结论，"
                    + "并在 data 中提供 title、summary、suggestions 和可选跳转 action。";
    private static final String PROMPT_LIVE_SELECTOR_DSL =
            "当 Skill 需要让商家选择直播场次时，输出 agentUiDsl=live_stream_selector 和 params 业务参数；"
                    + "完整 A2UI 由 adviser runtime 确定性生成。";
    private static final String PROMPT_LOCAL_METHOD_SELECT_COMPONENT =
            "当对话生成需要用户补充参考组件时，只输出 localMethod=selectComponentRefs 和 params；"
                    + "平台前端用现有 localMethod 链路展示选择结果。";
    private static final String PROMPT_CHOICE_PICKER_ATOM =
            "ChoicePicker 是 adviser runtime 生成完整 A2UI 时可使用的可信原子能力。"
                    + "生产 Skill 不直接手写完整 A2UI component tree。";
    private static final String DEMO_LIVE_SELECTOR_DSL =
            "{\"agentUiDsl\":\"live_stream_selector\",\"params\":{\"streams\":[{\"id\":\"live_001\","
                    + "\"title\":\"6月23日晚场直播\"}]}}";
    private static final String PARAMS_SCHEMA_LIVE_SELECTOR_DSL =
            "{\"type\":\"object\",\"properties\":{\"timeRange\":{\"type\":\"string\"},"
                    + "\"maxCount\":{\"type\":\"number\"}},\"required\":[\"timeRange\"]}";
    private static final String DEMO_LIVE_PLAN_CARD =
            "{\"componentName\":\"LivePlanCreateCard\",\"data\":{\"title\":\"直播计划创建\","
                    + "\"planName\":\"晚场直播\",\"startTime\":\"2026-06-13 20:00\"}}";
    private static final String DEMO_LOCAL_METHOD_SELECT_COMPONENT =
            "{\"localMethod\":\"selectComponentRefs\",\"params\":{\"selected\":[\"live_stream_selector\"]}}";
    private static final String DEMO_CHOICE_PICKER_ATOM =
            "{\"type\":\"updateComponents\",\"surfaceId\":\"choice-picker-demo\","
                    + "\"components\":[{\"id\":\"liveChoice\",\"type\":\"ChoicePicker\"}]}";
    private static final int DEFAULT_ITEM_CAPACITY = 4;

    @Resource
    private SkillFactoryConfigReader skillFactoryConfigReader;

    /**
     * 读取 SkillFactory 页面配置。
     *
     * <p>KConf 为空时返回后端默认配置，保证页面结构完整；KConf 结构错误时记录日志并回退默认配置。
     * 这样可以避免一次错误配置导致 SkillFactory 页面整页不可用。
     */
    public Map<String, Object> getConfig() {
        Map<String, Object> config = getPageConfig();
        config.put(FIELD_CAPABILITY_CLUSTERS, skillFactoryConfigReader.getCapabilityClusterConfigMap());
        return config;
    }

    /** 读取既有页面配置，保留原有默认页面行为。 */
    private Map<String, Object> getPageConfig() {
        try {
            Map<String, SkillFactoryPageConfig> configMap =
                    skillFactoryConfigReader.getPageConfigMap();
            SkillFactoryPageConfig pageConfig = selectConfig(configMap);
            Map<String, Object> config = toConfigMap(pageConfig, configMap);
            if (config == null || config.isEmpty()) {
                log.info("SkillFactory页面主配置为空，返回默认页面配置并保留可用biz配置, configKeys={}",
                        configMap == null ? null : configMap.keySet());
                Map<String, Object> defaultConfig = defaultConfig();
                defaultConfig.put(FIELD_BIZ_CONFIGS, toBizConfigs(configMap));
                return defaultConfig;
            }
            log.info("SkillFactory页面配置读取完成, configKey={}, specialistCount={}, businessDomainCount={}, "
                            + "capabilityDomainCount={}, quickPromptCount={}, referenceCount={}, "
                            + "referenceRenderAssetCount={}, bizConfigCount={}",
                    selectedConfigKey(configMap),
                    sizeOf(config.get(FIELD_SPECIALISTS)),
                    sizeOf(config.get(FIELD_BUSINESS_DOMAINS)),
                    sizeOf(config.get(FIELD_CAPABILITY_DOMAINS)),
                    sizeOf(config.get(FIELD_QUICK_PROMPTS)),
                    sizeOf(config.get(FIELD_REFERENCE_COMPONENTS)),
                    sizeOf(config.get(FIELD_REFERENCE_RENDER_ASSETS)),
                    sizeOf(config.get(FIELD_BIZ_CONFIGS)));
            return config;
        } catch (Exception e) {
            log.warn("SkillFactory页面配置KConf读取失败，返回默认配置, error={}", e.getMessage());
            return defaultConfig();
        }
    }

    /**
     * 按请求专员 ID 解析后端受控的专员配置。
     *
     * <p>注册接口只信任 KConf 中存在的专员 ID，并以 KConf 名称作为关系快照展示名。返回顺序与请求
     * 一致，重复 ID 自动去重；不存在的 ID 会直接阻断注册，避免写入无法发布的运行态关系。
     */
    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> resolveSpecialists(String requestedSpecialistIds) {
        String[] rawRequestedIds = StringUtils.split(
                StringUtils.defaultString(requestedSpecialistIds), ',');
        if (rawRequestedIds == null || rawRequestedIds.length == 0) {
            return new ArrayList<>();
        }
        List<String> requestedIds = Arrays.stream(rawRequestedIds)
                .map(StringUtils::trimToEmpty)
                .filter(StringUtils::isNotBlank)
                .distinct()
                .collect(Collectors.toList());
        if (requestedIds.isEmpty()) {
            return new ArrayList<>();
        }
        Object configuredValue = getConfig().get(FIELD_SPECIALISTS);
        List<Map<String, Object>> configured = configuredValue instanceof List
                ? (List<Map<String, Object>>) configuredValue : new ArrayList<>();
        Map<String, Map<String, Object>> configuredById = new LinkedHashMap<>();
        for (Map<String, Object> specialist : configured) {
            if (specialist != null && specialist.get(FIELD_ID) != null) {
                configuredById.put(String.valueOf(specialist.get(FIELD_ID)), specialist);
            }
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (String requestedId : requestedIds) {
            Map<String, Object> specialist = configuredById.get(requestedId);
            if (specialist == null) {
                log.warn("SkillFactory注册请求包含未配置专员, specialistId:{}", requestedId);
                throw new IllegalArgumentException("所属专员未在skillFactoryPageConfig中配置：" + requestedId);
            }
            result.add(new LinkedHashMap<>(specialist));
        }
        return result;
    }

    /** 按稳定值解析后端受控的业务域配置。 */
    public Map<String, Object> resolveBusinessDomain(String requestedValue) {
        return resolveControlledOption(FIELD_BUSINESS_DOMAINS, requestedValue, "业务域");
    }

    /** 按稳定值解析后端受控的能力域配置。 */
    public Map<String, Object> resolveCapabilityDomain(String requestedValue) {
        return resolveControlledOption(FIELD_CAPABILITY_DOMAINS, requestedValue, "能力域");
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> resolveControlledOption(String configField, String requestedValue,
            String fieldName) {
        String normalizedValue = StringUtils.trimToEmpty(requestedValue);
        if (StringUtils.isBlank(normalizedValue)) {
            throw new IllegalArgumentException(fieldName + "不能为空");
        }
        Object configuredValue = getConfig().get(configField);
        List<Map<String, Object>> configured = configuredValue instanceof List
                ? (List<Map<String, Object>>) configuredValue : new ArrayList<>();
        for (Map<String, Object> option : configured) {
            if (option != null && StringUtils.equals(normalizedValue,
                    StringUtils.trimToEmpty(String.valueOf(option.get(FIELD_VALUE))))) {
                return new LinkedHashMap<>(option);
            }
        }
        log.warn("SkillFactory请求包含未配置受控选项, fieldName:{}, value:{}", fieldName, normalizedValue);
        throw new IllegalArgumentException(
                fieldName + "未在skillFactoryPageConfig中配置：" + normalizedValue);
    }

    private Map<String, Object> defaultConfig() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_AGENT_ID, SKILL_CODING_AGENT_ID);
        result.put(FIELD_OWNER_ID, SKILL_CODING_OWNER_ID);
        result.put(FIELD_SCOPE_TYPE, SCOPE_TYPE_SKILL);
        result.put(FIELD_BIZ_CONFIGS, defaultBizConfigs());
        result.put(FIELD_SPECIALISTS, defaultSpecialists());
        result.put(FIELD_BUSINESS_DOMAINS, defaultBusinessDomains());
        result.put(FIELD_CAPABILITY_DOMAINS, defaultCapabilityDomains());
        result.put(FIELD_QUICK_PROMPTS, defaultQuickPrompts());
        result.put(FIELD_REFERENCE_COMPONENTS, defaultReferenceComponents());
        result.put(FIELD_REFERENCE_RENDER_ASSETS, defaultReferenceRenderAssets());
        result.put(FIELD_LINKS, defaultLinks());
        return result;
    }

    private Map<String, Object> defaultBizConfigs() {
        Map<String, Object> result = new LinkedHashMap<>();
        Map<String, Object> skillConfig = new LinkedHashMap<>();
        skillConfig.put(FIELD_AGENT_ID, SKILL_CODING_AGENT_ID);
        skillConfig.put(FIELD_OWNER_ID, SKILL_CODING_OWNER_ID);
        skillConfig.put(FIELD_SCOPE_TYPE, SCOPE_TYPE_SKILL);
        result.put(CONFIG_KEY_HADES_SKILL_FACTORY, skillConfig);
        return result;
    }

    private SkillFactoryPageConfig selectConfig(Map<String, SkillFactoryPageConfig> configMap) {
        if (configMap == null || configMap.isEmpty()) {
            return null;
        }
        SkillFactoryPageConfig config = configMap.get(CONFIG_KEY_HADES_SKILL_FACTORY);
        if (Objects.nonNull(config)) {
            return config;
        }
        return configMap.get(CONFIG_KEY_DEFAULT);
    }

    private String selectedConfigKey(Map<String, SkillFactoryPageConfig> configMap) {
        if (configMap == null || configMap.isEmpty()) {
            return null;
        }
        if (configMap.containsKey(CONFIG_KEY_HADES_SKILL_FACTORY)) {
            return CONFIG_KEY_HADES_SKILL_FACTORY;
        }
        if (configMap.containsKey(CONFIG_KEY_DEFAULT)) {
            return CONFIG_KEY_DEFAULT;
        }
        return null;
    }

    private Map<String, Object> toConfigMap(SkillFactoryPageConfig pageConfig,
                                            Map<String, SkillFactoryPageConfig> configMap) {
        if (Objects.isNull(pageConfig)) {
            return null;
        }
        Map<String, Object> result = new LinkedHashMap<>();
        putIfNotBlank(result, FIELD_AGENT_ID, pageConfig.getAgentId());
        putIfNotBlank(result, FIELD_OWNER_ID, pageConfig.getOwnerId());
        putIfNotBlank(result, FIELD_SCOPE_TYPE, pageConfig.getScopeType());
        putIfNotBlank(result, FIELD_CAPABILITY_PRODUCTION_HOST, pageConfig.getCapabilityProductionHost());
        putIfNotBlank(result, FIELD_CAPABILITY_PRE_RELEASE_HOST, pageConfig.getCapabilityPreReleaseHost());
        putIfNotNull(result, FIELD_BIZ_CONFIGS, toBizConfigs(configMap));
        putIfNotNull(result, FIELD_SPECIALISTS, normalizeSpecialists(pageConfig.getSpecialists()));
        putIfNotNull(result, FIELD_BUSINESS_DOMAINS, pageConfig.getBusinessDomains());
        putIfNotNull(result, FIELD_CAPABILITY_DOMAINS, pageConfig.getCapabilityDomains());
        putIfNotNull(result, FIELD_QUICK_PROMPTS, pageConfig.getQuickPrompts());
        putIfNotNull(result, FIELD_REFERENCE_COMPONENTS, pageConfig.getReferenceComponents());
        putIfNotNull(result, FIELD_REFERENCE_RENDER_ASSETS, pageConfig.getReferenceRenderAssets());
        putIfNotNull(result, FIELD_LINKS, pageConfig.getLinks());
        return result;
    }

    private Map<String, Object> toBizConfigs(Map<String, SkillFactoryPageConfig> configMap) {
        Map<String, Object> result = new LinkedHashMap<>();
        if (configMap == null || configMap.isEmpty()) {
            result.putAll(defaultBizConfigs());
            return result;
        }
        configMap.forEach((configKey, pageConfig) -> {
            Map<String, Object> bizConfig = toBizConfigMap(configKey, pageConfig);
            if (!bizConfig.isEmpty()) {
                result.put(configKey, bizConfig);
            }
        });
        if (!result.containsKey(CONFIG_KEY_HADES_SKILL_FACTORY)
                && result.containsKey(CONFIG_KEY_DEFAULT)) {
            result.put(CONFIG_KEY_HADES_SKILL_FACTORY, result.get(CONFIG_KEY_DEFAULT));
        }
        if (!result.containsKey(CONFIG_KEY_HADES_SKILL_FACTORY)) {
            result.putAll(defaultBizConfigs());
        }
        return result;
    }

    private Map<String, Object> toBizConfigMap(String configKey, SkillFactoryPageConfig pageConfig) {
        Map<String, Object> result = new LinkedHashMap<>();
        if (Objects.isNull(pageConfig)) {
            return result;
        }
        putIfNotBlank(result, FIELD_AGENT_ID, pageConfig.getAgentId());
        putIfNotBlank(result, FIELD_OWNER_ID, pageConfig.getOwnerId());
        putIfNotBlank(result, FIELD_SCOPE_TYPE, resolveScopeType(configKey, pageConfig));
        putIfNotBlank(result, FIELD_CAPABILITY_PRODUCTION_HOST, pageConfig.getCapabilityProductionHost());
        putIfNotBlank(result, FIELD_CAPABILITY_PRE_RELEASE_HOST, pageConfig.getCapabilityPreReleaseHost());
        putIfNotNull(result, FIELD_CAPABILITY_DOMAINS, pageConfig.getCapabilityDomains());
        return result;
    }

    /**
     * 归一化专员下拉配置。
     *
     * <p>KConf 允许用 `id/name`、`value/label` 或 `digitalEmployeeId/specialistName`
     * 描述“展示文字 + 绑定接口传参数字”。这里统一补齐为前端稳定消费的 `id/name`，
     * 不在页面或绑定接口里再猜字段。
     */
    private List<Map<String, Object>> normalizeSpecialists(List<Map<String, Object>> specialists) {
        if (specialists == null || specialists.isEmpty()) {
            return null;
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> specialist : specialists) {
            if (specialist == null || specialist.isEmpty()) {
                continue;
            }
            String id = firstNotBlank(specialist, FIELD_ID, FIELD_DIGITAL_EMPLOYEE_ID,
                    FIELD_SPECIALIST_ID, FIELD_VALUE);
            String name = firstNotBlank(specialist, FIELD_NAME, FIELD_SPECIALIST_NAME, FIELD_LABEL);
            if (!isNotBlank(id) || !isNotBlank(name)) {
                log.warn("SkillFactory页面专员配置缺少id或name，跳过该项, keys={}", specialist.keySet());
                continue;
            }
            Map<String, Object> normalized = new LinkedHashMap<>(specialist);
            normalized.put(FIELD_ID, id);
            normalized.put(FIELD_NAME, name);
            result.add(normalized);
        }
        return result;
    }

    private String firstNotBlank(Map<String, Object> item, String... keys) {
        for (String key : keys) {
            Object value = item.get(key);
            if (Objects.nonNull(value) && isNotBlank(String.valueOf(value))) {
                return String.valueOf(value).trim();
            }
        }
        return null;
    }

    private String resolveScopeType(String configKey, SkillFactoryPageConfig pageConfig) {
        if (Objects.nonNull(pageConfig) && isNotBlank(pageConfig.getScopeType())) {
            return pageConfig.getScopeType().trim();
        }
        if (CONFIG_KEY_HADES_COMPONENT_CENTER_AUTHORING.equals(configKey)) {
            return SCOPE_TYPE_COMPONENT;
        }
        if (CONFIG_KEY_HADES_SKILL_FACTORY.equals(configKey) || CONFIG_KEY_DEFAULT.equals(configKey)) {
            return SCOPE_TYPE_SKILL;
        }
        return null;
    }

    private void putIfNotNull(Map<String, Object> result, String key, Object value) {
        if (Objects.nonNull(value)) {
            result.put(key, value);
        }
    }

    private void putIfNotBlank(Map<String, Object> result, String key, String value) {
        if (isNotBlank(value)) {
            result.put(key, value.trim());
        }
    }

    private boolean isNotBlank(String value) {
        return value != null && !value.trim().isEmpty();
    }

    private List<Map<String, Object>> defaultSpecialists() {
        List<Map<String, Object>> items = new ArrayList<>();
        items.add(item(FIELD_ID, SPECIALIST_LIVE_ID, FIELD_NAME, SPECIALIST_LIVE_NAME,
                FIELD_ROLE_CODE, ROLE_LIVE_SPECIALIST));
        items.add(item(FIELD_ID, SPECIALIST_CONTENT_ID, FIELD_NAME, SPECIALIST_CONTENT_NAME,
                FIELD_ROLE_CODE, ROLE_CONTENT_SPECIALIST));
        items.add(item(FIELD_ID, SPECIALIST_GUARANTEE_ID, FIELD_NAME, SPECIALIST_GUARANTEE_NAME,
                FIELD_ROLE_CODE, ROLE_GUARANTEE_SPECIALIST));
        return items;
    }

    private List<Map<String, Object>> defaultBusinessDomains() {
        List<Map<String, Object>> items = new ArrayList<>();
        items.add(item(FIELD_VALUE, BUSINESS_DOMAIN_LIVE_VALUE, FIELD_LABEL, BUSINESS_DOMAIN_LIVE_VALUE));
        items.add(item(FIELD_VALUE, BUSINESS_DOMAIN_CONTENT_VALUE, FIELD_LABEL, BUSINESS_DOMAIN_CONTENT_VALUE));
        items.add(item(FIELD_VALUE, BUSINESS_DOMAIN_GUARANTEE_VALUE, FIELD_LABEL,
                BUSINESS_DOMAIN_GUARANTEE_VALUE));
        return items;
    }

    private List<Map<String, Object>> defaultCapabilityDomains() {
        List<Map<String, Object>> items = new ArrayList<>();
        items.add(item(FIELD_VALUE, CAPABILITY_DOMAIN_PLAN_VALUE, FIELD_LABEL, CAPABILITY_DOMAIN_PLAN_VALUE));
        items.add(item(FIELD_VALUE, CAPABILITY_DOMAIN_REVIEW_VALUE, FIELD_LABEL, CAPABILITY_DOMAIN_REVIEW_VALUE));
        items.add(item(FIELD_VALUE, CAPABILITY_DOMAIN_CONTENT_VALUE, FIELD_LABEL,
                CAPABILITY_DOMAIN_CONTENT_VALUE));
        items.add(item(FIELD_VALUE, CAPABILITY_DOMAIN_GUARANTEE_VALUE, FIELD_LABEL,
                CAPABILITY_DOMAIN_GUARANTEE_VALUE));
        return items;
    }

    private List<Map<String, Object>> defaultQuickPrompts() {
        List<Map<String, Object>> items = new ArrayList<>();
        items.add(item(FIELD_KEY, QUICK_PROMPT_READINESS, FIELD_LABEL, "是否达到准出标准",
                FIELD_PROMPT, PROMPT_READINESS));
        items.add(item(FIELD_KEY, QUICK_PROMPT_TODO, FIELD_LABEL, "待定事项清单",
                FIELD_PROMPT, PROMPT_TODO));
        items.add(item(FIELD_KEY, QUICK_PROMPT_CARD_PROTOCOL, FIELD_LABEL, "生成卡片协议",
                FIELD_PROMPT, PROMPT_CARD_PROTOCOL));
        return items;
    }

    private List<Map<String, Object>> defaultReferenceComponents() {
        List<Map<String, Object>> items = new ArrayList<>();
        items.add(item(FIELD_CODE, COMPONENT_LIVE_PLAN_CREATE_CARD, FIELD_NAME, "直播计划创建结果卡",
                FIELD_COMPONENT_NAME, COMPONENT_LIVE_PLAN_CREATE_CARD, FIELD_RENDER_PROTOCOL,
                PROTOCOL_CARD_CONTAINER, FIELD_SCENE, SCENE_LIVE_PLAN, FIELD_PROMPT,
                PROMPT_LIVE_PLAN_COMPONENT));
        items.add(item(FIELD_CODE, COMPONENT_CHOICE_PICKER, FIELD_NAME, "直播复盘选择器",
                FIELD_COMPONENT_NAME, COMPONENT_CHOICE_PICKER, FIELD_RENDER_PROTOCOL, PROTOCOL_A2UI,
                FIELD_SCENE, SCENE_LIVE_REVIEW, FIELD_PROMPT, PROMPT_CHOICE_PICKER_COMPONENT));
        items.add(item(FIELD_CODE, COMPONENT_MARKDOWN_CONCLUSION_CARD, FIELD_NAME, "通用结论卡",
                FIELD_COMPONENT_NAME, COMPONENT_MARKDOWN_CONCLUSION_CARD, FIELD_RENDER_PROTOCOL,
                PROTOCOL_CARD_CONTAINER, FIELD_SCENE, SCENE_COMMON, FIELD_PROMPT, PROMPT_MARKDOWN_COMPONENT));
        return items;
    }

    private List<Map<String, Object>> defaultReferenceRenderAssets() {
        List<Map<String, Object>> items = new ArrayList<>();
        items.add(item(FIELD_CODE, DSL_LIVE_STREAM_SELECTOR, FIELD_NAME, "直播场次选择 DSL",
                FIELD_ASSET_TYPE, ASSET_TYPE_BUSINESS_DSL, FIELD_RENDER_PROTOCOL, PROTOCOL_AGENT_UI_DSL,
                FIELD_DSL_CODE, DSL_LIVE_STREAM_SELECTOR, FIELD_SCENE, SCENE_LIVE_REVIEW,
                FIELD_OWNER, OWNER_SKILL_FACTORY, FIELD_LIFECYCLE_STATUS, STATUS_REGISTERED,
                FIELD_ENABLED, true, FIELD_PROTOCOL_VERSION, "UI_DSL@1.0",
                FIELD_INTEGRATION_PROMPT, PROMPT_LIVE_SELECTOR_DSL,
                FIELD_PARAMS_SCHEMA_JSON, PARAMS_SCHEMA_LIVE_SELECTOR_DSL,
                FIELD_OFFICIAL_DEMO_JSON, DEMO_LIVE_SELECTOR_DSL));
        items.add(item(FIELD_CODE, COMPONENT_LIVE_PLAN_CREATE_CARD, FIELD_NAME, "直播计划创建结果卡",
                FIELD_ASSET_TYPE, ASSET_TYPE_CARD_CONTAINER, FIELD_RENDER_PROTOCOL, PROTOCOL_CARD_CONTAINER,
                FIELD_COMPONENT_NAME, COMPONENT_LIVE_PLAN_CREATE_CARD, FIELD_SCENE, SCENE_LIVE_PLAN,
                FIELD_OWNER, OWNER_SKILL_FACTORY, FIELD_LIFECYCLE_STATUS, STATUS_REGISTERED,
                FIELD_ENABLED, true, FIELD_PROTOCOL_VERSION, "CARD_CONTAINER@1.0",
                FIELD_INTEGRATION_PROMPT, PROMPT_LIVE_PLAN_COMPONENT,
                FIELD_OFFICIAL_DEMO_JSON, DEMO_LIVE_PLAN_CARD));
        items.add(item(FIELD_CODE, LOCAL_METHOD_SELECT_COMPONENT_REFS, FIELD_NAME, "选择参考组件 localMethod",
                FIELD_ASSET_TYPE, ASSET_TYPE_LOCAL_METHOD, FIELD_RENDER_PROTOCOL, PROTOCOL_LOCAL_METHOD,
                FIELD_LOCAL_METHOD, LOCAL_METHOD_SELECT_COMPONENT_REFS, FIELD_SCENE, SCENE_SELECT_COMPONENT,
                FIELD_OWNER, OWNER_SKILL_FACTORY, FIELD_LIFECYCLE_STATUS, STATUS_REGISTERED,
                FIELD_ENABLED, true, FIELD_INTEGRATION_PROMPT, PROMPT_LOCAL_METHOD_SELECT_COMPONENT,
                FIELD_OFFICIAL_DEMO_JSON, DEMO_LOCAL_METHOD_SELECT_COMPONENT));
        items.add(item(FIELD_CODE, COMPONENT_CHOICE_PICKER, FIELD_NAME, "A2UI 选择器原子能力",
                FIELD_ASSET_TYPE, ASSET_TYPE_A2UI_ATOM, FIELD_RENDER_PROTOCOL, PROTOCOL_A2UI_ATOM,
                FIELD_COMPONENT_NAME, COMPONENT_CHOICE_PICKER, FIELD_SCENE, "A2UI 原子选择器能力",
                FIELD_OWNER, OWNER_SKILL_FACTORY, FIELD_LIFECYCLE_STATUS, STATUS_REGISTERED,
                FIELD_ENABLED, true, FIELD_PROTOCOL_VERSION, "A2UI@1.0",
                FIELD_RENDERER_VERSION, "a2ui-renderer@0.1.0",
                FIELD_INTEGRATION_PROMPT, PROMPT_CHOICE_PICKER_ATOM,
                FIELD_OFFICIAL_DEMO_JSON, DEMO_CHOICE_PICKER_ATOM));
        return items;
    }

    private Map<String, Object> defaultLinks() {
        return item(FIELD_B_END_DEBUG_PAGE_URL, B_END_DEBUG_PAGE_URL, FIELD_TRACE_PAGE_URL, TRACE_PAGE_URL);
    }

    private Map<String, Object> item(Object... values) {
        Map<String, Object> result = new LinkedHashMap<>(DEFAULT_ITEM_CAPACITY);
        for (int i = 0; i + 1 < values.length; i += 2) {
            result.put(String.valueOf(values[i]), values[i + 1]);
        }
        return result;
    }

    private int sizeOf(Object value) {
        if (value instanceof List) {
            return ((List<?>) value).size();
        }
        if (value instanceof Map) {
            return ((Map<?, ?>) value).size();
        }
        return 0;
    }
}
