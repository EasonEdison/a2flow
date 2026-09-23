package dev.a2flow.management.config;

import org.apache.commons.lang3.StringUtils;

import lombok.Data;

/**
 * SkillFactory 专用模型配置。
 *
 * <p>该模型映射 `skillFactoryAgentBizSummaryMapConfig.*.modelConfig`，只服务 M 端 AI Coding
 * 和后续可迁移的文件生成能力。上游是 SkillFactory 独立 KConf，下游由
 * `SkillFactoryConfigReader` 在 SkillFactory 入口边界转换成当前通用模型调用器需要的配置对象；
 * 它不复用公共 `agentBizSummaryMapConfig` 的 value 类型，也不负责普通数字员工模型配置。
 */
@Data
public class SkillFactoryLlmModelConfig {

    private static final String DEFAULT_REASONING_EFFORT = "high";

    private int connectTimeoutMs = 20_000;
    private int readTimeoutMs = 150_000;
    private String baseUrl = "https://example.invalid/REQUIRES_CONFIGURATION";
    private String completionsPath = "/v1/endpoints/chat/completions";
    private String apiKey = StringUtils.EMPTY;
    private String model = StringUtils.EMPTY;
    private Double temperature = 0.7;
    private Integer maxToken = 8192;

    /**
     * 是否请求模型开启原生思考通道。默认开启，KConf 可按 bizKey 显式关闭。
     */
    private boolean thinking = true;

    /**
     * 模型思考强度。该值透传给万青的 reasoning_effort，不在业务层自行降级或改写。
     */
    private String reasoningEffort = DEFAULT_REASONING_EFFORT;
}
