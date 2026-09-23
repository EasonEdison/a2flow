package dev.a2flow.management.lifecycle.domain;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 创建成功后的稳定控制面响应。
 *
 * <p>上游由 WorkflowDefinitionService 在 Workflow 定义与资产 OWNER 关系原子创建成功后组装；
 * 下游由统一 dispatcher 的 WORKFLOW_CREATE 方法返回给 M 端配置工作台。响应只携带新资产继续拉取
 * 详情和草稿所需的稳定身份、初始 revision/digest 与创建时间。
 *
 * <p>不负责：返回完整草稿、发布状态、环境指针或运行态字段；这些事实由独立详情、草稿和
 * publish-center-common-v2 查询提供。
 */
@Data
@Accessors(chain = true)
public class WorkflowCreateResult {

    private String workflowCode;
    private long draftRevision;
    private String draftDigest;
    private long createdAt;
}
