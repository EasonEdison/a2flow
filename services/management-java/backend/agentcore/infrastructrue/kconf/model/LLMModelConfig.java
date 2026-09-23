package dev.a2flow.management.agentcore.infrastructrue.kconf.model;

import org.apache.commons.lang3.StringUtils;

import lombok.Data;

/**
 * AI Coding 模型调用的运行时配置。
 *
 * <p>该对象由 SkillFactory 专用 KConf 模型在入口边界转换而来，供万青模型客户端读取连接参数、
 * 模型参数和思考参数。它不负责读取 KConf，也不包含会话、工具或工作区业务状态。
 *

 * Created on 2026-04-26
 */
@Data
public class LLMModelConfig {

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
     * 是否请求模型开启原生思考通道。默认开启，由 SkillFactory modelConfig 控制。
     */
    private boolean thinking = true;

    /**
     * 模型思考强度，透传给万青 reasoning_effort。
     */
    private String reasoningEffort = DEFAULT_REASONING_EFFORT;
}
