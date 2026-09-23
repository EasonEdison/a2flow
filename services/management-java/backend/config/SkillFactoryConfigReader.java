package dev.a2flow.management.config;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;
import dev.a2flow.management.agentcore.infrastructrue.kconf.model.AgentMemoryConfig;
import dev.a2flow.management.agentcore.infrastructrue.kconf.model.AgentPropertiesConfig;
import dev.a2flow.management.agentcore.infrastructrue.kconf.model.LLMModelConfig;
import dev.a2flow.management.support.JsonSupport;
import lombok.Data;

/** Deployment-owned JSON configuration, without remote configuration clients or implicit environments. */
@Component
public class SkillFactoryConfigReader {
    private static final String DEFAULT_BIZ_KEY = "HADES_SKILL_FACTORY";
    private final ConfigurationDocument configuration;

    public SkillFactoryConfigReader() {
        String configuredPath = System.getProperty("a2flow.management.config");
        if (StringUtils.isBlank(configuredPath)) configuredPath = System.getenv("A2FLOW_MANAGEMENT_CONFIG");
        if (StringUtils.isBlank(configuredPath)) {
            throw new IllegalStateException("A2FLOW_MANAGEMENT_CONFIG must reference a management JSON configuration file");
        }
        try {
            configuration = JsonSupport.fromJSON(Files.readString(Path.of(configuredPath)), ConfigurationDocument.class);
            if (configuration == null) throw new IllegalStateException("Management configuration must be an object");
        } catch (IOException | IllegalArgumentException e) {
            throw new IllegalStateException("Management configuration could not be loaded", e);
        }
    }

    public SkillFactoryAgentBizSummaryConfig getAgentBizSummaryConfig(String bizKey) {
        String key = StringUtils.defaultIfBlank(bizKey, DEFAULT_BIZ_KEY);
        SkillFactoryAgentBizSummaryConfig value = configuration.getAgents().get(key);
        if (value == null) throw new IllegalStateException("Management agent configuration is missing: " + key);
        return copy(value, SkillFactoryAgentBizSummaryConfig.class);
    }

    public AgentPropertiesConfig buildAgentPropertiesConfig(SkillFactoryAgentBizSummaryConfig bizConfig) {
        SkillFactoryAgentPropertiesConfig source = bizConfig == null ? null : bizConfig.getPropertiesConfig();
        if (source == null) throw new IllegalStateException("Agent properties configuration is missing");
        AgentPropertiesConfig target = new AgentPropertiesConfig();
        if (StringUtils.isNotBlank(source.getWorkspace())) target.setWorkspace(source.getWorkspace());
        if (StringUtils.isNotBlank(source.getDefaultEngineStrategy())) target.setDefaultEngineStrategy(source.getDefaultEngineStrategy());
        if (source.getMaxIterations() != null) target.setMaxIterations(source.getMaxIterations());
        if (source.getTools() != null) target.setTools(source.getTools());
        String prompt = configuration.getPrompts().get(source.getEngineSystemPrompt());
        if (StringUtils.isBlank(prompt)) throw new IllegalStateException("Configured engine system prompt is missing or empty");
        target.setEngineSystemPrompt(prompt);
        if (source.getThoughtsAndAnswers() != null) target.setThoughtsAndAnswers(source.getThoughtsAndAnswers());
        if (source.getStoreMessages() != null) target.setStoreMessages(source.getStoreMessages());
        if (source.getSessionLock() != null) target.setSessionLock(source.getSessionLock());
        if (source.getSessionLockTimeouts() != null) target.setSessionLockTimeouts(source.getSessionLockTimeouts());
        if (StringUtils.isNotBlank(source.getSessionLockTips())) target.setSessionLockTips(source.getSessionLockTips());
        if (source.getCancelCacheTimeouts() != null) target.setCancelCacheTimeouts(source.getCancelCacheTimeouts());
        return target;
    }

    public LLMModelConfig buildLlmModelConfig(SkillFactoryAgentBizSummaryConfig bizConfig) {
        SkillFactoryLlmModelConfig source = bizConfig == null ? null : bizConfig.getModelConfig();
        if (source == null) throw new IllegalStateException("LLM model configuration is missing");
        LLMModelConfig target = new LLMModelConfig();
        target.setConnectTimeoutMs(source.getConnectTimeoutMs());
        target.setReadTimeoutMs(source.getReadTimeoutMs());
        target.setBaseUrl(source.getBaseUrl());
        target.setCompletionsPath(source.getCompletionsPath());
        target.setApiKey(source.getApiKey());
        target.setModel(source.getModel());
        target.setTemperature(source.getTemperature());
        target.setMaxToken(source.getMaxToken());
        target.setThinking(source.isThinking());
        if (StringUtils.isNotBlank(source.getReasoningEffort())) target.setReasoningEffort(source.getReasoningEffort());
        return target;
    }

