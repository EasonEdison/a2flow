package dev.a2flow.management.release;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.release.ReleaseModels.ReleaseChange;
import dev.a2flow.management.release.ReleaseModels.ReleaseDeployment;
import dev.a2flow.management.release.ReleaseModels.ReleaseOperationResult;

/**
 * 共享发布 mutation 结果收敛器。
 *
 * <p>上游输入是已持久化的 Change 或 Deployment，下游输出是管理接口的三字段 data。
 * 本类只负责字段投影和消息优先级，不读取 Repository、不推进状态机，也不解释资产类型。
 */
final class ReleaseOperationResultFactory {

    private static final String DOMAIN_RESULT_MESSAGE = "message";
    private static final String STATUS_UNKNOWN = "UNKNOWN";

    private ReleaseOperationResultFactory() {
    }

    /** 把已持久化 Change 收敛为最小响应。 */
    static ReleaseOperationResult from(ReleaseChange change, String fallbackMessage) {
        return result(change.getChangeId(), change.getStatus(), fallbackMessage);
    }

    /** 把已持久化 Deployment 收敛为最小响应，并保留最具体的领域消息。 */
    static ReleaseOperationResult from(ReleaseDeployment deployment, String fallbackMessage) {
        Object domainMessage = deployment.getDomainResult() == null
                               ? null : deployment.getDomainResult().get(DOMAIN_RESULT_MESSAGE);
        String message = StringUtils.trimToNull(deployment.getMessage());
        if (message == null && domainMessage instanceof String) {
            message = StringUtils.trimToNull((String) domainMessage);
        }
        return result(deployment.getDeploymentId(), deployment.getStatus(),
                StringUtils.defaultIfBlank(message, fallbackMessage));
    }

    private static ReleaseOperationResult result(String operationId, String status, String message) {
        return new ReleaseOperationResult()
                .setOperationId(operationId)
                .setStatus(StringUtils.defaultIfBlank(status, STATUS_UNKNOWN))
                .setMessage(message);
    }
}
