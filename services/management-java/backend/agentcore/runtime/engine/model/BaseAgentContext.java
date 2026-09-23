package dev.a2flow.management.agentcore.runtime.engine.model;

import java.util.Map;

import com.google.common.collect.Maps;

import lombok.Data;

/**

 * Created on 2026-04-24
 * agent执行时, 需要注入至TOOL/SKILL的基础上下文
 */
@Data
public class BaseAgentContext {
    private String ownerId;
    @com.fasterxml.jackson.databind.annotation.JsonSerialize(using = com.fasterxml.jackson.databind.ser.std.ToStringSerializer.class)
    private Long userId;
    private String userMessage;
    private String cookie; // 登录态cookie
    private String client; // pc、app
    private String env; // prod, prt, staging
    private Map<String, Object> extraBizParam = Maps.newHashMap();
}
