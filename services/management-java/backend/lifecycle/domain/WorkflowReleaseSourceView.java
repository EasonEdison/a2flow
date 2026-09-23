package dev.a2flow.management.lifecycle.domain;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 发布读取边界返回的完整草稿事实。
 *
 * <p>上游由 WorkflowDefinitionService 在可信操作人权限校验后从单条定义记录构造，下游仅供
 * WorkflowReleaseAssetAdapter 执行强类型解析、编译和冻结。该对象不承载公共发布状态、环境指针
 * 或运行态数据，也不允许发布 Adapter 越过 Service 访问 Mapper。
 */
@Data
@Accessors(chain = true)
public class WorkflowReleaseSourceView {

    private String workflowCode;
    private String specialistCode;
    private String displayName;
    private String description;
    private Long draftRevision;
    private String draftDigest;
    private Integer draftContractVersion;
    private String draftPayloadJson;
}
