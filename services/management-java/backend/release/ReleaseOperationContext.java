package dev.a2flow.management.release;

import org.apache.commons.lang3.StringUtils;

/**
 * 共享发布控制面传给领域 Adapter 的可信操作上下文。
 *
 * <p>上游只能由 {@link AssetReleaseApplicationService} 使用服务端当前用户身份构造，下游 Adapter
 * 仅可读取该身份执行授权相关的快照和门禁逻辑。本类型不接收页面参数、变更创建人或系统默认身份，
 * 也不负责发布来源、环境和产物建模，这些信息继续由既有发布模型承载。
 */
public final class ReleaseOperationContext {

    private static final String ERROR_OPERATOR_REQUIRED = "release operation operator is required";

    private final String operator;

    ReleaseOperationContext(String operator) {
        if (StringUtils.isBlank(operator)) {
            throw new IllegalArgumentException(ERROR_OPERATOR_REQUIRED);
        }
        this.operator = StringUtils.trim(operator);
    }

    /** 返回服务端已认证的当前操作人。 */
    public String getOperator() {
        return operator;
    }
}
