package dev.a2flow.management.authoring.session.domain;

import org.apache.commons.lang3.StringUtils;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Authoring Chat 会话归属范围。
 *
 * <p>该领域对象定义一组共享会话的业务边界。同一个 bizKey、scopeType 和 scopeId 下的会话
 * 对所有操作者共享，不按 operator 隔离；workspaceId 只用于恢复当前创作上下文，不参与会话唯一性。
 * Repository 使用该对象查询持久化数据，RPC 参数解析和页面返回结构不属于该对象职责。
 */
@Data
@Accessors(chain = true)
public class AuthoringSessionScope {

    private String bizKey;
    private String scopeType;
    private String scopeId;
    private String workspaceId;
    private String operator;

    /**
     * 返回可用于日志定位的稳定 scope key。
     */
    public String scopeKey() {
        return String.join("|",
                StringUtils.defaultString(bizKey),
                StringUtils.defaultString(scopeType),
                StringUtils.defaultString(scopeId));
    }
}
