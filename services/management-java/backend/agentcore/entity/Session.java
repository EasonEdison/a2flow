package dev.a2flow.management.agentcore.entity;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Session 实体

 * @date 2026/4/27
 */
@Data
@Accessors(chain = true)
public class Session {

    /**
     * Agent ID
     */
    private Long agentId;

    /**
     * 会话者ID
     */
    @com.fasterxml.jackson.databind.annotation.JsonSerialize(using = com.fasterxml.jackson.databind.ser.std.ToStringSerializer.class)
    private Long userId;

    /**
     * 会话ID
     */
    private String sessionId;

    /**
     * 创建时间（时间戳）
     */
    private Long createTime;

    /**
     * 更新时间（时间戳）
     */
    private Long updateTime;

}