    public AgentMemoryConfig buildAgentMemoryConfig(SkillFactoryAgentBizSummaryConfig bizConfig) {
        SkillFactoryMemoryConfig source = bizConfig == null ? null : bizConfig.getMemoryConfig();
        if (source == null) throw new IllegalStateException("Agent memory configuration is missing");
        AgentMemoryConfig target = new AgentMemoryConfig();
        target.setFilterStrategyList(source.getFilterStrategyList());
        target.setMemorySecondsTime(source.getMemorySecondsTime());
        target.setMaxMessageCount(source.getMaxMessageCount());
        target.setMaxCharacters(source.getMaxCharacters());
        target.setMemoryStartTimeLimit(source.getMemoryStartTimeLimit());
        target.setPullMessageCount(source.getPullMessageCount());
        return target;
    }

    public Map<String, SkillFactoryPageConfig> getPageConfigMap() {
        Map<String, SkillFactoryPageConfig> result = new LinkedHashMap<>();
        configuration.getPages().forEach((key,value) -> result.put(key, copy(value, SkillFactoryPageConfig.class)));
        return result;
    }

    public WorkspaceChangeGuardConfig getWorkspaceChangeGuardConfig(String bizKey) {
        WorkspaceChangeGuardConfig value = configuration.getWorkspaceChangeGuard();
        if (value == null) throw new IllegalStateException("Workspace change guard configuration is missing");
        return value;
    }

    public SkillFactoryAgentToolConfig getAgentToolConfig(String bizKey) {
        SkillFactoryAgentToolConfig value = properties(bizKey).getAgentToolConfig();
        return value == null ? new SkillFactoryAgentToolConfig() : value;
    }

    public AuthoringGuideConfig getAuthoringGuideConfig(String bizKey) {
        AuthoringGuideConfig value = properties(bizKey).getAuthoringGuideConfig();
        return value == null ? new AuthoringGuideConfig() : value;
    }

    public SkillFactoryHttpDebugConfig getHttpDebugConfig(String bizKey) { return properties(bizKey).getHttpDebugConfig(); }

    public SkillFactoryPermissionConfig getPermissionConfig() {
        return configuration.getPermission() == null ? new SkillFactoryPermissionConfig()
                : copy(configuration.getPermission(), SkillFactoryPermissionConfig.class);
    }

    public String getMountedSkillProtocolPrompt() { return StringUtils.defaultString(configuration.getMountedSkillProtocolPrompt()); }
    public Path getHadesSkillFactoryWorkspaceRoot() { return getWorkspaceRoot(DEFAULT_BIZ_KEY); }

    public Path getWorkspaceRoot(String bizKey) {
        String workspace = configuration.getWorkspaceRoot();
        if (StringUtils.isBlank(workspace)) throw new IllegalStateException("Workspace root configuration is missing");
        return Path.of(workspace).toAbsolutePath().normalize();
    }

    public Map<String, CapabilityClusterConfig> getCapabilityClusterConfigMap() {
        Map<String, CapabilityClusterConfig> result = new LinkedHashMap<>();
        configuration.getCapabilityClusters().forEach((key,value) -> result.put(key, copy(value, CapabilityClusterConfig.class)));
        return result;
    }

    private SkillFactoryAgentPropertiesConfig properties(String bizKey) {
        SkillFactoryAgentPropertiesConfig value = getAgentBizSummaryConfig(bizKey).getPropertiesConfig();
        if (value == null) throw new IllegalStateException("Agent properties configuration is missing");
        return value;
    }

    private static <T> T copy(T value, Class<T> type) {
        return value == null ? null : JsonSupport.fromJSON(JsonSupport.toJSON(value), type);
    }

    @Data
    public static class ConfigurationDocument {
        private String workspaceRoot;
        private WorkspaceChangeGuardConfig workspaceChangeGuard;
        private Map<String, SkillFactoryAgentBizSummaryConfig> agents = new LinkedHashMap<>();
        private Map<String, SkillFactoryPageConfig> pages = new LinkedHashMap<>();
        private Map<String, String> prompts = new LinkedHashMap<>();
        private Map<String, CapabilityClusterConfig> capabilityClusters = new LinkedHashMap<>();
        private SkillFactoryPermissionConfig permission;
        private String mountedSkillProtocolPrompt;
    }
}
